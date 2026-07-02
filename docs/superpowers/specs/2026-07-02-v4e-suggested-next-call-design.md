# V4-E Suggested Next Call Design

## Problem

V4-D tells agent hosts when a result has quality issues and whether effort should
escalate, but hosts still have to invent the next MCP request shape. That makes
agent loops inconsistent and easy to overfit to one client.

## Design

Add an advisory `suggested_next_call` object to normal middleware/MCP responses
when `quality_action_policy` recommends review or retry. The object must be
machine-readable enough for an agent host to call `creative_plan` again, while
remaining non-executing and privacy-conscious.

The suggested call should:

- set `tool` to `creative_plan`;
- set `automatic` to `false`;
- explain that the reason is `quality_action_policy`;
- carry safe request fields: `goal`, `provider_mode`, `privacy`, `effort`,
  `search_mode`, `search_provider`, `search_strict`, and
  `max_context_snippets`;
- use `quality_action_policy.escalate_effort_to` when available;
- avoid copying raw `repo_signals` or logs into the suggestion;
- include `repo_signal_requests` so the host knows which observed facts to pass
  again or improve.

When the policy is clear, `suggested_next_call` should be `null`.
Configuration-error responses should also return `null`.

Mirror the same object inside `agent_guidance` so hosts that only inspect
guidance can find it without scanning the full payload.

## Scope

Modify:

- `src/creativity_layer/quality_warnings.py`
- `src/creativity_layer/middleware.py`
- `tests/test_quality_warnings.py`
- `tests/test_middleware.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_config_packs.py`
- `docs/integrations/agent-dogfood-playbook.md`

Do not add automatic retries, provider calls, crawler behavior, or an HTTP API.
