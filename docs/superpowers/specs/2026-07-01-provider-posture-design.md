# Provider Posture Design

## Goal

Make user-facing MCP usage live-first while preserving deterministic execution as an explicit test provider for CI, local development, and reproducible protocol tests.

## Current Problem

The MCP surface is technically working, but omitted provider mode currently behaves like deterministic fixture mode. That is safe for tests but bad for real users because deterministic output looks generic and can make the project appear low quality. For open-source usage, a normal user should either get live OpenAI output or a clear setup error explaining what is missing.

## Selected Design

Add runtime defaults for MCP/smoke/user-facing planning:

- `CREATIVITY_LAYER_PROVIDER_MODE`
- `CREATIVITY_LAYER_EFFORT`
- `CREATIVITY_LAYER_PRIVACY`
- `CREATIVITY_LAYER_BUDGET_USD`

When no provider mode is explicitly supplied, the MCP tool and smoke runner should default to `live_openai`. If live environment is incomplete, the result remains a structured `configuration_error` with `agent_guidance` and no provider cost. Tests and CI should pass `provider_mode="deterministic"` explicitly.

Keep the internal enum value `deterministic` for compatibility, but update documentation to call it the deterministic test provider. Do not delete it, because it keeps tests fast, free, and repeatable.

## Boundaries

- No hosted API.
- No new provider implementation.
- No real OpenAI calls in normal tests.
- No breaking change for explicit `provider_mode="deterministic"` callers.
- No removal of deterministic test mode.

## Files

- `src/creativity_layer/runtime_defaults.py`: environment parsing for user-facing defaults.
- `src/creativity_layer/mcp_server.py`: use runtime defaults for omitted provider/effort/privacy/budget.
- `src/creativity_layer/mcp_smoke.py`: use runtime defaults for omitted CLI args.
- `tests/test_runtime_defaults.py`: direct runtime default parsing tests.
- `tests/test_mcp_server.py`: live-first omitted default and explicit deterministic behavior.
- `tests/test_mcp_smoke.py`: smoke runner default behavior and env override tests.
- `docs/integrations/mcp-agent-hosts.md`: live-first setup docs.
- `docs/integrations/agent-dogfood-playbook.md`: recommend explicit deterministic only for tests.
- `README.md`: describe user-facing live-first posture and deterministic test provider.

## Validation

Tests should prove that omitted MCP/smoke provider mode defaults to `live_openai`, explicit deterministic remains stable, runtime env defaults are honored, invalid env values return structured configuration errors instead of tracebacks, and docs no longer imply deterministic output represents product quality.

## Spec Self-Review

- This slice changes provider posture, not creative quality.
- Deterministic stays available for engineering stability.
- User-facing behavior becomes honest: live output or clear setup error.
- No networked tests are introduced.
