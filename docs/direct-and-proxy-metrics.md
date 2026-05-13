# Direct and Proxy Metrics

SemaTune can optimize from direct application metrics, proxy system metrics, or
a combination of both. Direct metrics define success. Proxy metrics explain
system behavior and can guide LLM reasoning when the direct metric is missing or
too noisy.

## Cookbook

### I Have p99 Latency

```json
{
  "optimization_metric": "latency_p99",
  "optimization_goal": "minimize"
}
```

Use this for TPCC or any target parser that exposes tail latency in
milliseconds.

### I Have Throughput

```json
{
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

Use this for `sysbench_cpu` and throughput-oriented targets.

### I Do Not Have Application Metrics

Use an LLM prompt mode with additional system metrics:

```json
{
  "tuner_type": "llm",
  "llm_prompt_mode": "indirect_all_signature",
  "llm_additional_metrics": [
    "instructions_per_cycle",
    "cache_misses",
    "cpu_load_cores_pct",
    "power_socket0_watts"
  ]
}
```

This gives the model a system signature to reason over. It does not magically
turn one proxy into a universal objective.

### I Use Bayesian, MLOS, Q-learning, Or DQN

Pick one scalar `optimization_metric` carefully. These tuners optimize the
number you give them. If you use a proxy such as IPC, then SemaTune optimizes
IPC, not hidden p99 latency.

### I Use LLM

Use the direct metric as the objective when available, and add proxy metrics as
supporting context:

```json
{
  "optimization_metric": "latency_p99",
  "optimization_goal": "minimize",
  "llm_prompt_mode": "full_metrics",
  "llm_additional_metrics": [
    "instructions_per_cycle",
    "cache_misses",
    "cpu_load_cores_pct"
  ]
}
```

### My Metric Is Missing

Check the path in this order:

1. Target parser output.
2. `BenchmarkMetrics.extra_metrics`.
3. `optimization_history_*.json`.
4. `llm_api_logs/llm_responses.jsonl` and full prompt logs.

Useful commands:

```bash
jq '.history[0].metrics' results/<run>/optimization_history_*.json
jq '.history[] | {iteration, metric: .metrics.latency_p99}' results/<run>/optimization_history_*.json
```

If the metric never appears in history, fix the target parser before changing
the tuner.

## Direct Metrics

A direct metric comes from the target application or load generator and is the
quantity the run is trying to improve.

Common direct metrics include:

- p99 or p95 latency
- average latency
- throughput
- goodput
- error rate
- deadline misses

When a direct metric is available and reliable, use it as the primary objective.

## Proxy Metrics

A proxy metric is not the final application objective, but it can describe the
system state that explains or predicts application behavior.

Examples include:

- instructions per cycle
- cycles, instructions, cache misses, and branch misses
- CPU utilization and run queue behavior
- I/O wait and context switches
- power or RAPL readings
- scheduler, CPU-frequency, networking, or memory pressure signals

No single proxy is portable across every target. Treat proxy metrics as
evidence, not as a universal replacement for the application objective.

## Prompt Modes For Proxy Metrics

| Mode | Primary metric visible? | Proxy metric use |
| --- | --- | --- |
| `default` | Yes | Minimal extra context unless configured. |
| `full_metrics` | Yes | Adds proxy metrics as supporting evidence. |
| `full_metrics_signature` | Yes | Adds explicit metric-signature comparison. |
| `indirect_recent` | No | Uses recent proxy metrics only. |
| `indirect_all_plain` | No | Uses all proxy history without signature wording. |
| `indirect_all_signature` | No | Uses all proxy history with signature comparison. |

See [LLM Prompt Modes](llm-prompt-modes.md) for canonical examples.

## Metric Dictionary For Included Targets

| Target | Metric names | Units | Source |
| --- | --- | --- | --- |
| `sysbench_cpu` | `throughput`, `goodput` | events/sec | Sysbench interval stream or final summary. |
| `sysbench_cpu` | `latency_p99`, `latency_p95`, `reported_latency_ms_avg` | ms | Sysbench interval stream. |
| `sysbench_cpu` | `events_total`, `interval_count`, `total_time_s` | count/sec | Parsed sysbench intervals. |
| `sysbench_cpu` | `instructions_per_cycle`, `cycles`, `instructions`, `cache_misses`, `branch_miss_rate_pct` | counters/ratios | `perf stat` when available. |
| `tpcc` | `latency_p99`, `latency_p95`, `latency_avg` | ms | BenchBase summary JSON. |
| `tpcc` | `throughput`, `goodput` | tx/s | BenchBase summary JSON. |
| `tpcc` | `measured_requests`, `duration_seconds` | count/sec | BenchBase summary JSON. |
| both | `power_socket0_watts`, `power_ram_watts` | watts | RAPL/powercap when available. |
| both | `cstate_poll_pct`, `cstate_c1_pct`, `cstate_c1e_pct`, `cstate_c6_pct` | percent | cpuidle sysfs when available. |
| both | `cpu_load_cores_pct`, `cpu_load_socket0_pct` | percent | Host sampling in SemaTune. |

For LLM runs, the exact metrics shown to the model are visible in
`<results_dir>/llm_api_logs/`. Review those logs before sharing results.
