"""The knob vocabulary: a name is only tunable if every layer knows it."""

from barebones_optimizer.parameter_manager import (
    PARAMETER_METADATA,
    ParameterManager,
    get_default_parameters,
)


def test_base_slice_ns_is_wired_through_every_layer():
    # Metadata alone is not enough: set_parameters dispatches by method lookup,
    # and a knob absent from the defaults never enters initial_params, so the
    # run records no baseline for it and a "fixed" control never touches it.
    assert "base_slice_ns" in PARAMETER_METADATA
    assert hasattr(ParameterManager, "set_base_slice_ns")
    assert "base_slice_ns" in get_default_parameters()


def test_scheduler_paths_are_registered_only_when_the_file_exists(monkeypatch):
    """EEVDF kernels have base_slice_ns and not the CFS three; CFS is the reverse."""
    eevdf = {"/sys/kernel/debug/sched/base_slice_ns",
             "/sys/kernel/debug/sched/migration_cost_ns"}
    monkeypatch.setattr(ParameterManager, "_ensure_debugfs_mounted", lambda self: None)
    monkeypatch.setattr(ParameterManager, "_register_numa_balancing_paths",
                        lambda self: None)
    monkeypatch.setattr(ParameterManager, "_path_exists",
                        lambda self, path: path in eevdf)

    paths = ParameterManager().param_paths
    assert set(paths) == {"base_slice_ns", "migration_cost_ns"}
    assert "min_granularity_ns" not in paths
