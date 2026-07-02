# Contributing

Thanks for helping improve muse. This project is open-source
middleware for AI coding agents, so contributions should keep the MCP workflow
and repo-agnostic agent use case clear.

## Development Setup

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
```

## Before Opening a PR

- Add or update tests for behavior changes.
- Run `python -m pytest -q`.
- Run `python -m ruff check .`.
- For MCP-facing changes, run `muse-mcp-smoke` with deterministic mode.
- For quality-related changes, run `muse-dogfood-quality` and include quality gate results.
- Do not commit real API keys, trace files with secrets, or local `.env` files.

## Design Direction

- Keep the core repo-agnostic. Do not hardcode behavior for one codebase or one prompt.
- Treat CLI commands as harnesses. MCP is the intended agent integration surface.
- Deterministic mode is for protocol and CI checks, not product-quality creative output.
- Prefer small, reviewable slices with tests and docs.

## Reporting Issues

Use the GitHub issue templates and include the MCP request shape, provider mode,
search mode, verification commands, and dogfood quality gates when relevant.
