"""The interface between a tuning run and the OS guardrails watching it.

Two files under GDL_RUN_DIR and the guardrails' own daemon logs; neither
process knows the other's pid.
"""

import json
import os

import pytest

from barebones_optimizer.benchmark import BenchmarkInterface


class _Bench(BenchmarkInterface):
    """The base class alone: the guardrail counters live there, so every
    benchmark gets them."""

    def execute_window(self, window_number, duration):
        raise NotImplementedError

    def parse_results(self, *a, **kw):
        raise NotImplementedError

    def pre_execute(self):
        pass

    def cleanup(self):
        pass


@pytest.fixture
def bench(tmp_path, monkeypatch):
    monkeypatch.setenv("GDL_RUN_DIR", str(tmp_path))
    log = tmp_path / "guardrail.log"
    log.write_text("[obs] {}\n")
    monkeypatch.setenv("GDL_GUARDRAIL_LOGS", str(log))
    b = _Bench.__new__(_Bench)
    return b, log


def acted(delta):
    """The two keys the best-parameters guard reads."""
    return {k: delta[k] for k in ("guardrail_fires", "guardrail_acted")}


def fire(log, n=1):
    with open(log, "a") as f:
        for _ in range(n):
            f.write("[!] TuxBot_guardrail: check violated -> dispatching actions\n")
            f.write("[SET] tuxbot_knobs := restore_numa\n")


def test_counts_only_the_lines_a_window_added(bench):
    b, log = bench
    fire(log, 2)                       # before the window opens
    b._guardrail_window_start = b._read_guardrail_logs()
    fire(log, 3)
    delta = b._guardrail_window_delta()
    assert acted(delta) == {"guardrail_fires": 3, "guardrail_acted": True}


def test_a_quiet_window_did_not_act(bench):
    b, log = bench
    b._guardrail_window_start = b._read_guardrail_logs()
    assert acted(b._guardrail_window_delta()) == {"guardrail_fires": 0,
                                           "guardrail_acted": False}


def test_a_rotated_log_is_read_whole(bench):
    """A log shorter than its offset was rotated under the window, so the
    offset names nothing and every fire in what is there is this window's."""
    b, log = bench
    fire(log, 4)
    b._guardrail_window_start = b._read_guardrail_logs()
    log.write_text("")                 # rotated
    fire(log, 2)
    assert acted(b._guardrail_window_delta()) == {"guardrail_fires": 2,
                                           "guardrail_acted": True}


def test_the_window_read_is_independent_of_the_backlog(bench):
    """The daemon appends an [obs] record every tick, so the log is hundreds of
    MB by the end of a sweep; a window reads only what it added."""
    b, log = bench
    with open(log, "a") as f:
        f.write("[obs] " + "x" * 4_000_000 + "\n")
    b._guardrail_window_start = b._read_guardrail_logs()
    fire(log, 1)
    with open(log, "rb") as f:
        f.seek(b._guardrail_window_start[str(log)])
        assert len(f.read()) < 1000
    assert b._guardrail_window_delta()["guardrail_fires"] == 1


def test_a_repair_step_acted_but_its_other_lines_did_not(bench):
    """A Repair moves a knob only on its `:=` lines; a metric reading, a
    settle or a hold is the guardrail talking, not acting."""
    b, log = bench
    b._guardrail_window_start = b._read_guardrail_logs()
    with open(log, "a") as f:
        f.write("[REPAIR] busy_poll: rx_notify_violations=0.2 at 50; probing its neighbours\n")
        f.write("[REPAIR] busy_poll := 25 (was 50, rx_notify_violations=0.2 at 50)\n")
        f.write("[REPAIR] busy_poll: settled at 25, holding (12s left)\n")
    assert acted(b._guardrail_window_delta()) == {"guardrail_fires": 1,
                                           "guardrail_acted": True}


def test_counts_repair_attempts_and_violated_ticks(bench):
    """Every [REPAIR] line is an attempt, a `:=` or not, and only evaluated
    in-scope ticks carry a verdict."""
    b, log = bench
    b._guardrail_window_start = b._read_guardrail_logs()
    with open(log, "a") as f:
        f.write('[obs] {"in_scope": false, "observations": {}}\n')
        f.write('[obs] {"in_scope": true, "evaluated": false}\n')
        f.write('[obs] {"in_scope": true, "holds": false}\n')
        f.write('[obs] {"in_scope": true, "holds": false}\n')
        f.write('[obs] {"in_scope": true, "holds": false}\n')
        f.write('[obs] {"in_scope": true, "holds": true}\n')
        f.write("[REPAIR] (busy_poll, base_slice_ns) := (0, 3000000) (was ...)\n")
        f.write("[REPAIR] (busy_poll, base_slice_ns) settled at (0, 3000000): holding 30s\n")
    delta = b._guardrail_window_delta()
    assert delta["guardrail_fires"] == 1
    assert delta["guardrail_repair_lines"] == 2
    assert delta["guardrail_ticks"] == 4
    assert delta["guardrail_violations"] == 3
    assert delta["guardrail_violated_frac"] == 0.75


def test_records_which_way_a_repair_moved_each_knob(bench):
    """From the value before a knob's first step to the one after its last; a
    knob probed and put back reads as unmoved."""
    b, log = bench
    b._guardrail_window_start = b._read_guardrail_logs()
    with open(log, "a") as f:
        f.write('[obs] {"in_scope": true, "holds": false}\n')
        f.write("[REPAIR] (busy_poll, base_slice_ns): rx_wait_q95=1.35157e+07 at (0, 3000000); probing its neighbours\n")
        f.write("[REPAIR] busy_poll := 10 (was 0, rx_wait_q95=1.35157e+07 at (0, 3000000))\n")
        f.write("[REPAIR] busy_poll := 0 (was 10, rx_wait_q95=1.35157e+07 at (0, 3000000))\n")
        f.write("[REPAIR] base_slice_ns := 1000000 (was 3000000, rx_wait_q95=1.35157e+07 at (0, 3000000))\n")
        f.write("[REPAIR] base_slice_ns := 500000 (was 1000000, rx_wait_q95=8.88067e+06 at (0, 1000000))\n")
        f.write('[obs] {"in_scope": true, "holds": true}\n')
    delta = b._guardrail_window_delta()
    assert delta["guardrail_moves"] == {
        "busy_poll": {"from": 0, "to": 0, "steps": 2},
        "base_slice_ns": {"from": 3000000, "to": 500000, "steps": 2}}
    assert delta["guardrail_held_at_end"] is True


def test_an_off_ladder_snap_is_a_move(bench):
    b, log = bench
    b._guardrail_window_start = b._read_guardrail_logs()
    with open(log, "a") as f:
        f.write("[REPAIR] busy_poll := 100 (was 82, off its ladder)\n")
        f.write('[obs] {"in_scope": true, "holds": false}\n')
    delta = b._guardrail_window_delta()
    assert delta["guardrail_moves"] == {"busy_poll": {"from": 82, "to": 100, "steps": 1}}
    assert delta["guardrail_held_at_end"] is False


def test_the_prompt_says_which_way_the_guardrail_moved():
    from barebones_optimizer.tuners.llm import LLMTuner

    t = LLMTuner.__new__(LLMTuner)
    metrics = {"guardrail_fires": 3, "guardrail_acted": True,
               "guardrail_ticks": 15, "guardrail_violations": 12,
               "guardrail_held_at_end": True,
               "guardrail_moves": {
                   "busy_poll": {"from": 0, "to": 0, "steps": 2},
                   "base_slice_ns": {"from": 3000000, "to": 500000, "steps": 2}}}
    note = t._format_guardrail_note(3, True, metrics)
    assert "check failed 12/15 ticks" in note
    assert "base_slice_ns 3ms -> 0.5ms (lower)" in note
    assert "busy_poll unchanged at 0" in note
    block = t._format_guardrail_block(3, True, metrics)
    assert "base_slice_ns 3ms -> 0.5ms (lower)" in block
    assert "held again" in block
    # A restore names no knob, so it keeps the override wording.
    assert "partially overridden" in t._format_guardrail_note(1, True, {})
    assert t._format_guardrail_block(0, False, metrics) == ""


def test_no_guardrail_configured_reports_nothing(tmp_path, monkeypatch):
    """The unguarded arm, not an error."""
    monkeypatch.delenv("GDL_GUARDRAIL_LOGS", raising=False)
    b = _Bench.__new__(_Bench)
    b._guardrail_window_start = b._read_guardrail_logs()
    assert b._guardrail_window_delta() == {}


def test_a_missing_log_counts_as_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("GDL_GUARDRAIL_LOGS", str(tmp_path / "absent.log"))
    b = _Bench.__new__(_Bench)
    assert b._read_guardrail_logs() == {str(tmp_path / "absent.log"): 0}


# -- what the optimizer publishes ------------------------------------------- #

def test_publishes_best_and_state(tmp_path, monkeypatch):
    from barebones_optimizer.optimizer import SimpleOptimizer

    opt = SimpleOptimizer.__new__(SimpleOptimizer)
    monkeypatch.setattr(opt, "GUARDRAIL_RUN_DIR", str(tmp_path), raising=False)
    opt.best_parameters = {"numa_scan_size_mb": 512}

    opt._publish_best_parameters()
    with open(tmp_path / "tuxbot_best.json") as f:
        assert json.load(f) == {"numa_scan_size_mb": 512}

    opt._publish_state("measuring")
    assert (tmp_path / "tuxbot_state").read_text() == "measuring"
    # Renamed into place, so a guardrail never reads a half-written file.
    assert not os.path.exists(tmp_path / "tuxbot_state.tmp")
