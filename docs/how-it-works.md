# How SemaTune Works

SemaTune is a host-side control loop. It does not replace a kernel scheduler,
database optimizer, or application-level autoscaler. Instead, it controls a
bounded set of OS parameters around a running target and asks whether changing
those parameters improves the target's measured behavior.

## Control Loop

Each tuning session follows the same shape:

1. Load a JSON config that names the target, metric, tuner, parameter ranges,
   run length, and output directory.
2. Prepare the target application once, if setup is needed.
3. Measure one window of target and system behavior.
4. Score the latest window using `optimization_metric` and `optimization_goal`.
5. Ask the tuner for the next parameter setting.
6. Validate the proposal against the active parameter schema and configured
   ranges.
7. Apply accepted values through the host-side parameter manager.
8. Repeat for `max_iterations`, then run `post_tuning_windows` with the final
   configuration.

By default, tuning happens in `outside-of-window` mode. SemaTune measures a
window, asks the tuner after the window completes, applies accepted changes, and
then measures the next window. The target can remain live across windows; for
example, `sysbench_cpu` uses one continuous `sysbench --report-interval`
process instead of restarting every iteration.

## Target Adapter

A target adapter is the bridge between SemaTune and an application. The adapter
knows how to prepare the target, run or observe a timed window, parse outputs,
and return metrics in the common `BenchmarkMetrics` shape.

For a simple command-line program, a target adapter may launch a process for the
run and parse stdout. For a long-running service, the adapter may start the
service once, drive load against it, collect latency and throughput, and keep
the service alive while SemaTune changes OS parameters.

The optimizer owns parameter application and run history. Target adapters should
focus on target lifecycle and metric extraction.

## OS Parameter Surface

SemaTune exposes a typed parameter surface instead of giving tuners shell
access. The config declares `parameter_ranges`, optional `parameters_to_tune`,
and any `fixed_parameters`. Parameter metadata defines whether a knob is
numeric or categorical and whether it is global or per-core.

When a tuner proposes a change, SemaTune accepts only parameters in the active
tunable set, checks values against configured ranges or domains, expands
per-core settings when needed, and writes through known Linux interfaces such as
`debugfs`, `sysfs`, CPU-frequency paths, and `sysctl`.

## Tuners

All tuners use the same outer loop. The difference is how they choose the next
configuration:

- `fixed` applies a known configuration and is useful for baselines.
- `llm` builds a prompt from knob metadata, current metrics, recent history, and
  optional workload context.
- `bayesian` and `mlos` use model-based search over the configured space.
- `qlearning` and `dqn` treat tuning as a sequential decision problem over a
  discretized action space.

The tuner returns a proposal; it does not write host state directly. That
boundary is important for reproducibility and safety.

## Outputs

Each session writes an optimization history, per-window target outputs, optional
system metrics, and, for LLM runs, full request/response logs. These files are
the audit trail for the control loop: what SemaTune observed, what the tuner
suggested, what was applied, and what happened next.

See [Results Format](results-format.md) for the exact layout.
