#!/usr/bin/env python3
"""Configuration model for the open-source v1 optimizer."""

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union


ParameterRange = Union[Tuple[int, int], Tuple[float, float], List[Union[int, str, bool]]]


@dataclass
class SimpleConfig:
    """Small, explicit config surface for sysbench_cpu and TPCC runs."""

    benchmark: str = "sysbench_cpu"
    pin_to_cores: Optional[str] = None

    # Sysbench CPU
    sysbench_threads: int = 16
    sysbench_rate: Optional[int] = None
    sysbench_cpu_max_prime: Optional[int] = 20000
    sysbench_interval_reporting: bool = True
    sysbench_report_interval: int = 1
    sysbench_continuous_duration: int = 3600
    sysbench_host: str = "127.0.0.1"
    sysbench_port: int = 5432
    sysbench_user: str = "admin"
    sysbench_password: str = ""
    sysbench_db: str = "benchdb"
    sysbench_tables: int = 4
    sysbench_table_size: int = 100000

    # RocksDB db_bench
    db_bench_binary: str = "~/rocksdb/db_bench"
    db_bench_db: str = "/mydata/rocksdb"
    db_bench_benchmarks: Optional[str] = None
    db_bench_merge_operator: Optional[str] = None
    db_bench_threads: int = 32
    db_bench_cache_size: int = 1048576
    db_bench_report_interval: int = 1

    # GAPBS graph kernels
    gapbs_dir: str = "~/gapbs"
    gapbs_kernel: Optional[str] = None
    gapbs_scale: int = 27
    gapbs_iterations: int = 1
    gapbs_trials: int = 100000
    gapbs_source: int = -1
    gapbs_tolerance: Optional[float] = None
    gapbs_graph_file: str = ""

    # Memcached + mutilate
    memcached_binary: str = "memcached"
    memcached_cpus: Optional[str] = None
    memcached_threads: int = 4
    memcached_memory_mb: int = 8192
    memcached_port: int = 11211
    mutilate_client_host: str = "node1"
    mutilate_binary: str = "~/mutilate/mutilate"
    mutilate_server_ip: str = "10.10.1.1"
    mutilate_qps: int = 0
    mutilate_threads: Optional[int] = None
    mutilate_connections: int = 8
    mutilate_depth: int = 1
    mutilate_keysize: str = "fb_key"
    mutilate_valuesize: str = "fb_value"
    mutilate_iadist: str = "fb_ia"
    mutilate_update: float = 0.0
    mutilate_records: int = 1000000
    # A load step: from window load_switch_window on, mutilate offers
    # mutilate_qps_after instead of mutilate_qps. None keeps one load.
    mutilate_qps_after: Optional[int] = None
    load_switch_window: Optional[int] = None

    # Redis + YCSB
    redis_binary: str = "redis-server"
    redis_cpus: Optional[str] = None
    redis_io_threads: int = 8
    redis_port: int = 6379
    ycsb_client_host: str = "node1"
    ycsb_home: str = "~/YCSB"
    ycsb_server_ip: str = "10.10.1.1"
    ycsb_workload: str = "~/workloads/ycsb/workloada"
    ycsb_target: int = 0
    ycsb_threads: int = 64
    ycsb_load_threads: int = 16
    ycsb_records: int = 1000000
    ycsb_properties: Optional[Dict[str, Any]] = None
    ycsb_hdr_dir: str = "/tmp/ycsb_hdr"

    # BenchBase TPCC
    benchbase_jar_path: str = "deps/benchbase/target/benchbase-postgres/benchbase.jar"
    benchbase_config_file: str = "config/benchbase/postgres/tpcc.xml"
    benchbase_timeout_buffer_seconds: int = 40
    benchbase_timeout_retries: int = 1

    # Tuning
    tuner_type: str = "fixed"
    llm_loop: str = "single"
    parameter_ranges: Dict[str, ParameterRange] = field(
        default_factory=lambda: {"min_granularity_ns": (100000, 50000000)}
    )
    parameter_types: Optional[Dict[str, str]] = None
    parameters_to_tune: Optional[List[str]] = None
    fixed_parameters: Dict[str, Any] = field(default_factory=dict)

    # Run length and objective
    optimization_metric: str = "throughput"
    optimization_goal: str = "maximize"
    max_iterations: int = 3
    post_tuning_windows: int = 0
    window_duration: int = 10
    settle_seconds: int = 0
    # Run length in windows, overriding max_iterations + post_tuning_windows,
    # so a run can outlast a retune it may or may not start.
    total_windows: Optional[int] = None
    # retune_after_windows consecutive post-tuning windows in which the
    # guardrail's check failed start a fresh tuning phase of retune_iterations
    # (default max_iterations).
    retune_on_guardrail: bool = False
    retune_after_windows: int = 2
    retune_iterations: Optional[int] = None
    continuous_apply: bool = False
    tuning_mode: str = "outside-of-window"
    results_dir: str = "results"

    # Optional constraints
    constraint_metric: Optional[str] = None
    constraint_threshold: Optional[float] = None
    constraint_direction: str = "less_than"
    constraint_penalty: float = 10.0

    # LLM tuner
    llm_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    # Base URL for the OpenAI-compatible backend. None means OpenRouter's own
    # endpoint, which is the upstream default. Point it at any OpenAI-protocol
    # server to use a different provider -- a LiteLLM proxy fronting Bedrock,
    # vLLM, or a local model -- without the tuner needing to know the
    # difference. Also readable from LLM_BASE_URL / OPENAI_BASE_URL.
    llm_base_url: Optional[str] = None
    llm_provider: str = "auto"
    llm_model_name: str = "gemini-2.5-flash"
    llm_secondary_model: str = "gemini-2.5-flash-lite"
    llm_actor_model: Optional[str] = None
    llm_speculator_model: Optional[str] = None
    llm_prompt_mode: str = "default"
    llm_replay_file: Optional[str] = None
    llm_temperature: float = 0.2
    llm_thinking_level: Optional[str] = None
    llm_thinking_budget: Optional[int] = None
    llm_actor_thinking_level: Optional[str] = None
    llm_actor_thinking_budget: Optional[int] = None
    llm_speculator_thinking_level: Optional[str] = None
    llm_speculator_thinking_budget: Optional[int] = None
    llm_request_max_retries: int = 3
    llm_request_retry_backoff_sec: float = 1.0
    llm_api_log_enabled: bool = True
    llm_api_log_dir: Optional[str] = None
    workload_description: Optional[str] = None
    # What the attached guardrail watches and does, for the LLM prompt's
    # GUARDRAILS section; None keeps the NUMA monitor's description.
    guardrail_description: Optional[str] = None
    llm_additional_metrics: Optional[List[str]] = None
    llm_actor_additional_metrics: Optional[List[str]] = None
    llm_speculator_additional_metrics: Optional[List[str]] = None
    include_param_descriptions: bool = True
    llm_prompt_extra_instructions: Optional[str] = None
    llm_prompt_extra_instructions_file: Optional[str] = None
    llm_speculator_hide_primary_metric: bool = False
    llm_speculator_aggregation_interval_s: Optional[float] = None
    use_indirect_optimization: bool = False
    llm_indirect_history_show_all_metrics: bool = True
    llm_indirect_prompt_style: str = "signature_compare"
    omit_explicit_pairwise_comparison_instruction: Union[bool, int] = False
    llm_full_metrics_prompt_mode: bool = False
    llm_full_metrics_explicit_signature_compare: bool = False
    previous_run_gist: Optional[str] = None

    # Bayesian tuner
    bayesian_n_trials: int = 50
    bayesian_seed: int = 42

    # Q-learning tuner
    qlearning_grid_points: int = 10
    qlearning_max_actions: int = 1000
    qlearning_learning_rate: float = 0.1
    qlearning_epsilon_start: float = 1.0
    qlearning_epsilon_end: float = 0.1
    qlearning_epsilon_decay: float = 0.995
    qlearning_gamma: float = 0.99
    qlearning_seed: Optional[int] = None

    # DQN tuner
    dqn_grid_points: int = 10
    dqn_max_actions: int = 1000
    dqn_learning_rate: float = 0.001
    dqn_epsilon_start: float = 1.0
    dqn_epsilon_end: float = 0.1
    dqn_epsilon_decay: float = 0.995
    dqn_batch_size: int = 32
    dqn_memory_size: int = 1000
    dqn_target_update_freq: int = 10
    dqn_hidden_size: int = 128
    dqn_gamma: float = 0.99
    dqn_seed: Optional[int] = None

    # MLOS tuner
    mlos_max_trials: int = 100
    mlos_n_random_init: int = 3
    mlos_max_ratio: Optional[float] = None
    mlos_use_default_config: bool = False
    mlos_n_random_probability: float = 0.1
    mlos_seed: int = 42
    mlos_run_name: Optional[str] = None
    mlos_output_directory: Optional[str] = None
    mlos_objective_weights: Optional[Dict[str, float]] = None

    # Compatibility fields used by optimizer paths; not enabled in v1 examples.
    trimming_enabled: bool = False
    trimming_cycles: int = 0
    trimming_model_name: Optional[str] = None
    trimming_strategy: str = "single_loop"
    trimming_suggest_params: bool = True
    workload_change_type: Optional[str] = None
    workload_change_interval: Optional[int] = None
    workload_change_param: Optional[str] = None
    use_perf_stat: bool = True

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["parameter_ranges"] = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.parameter_ranges.items()
        }
        return result

    def redacted_dict(self) -> Dict[str, Any]:
        result = self.to_dict()
        for key in ("llm_api_key", "openrouter_api_key"):
            if result.get(key):
                result[key] = "<redacted>"
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimpleConfig":
        known_fields = set(cls.__dataclass_fields__.keys())
        unknown = sorted(set(data) - known_fields)
        if unknown:
            raise ValueError(f"Unknown config fields: {unknown}")

        converted = dict(data)
        if "parameter_ranges" in converted:
            converted["parameter_ranges"] = cls._convert_ranges(converted["parameter_ranges"])
        return cls(**converted)

    @staticmethod
    def _convert_ranges(ranges: Dict[str, Any]) -> Dict[str, ParameterRange]:
        converted = {}
        for key, value in ranges.items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
            ):
                converted[key] = tuple(value)
            else:
                converted[key] = value
        return converted

    @classmethod
    def load(cls, file_path: str) -> "SimpleConfig":
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as handle:
            config = cls.from_dict(json.load(handle))
        config._resolve_llm_model_aliases()
        config.validate()
        return config

    def save(self, file_path: str) -> None:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2)

    def _resolve_llm_model_aliases(self) -> None:
        if self.llm_actor_model:
            self.llm_model_name = self.llm_actor_model
        if self.llm_speculator_model:
            self.llm_secondary_model = self.llm_speculator_model

    def apply_llm_prompt_mode(self) -> None:
        """Map the public prompt-mode enum to the older internal flags."""

        prompt_mode = str(self.llm_prompt_mode or "default").strip().lower()
        self.llm_prompt_mode = prompt_mode
        if prompt_mode == "default":
            return

        if prompt_mode == "full_metrics":
            self.use_indirect_optimization = False
            self.llm_full_metrics_prompt_mode = True
            self.llm_full_metrics_explicit_signature_compare = False
            return

        if prompt_mode == "full_metrics_signature":
            self.use_indirect_optimization = False
            self.llm_full_metrics_prompt_mode = True
            self.llm_full_metrics_explicit_signature_compare = True
            return

        if prompt_mode == "indirect_recent":
            self.use_indirect_optimization = True
            self.llm_indirect_history_show_all_metrics = False
            self.llm_indirect_prompt_style = "signature_compare"
            self.omit_explicit_pairwise_comparison_instruction = False
            return

        if prompt_mode == "indirect_all_plain":
            self.use_indirect_optimization = True
            self.llm_indirect_history_show_all_metrics = True
            self.llm_indirect_prompt_style = "all_metrics_plain"
            self.omit_explicit_pairwise_comparison_instruction = 2
            return

        if prompt_mode == "indirect_all_signature":
            self.use_indirect_optimization = True
            self.llm_indirect_history_show_all_metrics = True
            self.llm_indirect_prompt_style = "signature_compare"
            self.omit_explicit_pairwise_comparison_instruction = False
            return

    def validate(self) -> bool:
        from .benchmarks.benchmark_registry import BenchmarkType

        BenchmarkType.from_string(self.benchmark)

        if self.tuner_type not in {"fixed", "llm", "bayesian", "mlos", "qlearning", "dqn"}:
            raise ValueError("tuner_type must be one of: fixed, llm, bayesian, mlos, qlearning, dqn")
        if self.llm_loop not in {"single", "dual"}:
            raise ValueError("llm_loop must be 'single' or 'dual'")
        self.llm_provider = str(self.llm_provider or "auto").strip().lower()
        self.llm_prompt_mode = str(self.llm_prompt_mode or "default").strip().lower()
        if self.llm_provider not in {"auto", "gemini", "openrouter"}:
            raise ValueError("llm_provider must be one of: auto, gemini, openrouter")
        if self.llm_prompt_mode not in {
            "default",
            "full_metrics",
            "full_metrics_signature",
            "indirect_recent",
            "indirect_all_plain",
            "indirect_all_signature",
        }:
            raise ValueError(
                "llm_prompt_mode must be one of: default, full_metrics, "
                "full_metrics_signature, indirect_recent, indirect_all_plain, indirect_all_signature"
            )
        self.apply_llm_prompt_mode()
        if self.llm_prompt_mode != "default" and not (
            self.llm_additional_metrics
            or self.llm_actor_additional_metrics
            or self.llm_speculator_additional_metrics
        ):
            raise ValueError("non-default llm_prompt_mode requires llm_additional_metrics or per-agent additional metrics")
        if self.llm_loop == "dual":
            if self.tuner_type != "llm":
                raise ValueError("llm_loop='dual' requires tuner_type='llm'")
            if not self.llm_actor_model:
                raise ValueError("llm_loop='dual' requires llm_actor_model")
            if not self.llm_speculator_model:
                raise ValueError("llm_loop='dual' requires llm_speculator_model")
        if self.trimming_enabled:
            if self.tuner_type != "llm":
                raise ValueError("trimming_enabled requires tuner_type='llm'")
            if self.llm_loop != "single":
                raise ValueError("trimming_enabled is supported only for llm_loop='single' in v1")
            if self.trimming_cycles <= 0:
                raise ValueError("trimming_enabled requires trimming_cycles > 0")
        if self.optimization_goal not in {"maximize", "minimize"}:
            raise ValueError("optimization_goal must be 'maximize' or 'minimize'")
        if self.tuning_mode not in {"outside-of-window", "in-window"}:
            raise ValueError("tuning_mode must be 'outside-of-window' or 'in-window'")
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        if self.post_tuning_windows < 0:
            raise ValueError("post_tuning_windows must be non-negative")
        if self.window_duration <= 0:
            raise ValueError("window_duration must be positive")
        if self.settle_seconds < 0:
            raise ValueError("settle_seconds must be non-negative")
        if self.total_windows is not None:
            if self.total_windows < self.max_iterations + self.post_tuning_windows:
                raise ValueError("total_windows must cover max_iterations + post_tuning_windows")
            if self.tuning_mode != "outside-of-window":
                raise ValueError("total_windows needs tuning_mode 'outside-of-window'")
        if self.retune_on_guardrail:
            if self.tuning_mode != "outside-of-window":
                raise ValueError("retune_on_guardrail needs tuning_mode 'outside-of-window'")
            if self.retune_after_windows <= 0:
                raise ValueError("retune_after_windows must be positive")
            if self.retune_iterations is not None and self.retune_iterations <= 0:
                raise ValueError("retune_iterations must be positive")
        if self.sysbench_report_interval <= 0:
            raise ValueError("sysbench_report_interval must be positive")
        if self.sysbench_continuous_duration <= 0:
            raise ValueError("sysbench_continuous_duration must be positive")
        if self.benchbase_timeout_buffer_seconds < 0:
            raise ValueError("benchbase_timeout_buffer_seconds must be non-negative")
        if self.benchbase_timeout_retries < 0:
            raise ValueError("benchbase_timeout_retries must be non-negative")
        if self.llm_prompt_extra_instructions_file and not os.path.exists(self.llm_prompt_extra_instructions_file):
            raise ValueError(
                f"llm_prompt_extra_instructions_file not found: {self.llm_prompt_extra_instructions_file}"
            )

        if self.benchmark in ("db_bench", "db_bench_rwm"):
            if self.db_bench_threads <= 0:
                raise ValueError("db_bench_threads must be positive")
            if self.db_bench_report_interval <= 0:
                raise ValueError("db_bench_report_interval must be positive")
            if not self.db_bench_db:
                raise ValueError("db_bench requires db_bench_db")

        if self.benchmark in ("gapbs", "gapbs_pr"):
            if self.gapbs_scale <= 0:
                raise ValueError("gapbs_scale must be positive")
            if self.gapbs_trials <= 0:
                raise ValueError("gapbs_trials must be positive")
            if self.gapbs_iterations <= 0:
                raise ValueError("gapbs_iterations must be positive")
            if self.gapbs_source < -1:
                raise ValueError(
                    "gapbs_source must be a vertex id, or -1 for GAPBS's own "
                    "source sequence"
                )
            if self.gapbs_tolerance is not None and self.gapbs_tolerance < 0:
                raise ValueError("gapbs_tolerance must be non-negative")

        if self.benchmark == "memcached":
            if self.memcached_threads <= 0:
                raise ValueError("memcached_threads must be positive")
            if self.mutilate_qps < 0:
                raise ValueError("mutilate_qps must be non-negative (0 is mutilate's peak)")
            if self.mutilate_connections <= 0 or self.mutilate_depth <= 0:
                raise ValueError("mutilate_connections and mutilate_depth must be positive")
            if not 0.0 <= self.mutilate_update <= 1.0:
                raise ValueError("mutilate_update is a SET:GET ratio in [0, 1]")
            if (self.mutilate_qps_after is None) != (self.load_switch_window is None):
                raise ValueError("mutilate_qps_after and load_switch_window go together")
            if self.load_switch_window is not None and self.load_switch_window < 2:
                raise ValueError("load_switch_window must be 2 or later")
            if self.mutilate_qps_after is not None and self.mutilate_qps_after < 0:
                raise ValueError("mutilate_qps_after must be non-negative (0 is mutilate's peak)")
            if self.pin_to_cores:
                raise ValueError(
                    "memcached pins itself with memcached_cpus; pin_to_cores would "
                    "also rebind NIC IRQs whenever busy_poll or busy_read is set"
                )

        if self.benchmark == "ycsb_redis":
            if self.redis_io_threads <= 0:
                raise ValueError("redis_io_threads must be positive (1 is single-threaded)")
            if self.ycsb_target < 0:
                raise ValueError("ycsb_target must be non-negative (0 is unthrottled)")
            if self.ycsb_threads <= 0 or self.ycsb_load_threads <= 0:
                raise ValueError("ycsb_threads and ycsb_load_threads must be positive")
            if self.ycsb_records <= 0:
                raise ValueError("ycsb_records must be positive")
            if self.pin_to_cores:
                raise ValueError(
                    "redis pins itself with redis_cpus; pin_to_cores would "
                    "also rebind NIC IRQs whenever busy_poll or busy_read is set"
                )

        if self.benchmark == "tpcc":
            if not self.benchbase_jar_path:
                raise ValueError("tpcc requires benchbase_jar_path")
            if not self.benchbase_config_file:
                raise ValueError("tpcc requires benchbase_config_file")

        for param_name, param_range in self.parameter_ranges.items():
            if isinstance(param_range, tuple):
                if len(param_range) != 2 or param_range[0] >= param_range[1]:
                    raise ValueError(f"{param_name} range must be [min, max] with min < max")
            elif isinstance(param_range, list):
                if not param_range:
                    raise ValueError(f"{param_name} categorical range cannot be empty")
            else:
                raise ValueError(f"{param_name} range must be [min, max] or a categorical list")

        if self.parameters_to_tune is not None:
            missing = sorted(set(self.parameters_to_tune) - set(self.parameter_ranges))
            if missing:
                raise ValueError(f"parameters_to_tune contains names missing from parameter_ranges: {missing}")

        return True
