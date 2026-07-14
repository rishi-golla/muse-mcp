# V5-A Live-Only Public API Plan

## Task 1: Runtime Boundary

- Modify `src/muse/runtime_defaults.py`.
- Add an internal opt-in env var for deterministic provider use.
- Reject deterministic provider mode in public runtime defaults when the opt-in
  is absent.
- Verify with focused runtime-default tests.

## Task 2: MCP And Smoke Contract Tests

- Modify `tests/test_mcp_server.py` and `tests/test_mcp_smoke.py`.
- Keep existing deterministic coverage behind `MUSE_ENABLE_TEST_PROVIDER=1`.
- Add public-path tests that delete the opt-in and assert structured
  `configuration_error` results.

## Task 3: Public Documentation

- Modify `README.md`, `docs/integrations/mcp-agent-hosts.md`, and
  `docs/integrations/agent-dogfood-playbook.md`.
- Replace deterministic onboarding with live OpenAI setup and no-provider smoke
  examples.
- Explain deterministic as an internal maintainer fixture only.

## Task 4: Verification

- Run focused tests for runtime defaults, MCP server, smoke, and open-source
  readiness.
- Run full pytest and ruff.
- Run a no-key smoke command and verify it returns a live OpenAI
  `configuration_error`, proving public defaults are live.
