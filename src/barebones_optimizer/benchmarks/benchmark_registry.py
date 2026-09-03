#!/usr/bin/env python3
"""Registry for the v1 supported benchmark surface."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


@dataclass(frozen=True)
class BenchmarkInfo:
    """Information needed to construct a supported benchmark."""

    name: str
    script: str
    requires_setup: bool
    requires_cleanup: bool
    base_command: List[str]
    description: str = ""
    default_options: Dict[str, Any] = field(default_factory=dict)


class BenchmarkType(Enum):
    """Only the open-source v1 benchmarks are public and selectable."""

    SYSBENCH_CPU = BenchmarkInfo(
        name="sysbench_cpu",
        script="cpu",
        requires_setup=False,
        requires_cleanup=False,
        base_command=["sysbench"],
        description="Sysbench CPU prime-number workload",
        default_options={"cpu_max_prime": 20000},
    )

    DB_BENCH = BenchmarkInfo(
        name="db_bench",
        script="",
        requires_setup=False,
        requires_cleanup=False,
        base_command=["db_bench"],
        description="RocksDB db_bench against a pre-built database",
    )

    GAPBS = BenchmarkInfo(
        name="gapbs",
        script="",
        requires_setup=False,
        requires_cleanup=False,
        base_command=["bc"],
        description="GAP Benchmark Suite graph kernel over a generated graph",
    )

    GAPBS_PR = BenchmarkInfo(
        name="gapbs_pr",
        script="",
        requires_setup=False,
        requires_cleanup=False,
        base_command=["pr"],
        description="GAP Benchmark Suite PageRank over a generated graph",
    )

    TPCC = BenchmarkInfo(
        name="tpcc",
        script="",
        requires_setup=True,
        requires_cleanup=False,
        base_command=["java", "-jar", "benchbase.jar"],
        description="BenchBase TPC-C workload on PostgreSQL",
    )

    @classmethod
    def from_string(cls, name: str) -> "BenchmarkType":
        for benchmark_type in cls:
            if benchmark_type.value.name == name:
                return benchmark_type
        raise ValueError(
            f"Unsupported benchmark '{name}'. Supported v1 benchmarks: {cls.list_all()}"
        )

    @classmethod
    def list_all(cls) -> List[str]:
        return [bt.value.name for bt in cls]

    @classmethod
    def get_info(cls, name: str) -> BenchmarkInfo:
        return cls.from_string(name).value
