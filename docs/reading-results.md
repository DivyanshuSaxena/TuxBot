# Reading Results

This page answers two questions:

- Did the run work?
- What did SemaTune actually change?

The snippets below use sanitized real-shape examples. Paths use
`results/<run>/...` instead of machine-specific absolute paths.

## Optimization History Entry

```json
{
  "iteration": 1,
  "parameters": {
    "min_granularity_ns": 3000000
  },
  "metrics": {
    "throughput": 1481.85,
    "goodput": 1481.85,
    "latency_p99": 2.79,
    "interval_reporting": true,
    "intervals_file": "results/sysbench_cpu_fixed/sysbench_cpu_windows/window_1/sysbench_intervals.json",
    "continuous_log_file": "results/sysbench_cpu_fixed/sysbench_cpu_windows/continuous_sysbench.log",
    "instructions_per_cycle": 0.42
  },
  "reward": 1481.85,
  "constraint_violated": false,
  "post_tuning_phase": false,
  "tuner_timing": {
    "parameters_applied": true,
    "target_iteration": 2,
    "justification": null,
    "token_metrics": null
  }
}
```

The top-level file also includes `best_parameters`, `best_reward`, `iterations`,
`total_time`, `timestamp`, and `terminated_reason`.

## LLM Response Index Entry

```json
{
  "iteration": 2,
  "agent": "single",
  "provider": "gemini",
  "model": "gemma-4-31b-it",
  "log_file": "results/sysbench_cpu_llm/llm_api_logs/llm_api_iter0002_single_20260512_183912_877.txt",
  "response_text": "Analysis: ...\nConfig: {\"min_granularity_ns\": 10000000, \"converged\": false}",
  "response_parsed": {
    "min_granularity_ns": 10000000,
    "converged": false
  },
  "request_config": {
    "temperature": 0.2,
    "thinking_config": {
      "thinking_level": "HIGH"
    }
  }
}
```

If `response_parsed` is `null`, inspect the full log file. The model may have
returned text that was usable by fallback parsing but not recorded as structured
JSON in the compact index.

## Sysbench Interval File

```json
{
  "window_number": 1,
  "window_duration": 10,
  "report_interval": 1,
  "continuous_log_file": "results/sysbench_cpu_fixed/sysbench_cpu_windows/continuous_sysbench.log",
  "intervals": [
    {
      "elapsed_s": 1,
      "threads": 4,
      "events_per_second": 1482.31,
      "latency_percentile": 99,
      "latency_ms": 2.79,
      "latency_p99_ms": 2.79
    }
  ],
  "metrics": {
    "throughput": 1481.85,
    "events_total": 14818,
    "interval_count": 10
  }
}
```

## TPCC Window Output

BenchBase windows write a summary JSON plus CSVs:

```json
{
  "Throughput (requests/second)": 214.86,
  "Goodput (requests/second)": 214.03,
  "Measured Requests": 6446,
  "Latency Distribution": {
    "Average Latency (microseconds)": 74268.0,
    "95th Percentile Latency (microseconds)": 276111.0,
    "99th Percentile Latency (microseconds)": 597266.0
  }
}
```

SemaTune converts latency values to milliseconds in optimization history:
`latency_p99: 597.266`.

## Useful `jq` Commands

Best reward:

```bash
jq '{best_reward, best_parameters, terminated_reason}' \
  results/<run>/optimization_history_*.json
```

Final parameters:

```bash
jq '.history[-1].parameters' results/<run>/optimization_history_*.json
```

Parameter trajectory:

```bash
jq '.history[] | {iteration, parameters}' results/<run>/optimization_history_*.json
```

Metrics and rewards:

```bash
jq '.history[] | {iteration, reward, post_tuning_phase, metrics}' \
  results/<run>/optimization_history_*.json
```

Failed or rejected proposals:

```bash
jq '.history[] | select(.tuner_timing.apply_failed == true or .tuner_request_skipped == true)' \
  results/<run>/optimization_history_*.json
```

LLM justifications:

```bash
jq '.history[] | select(.llm_justification) |
  {iteration, llm_justification, parameters}' \
  results/<run>/optimization_history_*.json
```

Token usage:

```bash
jq '.history[] | select(.token_metrics) |
  {iteration, token_metrics}' \
  results/<run>/optimization_history_*.json
```

Post-tuning windows only:

```bash
jq '.history[] | select(.post_tuning_phase == true) |
  {iteration, reward, parameters, metrics}' \
  results/<run>/optimization_history_*.json
```

Compact LLM response stream:

```bash
jq '{iteration, agent, provider, model, response_text}' \
  results/<run>/llm_api_logs/llm_responses.jsonl
```

## Success Checklist

A successful run should have:

- one `optimization_history_*.json`
- one history entry per measured tuning or post-tuning window
- non-null value for the configured `optimization_metric`
- target-specific window outputs
- `llm_api_logs/llm_responses.jsonl` for live LLM runs
- `terminated_reason` that matches how the run ended
