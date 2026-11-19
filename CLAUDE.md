# cputune: notes for agents

Tool to rank CPU cores and lock/limit frequencies for stable benchmarks. Users: Martin, and AI
agents that run benchmarks (`cputune run -- <cmd>`, `--json`).

## Layout

- `cputune`: the whole tool. One file, Python 3.9+, standard library only: keep it so (users copy
  one file; `update` replaces one file). Sections start with `# ----- <name>`: terminal output,
  read sysfs, measure, render, show/watch, root, change settings, sudoers, install/update, main.
- `tests/test_cputune.py`: unittest. `tests/fake_sysfs.py` builds fake `/sys` trees from
  `tests/machines/*.txt` (recorded output of 6 real machines: Intel hybrid, EPYC acpi-cpufreq,
  3 Ryzen amd-pstate-epp, Raspberry Pi). `tests/check_version.py`: CI version check.
- `.github/workflows/test.yml`: tests (python:3.9-slim and 3.14-slim containers; setup-python has
  no 3.9 on new runners), `version` (PRs), `release` (main).
- `docs/show.png`: README screenshot; `docs/ansi2png.py` makes it (usage in its docstring).

## Checks

```sh
python3 -m unittest discover -s tests          # ~15 s; also run with python3.9 (installed here)
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
- Mutation checks: back up the file to the scratchpad, apply one replacement, run one test with a
  timeout (`watch` never ends), restore in `finally`, then `cmp`. Check that the mutation compiles.
  Never `pkill -f` a pattern from your own command line: it kills your own shell.

## This machine

- Ryzen 9 7950X, `amd-pstate-epp`, kernel 7.x: no `amd_pstate_nominal_freq`; base frequency comes
  from `acpi_cppc/nominal_freq` (MHz). `cpuinfo_avg_freq` exists.
- sudo needs a password, so agents cannot run `lock`, `limit`, `reset`, `run` or
  `sudoers --install` for real: give Martin the command to run.
- Fedora sudo: `env_reset`, `always_set_home`.
- GitHub: no MCP tools; use `gh` (logged in). Right after a push, `gh pr checks` reports no checks:
  use `gh run list --branch <b>` and `gh run watch <id> --exit-status`.

## Rules

- Security: a sudo rule lets every program of the user run `cputune` as root. Under sudo only
  `lock`, `limit`, `reset` and `update` run (`SUDO_COMMANDS`), the test hooks are off, and no root
  code may run a program or write a file that the user chooses. Keep it so; test it in `SecurityTest`.
- Every change to `cputune` increases `__version__`: fix = patch, feature = minor, breaking change
  (command, path or variable names) = major. `update` only installs higher versions; CI fails the
  PR otherwise.
- `main` is protected, also for admins: branch, PR, green checks, squash merge. Commit, push, open
  PRs and merge only when Martin asks in the current request; auto mode also blocks these, and
  branch deletion, without an explicit request.
- Releases are automatic: after a merge to `main` with green tests, the `release` job creates the
  tag `vX.Y.Z` and the GitHub release with `cputune` attached. Do not tag by hand. Check it with
  `gh release view vX.Y.Z`.
- README: short (under 100 lines), install and use first; details go to `--help`. Martin: nobody
  reads a wall of text. Plain language (ISO 24495, ASD-STE100): short sentences, active voice.

## Open

- `lock`, `limit`, `reset`, `run` and `sudoers --install` are not yet verified on real hardware
  (needs sudo). Intel, EPYC and Raspberry Pi are covered only by fake trees.
- Version 2.0.0 renamed `cpu-tune` to `cputune`. Copies of 1.x look for `cpu-tune` on GitHub, so
  they cannot update; `install` and `sudoers` warn about old copies (`legacy_note`).
