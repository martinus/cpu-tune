"""Fail when cpu-tune changed but its __version__ did not increase.

"cpu-tune update" installs a new version only when its number is higher, so
every change to the script needs a higher version.

Usage: python3 tests/check_version.py BASE_REF    (for example origin/main)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

VERSION = re.compile(rb'^__version__ = "([^"]+)"', re.M)


def version(source: bytes) -> tuple[int, ...]:
    m = VERSION.search(source)
    if not m:
        sys.exit("cpu-tune has no __version__ line")
    return tuple(int(p) for p in m[1].split(b"."))


def main() -> int:
    base_ref = sys.argv[1]
    current = (Path(__file__).parent.parent / "cpu-tune").read_bytes()
    base = subprocess.run(["git", "show", f"{base_ref}:cpu-tune"], capture_output=True)
    if base.returncode != 0:
        print(f"{base_ref} has no cpu-tune yet: nothing to compare")
        return 0
    if base.stdout == current:
        print("cpu-tune did not change")
        return 0
    old, new = version(base.stdout), version(current)
    show = lambda v: ".".join(map(str, v))  # noqa: E731
    if new <= old:
        print(f"cpu-tune changed, but __version__ {show(new)} is not higher than {show(old)} on {base_ref}")
        return 1
    print(f"cpu-tune {show(old)} -> {show(new)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
