# V4-E Suggested Next Call Plan

## Architecture

Create a pure helper in `quality_warnings.py` that converts the current
`quality_action_policy` plus safe request metadata into a nullable
`suggested_next_call` object. Middleware computes it once after action-policy
generation, returns it top-level, and mirrors it into `agent_guidance`.

## Tasks

1. Add RED tests for the pure suggestion helper.
   - File: `tests/test_quality_warnings.py`
   - Verify clear policies produce `None`.
   - Verify retry policies produce a `creative_plan` suggestion with escalated
     effort and no raw `repo_signals`.
   - Command:
     `python -m pytest tests\test_quality_warnings.py -q`

2. Implement the pure helper.
   - File: `src/creativity_layer/quality_warnings.py`
   - Add `build_suggested_next_call(...)`.
   - Add small internal mapping from warning names to repo-signal requests.
   - Command:
     `python -m pytest tests\test_quality_warnings.py -q`

3. Add RED middleware and MCP contract tests.
   - Files: `tests/test_middleware.py`, `tests/test_mcp_server.py`
   - Verify warning responses expose top-level and guidance
     `suggested_next_call`.
   - Verify configuration errors expose `None`.
   - Verify FastMCP structured output includes the same field.
   - Command:
     `python -m pytest tests\test_middleware.py tests\test_mcp_server.py -q`

4. Wire middleware serialization.
   - File: `src/creativity_layer/middleware.py`
   - Import `build_suggested_next_call`.
   - Compute the suggestion from request metadata and action policy.
   - Add `suggested_next_call` to normal and configuration-error payloads.
   - Pass it into `_agent_guidance`.
   - Command:
     `python -m pytest tests\test_middleware.py tests\test_mcp_server.py -q`

5. Document the contract.
   - Files: `docs/integrations/agent-dogfood-playbook.md`,
     `tests/test_mcp_config_packs.py`
   - Add a V4-E note describing advisory usage and privacy boundaries.
   - Command:
     `python -m pytest tests\test_mcp_config_packs.py -q`

6. Verify the slice.
   - Commands:
     `python -m pytest -q`
     `python -m ruff check .`
     `creativity-layer-mcp-smoke "Design a retry strategy for AI coding agents" --provider-mode deterministic --repo-language Python`
