# LLM Setup

LLM is a tuner selected with `tuner_type: "llm"`. There is no separate public
LLM command.
If you want to test LLM plumbing without provider calls, start with
[LLM Replay](llm-replay.md).

## API Keys

Users must enter their own API keys. Do not put real keys in JSON configs,
example files, docs, tests, or commits.

Gemini:

```bash
export GEMINI_API_KEY="<your Gemini API key>"
```

OpenRouter:

```bash
export OPENROUTER_API_KEY="<your OpenRouter API key>"
```

When running with `sudo`, preserve only the key you need:

```bash
sudo --preserve-env=PATH,OS_PARAM_TUNING_ROOT,GEMINI_API_KEY \
  OS_PARAM_TUNING_ROOT="$(pwd)" \
  .venv/bin/os-param-tuning run \
  --config config/examples/sysbench_cpu_llm_single.json
```

The config fields `llm_api_key` and `openrouter_api_key` remain for private
local compatibility. Shared configs should use environment variables.

## Provider Selection

Set `llm_provider` explicitly when you want predictable routing:

```json
{
  "tuner_type": "llm",
  "llm_provider": "gemini",
  "llm_model_name": "gemini-2.5-flash"
}
```

```json
{
  "tuner_type": "llm",
  "llm_provider": "openrouter",
  "llm_model_name": "openai/gpt-4o-mini"
}
```

`llm_provider: "auto"` routes bare `gemini-*` and `gemma-*` model names to
Gemini. Other model names use OpenRouter.

## Response Logs

LLM request/response logging is on by default:

```text
<results_dir>/llm_api_logs/
```

The quickest file to inspect is `llm_responses.jsonl`; it has one compact JSON
record per LLM call with provider, model, agent, response text, parsed response,
request config, and the path to the full log. Full logs include the prompt sent
to the provider and the raw SDK response.

Treat LLM logs as private run artifacts. They may include host details, workload
descriptions, parameter values, and prompt customization text.

## Prompt Customization

Prompt customization is additive. The built-in prompt remains the base:

```json
{
  "workload_description": "TPC-C high-percentile latency tuning on PostgreSQL",
  "llm_prompt_extra_instructions": "Prefer stable improvements over aggressive jumps.",
  "llm_prompt_extra_instructions_file": "config/prompts/local_notes.txt"
}
```

Use `workload_description` for workload facts and
`llm_prompt_extra_instructions` for strategy preferences. Complete prompt
replacement is intentionally not part of the documented interface.

See [LLM Prompt Modes](llm-prompt-modes.md) for the supported prompt recipes.

## Trimming

LLM trimming is a supported single-loop feature. It runs a short initial phase
that can narrow parameter ranges or eliminate parameters, then the primary LLM
tuner continues with the reduced search space.

```json
{
  "tuner_type": "llm",
  "llm_loop": "single",
  "trimming_enabled": true,
  "trimming_cycles": 5,
  "trimming_model_name": "gemini-2.5-flash",
  "trimming_suggest_params": true
}
```

Use `config/examples/tpcc_llm_8param_trimming_gemini.json` as the canonical
example. Trimming is disabled by default because it changes the search space and
adds LLM calls.
