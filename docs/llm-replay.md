# LLM Replay

`llm_replay_file` lets you run an LLM config without making Gemini or OpenRouter
API calls. The replay file supplies parameter proposals by iteration.

Replay is useful for CI, demos, and debugging LLM plumbing on a host where you
do not want to spend API calls.

## No-Key Replay Run

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_replay.json
```

The example config points to:

```text
config/replay/sysbench_cpu_llm_replay_history.json
```

No `GEMINI_API_KEY` or `OPENROUTER_API_KEY` is required.

## Replay File Shape

```json
{
  "history": [
    {
      "iteration": 1,
      "parameters": {
        "min_granularity_ns": 5000000
      },
      "timing_info": {
        "reasoning_response_duration": 0.0
      }
    }
  ]
}
```

For dual-loop replay, Speculator proposals use `quick_parameters`; Actor
proposals use `parameters`.

## What Replay Validates

Replay validates:

- config loading
- target execution
- metric parsing
- optimizer loop plumbing
- parameter filtering and application
- result history writing
- LLM tuner construction without provider credentials

Replay does not validate:

- live model quality
- provider routing
- provider authentication
- rate limits
- prompt quality under real model behavior

## Creating A Replay File From A Prior Run

Start from an optimization history and use each next window's measured
parameters as the proposal for the previous iteration:

```bash
jq '{history: [.history as $hist |
  range(0; (($hist | length) - 1)) as $i |
  {iteration: $hist[$i].iteration, parameters: $hist[$i + 1].parameters}]}' \
  results/<run>/optimization_history_*.json \
  > config/replay/my_replay.json
```

Then set:

```json
{
  "tuner_type": "llm",
  "llm_replay_file": "config/replay/my_replay.json"
}
```

Review replay files before committing them. They should not contain private
paths, provider responses, or host-specific notes.
