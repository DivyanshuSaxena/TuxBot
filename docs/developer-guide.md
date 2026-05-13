# Developer Guide

Use the included `sysbench_cpu` and TPCC targets as reference implementations
for new SemaTune targets. The documented tuner surface is `fixed`, `llm`,
`bayesian`, `mlos`, `qlearning`, and `dqn`.

For implementation contracts, see [Extending SemaTune](extending.md). For a
copy-paste-friendly target example, see [Add a Target Tutorial](add-a-target-tutorial.md).

## Local Checks

```bash
.venv/bin/pytest
.venv/bin/mkdocs build --strict
.venv/bin/python -m compileall src tests
.venv/bin/os-param-tuning --help
```

Host-mutating tests are opt-in:

```bash
sudo .venv/bin/pytest --run-host-mutation -m host_mutation
```

## Adding A Config Field

1. Add the field to `SimpleConfig`.
2. Validate it if bad values can silently change behavior.
3. Add or update an example config only if the field is part of the documented
   user surface.
4. Document the field in [Configuration Reference](configuration.md).
5. Add a config validation test when the field has meaningful constraints.

The docs coverage test checks that every `SimpleConfig` field appears in the
configuration reference.

## Adding An OS Parameter

1. Add metadata in `PARAMETER_METADATA`.
2. Add setter/getter behavior in `ParameterManager` when supported.
3. Keep the setter bounded to a known Linux interface, not arbitrary shell.
4. Document interface, unit, scope, restore behavior, prerequisites, failures,
   safe starting range, and interactions in [OS Parameter Reference](os-parameters.md).
5. Add tests for validation and value normalization.

The docs coverage test checks that every `PARAMETER_METADATA` key appears in
the OS parameter reference.

## Adding A Target

1. Implement the `BenchmarkInterface` adapter.
2. Add registry and factory wiring.
3. Add one small example config.
4. Add parser tests with tiny fixtures.
5. Keep live target tests behind `benchmark_smoke`; add `host_mutation` when
   the test changes host state.
6. Document setup, metrics, output files, and common failures.

## Adding A Tuner

1. Implement `TunerInterface`.
2. Add config validation and factory wiring.
3. Keep optional dependencies lazy.
4. Add example configs for the included targets when the tuner is documented.
5. Add construction/suggestion tests with fake metrics.
6. Document installation, expected use cases, and failure modes.

## Docs Coverage Tests

`tests/test_docs_coverage.py` guards against common drift:

- config fields missing from `configuration.md`
- OS parameters missing from `os-parameters.md`
- prompt modes missing from `llm-prompt-modes.md`
- documented recipe fixtures or examples missing from the tree

Update the tests when docs move, but do not weaken them to hide drift.

## Release Checklist

Before a public push:

```bash
.venv/bin/pytest
.venv/bin/mkdocs build --strict
.venv/bin/python -m compileall src tests
.venv/bin/os-param-tuning doctor
```

Also verify:

- README quick start still works.
- Fixed `sysbench_cpu` smoke run completes.
- `config/examples/*.json` contains no real API keys.
- `results/`, `site/`, logs, caches, and local archives are not committed.
- `CITATION.cff` and README citation placeholders are updated when final
  citation text exists.
- Safety and restore docs still match actual parameter behavior.

Do not commit generated results, plots, logs, local secrets, or
machine-specific paths.
