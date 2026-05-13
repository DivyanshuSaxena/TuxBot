# Installation

Install SemaTune on a host where it is safe to change Linux system parameters.
The `os-param-tuning` command is the current CLI entry point.
Read [Safety and Restore](safety-and-restore.md) before running anything beyond
the smoke configs.

## Host Requirements

Recommended baseline:

- Ubuntu 22.04 or 24.04 on bare metal
- Python 3.10+
- `sudo` access
- `sysbench`
- PostgreSQL 14+
- Java 21+
- Linux `perf`
- BenchBase built under `deps/benchbase`

Ubuntu package baseline:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git sysbench postgresql postgresql-contrib openjdk-21-jdk linux-tools-common linux-tools-generic linux-tools-$(uname -r)
```

Install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs,llm]"
```

Install all tuner extras:

```bash
pip install -e ".[dev,docs,llm,tuners]"
```

For narrower installs, use `.[bayesian]` for the SMAC-backed Bayesian tuner,
`.[mlos]` for the MLOS tuner, or `.[dqn]` for the PyTorch-backed DQN tuner.
The Q-learning tuner has no extra dependency.

LLM runs require your own provider key:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
export OPENROUTER_API_KEY="<your OpenRouter API key>"
```

Set only the key for the provider you use. Never commit real keys in JSON
configs.

Check host readiness:

```bash
.venv/bin/os-param-tuning doctor
```

Set up the default TPCC PostgreSQL database used by
`config/benchbase/postgres/tpcc.xml`:

```bash
sudo scripts/setup_tpcc_postgres.sh
PGPASSWORD=password psql -h localhost -U admin -d benchbase -c 'select 1;'
```

The setup script creates/updates database `benchbase`, role `admin`, and
password `password`, pins the detected PostgreSQL cluster to cores `0-9` when
the systemd service exists, and sets `max_worker_processes = 44` plus
`max_parallel_workers = 42`.

Build BenchBase after initializing the `deps/benchbase` submodule. The pinned
BenchBase checkout compiles with Java target 21, so use OpenJDK 21 here.

```bash
git submodule update --init deps/benchbase
cd deps/benchbase
./mvnw -P postgres -DskipTests package
tar -xzf target/benchbase-postgres.tgz -C target
cd ../..
```
