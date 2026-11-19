"""Tests for cputune. Run: python3 -m unittest discover -s tests

Each test builds a fake sysfs tree from a recorded machine (tests/machines/)
and runs the real script against it with CPUTUNE_ROOT. Then cputune does not
call sudo, and it does not put load on the real CPUs.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import json
import io
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fake_sysfs  # noqa: E402

SCRIPT = Path(__file__).resolve().parent.parent / "cputune"


def fake_sysfs_cpus(text: str) -> list[int]:
    cpus = []
    for part in text.strip().split(","):
        a, _, b = part.partition("-")
        cpus.extend(range(int(a), int(b or a) + 1))
    return cpus


class Case(unittest.TestCase):
    machine = "intel-i9-13950hx"

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="cputune-test-"))
        self.addCleanup(shutil.rmtree, self.root)
        fake_sysfs.build(self.root, self.machine)
        self.cpu = self.root / "sys/devices/system/cpu"
        self.state = self.root / "run/cputune.json"

    def run_tool(self, *args: str, columns: int = 100, script: Path = SCRIPT, **env_vars: str):
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "COLUMNS")}
        env.update(CPUTUNE_ROOT=str(self.root), COLUMNS=str(columns), **env_vars)
        return subprocess.run(
            [sys.executable, str(script), *args], env=env, capture_output=True, text=True, timeout=60
        )

    def ok(self, *args: str) -> subprocess.CompletedProcess:
        result = self.run_tool(*args)
        self.assertEqual(result.returncode, 0, f"{args}: {result.stderr}")
        return result

    def fails(self, *args: str, code: int = 1) -> subprocess.CompletedProcess:
        result = self.run_tool(*args)
        self.assertEqual(result.returncode, code, f"{args}: {result.stdout} {result.stderr}")
        return result

    def json(self, *args: str) -> dict:
        return json.loads(self.ok(*args, "--json").stdout)

    def f(self, cpu: int, name: str) -> str:
        return (self.cpu / f"cpu{cpu}/cpufreq" / name).read_text().strip()

    def set_f(self, cpu: int, name: str, value: object) -> None:
        (self.cpu / f"cpu{cpu}/cpufreq" / name).write_text(f"{value}\n")

    def snapshot(self) -> dict[str, str]:
        files = {}
        for path in sorted((self.root / "sys").rglob("*")):
            if path.is_file():
                files[str(path.relative_to(self.root))] = path.read_text()
        return files


class ShowTest(Case):
    def test_all_machines(self) -> None:
        for name in fake_sysfs.names():
            with self.subTest(machine=name):
                shutil.rmtree(self.root)
                machine = fake_sysfs.build(self.root, name)
                data = self.json("show")
                self.assertEqual(data["system"]["cpu_model"], machine.model)
                self.assertEqual(data["system"]["driver"], machine.driver)
                self.assertEqual(len(data["cores"]), len(machine.cores))
                self.assertEqual(sorted(c["cpus"] for c in data["cores"]), sorted(c[1] for c in machine.cores))
                ranks = [c["rank"] for c in data["cores"]]
                self.assertEqual(ranks, sorted(ranks, reverse=True))
                self.assertNotIn(0, data["default_lock_cpus"])
                self.assertIsNone(data["changed_by_cputune"])
                for color in ("always", "never"):
                    text = self.ok("show", "--color", color).stdout
                    self.assertIn(machine.model, text)
                    self.assertEqual("\033[" in text, color == "always")

    def test_default_lock_core(self) -> None:
        # Best rank without CPU 0. On a tie, the lowest CPU IDs.
        expected = {
            "intel-i9-13950hx": [8, 9],
            "amd-ryzen9-7950x": [1, 17],
            "amd-epyc-9354p": [1, 33],
            "amd-ryzen5-5500gt": [2, 8],  # 0,6 has the same rank but holds CPU 0
            "rpi4": [1],
        }
        for name, cpus in expected.items():
            with self.subTest(machine=name):
                shutil.rmtree(self.root)
                fake_sysfs.build(self.root, name)
                self.assertEqual(self.json()["default_lock_cpus"], cpus)

    def test_base_frequency_sources(self) -> None:
        cores = {tuple(c["cpus"]): c for c in self.json("show")["cores"]}
        self.assertEqual(cores[(8, 9)]["base_mhz"], 2200)  # Intel base_frequency, P-core
        self.assertEqual(cores[(16,)]["base_mhz"], 1600)  # E-core

    def test_now_and_widths(self) -> None:
        for columns in (40, 80, 250):
            result = self.run_tool("show", "--now", "--color", "always", columns=columns)
            self.assertEqual(result.returncode, 0, result.stderr)
        data = self.json("show", "--now")
        self.assertEqual({c["now_mhz"] for c in data["cores"]}, {3100})

    def test_without_cpufreq(self) -> None:
        for path in self.cpu.glob("cpu*/cpufreq"):
            shutil.rmtree(path)
        self.assertIn("no cpufreq", self.ok("show").stdout)
        self.assertIsNone(self.json("show")["default_lock_cpus"])
        self.assertIn("no CPU has cpufreq", self.fails("lock").stderr)

    def test_without_topology(self) -> None:
        for path in self.cpu.glob("cpu*/topology"):
            shutil.rmtree(path)
        data = self.json("show")
        self.assertEqual(len(data["cores"]), 32)  # one core for each CPU with cpufreq
        for path in self.cpu.glob("cpu*/cpufreq"):
            shutil.rmtree(path)
        self.assertIn("No CPU topology found", self.ok("show").stdout)
        self.assertEqual(self.json("show")["cores"], [])

    def test_default_command_and_errors(self) -> None:
        self.assertEqual(self.json()["command"], "show")
        self.assertIn("rank", self.ok("--color", "never").stdout)
        self.fails("lokc", code=2)
        self.fails("lock", "fast", code=2)
        self.assertIn("only for", self.fails("show", "--", "ls", code=2).stderr)

    def test_cpu_columns_are_aligned(self) -> None:
        shutil.rmtree(self.root)
        fake_sysfs.build(self.root, "amd-ryzen9-7950x")
        rows = [line for line in self.ok("show", "--color", "never").stdout.splitlines() if "425" in line]
        self.assertIn(" 236   1 17 ★   425", rows[0])
        self.assertIn(" 201  13 29     425", rows[8])
        self.assertEqual(len({row.index("425") for row in rows}), 1)
        self.assertNotIn(",", "".join(rows))

    def test_watch_reads_changes_and_stays_away(self) -> None:
        self.ok("lock")  # cpu 8,9
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"} | {"CPUTUNE_ROOT": str(self.root)}
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT), "watch", "--json", "--interval", "0.2", "--count", "30"],
            env=env, stdout=subprocess.PIPE, text=True,
        )
        self.addCleanup(proc.wait)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.kill)
        first = json.loads(proc.stdout.readline())
        self.assertEqual(next(c for c in first["cores"] if c["cpus"] == [2, 3])["now_mhz"], 3100)
        status = Path(f"/proc/{proc.pid}/status").read_text()
        allowed = next(line for line in status.splitlines() if line.startswith("Cpus_allowed_list"))
        nice = int(Path(f"/proc/{proc.pid}/stat").read_text().rsplit(")", 1)[1].split()[16])
        self.assertEqual(nice, 19)
        if os.cpu_count() >= 10:
            self.assertNotIn(8, fake_sysfs_cpus(allowed.split(":")[1]))
            self.assertNotIn(9, fake_sysfs_cpus(allowed.split(":")[1]))
        # Files that change between updates: the open file descriptors see the new values.
        self.set_f(2, "scaling_cur_freq", 1234000)
        self.set_f(3, "scaling_cur_freq", 1234000)  # now_mhz is the highest value of the siblings
        self.set_f(2, "scaling_max_freq", 2000000)
        for _ in range(8):  # 1.6 s: before the rescan after 5 s
            core = next(c for c in json.loads(proc.stdout.readline())["cores"] if c["cpus"] == [2, 3])
            if core["now_mhz"] == 1234 and core["max_mhz"] == 2000:
                break
        else:
            self.fail("watch did not show the new values")

    def test_watch(self) -> None:
        lines = self.ok("watch", "--count", "2", "--json").stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])["command"], "watch")
        self.assertIn("Ctrl+C", self.ok("watch", "--count", "1").stdout)


class LockTest(Case):
    def test_lock_default_intel(self) -> None:
        before = self.snapshot()
        data = self.json("lock")
        self.assertEqual(data["cpus"], [8, 9])
        self.assertEqual(data["boost_off"], "global")
        self.assertEqual(data["taskset"], "taskset -c 8,9")
        self.assertEqual((self.cpu / "intel_pstate/no_turbo").read_text().strip(), "1")
        for cpu in (8, 9):
            self.assertEqual(self.f(cpu, "scaling_governor"), "performance")
            self.assertEqual(self.f(cpu, "scaling_min_freq"), "2200000")
            self.assertEqual(self.f(cpu, "scaling_max_freq"), "2200000")
        # Other cores do not change.
        changed = {k for k in self.snapshot() if self.snapshot()[k] != before[k]}
        self.assertTrue(all("cpu8/" in k or "cpu9/" in k or "no_turbo" in k for k in changed), changed)
        state = json.loads(self.state.read_text())
        self.assertEqual(state["cpus"]["8"]["max"], 5500000)
        self.assertEqual(state["cpus"]["8"]["governor"], "powersave")
        self.assertEqual(state["boost"], {str(self.cpu / "intel_pstate/no_turbo"): "0"})
        shown = self.json("show")
        self.assertEqual(shown["changed_by_cputune"]["cpus"], [8, 9])
        self.assertTrue(next(c for c in shown["cores"] if c["cpus"] == [8, 9])["locked"])
        self.assertIn("cputune reset", self.ok("show").stdout)

    def test_second_lock_keeps_originals(self) -> None:
        self.ok("lock")
        self.ok("lock", "min", "--cpu", "8")
        self.ok("lock", "--cpu", "2")
        self.assertEqual(self.f(8, "scaling_max_freq"), "800000")
        state = json.loads(self.state.read_text())
        self.assertEqual(state["cpus"]["8"], {"governor": "powersave", "epp": "balance_performance",
                                              "min": 800000, "max": 5500000})
        self.assertEqual(state["cpus"]["2"]["max"], 5300000)
        self.assertEqual(state["boost"][str(self.cpu / "intel_pstate/no_turbo")], "0")

    def test_frequency_values(self) -> None:
        for value, khz in (("1.5GHz", "1500000"), ("1200MHz", "1200000"), ("2000", "2000000"),
                           ("min", "800000"), ("max", "5500000"), ("base", "2200000")):
            with self.subTest(value=value):
                self.ok("lock", value, "--cpu", "8")
                self.assertEqual(self.f(8, "scaling_min_freq"), khz)
                self.assertEqual(self.f(8, "scaling_max_freq"), khz)

    def test_bad_frequency_changes_nothing(self) -> None:
        before = self.snapshot()
        self.assertIn("outside 800-5500", self.fails("lock", "9999").stderr)
        self.assertIn("above the base frequency 2200", self.fails("lock", "3000").stderr)
        self.assertIn("Did you mean 2GHz?", self.fails("lock", "2").stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.state.exists())

    def test_cpu_lists_include_siblings(self) -> None:
        self.assertEqual(self.json("lock", "--cpu", "0")["cpus"], [0, 1])
        self.assertEqual(self.json("lock", "--cpu", "16")["cpus"], [16])
        self.assertEqual(self.json("lock", "--cpu", "3,16-17")["cpus"], [2, 3, 16, 17])
        self.assertIn("bad CPU list", self.fails("lock", "--cpu", "2-x").stderr)
        self.assertIn("bad CPU list", self.fails("lock", "--cpu", "5-3").stderr)
        self.assertIn("cpu99 has no cpufreq", self.fails("lock", "--cpu", "99").stderr)
        self.assertIn("cpu32 has no cpufreq", self.fails("lock", "--cpu", "32").stderr)  # offline

    def test_exclusive(self) -> None:
        self.ok("lock")
        self.assertIn("cputune reset", self.fails("lock", "--exclusive", "--cpu", "2").stderr)
        self.assertNotIn("2", json.loads(self.state.read_text())["cpus"])

    def test_json_error(self) -> None:
        result = self.fails("--json", "lock", "--cpu", "99")
        data = json.loads(result.stdout)
        self.assertFalse(data["ok"])
        self.assertEqual(data["command"], "lock")
        self.assertIn("cpu99", data["error"])

    def test_failed_read_leaves_no_state_file(self) -> None:
        (self.cpu / "cpu9/cpufreq/scaling_max_freq").unlink()
        self.assertIn("cannot read", self.fails("lock", "--cpu", "8").stderr)
        self.assertFalse(self.state.exists())
        self.assertEqual((self.cpu / "intel_pstate/no_turbo").read_text().strip(), "0")

    def test_measured_mismatch_warns(self) -> None:
        # The fake tree reports 3100 MHz, so the measurement cannot match the lock.
        data = self.json("lock")
        self.assertFalse(data["cores"][0]["ok"])
        self.assertIn("measured 3100 MHz", data["warnings"][0])
        self.set_f(8, "scaling_cur_freq", 2200000)
        self.assertTrue(self.json("lock")["cores"][0]["ok"])


class LockAmdTest(Case):
    machine = "amd-ryzen9-7950x"

    def test_per_core_boost(self) -> None:
        data = self.json("lock")
        self.assertEqual(data["cpus"], [1, 17])
        self.assertEqual(data["boost_off"], "core")
        self.assertEqual(data["cores"][0]["target_mhz"], 4501)  # acpi_cppc/nominal_freq
        for cpu in range(32):
            self.assertEqual(self.f(cpu, "boost"), "0" if cpu in (1, 17) else "1", cpu)
        self.assertEqual((self.cpu / "cpufreq/boost").read_text().strip(), "1")
        self.assertEqual(self.json("show")["system"]["boost_off_cpus"], [1, 17])


class LockAcpiTest(Case):
    machine = "amd-epyc-9354p"

    def test_global_boost_and_base(self) -> None:
        data = self.json("lock")
        self.assertEqual(data["cpus"], [1, 33])
        self.assertEqual(data["boost_off"], "global")
        self.assertEqual((self.cpu / "cpufreq/boost").read_text().strip(), "0")
        self.assertEqual(self.f(1, "scaling_max_freq"), "3250000")

    def test_base_from_available_frequencies(self) -> None:
        for path in self.cpu.glob("cpu*/acpi_cppc/nominal_freq"):
            path.unlink()
        self.set_f(2, "scaling_available_frequencies", "3100000 2200000 1500000")
        self.set_f(34, "scaling_available_frequencies", "3100000 2200000 1500000")
        self.assertEqual(self.json("lock", "--cpu", "2")["cores"][0]["target_mhz"], 3100)


class LockRaspberryTest(Case):
    machine = "rpi4"

    def test_no_boost_switch(self) -> None:
        data = self.json("lock")
        self.assertEqual(data["cpus"], [1])
        self.assertEqual(data["boost_off"], "none")
        self.assertIn("no boost switch", data["warnings"][0])
        self.assertEqual(self.f(1, "scaling_max_freq"), "1500000")  # no base: highest frequency


class LimitTest(Case):
    def test_limit_clamps(self) -> None:
        data = self.json("limit", "--max", "0", "--cpu", "3")
        self.assertEqual(data["cpus"], [2, 3])
        self.assertEqual((self.f(3, "scaling_min_freq"), self.f(3, "scaling_max_freq")), ("800000", "800000"))
        self.ok("limit", "--min", "99999")
        self.assertEqual((self.f(0, "scaling_min_freq"), self.f(0, "scaling_max_freq")), ("5300000", "5300000"))
        self.assertEqual((self.f(16, "scaling_min_freq"), self.f(16, "scaling_max_freq")), ("4000000", "4000000"))

    def test_max_wins_over_min(self) -> None:
        self.ok("limit", "--min", "3000", "--max", "2000")
        self.assertEqual((self.f(5, "scaling_min_freq"), self.f(5, "scaling_max_freq")), ("2000000", "2000000"))

    def test_words_and_boost_untouched(self) -> None:
        self.ok("limit", "--max", "base")
        self.assertEqual(self.f(0, "scaling_max_freq"), "2200000")
        self.assertEqual(self.f(16, "scaling_max_freq"), "1600000")
        self.assertEqual(self.f(0, "scaling_governor"), "powersave")
        self.assertEqual((self.cpu / "intel_pstate/no_turbo").read_text().strip(), "0")
        self.assertIn("set MHz", self.ok("show").stdout)

    def test_needs_a_value(self) -> None:
        self.assertIn("give --min, --max", self.fails("limit").stderr)


class ResetTest(Case):
    def test_restores_everything(self) -> None:
        before = self.snapshot()
        self.ok("lock")
        self.ok("lock", "1GHz", "--cpu", "2")
        self.ok("limit", "--max", "1200")
        self.set_f(8, "energy_performance_preference", "performance")  # as the driver does
        self.assertNotEqual(self.snapshot(), before)
        data = self.json("reset")
        self.assertTrue(data["restored"])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.state.exists())
        self.assertIsNone(self.json("show")["changed_by_cputune"])

    def test_restores_per_core_boost(self) -> None:
        shutil.rmtree(self.root)
        fake_sysfs.build(self.root, "amd-ryzen9-7950x")
        before = self.snapshot()
        self.ok("lock", "--cpu", "3")
        self.ok("reset")
        self.assertEqual(self.snapshot(), before)

    def test_without_state_opens_full_range(self) -> None:
        self.set_f(4, "scaling_max_freq", 1000000)
        self.set_f(4, "scaling_min_freq", 1000000)
        data = self.json("reset")
        self.assertFalse(data["restored"])
        self.assertEqual((self.f(4, "scaling_min_freq"), self.f(4, "scaling_max_freq")), ("800000", "5300000"))

    def test_skips_paths_that_are_not_boost_switches(self) -> None:
        self.ok("lock")
        state = json.loads(self.state.read_text())
        target = self.root / "proc/sys/kernel/osrelease"
        state["boost"][str(target)] = "hacked"
        self.state.write_text(json.dumps(state))
        data = self.json("reset")
        self.assertNotEqual(target.read_text().strip(), "hacked")
        self.assertIn("not a boost switch", data["warnings"][0])
        self.assertEqual((self.cpu / "intel_pstate/no_turbo").read_text().strip(), "0")

    def test_failed_write_keeps_state(self) -> None:
        self.ok("lock")
        governor = self.cpu / "cpu8/cpufreq/scaling_governor"
        governor.unlink()
        governor.mkdir()  # every write to it fails now
        self.assertIn("stays, so you can try again", self.fails("reset").stderr)
        self.assertTrue(self.state.exists())
        self.assertEqual(self.f(9, "scaling_governor"), "powersave")  # the other CPUs are restored

    def test_damaged_state(self) -> None:
        self.state.write_text("{not json")
        self.assertIn("sudo rm /run/cputune.json", self.fails("reset").stderr)


class RunTest(Case):
    def test_runs_pinned_and_resets(self) -> None:
        before = self.snapshot()
        code = "import os; print(os.environ['CPUTUNE_CPUS'])"
        result = self.ok("run", "--cpu", "4", "--", sys.executable, "-c", code)
        self.assertEqual(result.stdout, "4,5\n")  # cputune messages go to stderr
        self.assertIn("locked cpu 4,5 at 2200 MHz", result.stderr)
        self.assertIn("reset done", result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.state.exists())

    def test_exit_code_and_json(self) -> None:
        result = self.run_tool("run", "1500", "--json", "--", sys.executable, "-c", "raise SystemExit(7)")
        self.assertEqual(result.returncode, 7)
        data = json.loads(result.stderr[result.stderr.index("{"):])
        self.assertEqual(data["exit_code"], 7)
        self.assertEqual(data["cores"][0]["target_mhz"], 1500)
        self.assertFalse(self.state.exists())

    def test_refuses_when_already_changed(self) -> None:
        self.ok("lock")
        marker = self.root / "ran"
        result = self.fails("run", "--", sys.executable, "-c", f"open({str(marker)!r}, 'w')")
        self.assertIn("cputune reset", result.stderr)
        self.assertFalse(marker.exists())
        self.assertTrue(self.state.exists())  # the earlier lock stays

    def test_bad_lock_runs_nothing(self) -> None:
        marker = self.root / "ran"
        self.fails("run", "9999", "--", sys.executable, "-c", f"open({str(marker)!r}, 'w')")
        self.assertFalse(marker.exists())
        self.assertFalse(self.state.exists())

    def test_lock_that_fails_halfway_is_reset(self) -> None:
        governor = self.cpu / "cpu8/cpufreq/scaling_governor"
        governor.unlink()
        governor.mkdir()  # lock fails after boost is off
        self.assertIn("lock failed", self.fails("run", "--", "true").stderr)
        self.assertEqual((self.cpu / "intel_pstate/no_turbo").read_text().strip(), "0")

    def test_needs_a_command(self) -> None:
        self.assertIn("give the command after --", self.fails("run").stderr)
        self.assertIn("cannot run", self.fails("run", "--", "/does/not/exist").stderr)
        self.assertFalse(self.state.exists())


def with_version(version: str) -> bytes:
    """The cputune script with another __version__."""
    source = SCRIPT.read_bytes()
    current = re.search(rb'^__version__ = "[^"]+"', source, re.M)[0]
    return source.replace(current, f'__version__ = "{version}"'.encode(), 1)


class InstallTest(Case):
    def setUp(self) -> None:
        super().setUp()
        self.remote = self.root / "remote/cputune"  # stands in for GitHub
        self.remote.parent.mkdir()
        self.url = self.remote.as_uri()
        self.copy = self.root / "bin/cputune"  # an installed copy, not in a git checkout
        self.copy.parent.mkdir()
        self.copy.write_bytes(SCRIPT.read_bytes())

    def install(self, *args: str) -> dict:
        result = self.run_tool("install", "--json", *args, CPUTUNE_SOURCE_URL=self.url)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def update(self, script: Path | None = None) -> subprocess.CompletedProcess:
        return self.run_tool("update", "--json", script=script or self.copy, CPUTUNE_SOURCE_URL=self.url)

    def test_install_takes_the_newer_version(self) -> None:
        target = self.root / "home/.local/bin/cputune"
        self.remote.write_bytes(with_version("0.0.1"))
        self.assertEqual(self.install()["source"], "this file")
        self.assertEqual(target.read_bytes(), SCRIPT.read_bytes())
        self.assertEqual(target.stat().st_mode & 0o777, 0o755)
        self.remote.write_bytes(with_version("99.0.0"))
        data = self.install()
        self.assertEqual((data["source"], data["version"]), ("GitHub", "99.0.0"))
        self.assertEqual(target.read_bytes(), with_version("99.0.0"))
        self.assertEqual(self.install("--no-check")["source"], "this file")
        self.assertEqual(target.read_bytes(), SCRIPT.read_bytes())

    def test_warns_about_copies_with_the_old_name(self) -> None:
        self.remote.write_bytes(with_version("0.0.1"))
        self.assertNotIn("warnings", self.install())
        old = self.root / "usr/local/bin/cpu-tune"
        old.parent.mkdir(parents=True)
        old.write_text("old")
        for data in (self.install(), self.json("sudoers")):
            self.assertIn(f"sudo rm -f {old} /etc/sudoers.d/cpu-tune", data["warnings"][0])

    def test_install_system_and_offline(self) -> None:
        data = self.install("--system")  # no remote file: the download fails
        self.assertEqual(data["path"], str(self.root / "usr/local/bin/cputune"))
        self.assertIn("cannot download", data["warnings"][0])
        self.assertEqual((self.root / "usr/local/bin/cputune").read_bytes(), SCRIPT.read_bytes())

    def test_install_from_stdin_downloads(self) -> None:
        self.remote.write_bytes(with_version("99.0.0"))
        env = {k: v for k, v in os.environ.items()} | {
            "CPUTUNE_ROOT": str(self.root), "CPUTUNE_SOURCE_URL": self.url}
        result = subprocess.run([sys.executable, "-", "install"], input=SCRIPT.read_bytes(), env=env,
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "home/.local/bin/cputune").read_bytes(), with_version("99.0.0"))

    def test_update(self) -> None:
        self.remote.write_bytes(SCRIPT.read_bytes())
        data = json.loads(self.update().stdout)
        self.assertFalse(data["updated"])
        self.remote.write_bytes(with_version("99.0.0"))
        data = json.loads(self.update().stdout)
        self.assertTrue(data["updated"])
        self.assertEqual(data["new_version"], "99.0.0")
        self.assertEqual(self.copy.read_bytes(), with_version("99.0.0"))
        self.assertEqual(self.copy.stat().st_mode & 0o777, 0o755)
        self.remote.write_bytes(with_version("98.0.0"))  # never downgrade
        self.assertFalse(json.loads(self.update().stdout)["updated"])
        self.assertEqual(self.copy.read_bytes(), with_version("99.0.0"))

    def test_update_through_symlink(self) -> None:
        link = self.root / "link/cputune"
        link.parent.mkdir()
        link.symlink_to(self.copy)
        self.remote.write_bytes(with_version("99.0.0"))
        self.assertEqual(self.update(link).returncode, 0)
        self.assertTrue(link.is_symlink())
        self.assertEqual(self.copy.read_bytes(), with_version("99.0.0"))

    def test_update_refuses_bad_downloads(self) -> None:
        for name, content in (("html", b"<html>404</html>"),
                              ("syntax", with_version("99.0.0") + b"\ndef broken(:\n")):
            with self.subTest(name):
                self.remote.write_bytes(content)
                result = self.update()
                self.assertEqual(result.returncode, 1)
                self.assertIn("not a cputune script" if name == "html" else "does not compile",
                              json.loads(result.stdout)["error"])
                self.assertEqual(self.copy.read_bytes(), SCRIPT.read_bytes())
        self.assertEqual(sorted(p.name for p in self.copy.parent.iterdir()), ["cputune"])  # no temp files

    def test_update_refuses_git_checkout(self) -> None:
        self.remote.write_bytes(with_version("99.0.0"))
        for kind in ("dir", "file"):  # a clone has a .git folder, a worktree a .git file
            with self.subTest(kind):
                checkout = self.root / f"checkout-{kind}"
                (checkout / "sub").mkdir(parents=True)
                (checkout / ".git").mkdir() if kind == "dir" else (checkout / ".git").write_text("gitdir: x\n")
                script = checkout / "sub/cputune"
                script.write_bytes(SCRIPT.read_bytes())
                result = self.update(script)
                self.assertEqual(result.returncode, 1)
                self.assertIn("git pull", json.loads(result.stdout)["error"])
                self.assertEqual(script.read_bytes(), SCRIPT.read_bytes())

    def test_version(self) -> None:
        version = re.search(r'^__version__ = "([^"]+)"', SCRIPT.read_text(), re.M)[1]
        self.assertEqual(self.ok("--version").stdout.strip(), f"cputune {version}")
        self.assertEqual(self.json("show")["version"], version)


def load_module():
    """cputune as a module, to test functions that need states the tests cannot create.

    The module reads the environment when it loads: patch it before the call.
    """
    loader = importlib.machinery.SourceFileLoader("cputune", str(SCRIPT))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("cputune", loader))
    sys.modules["cputune"] = module  # @dataclass looks the module up here
    loader.exec_module(module)
    return module


class SudoersTest(Case):
    def test_guide_when_nothing_is_set_up(self) -> None:
        # The test checkout is not owned by root, so the rule must name the system copy.
        system_copy = self.root / "usr/local/bin/cputune"
        data = self.json("sudoers")
        self.assertEqual(data["path"], str(system_copy))
        self.assertFalse(data["installed"])
        self.assertIsNone(data["works"])  # sudo is not run in tests
        self.assertTrue(data["rule"].endswith(f"ALL=(root) NOPASSWD: {system_copy}"))
        self.assertTrue(data["setup"].endswith("sudoers --install"))
        text = self.ok("sudoers").stdout
        self.assertIn("Set it up with one command:", text)
        self.assertIn(f"install cputune to {system_copy}, owned by root", text)
        self.assertIn("Undo: sudo rm /etc/sudoers.d/cputune", text)

    def test_install(self) -> None:
        offline = (self.root / "missing").as_uri()  # GitHub is not used in tests
        result = self.run_tool("sudoers", "--install", "--json", CPUTUNE_SOURCE_URL=offline)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(len(data["done"]), 2)
        system_copy = self.root / "usr/local/bin/cputune"
        self.assertEqual(system_copy.read_bytes(), SCRIPT.read_bytes())
        self.assertEqual(system_copy.stat().st_mode & 0o777, 0o755)
        rule_file = self.root / "etc/sudoers.d/cputune"
        self.assertEqual(rule_file.stat().st_mode & 0o777, 0o440)
        lines = rule_file.read_text().splitlines()
        self.assertTrue(lines[0].startswith("# /etc/sudoers.d/cputune"))
        self.assertEqual(lines[1], data["rule"])
        self.assertEqual(len(lines), 2)

    def test_rule_only(self) -> None:
        result = self.ok("sudoers", "--rule")
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("# /etc/sudoers.d/cputune"))
        self.assertTrue(lines[1].endswith(f"NOPASSWD: {self.root / 'usr/local/bin/cputune'}"))
        self.assertIn("install --system", result.stderr)

    def test_guide_for_a_copy_owned_by_root(self) -> None:
        m = load_module()
        status = {"user": "ann", "path": "/usr/local/bin/cputune", "installed": True, "works": False,
                  "rule": "ann ALL=(root) NOPASSWD: /usr/local/bin/cputune", "file": "/etc/sudoers.d/cputune",
                  "setup": "cputune sudoers --install", "undo": "sudo rm /etc/sudoers.d/cputune"}
        text = "\n".join(m.render_sudoers(status))
        self.assertIn("cputune sudoers --install", text)
        self.assertNotIn("install cputune to", text)  # the copy is there already
        self.assertIn("ann ALL=(root) NOPASSWD: /usr/local/bin/cputune", text)
        text = "\n".join(m.render_sudoers(status | {"works": True}))
        self.assertIn("Everything is set up.", text)
        self.assertNotIn("sudoers --install", text)

    def test_owned_by_root(self) -> None:
        m = load_module()
        if os.stat(SCRIPT).st_uid != 0:
            self.assertFalse(m.owned_by_root(SCRIPT))
        self.assertFalse(m.owned_by_root(self.root / "missing"))
        if Path("/usr/bin/env").stat().st_uid == 0:
            self.assertTrue(m.owned_by_root(Path("/usr/bin/env")))
        tmp = Path("/tmp").stat()
        if tmp.st_uid == 0 and tmp.st_mode & 0o002:  # owned by root, but everyone can write it
            self.assertFalse(m.owned_by_root(Path("/tmp")))


class SecurityTest(Case):
    """A sudo rule lets every program of the user run cputune as root. These tests make
    sure that this gives no more than the CPU settings."""

    def load_as_sudo_root(self):
        env = {"SUDO_UID": "1000", "CPUTUNE_ROOT": str(self.root), "CPUTUNE_SOURCE_URL": "file:///evil"}
        with mock.patch("os.geteuid", return_value=0), mock.patch.dict(os.environ, env):
            return load_module()

    def test_sudo_allows_only_root_commands(self) -> None:
        m = self.load_as_sudo_root()
        self.assertTrue(m.UNDER_SUDO)
        self.assertEqual(m.SUDO_COMMANDS, ("lock", "limit", "reset", "update"))
        # Stubs instead of the real commands: under the simulated sudo, the test hooks are
        # off, so a real command would change this machine if the check ever broke.
        called: list[str] = []

        def stub(name: str):
            def cmd(args) -> None:
                called.append(name)
            cmd.__name__ = f"cmd_{name}"
            return cmd

        names = ("show", "watch", "lock", "run", "limit", "reset", "sudoers", "install", "update")
        with mock.patch.multiple(m, **{f"cmd_{n}": stub(n) for n in names}):
            for argv in (["run", "--", "sh"], ["install"], ["install", "--system"], ["sudoers", "--install"],
                         ["show"], ["watch"]):
                with self.subTest(argv=argv):
                    stderr = io.StringIO()
                    with mock.patch.object(sys, "argv", ["cputune", *argv]), contextlib.redirect_stderr(stderr):
                        self.assertEqual(m.main(), 1)
                    self.assertIn("do not start", stderr.getvalue())
            self.assertEqual(called, [])
            with mock.patch.object(sys, "argv", ["cputune", "lock"]):
                self.assertEqual(m.main(), 0)
            self.assertEqual(called, ["lock"])
        with mock.patch.object(sys, "argv", ["cputune", "--version"]), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as exit:
                m.main()
        self.assertEqual(exit.exception.code, 0)  # sudoers --install checks the rule with --version

    def test_no_test_hooks_under_sudo(self) -> None:
        m = self.load_as_sudo_root()
        self.assertFalse(m.TEST_MODE)
        self.assertEqual(m.ROOT, Path("/"))
        self.assertEqual(m.CPU_BASE, Path("/sys/devices/system/cpu"))

    def test_owned_by_root_checks_every_folder(self) -> None:
        m = load_module()
        path = Path("/usr/bin/env").resolve()
        real_stat = os.stat

        def fake_stat(writable: str):
            def stat(p, *args, **kwargs):
                if Path(p) not in (path, *path.parents):
                    return real_stat(p, *args, **kwargs)
                return types.SimpleNamespace(st_uid=0, st_mode=0o40775 if str(p) == writable else 0o40755)
            return stat

        with mock.patch("os.stat", fake_stat(writable="")):
            self.assertTrue(m.owned_by_root(path))
        top = str(list(path.parents)[-2])  # for example /usr: a folder far above the file
        with mock.patch("os.stat", fake_stat(writable=top)):
            self.assertFalse(m.owned_by_root(path))

    def test_owned_by_root_resolves_symlinks(self) -> None:
        m = load_module()
        own = self.root / "own-file"
        own.write_text("x")
        with mock.patch.object(Path, "resolve", lambda self, strict=False: own):
            self.assertFalse(m.owned_by_root(Path("/usr/bin/env")))  # really a link to a user file

    def test_rule_names_the_real_user(self) -> None:
        result = self.run_tool("sudoers", "--json", USER="mallory", LOGNAME="mallory")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["rule"].startswith(f"{pwd.getpwuid(os.getuid()).pw_name} ALL="))

    def test_replace_file_does_not_follow_planted_symlinks(self) -> None:
        m = load_module()
        folder = self.root / "bin"
        folder.mkdir()
        victim = self.root / "victim"
        victim.write_text("keep")
        for pid in range(4240, 4245):  # the names that a predictable temporary file would use
            (folder / f".cputune.{pid}.tmp").symlink_to(victim)
        with mock.patch("os.getpid", return_value=4242):
            m.replace_file(folder / "cputune", b"new")
        self.assertEqual(victim.read_text(), "keep")
        self.assertEqual((folder / "cputune").read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
