"""A guardrail that keeps repairing in post-tuning without its check coming
back starts a fresh tuning phase."""

import pytest

import barebones_optimizer.main_helpers as main_helpers
from barebones_optimizer.benchmark import BenchmarkMetrics
from barebones_optimizer.config import SimpleConfig
from barebones_optimizer.optimizer import SimpleOptimizer


class _Bench:
    """Scripted windows: `guardrail[i]` is window i's guardrail delta."""

    def __init__(self, guardrail):
        self.guardrail = guardrail
        self.load_steps = []

    def update_workload(self, iteration):
        self.load_steps.append(iteration)

    def execute_window(self, window_number, duration):
        m = BenchmarkMetrics()
        m.latency_p95 = 100.0 + window_number
        m.extra_metrics.update(self.guardrail.get(window_number, {}))
        return m


def firing(violations=3):
    """A window's guardrail delta."""
    return {"guardrail_fires": 1, "guardrail_acted": True,
            "guardrail_ticks": 5, "guardrail_violations": violations}


def run(guardrail, tmp_path, monkeypatch, **overrides):
    monkeypatch.setenv("GDL_RUN_DIR", str(tmp_path))
    monkeypatch.setattr(SimpleOptimizer, "GUARDRAIL_RUN_DIR", str(tmp_path))
    fields = dict(benchmark="memcached", optimization_metric="latency_p95",
                  optimization_goal="minimize", max_iterations=3,
                  post_tuning_windows=2, total_windows=14,
                  retune_on_guardrail=True, retune_iterations=3,
                  results_dir=str(tmp_path))
    fields.update(overrides)
    config = SimpleConfig(**fields)
    config.validate()

    created = []
    monkeypatch.setattr(main_helpers, "create_tuner_from_config",
                        lambda cfg: created.append(cfg) or object())
    opt = SimpleOptimizer(config, _Bench(guardrail), tuner=object())
    asked = []
    monkeypatch.setattr(opt, "_get_tuner_response_sync",
                        lambda metrics, it: (asked.append(it) or None, 0.0))
    monkeypatch.setattr(opt, "_freeze_best_parameters", lambda: True)
    written = []
    monkeypatch.setattr(opt.param_manager, "set_parameters",
                        lambda params: written.append(params) or True)
    monkeypatch.setattr(opt, "_initial_parameters",
                        lambda: {"busy_poll": 0, "base_slice_ns": 3000000})
    opt.written = written
    monkeypatch.setattr(opt, "_finish", lambda reason: reason)
    assert opt._run_outside_window_mode() == "complete"
    return opt, asked, created


def phases(opt):
    return [(e["iteration"], e["tuning_phase"], e["post_tuning_phase"])
            for e in opt.history]


def test_two_firing_post_tuning_windows_start_a_fresh_phase(tmp_path, monkeypatch):
    opt, asked, created = run({5: firing(), 6: firing()}, tmp_path, monkeypatch)
    assert [e["iteration"] for e in opt.history if e.get("retune_triggered")] == [6]
    assert len(created) == 1
    # Phase 1 tunes 1-3 and phase 2 tunes 7-9.
    # Phase 2's first window measures the defaults, as a run's first does,
    # so the fresh tuner is first asked after window 7.
    assert asked == [1, 2, 7, 8]
    assert opt.written == [{"busy_poll": 0, "base_slice_ns": 3000000}]
    assert [p for i, p, post in phases(opt) if not post] == [1, 1, 1, 2, 2, 2]
    assert opt.best_reward == 107.0   # phase 2's best, not window 1's 101


def test_one_failed_check_is_a_firing_window(tmp_path, monkeypatch):
    opt, _, created = run({5: firing(1), 6: firing(1)}, tmp_path, monkeypatch)
    assert len(created) == 1


def test_a_quiet_window_does_not_fire(tmp_path, monkeypatch):
    opt, asked, created = run({5: firing(0), 6: firing(0), 7: firing(0)},
                              tmp_path, monkeypatch)
    assert not created
    assert asked == [1, 2]


def test_firing_windows_must_be_consecutive(tmp_path, monkeypatch):
    opt, _, created = run({5: firing(), 6: firing(0), 7: firing()}, tmp_path, monkeypatch)
    assert not created


def test_violations_during_tuning_do_not_count(tmp_path, monkeypatch):
    opt, _, created = run({2: firing(), 3: firing()}, tmp_path, monkeypatch)
    assert not created


def test_one_retune_per_run(tmp_path, monkeypatch):
    guardrail = {i: firing() for i in range(4, 15)}
    opt, _, created = run(guardrail, tmp_path, monkeypatch, total_windows=20)
    assert len(created) == 1


def test_a_late_retune_searches_to_the_end(tmp_path, monkeypatch):
    opt, asked, created = run({11: firing(), 12: firing()}, tmp_path, monkeypatch)
    assert len(created) == 1
    assert [p for i, p, post in phases(opt) if i > 12] == [2, 2]
    # Asked after window 13 (the defaults), never after the run's last.
    assert asked == [1, 2, 13]


def test_the_last_window_cannot_retune(tmp_path, monkeypatch):
    opt, _, created = run({13: firing(), 14: firing()}, tmp_path, monkeypatch)
    assert not created


def test_off_by_default(tmp_path, monkeypatch):
    opt, _, created = run({5: firing(), 6: firing()}, tmp_path, monkeypatch,
                          retune_on_guardrail=False)
    assert not created
    assert all(e["tuning_phase"] == 1 for e in opt.history)


def test_total_windows_sets_the_run_length(tmp_path, monkeypatch):
    opt, _, _ = run({}, tmp_path, monkeypatch, retune_on_guardrail=False)
    assert len(opt.history) == 14


def test_load_step_fields_go_together():
    with pytest.raises(ValueError):
        SimpleConfig(benchmark="memcached", mutilate_qps_after=27000).validate()
