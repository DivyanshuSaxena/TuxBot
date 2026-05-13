# Tuners

SemaTune tuners all use the same outer control loop: receive recent metrics and
current parameters, propose the next parameter setting, and let the optimizer
validate and apply the proposal.

Run every tuner through the same command:

```bash
.venv/bin/os-param-tuning run --config config/examples/sysbench_cpu_fixed.json
```

## Supported Tuner Names

| Tuner | Extra install | Best first use |
| --- | --- | --- |
| `fixed` | none | Baselines, host validation, and smoke tests. |
| `llm` | `.[llm]` | Semantic tuning with Gemini or OpenRouter. |
| `bayesian` | `.[bayesian]` | Model-based scalar-objective search. |
| `mlos` | `.[mlos]` | MLOS-backed scalar-objective search. |
| `qlearning` | none | Small discretized action spaces. |
| `dqn` | `.[dqn]` | Larger discretized action spaces with PyTorch. |

Install all optional tuner dependencies:

```bash
pip install -e ".[tuners]"
```

## Choosing A Tuner

Use `fixed` first. It proves the target can run, metrics parse, and parameter
application does not immediately fail.

Use `llm` when parameter semantics and proxy metrics matter. The LLM tuner can
see parameter descriptions, recent history, direct metrics, and additional
system metrics.

Use Bayesian, MLOS, Q-learning, or DQN when you have one scalar reward that you
trust. These tuners do not understand that a proxy metric is only evidence; they
optimize the scalar you give them.

## Optional Dependency Boundaries

Optional tuner dependencies are imported lazily. Base tests and base CLI help
should work without SMAC, MLOS Core, or PyTorch installed. If an optional tuner
fails to import, install the matching extra.

## Related Pages

- [LLM Setup](llm-setup.md)
- [Dual-Loop LLM](dual-loop.md)
- [LLM Replay](llm-replay.md)
- [Configuration Recipes](config-recipes.md)
