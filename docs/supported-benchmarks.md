# Included Targets

SemaTune is organized around application targets. A target is any workload or
service that can be prepared, measured over a time window, and summarized into
metrics. The repository includes four maintained targets that are used
throughout the docs and tests.

The config field is still named `benchmark` for compatibility. On this page,
`benchmark: "sysbench_cpu"`, `benchmark: "db_bench"`, `benchmark: "gapbs"` and
`benchmark: "tpcc"` mean “select this target adapter.”

## `sysbench_cpu`

`sysbench_cpu` runs the built-in sysbench CPU prime-number workload. It is the
fastest target to use when checking installation, validating OS parameter
application, or learning the control loop.

Typical objective:

```json
{
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

Important target fields are documented in the
[Configuration Reference](configuration.md#sysbench_cpu-fields), and the
step-by-step run guide is [Running Sysbench CPU](running-sysbench-cpu.md).

## `db_bench`

`db_bench` runs RocksDB against a database built once beforehand. It is the
memory-resident target: the working set is far larger than one NUMA node, so
memory-placement parameters have something to move.

One process runs for the whole session and each window averages the interval
rows written inside it, so page cache and NUMA page placement carry across
iterations instead of being reset every window.

Typical objective:

```json
{
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

The interval stream carries throughput only, so `latency_avg` and
`latency_p95` stay `0` for this target.

Important target fields are documented in the
[Configuration Reference](configuration.md#db_bench-fields), and the
step-by-step run guide is [Running db_bench](running-db-bench.md).

## `gapbs`

`gapbs` runs a GAP Benchmark Suite graph kernel over a generated Kronecker
graph. Graph traversal has deliberately poor locality, so it is the target
whose performance depends most directly on where its memory sits.

One kernel run covers the whole session and each window reports the trials that
finished inside it. Generating and building the graph costs several times what
a trial does — 81s against 12s at scale 27 — so both happen once before the
first window rather than inside one.

Typical objective:

```json
{
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

Throughput is completed trials per second and `latency_avg` is the mean trial
time. A window can legitimately contain no completed trial when a trial is
longer than the window; throughput is then `0` rather than an error, and the
system metrics still describe the window.

Important target fields are documented in the
[Configuration Reference](configuration.md#gapbs-fields).

## `tpcc`

`tpcc` runs BenchBase TPC-C against PostgreSQL. It is the database-backed
example target and exercises a more realistic setup path: PostgreSQL service
configuration, BenchBase build/load, per-window execution, and tail-latency
metrics.

Typical objective:

```json
{
  "optimization_metric": "latency_p99",
  "optimization_goal": "minimize"
}
```

Important target fields are documented in the
[Configuration Reference](configuration.md#tpcc-benchbase-fields), and the
setup guide is [Running TPCC](running-tpcc.md).

## Adding More Targets

These included targets are examples of the target-adapter interface, not the
limit of the framework. To add another application, implement the adapter
contract described in [Extending SemaTune](extending.md): prepare the target,
observe or run one measured window, parse metrics, clean up, and provide a small
example config plus tests.
