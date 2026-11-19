#!/usr/bin/env bash
# Compares the speed of two CPUs with the stress-ng matrix benchmark.
#
# Usage: compare-cores.sh CPU_A CPU_B [ROUNDS]
#
# Each round runs the benchmark on CPU_A, then on CPU_B, and prints one line
# per run: "<bogo ops/s> <cpu>". Lock both cores first, so that boost and the
# governor do not change the result:
#
#   cpu-tune lock --cpu CPU_A,CPU_B
#   examples/compare-cores.sh CPU_A CPU_B
#   cpu-tune reset
set -euo pipefail

if [[ $# -lt 2 ]]; then
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
fi
A=$1
B=$2
ROUNDS=${3:-10}
BENCH_DURATION=10s
SLEEP_DURATION=2

bench() {
    taskset -c "$1" stress-ng --matrix 1 --timeout "$BENCH_DURATION" --metrics-brief 2>&1 |
        awk -v CPU="$1" '/^[^:]*: metrc: .* matrix[[:space:]]/ {print $(NF-1) " " CPU; exit}'
}

for _ in $(seq 1 "$ROUNDS"); do
    for cpu in "$A" "$B"; do
        sleep "$SLEEP_DURATION"
        bench "$cpu"
    done
done
