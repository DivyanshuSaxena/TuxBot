import json
import subprocess
from pathlib import Path

import pytest

from barebones_optimizer.benchmarks.benchbase import BenchBaseBenchmark
from barebones_optimizer.benchmarks.sysbench import SysbenchBenchmark
from barebones_optimizer.config import SimpleConfig


def test_sysbench_cpu_command_uses_configured_values(tmp_path):
    config = SimpleConfig(
        benchmark="sysbench_cpu",
        pin_to_cores="1-2",
        sysbench_threads=7,
        sysbench_cpu_max_prime=50000,
        results_dir=str(tmp_path),
    )
    benchmark = SysbenchBenchmark(config)

    assert benchmark._wrap_with_taskset(["sysbench", "cpu"]) == [
        "taskset",
        "-c",
        "1-2",
        "sysbench",
        "cpu",
    ]
    assert benchmark._build_sysbench_command(12) == [
        "sysbench",
        "cpu",
        "--cpu-max-prime=50000",
        "--threads=7",
        "--time=12",
        "--percentile=99",
        "run",
    ]

    interval_cmd = benchmark._build_sysbench_command(12, report_interval=1)
    assert "--report-interval=1" in interval_cmd


def test_sysbench_cpu_interval_parser_and_metrics(tmp_path):
    config = SimpleConfig(benchmark="sysbench_cpu", results_dir=str(tmp_path))
    benchmark = SysbenchBenchmark(config)

    interval = benchmark._parse_interval_line("[ 2s ] thds: 4 eps: 1483.92 lat (ms,99%): 2.52")
    assert interval == {
        "elapsed_s": 2,
        "threads": 4,
        "events_per_second": 1483.92,
        "latency_percentile": 99,
        "latency_ms": 2.52,
        "latency_p99_ms": 2.52,
    }

    metrics = benchmark._metrics_from_intervals([interval], duration=8)
    assert metrics.throughput == 1483.92
    assert metrics.goodput == 1483.92
    assert metrics.extra_metrics["latency_p99"] == 2.52
    assert metrics.extra_metrics["interval_count"] == 1


def test_sysbench_cpu_parser_reads_final_summary(tmp_path):
    output_dir = tmp_path / "window"
    output_dir.mkdir()
    (output_dir / "sysbench.log").write_text(
        """
CPU speed:
    events per second: 1234.56

General statistics:
    total time:                          10.0001s
    total number of events:              12345

Latency (ms):
         min:                                    1.10
         avg:                                    2.20
         max:                                    9.90
         95th percentile:                        4.40
         99th percentile:                        5.50
""",
        encoding="utf-8",
    )
    config = SimpleConfig(benchmark="sysbench_cpu", results_dir=str(tmp_path / "results"))
    benchmark = SysbenchBenchmark(config)

    metrics = benchmark.parse_results(str(output_dir))

    assert metrics.throughput == 1234.56
    assert metrics.goodput == 1234.56
    assert metrics.latency_avg == 2.20
    assert metrics.latency_p95 == 4.40
    assert metrics.extra_metrics["latency_p99"] == 5.50


def test_sysbench_pre_execute_fails_clearly_when_missing_sysbench(monkeypatch, tmp_path):
    config = SimpleConfig(benchmark="sysbench_cpu", results_dir=str(tmp_path))
    benchmark = SysbenchBenchmark(config)
    monkeypatch.setattr("barebones_optimizer.benchmarks.sysbench.shutil.which", lambda _: None)

    with pytest.raises(RuntimeError, match="sudo apt-get install -y sysbench"):
        benchmark.pre_execute()


def test_benchbase_temp_config_uses_window_duration(tmp_path):
    jar = tmp_path / "benchbase.jar"
    jar.write_text("", encoding="utf-8")
    xml = tmp_path / "tpcc.xml"
    xml.write_text(
        """<?xml version="1.0"?><parameters><works><work><time>1</time><rate>10</rate></work></works></parameters>""",
        encoding="utf-8",
    )
    config = SimpleConfig(
        benchmark="tpcc",
        benchbase_jar_path=str(jar),
        benchbase_config_file=str(xml),
        results_dir=str(tmp_path / "results"),
    )
    benchmark = BenchBaseBenchmark(config)

    temp_config = Path(benchmark._create_temp_config(window_number=1, duration=42))

    assert "<time>42</time>" in temp_config.read_text(encoding="utf-8")


def test_benchbase_preflight_fails_clearly_when_java_missing(monkeypatch, tmp_path):
    jar = tmp_path / "benchbase.jar"
    jar.write_text("", encoding="utf-8")
    xml = tmp_path / "tpcc.xml"
    xml.write_text(
        """<?xml version="1.0"?><parameters><url>jdbc:postgresql://localhost:5432/benchbase</url><username>admin</username><password>password</password><works><work><time>1</time></work></works></parameters>""",
        encoding="utf-8",
    )
    config = SimpleConfig(
        benchmark="tpcc",
        benchbase_jar_path=str(jar),
        benchbase_config_file=str(xml),
        results_dir=str(tmp_path / "results"),
    )
    benchmark = BenchBaseBenchmark(config)
    monkeypatch.setattr(
        "barebones_optimizer.benchmarks.benchbase.shutil.which",
        lambda name: None if name == "java" else f"/usr/bin/{name}",
    )

    with pytest.raises(RuntimeError, match="openjdk-21-jdk"):
        benchmark._preflight()


def test_benchbase_postgres_connectivity_error_names_setup_script(monkeypatch, tmp_path):
    jar = tmp_path / "benchbase.jar"
    jar.write_text("", encoding="utf-8")
    xml = tmp_path / "tpcc.xml"
    xml.write_text(
        """<?xml version="1.0"?><parameters><url>jdbc:postgresql://localhost:5432/benchbase</url><username>admin</username><password>password</password><works><work><time>1</time></work></works></parameters>""",
        encoding="utf-8",
    )
    config = SimpleConfig(
        benchmark="tpcc",
        benchbase_jar_path=str(jar),
        benchbase_config_file=str(xml),
        results_dir=str(tmp_path / "results"),
    )
    benchmark = BenchBaseBenchmark(config)
    monkeypatch.setattr("barebones_optimizer.benchmarks.benchbase.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "barebones_optimizer.benchmarks.benchbase.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 2, "", "connection refused"),
    )

    with pytest.raises(RuntimeError, match="scripts/setup_tpcc_postgres.sh"):
        benchmark._verify_postgres_connectivity()


def test_benchbase_parser_reads_summary_json(tmp_path):
    jar = tmp_path / "benchbase.jar"
    jar.write_text("", encoding="utf-8")
    xml = tmp_path / "tpcc.xml"
    xml.write_text(
        """<?xml version="1.0"?><parameters><works><work><time>1</time></work></works></parameters>""",
        encoding="utf-8",
    )
    config = SimpleConfig(
        benchmark="tpcc",
        benchbase_jar_path=str(jar),
        benchbase_config_file=str(xml),
        results_dir=str(tmp_path / "results"),
    )
    benchmark = BenchBaseBenchmark(config)
    output_dir = tmp_path / "benchbase-output"
    output_dir.mkdir()
    (output_dir / "tpcc.summary.json").write_text(
        json.dumps(
            {
                "Throughput (requests/second)": 100.0,
                "Goodput (requests/second)": 95.0,
                "Measured Requests": 1000,
                "Elapsed Time (nanoseconds)": 10000000000,
                "Latency Distribution": {
                    "Average Latency (microseconds)": 2000.0,
                    "95th Percentile Latency (microseconds)": 5000.0,
                    "99th Percentile Latency (microseconds)": 9000.0,
                },
            }
        ),
        encoding="utf-8",
    )

    metrics = benchmark.parse_results(str(output_dir))

    assert metrics.throughput == 100.0
    assert metrics.goodput == 95.0
    assert metrics.latency_avg == 2.0
    assert metrics.latency_p95 == 5.0
    assert metrics.extra_metrics["latency_p99"] == 9.0
