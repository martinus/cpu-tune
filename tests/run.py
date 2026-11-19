"""Runs all tests in parallel, one process per CPU. Usage: python3 tests/run.py [-v]

The same tests as "python3 -m unittest discover -s tests", but faster: most
tests wait for cputune subprocesses, so they run well side by side. Each
test has its own fake tree, so tests do not share files.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_ids(suite: unittest.TestSuite) -> list[str]:
    ids = []
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            ids += test_ids(test)
        else:
            ids.append(test.id())
    return ids


def discover() -> unittest.TestSuite:
    return unittest.defaultTestLoader.discover(str(HERE), top_level_dir=str(HERE))


def run_one(test_id: str) -> tuple[str, float, list[tuple[str, str]], int]:
    """Runs one test. Returns its ID, seconds, problems (kind, text) and the number of skips."""
    start = time.perf_counter()
    result = unittest.TestResult()
    suite = discover() if test_id.startswith("unittest.loader.") else None  # an import error
    if suite is None:
        suite = unittest.defaultTestLoader.loadTestsFromName(test_id)
    suite.run(result)
    problems = [("FAIL", f"{t}\n{text}") for t, text in result.failures]
    problems += [("ERROR", f"{t}\n{text}") for t, text in result.errors]
    problems += [("UNEXPECTED SUCCESS", str(t)) for t in result.unexpectedSuccesses]
    return test_id, time.perf_counter() - start, problems, len(result.skipped)


def main() -> int:
    verbose = "-v" in sys.argv[1:]
    sys.path.insert(0, str(HERE))
    start = time.perf_counter()
    ids = test_ids(discover())
    workers = min(len(ids), len(os.sched_getaffinity(0))) or 1
    problems: list[tuple[str, str]] = []
    skipped = 0
    # fork: the workers start at once and have the test modules loaded already.
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        for test_id, seconds, found, skips in pool.imap_unordered(run_one, ids):
            problems += found
            skipped += skips
            if verbose:
                status = "FAIL" if found else "ok"
                print(f"{seconds:5.1f}s {status:4} {test_id}", flush=True)
            else:
                print("F" if found else ".", end="", flush=True)
    if not verbose:
        print()
    for kind, text in problems:
        print("=" * 70 + f"\n{kind}: {text}")
    print("-" * 70)
    print(f"Ran {len(ids)} tests in {time.perf_counter() - start:.1f}s with {workers} processes")
    extra = f" (skipped={skipped})" if skipped else ""
    print(f"FAILED (problems={len(problems)}){extra}" if problems else f"OK{extra}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
