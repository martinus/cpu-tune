# cpu-tune <!-- omit in toc -->

`cpu-tune` shows the CPU cores of a Linux machine ranked by speed. It also locks
or limits CPU frequencies, so that benchmarks give stable results. It is one
Python file with no dependencies.

![cpu-tune show --now on a Ryzen 9 7950X, with load on three cores](docs/show.png)

- [Why](#why)
- [Install](#install)
- [Update](#update)
- [Quick start](#quick-start)
- [Commands](#commands)
  - [show: see the cores](#show-see-the-cores)
  - [watch: live view](#watch-live-view)
  - [lock: fix the frequency of a core](#lock-fix-the-frequency-of-a-core)
  - [run: lock, run, reset in one step](#run-lock-run-reset-in-one-step)
  - [limit: set a frequency range](#limit-set-a-frequency-range)
  - [reset: undo all changes](#reset-undo-all-changes)
- [Run without a password prompt](#run-without-a-password-prompt)
- [Use cpu-tune from AI agents](#use-cpu-tune-from-ai-agents)
- [How it works](#how-it-works)
- [Development](#development)
- [License](#license)

## Why

On a desktop or a laptop, the same benchmark often gives different results
from one run to the next. These are the most frequent causes:

- **Boost.** The CPU runs faster than its base frequency while it is cool, and
  slower when it gets hot.
- **Power saving.** The governor and the energy setting (EPP) change the
  frequency with the load.
- **Different cores.** Some cores are faster than others. On hybrid CPUs, the
  cores are of different types.
- **Moving processes.** The scheduler moves a process from one core to another.

`cpu-tune` removes these causes. It locks one fast core to its base frequency,
turns boost off, and runs the benchmark only on that core.

## Install

`cpu-tune` needs Python 3.9 or newer. To install it in `~/.local/bin`:

```sh
curl -fsSL https://raw.githubusercontent.com/martinus/cpu-tune/main/cpu-tune | python3 - install
```

To install it in `/usr/local/bin`, owned by root, add `--system`. Use this when
scripts or AI agents must use `cpu-tune` without a password prompt. See
[Run without a password prompt](#run-without-a-password-prompt).

```sh
curl -fsSL https://raw.githubusercontent.com/martinus/cpu-tune/main/cpu-tune | python3 - install --system
```

`cpu-tune install` also works from a git checkout. It installs the newer of
the checkout and the version on GitHub. Add `--no-check` to install the checkout
without looking on GitHub.

`install` tells you when the folder is not in your `PATH`, or when your shell
finds another `cpu-tune` first.

## Update

```sh
cpu-tune update
```

`update` downloads `cpu-tune` from the `main` branch on GitHub. If the version
there is higher, it replaces the copy that you started. Before it replaces the
file, it checks that the download is a `cpu-tune` script and that your Python
can compile it. It never runs the download to check it.

- A copy owned by root (`install --system`) is updated with `sudo`. The root
  process downloads the file itself, so a sudo rule for `cpu-tune` cannot be
  used to install some other file as root.
- A copy in a git checkout is not changed. Use `git pull` there.

## Quick start

```sh
cpu-tune                    # show the cores, best rank first
cpu-tune run -- ./bench     # lock the best core, run ./bench on it, then undo the lock
```

`run` is the easiest way to get stable results. It does all steps, and it
always undoes the lock at the end.

## Commands

| Command | What it does | Root |
| --- | --- | --- |
| `cpu-tune` or `cpu-tune show [--now]` | Shows the system and the cores, best rank first. | No |
| `cpu-tune watch` | Shows the core frequencies live. | No |
| `cpu-tune lock [FREQ] [--cpu CPUS]` | Locks cores to one frequency, with boost off. | Yes |
| `cpu-tune run [FREQ] [--cpu CPUS] -- COMMAND` | Locks, runs `COMMAND` on the locked cores, and resets. | Yes |
| `cpu-tune limit [--min FREQ] [--max FREQ] [--cpu CPUS]` | Sets the frequency range of cores. | Yes |
| `cpu-tune reset` | Undoes all changes of `lock`, `run` and `limit`. | Yes |
| `cpu-tune sudoers [--install]` | Shows or sets up the use without a password prompt. | With `--install` |
| `cpu-tune install [--system]` | Installs to `~/.local/bin`, or to `/usr/local/bin` with `--system`. | With `--system` |
| `cpu-tune update` | Updates this copy to the newest version on GitHub. | For a root-owned copy |
| `cpu-tune --version` | Prints the version. | No |

Values:

- `FREQ` is a number in MHz (`2400`), a number with a unit (`2400MHz`,
  `2.4GHz`), or one of the words `base`, `min` and `max`.
- `CPUS` is a CPU ID or a list: `3`, `2,3`, `0-7` or `all`.

All commands accept `--json` for machine-readable output, and
`--color auto|always|never`. `cpu-tune` also respects the `NO_COLOR` environment variable.

The commands that need root run `sudo` themselves. Do not start `cpu-tune` with
`sudo`.

### show: see the cores

`cpu-tune show` prints one line for each physical core:

- **rank**: the rank from the kernel. The scheduler uses it to pick the fastest
  cores first. On AMD it comes from `acpi_cppc/highest_perf`, on Intel from
  `topology/itmt_score`. Without these files, all cores get rank 100.
- **cpus**: the CPU IDs of the core. The second ID (gray) is the SMT sibling
  (Hyper-Threading) of the first.
- **min, base, max**: the hardware range and the base frequency in MHz.
- **bar**: the frequency range on a scale in GHz. `━` is the range up to the base
  frequency, `╍` is the boost range above it. When `lock` or `limit` changed a
  core, `─` shows the part outside the set range, and `◆` shows a locked frequency.
- **★** marks the core that `cpu-tune lock` uses when you do not give `--cpu`.

`--now` measures the frequency of each core for 1 second and shows it as a
colored bar. The color goes from blue (low) to red (high).

If `lock`, `run` or `limit` changed settings, `show` tells you, and it shows how
to undo the change.

This is the plain text output (for example in a pipe) on a Ryzen 9 7950X:

```text
AMD Ryzen 9 7950X 16-Core Processor   16 cores, 32 CPUs
driver amd-pstate-epp · governor powersave (performance powersave) · epp balance_performance · boost on
kernel 7.3.4-200.fc44.x86_64

                                 0         1         2         3         4         5        6 GHz
rank  cpus      min  base   max
 236   1 17 ★   425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 236   5 21     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 231   3 19     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 226   7 23     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 221   4 20     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 216   0 16     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 211   6 22     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 206   2 18     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 201  13 29     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 196  15 31     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 191   9 25     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 186  11 27     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 181  12 28     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 176  10 26     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 171  14 30     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍
 166   8 24     425  4501  5883      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╍╍╍╍╍╍╍╍╍╍╍╍╍

━ range   ╍ boost   ★ default core for lock   (all values in MHz)
```

The folder [tests/machines](tests/machines) has the core data of five more
machines: an i9-13950HX, an EPYC 9354P, a Ryzen 5 5500GT, a Ryzen AI 7 350 and a
Raspberry Pi 4. The tests use them.

### watch: live view

```sh
cpu-tune watch                 # update every second, stop with Ctrl+C
cpu-tune watch --interval 0.5
```

`watch` shows the same table as `show --now`, and updates it. Use it in a second
terminal while a benchmark runs: the locked core must stay at its frequency.
With `--json`, `watch` prints one JSON object per update. `--count N` stops
after N updates.

`watch` keeps its own load low, so that it does not change the result of a
benchmark:

- It runs with the lowest priority (nice 19).
- It does not run on the CPUs that `cpu-tune` locked.
- It wakes up once per update. It keeps the sysfs files open and reads each
  value with one system call. Topology and system info are read again only
  every 5 seconds.
- It redraws only the lines that changed.

On a Ryzen 9 7950X, one update takes less than 1 ms of CPU time. Reading the
frequencies did not cause measurable extra interrupts on the other cores.

### lock: fix the frequency of a core

```sh
cpu-tune lock                  # the core with ★, at base frequency
cpu-tune lock 3GHz --cpu 2     # cpu2 and its SMT sibling, at 3000 MHz
taskset -c 1,17 ./bench        # run the benchmark on the locked CPUs
cpu-tune reset
```

`lock` does these steps:

1. It saves the current settings in `/run/cpu-tune.json`.
2. It turns boost off. When the kernel has a switch for each core (`amd-pstate`
   on kernel 6.11 and newer), only the locked cores lose boost. Otherwise boost
   is off for all cores, and `lock` tells you.
3. It sets the governor to `performance`, when the driver has it.
4. It sets the minimum and the maximum frequency to the same value.
5. It runs a busy loop on each locked core and measures the frequency. `✓`
   means that the measured value is within 3% (at least 50 MHz) of the lock.

Defaults and checks:

- Without `FREQ`, `lock` uses the base frequency of each core. On hybrid CPUs,
  P-cores and E-cores have different base frequencies.
- Without `--cpu`, `lock` uses the best-ranked core that does not hold CPU 0,
  because CPU 0 often handles more interrupts. On a tie, the lowest CPU IDs win.
- `lock` always includes the SMT siblings of a CPU. Siblings share one physical
  core, and the core runs at the highest frequency that one of them asks for.
- A `FREQ` outside the hardware range, or above the base frequency, is an
  error. `lock` checks this before it changes anything.

At the end, `lock` prints the `taskset` command for your benchmark.

### run: lock, run, reset in one step

```sh
cpu-tune run -- ./bench --iterations 100
cpu-tune run 3GHz --cpu 4 -- python3 bench.py
```

`run` does these steps:

1. It locks the cores, as `lock` does.
2. It runs the command, pinned to the locked CPUs. The command runs as your
   user, not as root. The environment variable `CPU_TUNE_CPUS` holds the
   locked CPUs, for example `1,17`.
3. It resets all settings, also when the command fails or you press Ctrl+C.

`run` writes its own messages to stderr, so stdout holds only the output of
the command. The exit code of `run` is the exit code of the command.

`run` refuses to start when `cpu-tune` already changed settings. So two
benchmarks cannot use the same machine at the same time by accident.

If the benchmark runs longer than the sudo timeout (often 5 minutes), sudo asks
for the password again for the reset. A sudo rule without a password prevents this.

### limit: set a frequency range

```sh
cpu-tune limit --max 2400      # all cores: at most 2400 MHz
cpu-tune limit --max base      # all cores: at most the base frequency
cpu-tune limit --max 0         # all cores: lowest possible frequency
cpu-tune limit --min 99999     # all cores: highest possible frequency
cpu-tune limit --max 2GHz --cpu 0-7
```

`limit` changes all cores, unless you give `--cpu`. Values outside the hardware
range are clamped to it. If `--min` is above `--max`, `--max` wins. `limit` does
not change boost or the governor.

### reset: undo all changes

The first `lock`, `run` or `limit` saves the original settings in
`/run/cpu-tune.json`. Later commands add new CPUs to the file, but they never
overwrite saved values. `reset` restores boost, governor, EPP and frequency range,
and deletes the file.

Without the file, `reset` sets the full hardware range on all cores. It does
not change boost and governor then.

A reboot also undoes all changes, because sysfs and `/run` do not survive a reboot.

## Run without a password prompt

`lock`, `run`, `limit` and `reset` need root, and they run `sudo` themselves.
In a terminal, sudo asks for your password. Without a terminal, for example in
a script or an AI agent, `cpu-tune` uses `sudo -n`. Then sudo never waits for a
password. If sudo needs a password, `cpu-tune` stops with an error that tells you
what to do.

To allow `cpu-tune` without a password, run:

```sh
cpu-tune sudoers --install
```

It asks for your password once, and then:

1. It installs `cpu-tune` in `/usr/local/bin`, owned by root, if it is not there yet.
2. It checks the sudo rule with `visudo`, and installs it in `/etc/sudoers.d/cpu-tune`.
3. It checks that sudo now runs `cpu-tune` without a password.

`cpu-tune sudoers` without `--install` shows what is set up, and changes nothing.
`cpu-tune sudoers --rule` prints only the rule. It looks like this:

```text
martinus ALL=(root) NOPASSWD: /usr/local/bin/cpu-tune
```

To undo it: `sudo rm /etc/sudoers.d/cpu-tune`.

> [!WARNING]
> Do not use the rule for a copy of `cpu-tune` that your user can change, for
> example in `~/.local/bin`. Then every program that runs as your user can edit
> the script and get root. `cpu-tune sudoers` always names a copy that only root
> can change.

If you also have a copy in `~/.local/bin`, delete it, or make sure that
`/usr/local/bin` comes first in your `PATH`. The rule only works for the exact path.

## Use cpu-tune from AI agents

Install `cpu-tune` with a [sudo rule](#run-without-a-password-prompt). Then copy
this text into the instructions of your agent, for example `AGENTS.md` or `CLAUDE.md`:

```markdown
## Benchmarks

Use `cpu-tune` for all benchmarks and performance comparisons:

- Run each benchmark with `cpu-tune run -- <command>`. It locks the best core
  at base frequency with boost off, pins the command to it, and resets all
  settings at the end. stdout holds only the output of the command. The exit
  code is the exit code of the command.
- Compare results only from runs with the same `cpu-tune run` options.
- To see the state of the machine, run `cpu-tune show --json`. If
  `changed_by_cpu_tune` is not null, another lock is active: do not reset it
  without asking the user.
- If `cpu-tune` reports that sudo needs a password, stop and tell the user to
  run `cpu-tune sudoers --install` once. Do not run `sudo` yourself.
```

All commands accept `--json`. Errors give `"ok": false` and an `"error"` text,
and the exit code is 1. Warnings, for example a measured frequency that does
not match the lock, are in the `"warnings"` list. This is the output of
`cpu-tune lock --json`:

```json
{
  "ok": true,
  "command": "lock",
  "cpus": [1, 17],
  "cores": [
    {
      "cpus": [1, 17],
      "target_mhz": 4501,
      "measured_mhz": 4498,
      "ok": true
    }
  ],
  "boost_off": "core",
  "governor": "performance",
  "taskset": "taskset -c 1,17",
  "undo": "cpu-tune reset"
}
```

`cpu-tune show --json` gives the system info, `default_lock_cpus`, and for each
core: `rank`, `cpus`, `hw_min_mhz`, `hw_max_mhz`, `base_mhz`, `min_mhz`,
`max_mhz`, `locked` and `now_mhz` (with `--now`).

## How it works

`cpu-tune` reads and writes these files in `/sys/devices/system/cpu`:

| What | Files |
| --- | --- |
| Cores and siblings | `cpuN/topology/thread_siblings_list` |
| Rank | `cpuN/acpi_cppc/highest_perf`, `cpuN/cpufreq/amd_pstate_prefcore_ranking`, `cpuN/topology/itmt_score` |
| Hardware range | `cpuN/cpufreq/cpuinfo_min_freq`, `cpuinfo_max_freq` |
| Set range | `cpuN/cpufreq/scaling_min_freq`, `scaling_max_freq` |
| Base frequency | `base_frequency` (Intel), `amd_pstate_nominal_freq` (older AMD kernels), `acpi_cppc/nominal_freq`, the highest value of `scaling_available_frequencies` (acpi-cpufreq), `cpuinfo_max_freq` |
| Boost | `cpuN/cpufreq/boost` (per core), `intel_pstate/no_turbo`, `cpufreq/boost` |
| Governor, EPP | `cpuN/cpufreq/scaling_governor`, `energy_performance_preference` |
| Measured frequency | `cpuN/cpufreq/cpuinfo_avg_freq` (new kernels), `scaling_cur_freq` |

Tested drivers: `intel_pstate`, `amd-pstate-epp` and `acpi-cpufreq`, and
`cpufreq-dt` (Raspberry Pi, no boost switch). `cpu-tune show` works on all Linux
systems, also without a cpufreq driver.

`cpu-tune` was called `core-ranker` before, and the script was `core_ranks.py`.
`cpu-tune show` replaces it.

## Development

```sh
python3 -m unittest discover -s tests
```

Increase `__version__` in `cpu-tune` for every change to the script.
`cpu-tune update` installs a new version only when its number is higher. CI
checks this for each pull request with `tests/check_version.py`.

Releases are automatic. When a new `__version__` reaches `main` and the tests
pass, CI creates the tag `vX.Y.Z` and a
[GitHub release](https://github.com/martinus/cpu-tune/releases) with the
script attached.

The tests build fake sysfs trees from the recorded machines in
[tests/machines](tests/machines), and run `cpu-tune` against them. The
environment variable `CPU_TUNE_ROOT` points `cpu-tune` at a fake tree. Then it
does not run sudo, and it does not put load on the real CPUs.

The fake trees have static files. A real kernel changes some files when you
write to others, for example `cpuinfo_max_freq` when boost goes off. Test
changes on real hardware too.

[examples/compare-cores.sh](examples/compare-cores.sh) compares two cores with
`stress-ng`.

## License

[0BSD](LICENSE)
