# Running db_bench

`db_bench` tunes against a RocksDB database that already exists on the machine.
It is the memory-resident target: where `sysbench_cpu` is a CPU-bound prime
loop, `db_bench` reads a working set far larger than any one NUMA node, so
memory-placement parameters have something to move.

## Prerequisites

Build `db_bench` from a RocksDB checkout:

```bash
git clone --depth 1 --branch v8.11.3 https://github.com/facebook/rocksdb.git ~/rocksdb
cd ~/rocksdb && CC=gcc CXX=g++ DEBUG_LEVEL=0 OPT=-O3 make db_bench -j"$(nproc)"
```

Create the database once. It is a fixture: a tuning run opens it with
`--use_existing_db=1` and never builds it.

```bash
mkdir -p /mydata/rocksdb
~/rocksdb/db_bench --benchmarks=fillseq --num=50000000 --value_size=1024 \
    --threads=1 --db=/mydata/rocksdb --compression_type=none \
    --disable_wal=1 --max_background_jobs=16
```

`--num` is the total key count and every `fillseq` thread writes the whole
`[0, num)` range, so `--threads=1` builds the same database as `--threads=16`
with a sixteenth of the writes. At 1KB values, 50M keys is roughly 50GB.

## Configuration

```json
{
  "benchmark": "db_bench",
  "db_bench_db": "/mydata/rocksdb",
  "db_bench_benchmarks": "readwhilewriting",
  "db_bench_threads": 32,
  "optimization_metric": "throughput",
  "optimization_goal": "maximize",
  "window_duration": 60,
  "settle_seconds": 15
}
```

## How a window is measured

One `db_bench` process runs for the whole session with
`--report_interval_seconds`, and each window averages the interval rows written
inside it. Nothing is relaunched between windows, so the page cache and NUMA
page placement carry across iterations — which is the point when the parameters
being tuned are the ones that build that placement up.

Two consequences:

- **No per-window latency.** The interval CSV reports throughput only, and
  `db_bench` prints its latency histogram when it exits. `latency_avg` and
  `latency_p95` stay `0`, so `optimization_metric` must be `throughput` or a
  system metric.
- **The process must outlast the run.** Its `--duration` is derived from
  `max_iterations`, `post_tuning_windows`, `window_duration` and
  `settle_seconds` with headroom for tuner think time. If it exits early the
  run fails loudly rather than measuring an idle machine.

## Objective

Throughput is average interval QPS over the window. NUMA locality counters are
recorded on every window alongside it — `numa_local_pct`,
`numa_hint_local_pct`, and the raw `/proc/vmstat` deltas including
`numa_pte_updates` and `numa_pages_migrated`. A throughput gain that moved no
locality counter did not come from a NUMA parameter.
