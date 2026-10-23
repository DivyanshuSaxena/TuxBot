import base64
import struct
import zlib

import pytest

from barebones_optimizer.benchmarks.ycsb_redis import (
    HEADER, HdrInterval, YcsbRedisBenchmark, decode_histogram,
    histogram_mean, histogram_percentile, window_stats,
)
from barebones_optimizer.config import SimpleConfig


def _zigzag(value):
    value = (value << 1) ^ (value >> 63)
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _encode(counts):
    """A V2 compressed histogram, lowest 1 and 3 digits as YCSB records.

    `counts` maps value -> count for values below 2048, where every value has
    its own index; that is the region a test can lay out by hand.
    """
    body = bytearray()
    index = 0
    for value in sorted(counts):
        if value > index:
            body += _zigzag(-(value - index))
        body += _zigzag(counts[value])
        index = value + 1
    payload = HEADER.pack(0x1C849313, len(body), 0, 3, 1, 3600000000, 1.0) + body
    packed = zlib.compress(bytes(payload))
    return base64.b64encode(struct.pack(">ii", 0x1C849314, len(packed)) + packed).decode()


def _interval(op, start, counts, length=1.0):
    return HdrInterval.parse(op, f"{start:.3f},{length:.3f},0.0,{_encode(counts)}")


def _ycsb(tmp_path, **overrides):
    fields = dict(benchmark="ycsb_redis", results_dir=str(tmp_path), ycsb_target=1000)
    fields.update(overrides)
    return YcsbRedisBenchmark(SimpleConfig(**fields))


def test_decode_lays_counts_out_by_value():
    buckets = decode_histogram(_encode({100: 3, 250: 7}))
    assert buckets == {(100, 101): 3, (250, 251): 7}
    assert histogram_percentile(buckets, 30) == 100.0
    assert histogram_percentile(buckets, 95) == 250.0
    assert histogram_mean(buckets) == pytest.approx((3 * 100 + 7 * 250) / 10)


def test_hdr_log_header_and_legend_are_not_intervals():
    assert HdrInterval.parse("READ", "#[StartTime: 1.0 (seconds since epoch)]") is None
    assert HdrInterval.parse("READ", '"StartTimestamp","Interval_Length",...') is None
    tagged = HdrInterval.parse("READ", f"Tag=x,1.000,1.000,0.0,{_encode({5: 1})}")
    assert tagged.start == 1.0 and tagged.buckets == {(5, 6): 1}


def test_window_stats_merges_operations_over_their_own_spans():
    intervals = [
        _interval("READ", 10.0, {100: 400}), _interval("READ", 11.0, {100: 600}),
        # UPDATE's file keeps its own clock; its span is still two seconds.
        _interval("UPDATE", 500.0, {300: 100}), _interval("UPDATE", 501.0, {300: 100}),
    ]
    stats = window_stats(intervals)
    assert stats["requests"] == 1200
    assert stats["op_counts"] == {"READ": 1000, "UPDATE": 200}
    assert stats["achieved_qps"] == pytest.approx(500 + 100)
    assert stats["latency_p50"] == 100.0
    assert stats["latency_p95"] == 300.0


def test_consume_advances_past_complete_lines_only(tmp_path):
    benchmark = _ycsb(tmp_path)
    full = f"1.000,1.000,0.0,{_encode({50: 2})}\n"
    partial = "2.000,1.0"
    out = (f"@@BEGIN READ.hdr 0\n#[header]\n{full}{partial}\n@@END\n"
           f"@@BEGIN UPDATE.hdr 0\n\n@@END\n")
    parsed = benchmark._consume(out)
    assert [(i.op, i.start) for i in parsed] == [("READ", 1.0)]
    assert benchmark._offsets == {"READ.hdr": len("#[header]\n" + full), "UPDATE.hdr": 0}
    script = benchmark._fetch_script()
    assert f"READ.hdr) o={len('#[header]' + chr(10) + full)};;" in script
    assert "*) o=0;;" in script

    # A file read whole after shrinking below its offset restarts from there.
    benchmark._consume(f"@@BEGIN READ.hdr 0\n{full}\n@@END\n")
    assert benchmark._offsets["READ.hdr"] == len(full)


def test_parse_results_rescores_a_saved_window(tmp_path):
    benchmark = _ycsb(tmp_path)
    window = tmp_path / "window_1"
    window.mkdir()
    (window / "ycsb_intervals.txt").write_text(
        f"READ 1.000,1.000,0.0,{_encode({80: 250})}\n"
        f"READ 2.000,1.000,0.0,{_encode({90: 250})}\n"
    )
    metrics = benchmark.parse_results(str(window))
    assert metrics.throughput == pytest.approx(250.0)
    assert metrics.extra_metrics["qps_ratio"] == pytest.approx(0.25)
    assert metrics.extra_metrics["ops_read"] == 500


def test_ycsb_command_expands_home_on_the_client(tmp_path):
    benchmark = _ycsb(tmp_path, ycsb_properties={"requestdistribution": "uniform"})
    cmd = benchmark._ycsb_command("run", {"status.interval": 1}, 64, ["-target", "1000"])
    assert cmd.startswith("cd ~/YCSB && ./bin/ycsb run redis -s -P ~/workloads/ycsb/workloada ")
    assert "-p redis.host=10.10.1.1" in cmd and "-p requestdistribution=uniform" in cmd
    assert cmd.endswith("-threads 64 -target 1000")


def test_redis_runs_threaded_io_without_persistence(tmp_path):
    cmd = _ycsb(tmp_path, redis_cpus="0-3")._redis_command()
    assert cmd[:3] == ["taskset", "-c", "0-3"]
    assert cmd[cmd.index("--save") + 1] == ""
    assert cmd[cmd.index("--io-threads") + 1] == "8"
    assert "--io-threads" not in _ycsb(tmp_path, redis_io_threads=1)._redis_command()


def test_ycsb_redis_refuses_pin_to_cores():
    with pytest.raises(ValueError, match="pin_to_cores"):
        SimpleConfig(benchmark="ycsb_redis", pin_to_cores="0-3").validate()


def test_fetch_script_reads_appends_and_survives_a_truncated_file(tmp_path):
    import subprocess

    hdr = tmp_path / "hdr"
    hdr.mkdir()
    benchmark = _ycsb(tmp_path, ycsb_hdr_dir=str(hdr))

    def fetch():
        out = subprocess.run(["bash", "-c", benchmark._fetch_script()],
                             capture_output=True, text=True, check=True).stdout
        return [(i.op, i.start) for i in benchmark._consume(out)]

    line = lambda t: f"{t:.3f},1.000,0.0,{_encode({100: 1})}\n"
    (hdr / "READ.hdr").write_text("#[header]\n" + line(1) + line(2)[:10])
    assert fetch() == [("READ", 1.0)]
    with open(hdr / "READ.hdr", "a") as handle:
        handle.write(line(2)[10:] + line(3))
    (hdr / "UPDATE.hdr").write_text(line(7))
    assert sorted(fetch()) == [("READ", 2.0), ("READ", 3.0), ("UPDATE", 7.0)]
    assert fetch() == []

    # A new run's file, shorter than the recorded offset, is read from the top.
    (hdr / "READ.hdr").write_text(line(9))
    assert fetch() == [("READ", 9.0)]
