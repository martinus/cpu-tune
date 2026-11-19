# cpu-tune: notes for agents

- `cpu-tune` is one file: Python 3.9+, standard library only. Keep it that way.
- Tests: `python3 -m unittest discover -s tests` (also with `python3.9` when available).
  Lint: `ruff check --select E,F,W,B,UP --target-version py39 --line-length 120 cpu-tune tests`.
- Tests run against fake sysfs trees (`CPU_TUNE_ROOT`). Do not run `lock`, `run`, `limit` or `reset`
  on the real machine without asking: they change CPU settings as root.
- Security: a sudo rule lets any program of the user run `cpu-tune` as root. Under sudo, only
  `lock`, `limit`, `reset` and `update` may run (`SUDO_COMMANDS`), and no code that root runs may
  execute a program, or write a file, that the user chooses. Keep it so, and test it in `SecurityTest`.
- Every change to `cpu-tune` increases `__version__`: a fix the patch number, a new feature the minor
  number. `cpu-tune update` only installs higher versions, and CI fails the PR otherwise.
- `main` is protected, also for admins: branch, pull request, green checks, squash merge.
  Merge only when Martin approves.
- Releases are automatic: after a merge to `main` with green tests, the `release` job in
  `.github/workflows/test.yml` creates the tag `vX.Y.Z` and the GitHub release with `cpu-tune`
  attached. Do not tag by hand. If the job failed, fix it, or release by hand with:
  `gh release create vX.Y.Z cpu-tune --target <sha on main> --title "cpu-tune X.Y.Z" --generate-notes`.
- Documentation: plain language (ISO 24495, ASD-STE100 style): short sentences, active voice.
