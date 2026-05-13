# Configuration Reference

SemaTune configs are JSON files loaded by `SimpleConfig`. Unknown fields fail
fast so a typo does not silently change a tuning session. The field name
`benchmark` is kept for compatibility with the current CLI; in these docs,
think of it as the target adapter name.

Required practical fields:

- `benchmark`: `sysbench_cpu` or `tpcc`
- `tuner_type`: `fixed`, `llm`, `bayesian`, `mlos`, `qlearning`, or `dqn`
- `parameter_ranges`: tunable parameter search space
- `optimization_metric`: metric to optimize
- `optimization_goal`: `maximize` or `minimize`
- `max_iterations`, `window_duration`, `results_dir`

## Common Run Fields

| Field | Meaning |
| --- | --- |
| `benchmark` | Target adapter name. The maintained examples are `sysbench_cpu` and `tpcc`. |
| `pin_to_cores` | CPU list passed to `taskset`, for example `0-3`. |
| `results_dir` | Directory where history, window outputs, target logs, and LLM logs are written. |
| `use_perf_stat` | Whether to collect `perf stat` metrics when available. |

## `sysbench_cpu` Fields

These fields apply only when `benchmark` is `sysbench_cpu`.

| Field | Meaning |
| --- | --- |
| `sysbench_threads` | Sysbench CPU worker thread count. |
| `sysbench_rate` | Optional sysbench event rate limit. |
| `sysbench_cpu_max_prime` | Sysbench CPU prime limit. |
| `sysbench_interval_reporting` | Keep `sysbench_cpu` running as one live `--report-interval` process. Default is `true`. |
| `sysbench_report_interval` | Seconds between live sysbench interval reports. Default is `1`. |
| `sysbench_continuous_duration` | Maximum lifetime for the live sysbench process. Increase for long LLM runs. Default is `3600`. |

## TPCC / BenchBase Fields

These fields apply only when `benchmark` is `tpcc`.

| Field | Meaning |
| --- | --- |
| `benchbase_jar_path` | Path to the built BenchBase PostgreSQL jar. |
| `benchbase_config_file` | TPCC XML template used to create per-window configs. |
| `benchbase_timeout_buffer_seconds` | Extra seconds added to BenchBase process timeouts. |
| `benchbase_timeout_retries` | Retry count after a BenchBase timeout. |

## Tuning Fields

| Field | Meaning |
| --- | --- |
| `tuner_type` | Tuner implementation: `fixed`, `llm`, `bayesian`, `mlos`, `qlearning`, or `dqn`. |
| `parameter_ranges` | Search space. Numeric ranges are two-number arrays; categorical ranges are value arrays. |
| `parameter_types` | Optional explicit type hints. Usually leave unset and use metadata defaults. |
| `parameters_to_tune` | Optional subset of `parameter_ranges`; omitted means tune all listed ranges. |
| `fixed_parameters` | Parameters applied before the run and kept constant unless trimming eliminates another parameter. |
| `optimization_metric` | Metric read from `BenchmarkMetrics`, for example direct metrics like `throughput` or `latency_p99`, or a proxy metric when that is the chosen objective. |
| `optimization_goal` | `maximize` or `minimize`. |
| `max_iterations` | Number of tuning windows. |
| `post_tuning_windows` | Extra windows after tuning using the final parameter set. |
| `window_duration` | Measurement window duration in seconds. |
| `continuous_apply` | Re-apply parameters during a window for in-window modes. |
| `tuning_mode` | `outside-of-window` or `in-window`. Default is `outside-of-window`: tune after a measured window, then apply before the next measured window. |
| `constraint_metric` | Optional metric that must satisfy a constraint. |
| `constraint_threshold` | Constraint threshold. |
| `constraint_direction` | `less_than` or `greater_than`. |
| `constraint_penalty` | Compatibility field retained for older configs. Current scoring ignores this value and uses a fixed 10x multiplicative penalty when a constraint is violated. |
| `workload_change_type` | Experimental workload-change label for internal scenarios. |
| `workload_change_interval` | Experimental workload-change cadence. |
| `workload_change_param` | Experimental workload-change parameter. |

## LLM Fields

Users must provide their own API keys. Do not put keys in JSON configs that may
be committed or shared.

| Field | Meaning |
| --- | --- |
| `llm_provider` | `auto`, `gemini`, or `openrouter`. In `auto`, `gemini-*` model names use Gemini and other names use OpenRouter. |
| `llm_loop` | `single` or `dual`. Dual loop requires `tuner_type: llm`. |
| `llm_model_name` | Single-loop model name, or Actor fallback model. |
| `llm_secondary_model` | Speculator fallback model. |
| `llm_actor_model` | Required Actor model for `llm_loop: dual`. |
| `llm_speculator_model` | Required Speculator model for `llm_loop: dual`. |
| `llm_prompt_mode` | Public prompt recipe: `default`, `full_metrics`, `full_metrics_signature`, `indirect_recent`, `indirect_all_plain`, or `indirect_all_signature`. |
| `llm_additional_metrics` | Extra metrics shown to the LLM. Required by non-default prompt modes. |
| `llm_actor_additional_metrics` | Actor-specific extra metrics for dual-loop runs. |
| `llm_speculator_additional_metrics` | Speculator-specific extra metrics for dual-loop runs. |
| `include_param_descriptions` | Include OS parameter descriptions in the prompt. Default is `true`. |
| `workload_description` | Short workload context appended to the default prompt. |
| `llm_prompt_extra_instructions` | Extra prompt text appended after the default strategy. |
| `llm_prompt_extra_instructions_file` | File containing extra prompt text, read relative to the run working directory. |
| `llm_temperature` | Sampling temperature for LLM calls. |
| `llm_thinking_level` | Optional Gemini thinking level for models that support it. |
| `llm_thinking_budget` | Optional Gemini thinking token budget. |
| `llm_actor_thinking_level` | Actor-specific Gemini thinking level for dual-loop runs. |
| `llm_actor_thinking_budget` | Actor-specific Gemini thinking budget for dual-loop runs. |
| `llm_speculator_thinking_level` | Speculator-specific Gemini thinking level for dual-loop runs. |
| `llm_speculator_thinking_budget` | Speculator-specific Gemini thinking budget for dual-loop runs. |
| `llm_request_max_retries` | Retry attempts for LLM request failures. |
| `llm_request_retry_backoff_sec` | Sleep between LLM request retries. |
| `llm_replay_file` | Replay prior LLM responses from history instead of calling an API. |
| `llm_api_log_enabled` | Write exact LLM request/response logs. Default is `true`. |
| `llm_api_log_dir` | Override directory for LLM API logs. By default logs go to `<results_dir>/llm_api_logs/`. |
| `llm_speculator_hide_primary_metric` | Hide the primary metric from the Speculator in dual-loop runs. |
| `llm_speculator_aggregation_interval_s` | Aggregate Speculator-visible metrics over a recent time interval. |
| `previous_run_gist` | Prior-run summary injected into the prompt. |
| `llm_api_key` | Backward-compatible Gemini key field. Prefer `GEMINI_API_KEY`. |
| `openrouter_api_key` | Backward-compatible OpenRouter key field. Prefer `OPENROUTER_API_KEY`. |

Legacy prompt flags remain accepted for old private configs but new examples
should prefer `llm_prompt_mode`:

| Legacy Field | Meaning |
| --- | --- |
| `use_indirect_optimization` | Hide the primary metric and steer from additional metrics. |
| `llm_indirect_history_show_all_metrics` | Show additional metrics for all history entries instead of only recent ones. |
| `llm_indirect_prompt_style` | Internal indirect prompt style, usually `signature_compare` or `all_metrics_plain`. |
| `omit_explicit_pairwise_comparison_instruction` | Internal mode-2 compatibility flag. |
| `llm_full_metrics_prompt_mode` | Internal flag for full-metrics prompt mode. |
| `llm_full_metrics_explicit_signature_compare` | Internal flag for signature-comparison wording. |

## Trimming Fields

LLM trimming is a supported single-loop LLM feature. It is shipped in the repo
but disabled unless the config opts in.

| Field | Meaning |
| --- | --- |
| `trimming_enabled` | Enable an initial LLM search-space trimming phase. |
| `trimming_cycles` | Number of trimming cycles before the primary tuner starts. |
| `trimming_model_name` | Optional model override for the trimming phase. |
| `trimming_strategy` | Strategy label for the trimming run. Public examples use `single_loop`. |
| `trimming_suggest_params` | Whether the trimming LLM also suggests parameter values during trimming. |

## Optional Tuner Fields

| Field | Meaning |
| --- | --- |
| `bayesian_n_trials` | SMAC trial budget for the Bayesian tuner. |
| `bayesian_seed` | Bayesian tuner random seed. |
| `mlos_max_trials` | Trial budget for the MLOS tuner. |
| `mlos_n_random_init` | Initial random suggestions for MLOS. |
| `mlos_max_ratio` | Optional MLOS budget ratio. |
| `mlos_use_default_config` | Ask MLOS to seed with default config when supported. |
| `mlos_n_random_probability` | Probability of random MLOS suggestions after initialization. |
| `mlos_seed` | MLOS random seed. |
| `mlos_run_name` | Optional MLOS run name. |
| `mlos_output_directory` | Optional MLOS output directory. |
| `mlos_objective_weights` | Optional weighted multi-objective config for MLOS. |
| `qlearning_grid_points` | Discretization points per numeric parameter. |
| `qlearning_max_actions` | Maximum allowed discrete action count. |
| `qlearning_learning_rate` | Tabular Q-learning update rate. |
| `qlearning_epsilon_start` | Initial exploration probability. |
| `qlearning_epsilon_end` | Minimum exploration probability. |
| `qlearning_epsilon_decay` | Exploration decay multiplier. |
| `qlearning_gamma` | Discount factor. |
| `qlearning_seed` | Q-learning random seed. |
| `dqn_grid_points` | DQN discretization points per numeric parameter. |
| `dqn_max_actions` | Maximum allowed DQN action count. |
| `dqn_learning_rate` | DQN optimizer learning rate. |
| `dqn_epsilon_start` | Initial DQN exploration probability. |
| `dqn_epsilon_end` | Minimum DQN exploration probability. |
| `dqn_epsilon_decay` | DQN exploration decay multiplier. |
| `dqn_batch_size` | Replay batch size. |
| `dqn_memory_size` | Replay memory capacity. |
| `dqn_target_update_freq` | Target-network update interval. |
| `dqn_hidden_size` | Hidden layer width. |
| `dqn_gamma` | Discount factor. |
| `dqn_seed` | DQN random seed. |
