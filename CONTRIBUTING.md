# Contributing

Thanks for helping make this project more reproducible.

## Scope

The public v1 scope is intentionally limited to `sysbench_cpu` and BenchBase
`tpcc`. Please keep changes inside that surface unless a maintainer explicitly
accepts a broader design.

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs,llm]"
pytest
mkdocs build --strict
```

Host-mutating tests must be explicitly requested:

```bash
sudo .venv/bin/pytest --run-host-mutation -m host_mutation
```

## Secrets

Do not commit API keys, private paths, result dumps, generated logs, or local
environment files. Use `GEMINI_API_KEY` or `OPENROUTER_API_KEY` in your shell.
