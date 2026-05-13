# Included Targets

SemaTune is organized around application targets. A target is any workload or
service that can be prepared, measured over a time window, and summarized into
metrics. The repository includes two maintained targets that are used throughout
the docs and tests.

The config field is still named `benchmark` for compatibility. On this page,
`benchmark: "sysbench_cpu"` and `benchmark: "tpcc"` mean “select this target
adapter.”

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
