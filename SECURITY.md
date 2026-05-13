# Security

This project executes benchmarks and writes Linux kernel/system parameters. Run
it only on machines where you are allowed to change scheduler, CPU, and sysctl
settings.

## Reporting Issues

Please report security issues privately to the maintainers before opening a
public issue.

## Secret Handling

LLM credentials must be supplied through environment variables:

- `GEMINI_API_KEY`
- `OPENROUTER_API_KEY`

Committed configs must not contain live API keys or host credentials.

## Run Artifact Privacy

LLM response logs under `results/<run>/llm_api_logs/` contain full prompts,
model responses, parsed parameter suggestions, and raw SDK response summaries.
Treat them as private artifacts unless you have reviewed and sanitized them.
