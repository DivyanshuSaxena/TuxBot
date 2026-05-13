# LLM Prompt Modes

Use `llm_prompt_mode` in shared configs. Non-default modes require
`llm_additional_metrics` or per-agent additional metrics.

| Mode | Meaning | Example |
| --- | --- | --- |
| `default` | Original primary-metric prompt and strategy text. | `tpcc_llm_8param_default_gemini.json` |
| `full_metrics` | Primary metric remains the objective; extra metrics are supporting evidence. | `tpcc_llm_8param_full_metrics.json` |
| `full_metrics_signature` | Full-metrics mode plus explicit metric-signature comparison. | `tpcc_llm_8param_full_metrics_signature.json` |
| `indirect_recent` | Primary metric is hidden/noisy; only recent entries show extra metrics. | `tpcc_llm_8param_indirect_recent.json` |
| `indirect_all_plain` | Primary metric is hidden/noisy; all history shows extra metrics without signature-comparison wording. | `tpcc_llm_8param_indirect_all_plain.json` |
| `indirect_all_signature` | Primary metric is hidden/noisy; all history shows extra metrics with signature-comparison wording. | `tpcc_llm_8param_indirect_all_signature.json` |

## Default Mode

`default` is the best first mode. It shows the primary optimization metric,
active parameter set, parameter descriptions, current configuration, and recent
history.

The default prompt includes OS parameter descriptions. Set
`include_param_descriptions: false` only when you intentionally want a shorter
prompt.

## Full-Metrics Modes

Use `full_metrics` when the direct objective is available but you want the LLM
to see supporting system signals:

```json
{
  "llm_prompt_mode": "full_metrics",
  "optimization_metric": "latency_p99",
  "optimization_goal": "minimize",
  "llm_additional_metrics": ["instructions_per_cycle", "cache_misses"]
}
```

Use `full_metrics_signature` when you want stronger wording around comparing
metric signatures across configurations.

## Indirect Modes

Use indirect modes when the application metric is unavailable, hidden, or too
noisy for direct prompting. The LLM reasons from additional system metrics.

```json
{
  "llm_prompt_mode": "indirect_all_signature",
  "llm_additional_metrics": [
    "instructions_per_cycle",
    "cache_misses",
    "cpu_load_cores_pct",
    "power_socket0_watts"
  ]
}
```

Indirect modes are LLM-only. Classical tuners still need one scalar
`optimization_metric`.

## Where To Inspect Prompt Shape

After a run, inspect:

```text
<results_dir>/llm_api_logs/llm_api_iter<iteration>_<agent>_<timestamp>.txt
```

That file shows the exact prompt and request config for the call.
