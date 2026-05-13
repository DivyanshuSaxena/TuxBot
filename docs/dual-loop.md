# Dual-Loop LLM

Single-loop LLM uses one model to propose once per tuning step. Dual-loop LLM
uses two LLM agents:

- **Speculator**: fast model for quick local exploration or correction.
- **Actor**: slower model for deeper reasoning over accumulated history.

Dual loop is selected with:

```json
{
  "tuner_type": "llm",
  "llm_loop": "dual",
  "llm_speculator_model": "gemini-2.5-flash-lite",
  "llm_actor_model": "gemini-2.5-flash"
}
```

## Gemma 4 Example

```json
{
  "llm_provider": "gemini",
  "llm_loop": "dual",
  "llm_speculator_model": "gemma-4-26b-a4b-it",
  "llm_speculator_thinking_level": "MINIMAL",
  "llm_actor_model": "gemma-4-31b-it",
  "llm_actor_thinking_level": "HIGH"
}
```

Canonical file: `config/examples/sysbench_cpu_llm_dual_gemma4.json`.

## Outside-Of-Window Versus In-Window

The default `tuning_mode` is `outside-of-window`: SemaTune measures a window,
asks the tuner after that window, applies accepted changes, then measures the
next window.

Dual loop can also be useful for in-window experiments, where a fast Speculator
can produce lower-latency changes while the Actor performs slower analysis. Use
in-window tuning only after the outside-of-window path is working on your host.

## Logs

LLM logs include the `agent` field:

```text
<results_dir>/llm_api_logs/llm_responses.jsonl
```

Look for `agent: "quick"` or `agent: "speculator"` for Speculator calls, and
`agent: "reasoning"` or `agent: "actor"` for Actor calls, depending on the
optimizer path.

## When To Use Dual Loop

Use dual loop when:

- LLM latency matters during tuning.
- A cheaper/faster model can handle local moves.
- A stronger model should periodically revise strategy.
- You want separate model choices or thinking levels for quick and deep calls.

Do not use it first. Start with fixed, then single-loop LLM or replay, then dual
loop after the target and metrics are stable.
