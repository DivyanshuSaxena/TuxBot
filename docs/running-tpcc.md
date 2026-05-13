# Running TPCC

TPCC is the included database-backed target. It shows how SemaTune handles a
service with setup, load, measurement windows, and application tail-latency
metrics. TPCC requires PostgreSQL and a built BenchBase jar.
Read [Safety and Restore](safety-and-restore.md) before running long TPCC
tuning sessions.

The TPCC XML at `config/benchbase/postgres/tpcc.xml` expects:

- database: `benchbase`
- user: `admin`
- password: `password`
- host: `localhost`
- port: `5432`

Set up PostgreSQL:

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib openjdk-21-jdk
sudo scripts/setup_tpcc_postgres.sh
PGPASSWORD=password psql -h localhost -U admin -d benchbase -c 'select 1;'
```

Build BenchBase with PostgreSQL support:

```bash
git submodule update --init deps/benchbase
cd deps/benchbase
./mvnw -P postgres -DskipTests package
tar -xzf target/benchbase-postgres.tgz -C target
cd ../..
```

Run the fixed smoke config. `BenchBaseBenchmark.pre_execute()` runs
`--create=true --load=true` before measurement, using a temporary copy of the
XML.

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/tpcc_fixed.json
```

For a single-loop LLM run:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/tpcc_llm_single.json
```

For a dual-loop LLM run:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/tpcc_llm_dual.json
```

For the full 8-parameter TPCC LLM profile:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/tpcc_llm_8param_default_gemini.json
```

OpenRouter uses the same runner with a different key and config:

```bash
export OPENROUTER_API_KEY="<your OpenRouter API key>"
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,OPENROUTER_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/tpcc_llm_8param_default_openrouter.json
```

Bayesian or MLOS runs require optional tuner extras:

```bash
pip install -e ".[tuners]"
.venv/bin/os-param-tuning run --config config/examples/tpcc_bayesian.json
.venv/bin/os-param-tuning run --config config/examples/tpcc_mlos.json
```

Q-learning runs without extra dependencies; DQN needs PyTorch:

```bash
.venv/bin/os-param-tuning run --config config/examples/tpcc_qlearning.json
pip install -e ".[dqn]"
.venv/bin/os-param-tuning run --config config/examples/tpcc_dqn.json
```

SemaTune updates the `<time>` element in a temporary copy of the TPCC XML for
each measurement window.

If the console script is unavailable, the module fallback is:

```bash
.venv/bin/python -m barebones_optimizer.main run --config config/examples/tpcc_fixed.json
```
