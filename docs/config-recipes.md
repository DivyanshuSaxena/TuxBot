# Configuration Recipes

This page shows minimal working shapes. Each snippet omits optional fields so
you can see the idea quickly. Use [Configuration Reference](configuration.md)
for the full field list.

The config field is still named `benchmark` for compatibility. In SemaTune docs,
read it as the target adapter name.

## Minimal Fixed `sysbench_cpu`

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "fixed",
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "fixed_parameters": {
    "min_granularity_ns": 3000000
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize",
  "max_iterations": 3,
  "window_duration": 10,
  "pin_to_cores": "0-3",
  "results_dir": "results/sysbench_cpu_fixed"
}
```

Canonical file: `config/examples/sysbench_cpu_fixed.json`.

## Minimal Single-Loop LLM `sysbench_cpu`

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "llm",
  "llm_provider": "gemini",
  "llm_loop": "single",
  "llm_model_name": "gemini-2.5-flash",
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize",
  "max_iterations": 3,
  "window_duration": 10,
  "results_dir": "results/sysbench_cpu_llm_single"
}
```

Run with your own `GEMINI_API_KEY`. Canonical file:
`config/examples/sysbench_cpu_llm_single.json`.

## Minimal OpenRouter LLM Run

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "llm",
  "llm_provider": "openrouter",
  "llm_model_name": "openai/gpt-4o-mini",
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize",
  "max_iterations": 3,
  "window_duration": 10,
  "results_dir": "results/sysbench_cpu_llm_openrouter"
}
```

Run with your own `OPENROUTER_API_KEY`. Canonical file:
`config/examples/sysbench_cpu_llm_openrouter.json`.

## Minimal TPCC Fixed Run

```json
{
  "benchmark": "tpcc",
  "tuner_type": "fixed",
  "benchbase_jar_path": "deps/benchbase/target/benchbase-postgres/benchbase.jar",
  "benchbase_config_file": "config/benchbase/postgres/tpcc.xml",
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "latency_p99",
  "optimization_goal": "minimize",
  "max_iterations": 3,
  "window_duration": 30,
  "results_dir": "results/tpcc_fixed"
}
```

Canonical file: `config/examples/tpcc_fixed.json`.

## Minimal TPCC LLM Run

```json
{
  "benchmark": "tpcc",
  "tuner_type": "llm",
  "llm_provider": "gemini",
  "llm_model_name": "gemini-2.5-flash",
  "benchbase_jar_path": "deps/benchbase/target/benchbase-postgres/benchbase.jar",
  "benchbase_config_file": "config/benchbase/postgres/tpcc.xml",
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "latency_p99",
  "optimization_goal": "minimize",
  "max_iterations": 3,
  "window_duration": 30,
  "results_dir": "results/tpcc_llm_single"
}
```

Canonical file: `config/examples/tpcc_llm_single.json`.

## Optional Tuners

Bayesian:

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "bayesian",
  "bayesian_n_trials": 20,
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

MLOS:

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "mlos",
  "mlos_max_trials": 20,
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

Q-learning:

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "qlearning",
  "qlearning_grid_points": 8,
  "qlearning_max_actions": 1000,
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

DQN:

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "dqn",
  "dqn_grid_points": 8,
  "dqn_max_actions": 1000,
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

Install optional dependencies with `pip install -e ".[tuners]"`, or install
only the relevant extra.

## Indirect/Proxy-Metric LLM Config

```json
{
  "benchmark": "tpcc",
  "tuner_type": "llm",
  "llm_prompt_mode": "indirect_all_signature",
  "llm_additional_metrics": [
    "instructions_per_cycle",
    "cache_misses",
    "cpu_load_cores_pct",
    "power_socket0_watts"
  ],
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "latency_p99",
  "optimization_goal": "minimize"
}
```

See `config/examples/tpcc_llm_8param_indirect_all_signature.json`.

## Dual-Loop LLM Config

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "llm",
  "llm_loop": "dual",
  "llm_provider": "gemini",
  "llm_speculator_model": "gemma-4-26b-a4b-it",
  "llm_speculator_thinking_level": "MINIMAL",
  "llm_actor_model": "gemma-4-31b-it",
  "llm_actor_thinking_level": "HIGH",
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

See `config/examples/sysbench_cpu_llm_dual_gemma4.json`.

## Trimming Config

```json
{
  "benchmark": "tpcc",
  "tuner_type": "llm",
  "llm_loop": "single",
  "trimming_enabled": true,
  "trimming_cycles": 5,
  "trimming_model_name": "gemini-2.5-flash",
  "trimming_suggest_params": true,
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000],
    "latency_ns": [6000000, 48000000]
  },
  "optimization_metric": "latency_p99",
  "optimization_goal": "minimize"
}
```

See `config/examples/tpcc_llm_8param_trimming_gemini.json`.

## Long LLM `sysbench_cpu` Run

Use a longer continuous process duration so one live sysbench process outlives
LLM latency and all post-tuning windows:

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "llm",
  "sysbench_interval_reporting": true,
  "sysbench_report_interval": 1,
  "sysbench_continuous_duration": 3600,
  "max_iterations": 20,
  "post_tuning_windows": 10,
  "window_duration": 10,
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize"
}
```

## No-API LLM Replay Config

Replay exercises LLM parsing and optimizer plumbing without contacting Gemini or
OpenRouter:

```json
{
  "benchmark": "sysbench_cpu",
  "tuner_type": "llm",
  "llm_replay_file": "config/replay/sysbench_cpu_llm_replay_history.json",
  "parameter_ranges": {
    "min_granularity_ns": [1000000, 10000000]
  },
  "optimization_metric": "throughput",
  "optimization_goal": "maximize",
  "max_iterations": 2,
  "post_tuning_windows": 1,
  "window_duration": 5,
  "results_dir": "results/sysbench_cpu_llm_replay"
}
```

Canonical file: `config/examples/sysbench_cpu_llm_replay.json`.
