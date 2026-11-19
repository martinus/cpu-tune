# cputune: notes for agents

Tool to rank CPU cores and lock/limit frequencies for stable benchmarks. Users: Martin, and AI
agents that run benchmarks (`cputune run -- <cmd>`, `--json`).

## Layout

- `cputune`: the whole tool. One file, Python 3.9+, standard library only: keep it so (users copy
  one file; `update` replaces one file). Sections start with `# ----- <name>`: terminal output,
  read sysfs, measure, render, show/watch, check, root, change settings, sudoers, install/update, main.
- `tests/test_cputune.py`: unittest. `tests/fake_sysfs.py` builds fake `/sys` trees from
  `tests/machines/*.txt` (recorded output of 6 real machines: Intel hybrid, EPYC acpi-cpufreq,
  3 Ryzen amd-pstate-epp, Raspberry Pi). `tests/check_version.py`: CI version check.
- `tests/run.py`: runs the tests in parallel (CI uses it). `tests/hardware_check.py`: lock, limit,
  reset and run on the real machine, with sudo; Martin runs it, CI cannot.
- `.github/workflows/test.yml`: tests (python:3.9-slim and 3.14-slim containers; setup-python has
  no 3.9 on new runners), `version` (PRs), `release` (main).
- `docs/show.png`: README screenshot; `docs/ansi2png.py` makes it (usage in its docstring).

## Checks

```sh
python3 tests/run.py                           # ~5 s, parallel; also run with python3.9 (installed here)
ruff check --select E,F,W,B,UP --target-version py39 --line-length 120 cputune tests docs
shellcheck examples/*.sh
```

## Test patterns

- CLI behavior: run the real script in a subprocess with `CPUTUNE_ROOT=<fake tree>` (`Case.ok`,
  `.fails`, `.json`). The test hooks (`CPUTUNE_ROOT`, `CPUTUNE_SOURCE_URL`) skip sudo, CPU load
  and GitHub. Fake files are static: kernel side effects (lower `cpuinfo_max_freq` with boost off)
  are not simulated.
- States a test user cannot create (root, sudo, files owned by root): `load_module()` plus
  `unittest.mock`, see `SecurityTest`. Stub the `cmd_*` functions there: under simulated sudo the
  hooks are off, so a real command would change this machine.
- Tests must not depend on git: CI containers have no git, so the checkout has no `.git`.
- Keep tests fast: CI waits for them. Fake trees go to `/dev/shm` (8 times faster than disk; Docker
  mounts it noexec, so a test that runs files of its tree sets `tmp = None`, see `RootCopyTest`). No
  `sleep` in tests: under `CPUTUNE_ROOT`, cputune does not wait. Tests run in parallel, so a test
  must not change files outside its own tree.
- Tests also pass as root (the CI containers run as root). A test that needs a copy not owned by
  root copies the script into its tree, see `SudoersTest`.
- Mutation checks: back up the file to the scratchpad, apply one replacement, run one test with a
  timeout (`watch` never ends), restore in `finally`, then `cmp`. Check that the mutation compiles.
  Never `pkill -f` a pattern from your own command line: it kills your own shell.

## This machine

- Ryzen 9 7950X, `amd-pstate-epp`, kernel 7.x: no `amd_pstate_nominal_freq`; base frequency comes
  from `acpi_cppc/nominal_freq` (MHz). `cpuinfo_avg_freq` exists. Measured with `lock -c 4`
  (2.3.0): 3000 -> 2729 MHz, 4000 -> 3601, 4501 -> 4304, 425 (min) -> 2170. The same within 0.5 %
  each time, with and without `tuned`. TSC 4499.7 MHz, CPPC linear (35.44 MHz per perf), so the
  measurement is right: the firmware runs below the request and not below about 2170 MHz.
  `amd_pstate_lowest_nonlinear_freq` is 3012 MHz. `tuned` and `tuned-ppd` run (profile balanced).
- sudo needs a password, so agents cannot run `lock`, `limit`, `reset`, `run` or
  `install --no-password` for real: give Martin the command to run.
- Fedora sudo: `env_reset`, `always_set_home`.
- GitHub: no MCP tools; use `gh` (logged in). Right after a push, `gh pr checks` reports no checks:
  use `gh run list --branch <b>` and `gh run watch <id> --exit-status`.

## Rules

- Few commands: show (`cputune`, `-w` live), run, lock, limit, reset, install. `cputune --help`
  groups them by task (`HELP`); argparse lists none. `watch`, `check`, `update` and `sudoers` are
  hidden aliases (no `help=`): scripts keep working, and root needs `update` for its own copy.
- Security: a sudo rule lets every program of the user run `cputune` as root. Under sudo only
  `lock`, `limit`, `reset` and `update` run (`SUDO_COMMANDS`), the test hooks are off, and no root
  code may run a program or write a file that the user chooses. When a root-owned
  `/usr/local/bin/cputune` exists, sudo always runs that copy (`root_copy`): the rule names it, and
  root must not run a copy the user can change. Keep it so; test it in `SecurityTest`, `RootCopyTest`.
- A reboot undoes everything: cputune changes settings only where a reboot resets them (`/sys`,
  and its state in `/run`). Never write a setting that stays, for example `systemctl set-property`
  without `--runtime`, or files in `/etc`. Only `install` (and its aliases `update`, `sudoers`) writes
  files that stay, on purpose.
- Only one installed copy (`install_copy`): with `/usr/local/bin/cputune`, `install` updates it, and
  `install --system` deletes `~/.local/bin/cputune`. Two copies drift apart, and PATH finds the wrong one.
- Every change to `cputune` increases `__version__`: fix = patch, feature = minor, breaking change
  (command, path or variable names) = major. `update` only installs higher versions; CI fails the
  PR otherwise.
- `main` is protected, also for admins: branch, PR, green checks, squash merge. Commit, push, open
  PRs and merge only when Martin asks in the current request; auto mode also blocks these, and
  branch deletion, without an explicit request.
- Releases are automatic: after a merge to `main` with green tests, the `release` job creates the
  tag `vX.Y.Z` and the GitHub release with `cputune` attached. Do not tag by hand. Check it with
  `gh release view vX.Y.Z`. `install` and `update` download the latest release (`SOURCE_URL`), not
  `main`: raw.githubusercontent.com caches `main` for 5 minutes.
- README: short (under 100 lines), install and use first; details go to `--help`. Martin: nobody
  reads a wall of text. Plain language (ISO 24495, ASD-STE100): short sentences, active voice.

## Open

- `lock`, `limit`, `reset`, `run` and `install --no-password` are not yet verified on real hardware
  (needs sudo): Martin runs `tests/hardware_check.py`. Intel, EPYC and Raspberry Pi are covered only
  by fake trees.
- Version 2.0.0 renamed `cpu-tune` to `cputune`. Copies of 1.x look for `cpu-tune` on GitHub, so
  they cannot update; `install` and `sudoers` warn about old copies (`legacy_note`).
