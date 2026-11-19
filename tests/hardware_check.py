#!/usr/bin/env python3
"""Checks lock, limit, reset and run on this real machine. CI cannot do this: it has no cpufreq.

Usage: python3 tests/hardware_check.py [CPUTUNE]     (default: the cputune of this checkout)

It changes CPU settings with sudo, and it puts load on one core for a few seconds. After
each step it compares the real sysfs files with what it expects. At the end, all settings
are as before: the script runs "cputune reset" also when a step fails, and a reboot resets
everything too. Stop other benchmarks first. Takes about 30 seconds.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

CPUTUNE = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "cputune")
CPU = Path("/sys/devices/system/cpu")
STATE = Path("/run/cputune.json")
BUSY = [sys.executable, "-c", "import time\nend = time.time() + 3\nwhile time.time() < end: pass"]
failures: list[str] = []


def cputune(*args: str, command: list[str] | None = None) -> tuple[int, dict]:
    """Runs cputune with --json. Returns the exit code and the JSON (run writes it to stderr)."""
    argv = [sys.executable, str(CPUTUNE), *args, "--json", *(["--", *command] if command else [])]
    result = subprocess.run(argv, capture_output=True, text=True)
    text = result.stderr if args[0] == "run" else result.stdout
    try:
        return result.returncode, json.loads(text[text.index("{"):])
    except ValueError:
        return result.returncode, {"ok": False, "error": (result.stdout + result.stderr).strip()}


def settings() -> dict[str, str]:
    """All values that lock, limit and reset change."""
    names = ("scaling_min_freq", "scaling_max_freq", "scaling_governor", "energy_performance_preference", "boost")
    paths = [p for name in names for p in CPU.glob(f"cpu[0-9]*/cpufreq/{name}")]
    paths += [CPU / "cpufreq/boost", CPU / "intel_pstate/no_turbo"]
    return {str(p): p.read_text().strip() for p in sorted(paths) if p.exists()}


def read(cpu: int, name: str) -> str:
    return (CPU / f"cpu{cpu}/cpufreq" / name).read_text().strip()


def step(name: str, ok: bool, details: object = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n      {details}" if details and not ok else ""), flush=True)
    if not ok:
        failures.append(name)
    return ok


def same_as(before: dict[str, str], name: str) -> None:
    after = settings()
    diff = {k: (before.get(k), after.get(k)) for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    step(name, not diff and not STATE.exists(), diff or f"{STATE} still exists")


def locked_ok(data: dict) -> bool:
    """Each locked CPU has minimum = maximum = target, and cputune accepts the measured frequency."""
    for core in data.get("cores", []):
        print(f"      cpu {core['cpus']}: lock {core['target_mhz']} MHz, measured {core['measured_mhz']} MHz")
        for cpu in core["cpus"]:
            low, high = read(cpu, "scaling_min_freq"), read(cpu, "scaling_max_freq")
            if low != high or int(low) // 1000 != core["target_mhz"]:
                return False
    return bool(data.get("cores")) and all(core["ok"] for core in data["cores"])


def main() -> int:
    if not (CPU / "cpu0/cpufreq").exists():
        sys.exit("This machine has no cpufreq: nothing to check.")
    code, show = cputune("show")
    if not show.get("ok"):
        sys.exit(f"cputune show failed: {show}")
    if show["changed_by_cputune"]:
        sys.exit("cputune already changed settings. Run 'cputune reset' first.")
    root_copy = Path("/usr/local/bin/cputune")
    if root_copy.exists() and root_copy.resolve() != CPUTUNE.resolve():
        version = subprocess.run([str(root_copy), "--version"], text=True, stdout=subprocess.PIPE).stdout.strip()
        print(f"Note: sudo runs {root_copy} ({version}), not {CPUTUNE}.\n"
              f"To check this copy as root, install it first: {CPUTUNE} install --system --no-check\n")
    print(f"{show['system']['cpu_model']}, driver {show['system']['driver']}, kernel {show['system']['kernel']}")
    print("sudo may ask for your password.\n", flush=True)
    before = settings()
    try:
        code, data = cputune("check")
        step("check", code == 0 and data.get("ok"), data)
        for item in data.get("checks", []):
            if item["level"] == "warn":
                print(f"      warning: {item['text']}")

        code, data = cputune("lock")
        step("lock: default core, min = max = base, measured under load", code == 0 and locked_ok(data), data)
        _, shown = cputune("show")
        step("show: names the locked CPUs", (shown.get("changed_by_cputune") or {}).get("cpus") == data.get("cpus"))
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        step("state file has the boot ID", state.get("boot_id") == boot_id, state.get("boot_id"))
        code, data = cputune("reset")
        same_as(before, "reset after lock: all settings as before")

        code, data = cputune("lock", "min", "--cpu", "2")
        step("lock min --cpu 2", code == 0 and locked_ok(data), data)
        cputune("reset")
        same_as(before, "reset after lock min")

        code, data = cputune("limit", "--max", "min")
        ranges_ok = code == 0 and all(read(r["cpu"], "scaling_max_freq") == read(r["cpu"], "cpuinfo_min_freq")
                                      for r in data.get("ranges", []))
        step("limit --max min: all CPUs", ranges_ok, data)
        cputune("reset")
        same_as(before, "reset after limit")

        code, data = cputune("run", command=BUSY)
        cores = data.get("cores") or [{}]
        step("run: 3 s of load, frequency stays at the lock", code == 0 and data.get("stable") is True, data)
        print(f"      measured {cores[0].get('measured_mhz')} MHz, during the run {cores[0].get('run_avg_mhz')} MHz "
              f"(lowest {cores[0].get('run_min_mhz')}), throttled: {cores[0].get('throttled')}")
        same_as(before, "run resets")

        code, data = cputune("run", "--strict", command=[sys.executable, "-c", "raise SystemExit(7)"])
        step("run --strict: exit code of the command", code == 7 and data.get("exit_code") == 7, data)
        same_as(before, "run --strict resets")

        # SIGTERM (as from a CI timeout) while the command runs: run must reset.
        proc = subprocess.Popen([sys.executable, str(CPUTUNE), "run", "--", "sleep", "30"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if STATE.exists():
                break
            time.sleep(0.1)
        time.sleep(3)  # the lock measures for about 1 s, then the command starts
        os.kill(proc.pid, signal.SIGTERM)
        proc.wait(timeout=30)
        same_as(before, "run resets after SIGTERM")
    finally:
        if STATE.exists():
            print("Resetting after a failure.")
            cputune("reset")
    print(f"\n{'All checks passed.' if not failures else f'{len(failures)} checks failed.'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
