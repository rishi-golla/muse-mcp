# V5-E External Repo Dogfood Implementation Plan

## Task 1: Add dogfood API tests

- File: `tests/test_external_dogfood.py`
- Verify `run_external_dogfood` creates a marked external repo with sample
  project files, MCP config, and agent instructions.
- Verify the returned report is JSON-safe and live-only in public posture.
- Verify the function refuses to replace an unmarked existing directory.

## Task 2: Add CLI tests

- File: `tests/test_external_dogfood_cli.py`
- Verify JSON output includes the dogfood report.
- Verify `--strict-live` returns non-zero when OpenAI live preflight fails.
- Verify `pyproject.toml` exposes `muse-external-dogfood`.

## Task 3: Implement dogfood API and CLI

- Files:
  - `src/muse/external_dogfood.py`
  - `src/muse/external_dogfood_cli.py`
  - `pyproject.toml`
- Reuse `render_mcp_config`, `render_agent_instructions`, and
  `check_live_openai_environment`.
- Protect existing directories with `.muse-external-dogfood`.
- Keep default behavior no-spend.

## Task 4: Document the command

- Files:
  - `README.md`
  - `docs/integrations/mcp-agent-hosts.md`
- Add copy-pasteable usage showing how to validate an external repo before
  connecting a real agent host.

## Verification

- `python -m pytest tests/test_external_dogfood.py tests/test_external_dogfood_cli.py`
- `python -m pytest tests/test_mcp_config_packs.py`
- `python -m pytest`
- `python -m ruff check .`
