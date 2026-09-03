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
    assert delta == {"guardrail_fires": 3, "guardrail_acted": True}


def test_a_quiet_window_did_not_act(bench):
    b, log = bench
    b._guardrail_window_start = b._read_guardrail_logs()
    assert b._guardrail_window_delta() == {"guardrail_fires": 0,
                                           "guardrail_acted": False}


def test_a_rotated_log_is_read_whole(bench):
    """A log shorter than its offset was rotated under the window, so the
    offset names nothing and every fire in what is there is this window's."""
    b, log = bench
    fire(log, 4)
    b._guardrail_window_start = b._read_guardrail_logs()
    log.write_text("")                 # rotated
    fire(log, 2)
    assert b._guardrail_window_delta() == {"guardrail_fires": 2,
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
