# cpu-tune

`cpu-tune` shows the CPU cores of a Linux machine ranked by speed, and locks
their frequency, so that benchmarks give stable results. It is one Python file
(3.9 or newer) with no dependencies.

![cpu-tune show --now on a Ryzen 9 7950X, with load on three cores](docs/show.png)

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/martinus/cpu-tune/main/cpu-tune | python3 - install
```

This installs `cpu-tune` in `~/.local/bin`. `cpu-tune update` installs a newer
version from GitHub.

## Use

```sh
cpu-tune                       # show the cores, best rank first
cpu-tune watch                 # live view of the core frequencies
cpu-tune run -- ./bench        # lock the best core, run ./bench on it, then reset
cpu-tune lock                  # lock the best core (without CPU 0) at base frequency
cpu-tune lock 3GHz --cpu 2     # lock CPU 2 and its SMT sibling at 3000 MHz
cpu-tune limit --max 2400      # all cores: at most 2400 MHz
cpu-tune reset                 # undo lock and limit
```

`lock` turns boost off, sets the `performance` governor, and sets the minimum
and maximum frequency to the same value. Then it measures the frequency under
load. `reset` restores the settings from before. A reboot also restores them.

`run` is the easiest way to get stable results: it locks, runs the command on
the locked CPUs as your user, and always resets, also after Ctrl+C.

`cpu-tune --help` and `cpu-tune <command> --help` show all options. All commands
accept `--json`.

## Use without a password prompt

`lock`, `run`, `limit` and `reset` need root, and they run `sudo` themselves.
Scripts and AI agents have no terminal to type a password. To allow `cpu-tune`
without a password, run this once:

```sh
cpu-tune sudoers --install
```

It installs `cpu-tune` in `/usr/local/bin`, owned by root, and adds a sudo rule
for that copy. `cpu-tune sudoers` shows the status. Under sudo, `cpu-tune` only
runs `lock`, `limit`, `reset` and `update`, so the rule gives no more than the
CPU settings. Undo: `sudo rm /etc/sudoers.d/cpu-tune`.

## Use from AI agents

Copy this into the instructions of your agent, for example `AGENTS.md` or `CLAUDE.md`:

```markdown
For benchmarks, use `cpu-tune run -- <command>`. It locks a fast core at a fixed
frequency, runs the command on it, and resets. stdout and the exit code are the
ones of the command. `cpu-tune show --json` shows the state of the machine. If
`cpu-tune` says that sudo needs a password, stop and ask the user to run
`cpu-tune sudoers --install`.
```

## Development

```sh
python3 -m unittest discover -s tests
```

The tests run against fake sysfs trees, built from the recorded machines in
[tests/machines](tests/machines). Increase `__version__` for every change to
`cpu-tune`. After a merge to `main`, CI creates the tag and the
[GitHub release](https://github.com/martinus/cpu-tune/releases).

## License

[0BSD](LICENSE)
