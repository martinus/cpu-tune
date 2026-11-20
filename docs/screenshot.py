"""Make the README screenshot on this machine: cputune --now, with load on three CPUs.

    python3 docs/screenshot.py                      # writes docs/show.png
    python3 docs/screenshot.py /tmp/x.png --load 2,4,6 --columns 110 --scale 1

It runs the cputune next to this directory (--cputune for another copy) and prints its output.
Needs google-chrome or chromium in PATH. Stop other programs first: their load shows up too.
"""

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from ansi2png import render

DOCS = Path(__file__).resolve().parent


def default_load() -> str:
    """Three CPUs, not CPU 0: odd numbers, as on the current screenshot (1,3,5)."""
    cpus = sorted(os.sched_getaffinity(0))
    return ",".join(str(c) for c in ([c for c in cpus if c % 2] or cpus[1:])[:3])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("output", nargs="?", type=Path, default=DOCS / "show.png", help="PNG file (default: docs/show.png)")
    p.add_argument("--load", default=default_load(), help="CPUs to keep busy, such as 1,3,5 (default: %(default)s)")
    p.add_argument("--columns", type=int, default=104, help="terminal width for cputune (default: 104)")
    p.add_argument("--scale", type=int, default=2, help="pixels per CSS pixel; 2 is sharp on HiDPI (default: 2)")
    p.add_argument("--cputune", type=Path, default=DOCS.parent / "cputune", help="the cputune to run")
    args = p.parse_args()

    cpus = [int(c) for c in args.load.split(",") if c.strip()]
    busy = [subprocess.Popen([sys.executable, "-c", f"import os\nos.sched_setaffinity(0, {{{c}}})\nwhile 1: pass"])
            for c in cpus]
    try:
        time.sleep(0.5)  # the busy CPUs reach their frequency
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "CPUTUNE_ROOT")}
        env["COLUMNS"] = str(args.columns)
        result = subprocess.run([sys.executable, str(args.cputune), "--now", "--color", "always"],
                                env=env, capture_output=True, text=True, check=True)
    finally:
        for proc in busy:
            proc.kill()
            proc.wait()

    text = result.stdout.rstrip("\n")
    print(text)
    longest = max(len(re.sub(r"\x1b\[[0-9;]*m", "", line)) for line in text.splitlines())
    width = int(longest * 8.5 + 56)  # 14 px monospace: about 8.4 px per column, plus padding
    render(text, args.output, width, args.scale)
    print(f"\nwrote {args.output}")


if __name__ == "__main__":
    main()
