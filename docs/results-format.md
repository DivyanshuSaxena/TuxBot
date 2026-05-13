# Results Format

Each SemaTune run writes into `results_dir`. Treat the directory as an audit
trail for the control loop: the target output, per-window metrics, tuner
response, accepted parameter values, and LLM prompts or responses when used.

Important files:

- `optimization_history_<benchmark>_<timestamp>.json`: full optimization history
- `window_<n>_metrics.json`: system metrics per window when collected
- target-specific window output directories

For LLM runs:

- `llm_api_logs/llm_responses.jsonl`: one compact record per LLM response,
  including model, agent, parsed response, response text, and a pointer to the
  full log file
- `llm_api_logs/llm_api_iter<iteration>_<agent>_<timestamp>.txt`: exact prompt,
  generation config, response text, parsed response, and raw SDK representation

For `sysbench_cpu` runs:

- `sysbench_cpu_windows/continuous_sysbench.log`: the live
  `sysbench --report-interval` stream for the whole run
- `sysbench_cpu_windows/window_<n>/sysbench_intervals.json`: parsed interval
  reports and the per-window aggregate used by the optimizer
- `sysbench_cpu_windows/window_<n>/sysbench_interval.log`: raw interval lines
  captured for that window

The optimizer no longer writes `run_metadata.json`; it also does not capture git
diffs or dirty status. Keep experiment notes outside the result directory when
you need lab-book metadata.

Use [Reading Results](reading-results.md) for example JSON snippets and `jq`
commands.
