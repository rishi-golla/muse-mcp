# V3-J Search Context MCP Design

## Purpose

V3-J makes the MCP planning surface capable of using bounded search context when an agent explicitly asks for it. V3-I made MCP live-first, but live model output still depends mostly on the model's prior knowledge plus caller-supplied repo signals. This slice adds a controlled search-context switch so agents can request better grounding without turning muse into a repo crawler, daemon, or CLI replacement.

The narrow claim for this slice:

> An MCP caller can opt into search context for a planning request, receive JSON-safe metadata about what search context was used or skipped, and preserve cost/privacy controls.

## Approach

Use an explicit `search_mode` field on the middleware and MCP request:

- `off`: default. No search context is attempted.
- `light`: gather a small bounded context set intended for normal planning.
- `deep`: gather a broader bounded context set for higher-effort planning.

`search_mode` is intentionally independent of `effort`. `effort` controls creative search budget and generations; `search_mode` controls external context. This avoids hidden network calls when a user only wanted a deeper model run.

Live search must be gated by `MUSE_LIVE_SEARCH_APPROVED=1`. If search is requested without approval or without provider credentials, the MCP result should still return a normal planning payload when possible, plus search metadata explaining that search was skipped. Search setup problems should not crash the agent host.

## Scope

Included:

- Add request-level `search_mode` validation to the transport-neutral middleware and MCP tool.
- Add runtime default support with `MUSE_SEARCH_MODE`.
- Add a small `SearchContextResolver` that converts search mode, approval state, and available repo/task facts into a context bundle.
- Reuse existing search/context models rather than inventing a second source format.
- Return top-level `search_context` metadata in MCP/middleware payloads.
- Keep deterministic tests no-network by using deterministic/fake search providers.
- Document how agents should opt in and why `off` remains the default.

Excluded:

- No automatic search from `quick`, `standard`, or `deep`.
- No repository crawling.
- No persistent hosted cache.
- No new HTTP API or daemon.
- No claim that search proves originality.
- No mandatory live Exa/Brave/OpenAI smoke in normal tests.

## Data Flow

1. Agent observes repo/task facts and calls `muse_plan`.
2. MCP applies explicit request fields first, then runtime defaults.
3. Middleware validates `search_mode`.
4. If `search_mode` is `off`, middleware runs exactly as it does today and returns `search_context.mode: "off"`.
5. If `search_mode` is `light` or `deep`, middleware asks `SearchContextResolver` for bounded context.
6. Resolver checks `MUSE_LIVE_SEARCH_APPROVED`.
7. If not approved, resolver returns skipped metadata and no context snippets.
8. If approved and configured, resolver builds search queries from task goal and supplied repo signals, executes bounded searches through existing providers, converts results to `ContextSnippet` data, and returns metadata.
9. Middleware merges returned context into the task before running the engine.
10. Result serialization includes `search_context` with mode, used/skipped state, source count, context tags, and sanitized error messages.

## Search Modes

`off`:

- No search provider construction.
- No approval required.
- Metadata reports no search used.

`light`:

- Intended for normal live MCP dogfooding.
- Small result limits and snippet counts.
- Query focus: task goal plus the most relevant repo/framework tags.
- Prefer broad prior-art/evidence context over distant inspiration.

`deep`:

- Intended for higher-cost planning before important implementation decisions.
- More snippets than `light`, still bounded.
- May include both inspiration-style and prior-art-style context.
- Still requires explicit approval and credentials.

## Privacy and Cost

Search is off by default because task goals and repo facts may contain private product details. Approval must be explicit through environment or a later host-managed policy. This slice uses `MUSE_LIVE_SEARCH_APPROVED=1` as the local approval mechanism because it is already documented for live search tests and avoids adding persistence.

Search metadata must not include API keys, raw provider response objects, or unbounded page text. Private traces should continue to hash sensitive content through existing trace behavior.

## Error Handling

Search setup and provider failures should be non-fatal for planning unless the caller later asks for strict search. For V3-J:

- Invalid `search_mode` returns a structured validation/configuration error.
- Requested search without approval returns finalists generated without search plus `search_context.skipped_reason: "approval_required"`.
- Missing live search credentials returns finalists generated without search plus `search_context.skipped_reason: "configuration_error"`.
- Provider search failures return finalists generated without search plus sanitized search errors.

This keeps agent workflows moving while making it obvious that search grounding was not used.

## Files

- `src/muse/search_context.py`: search mode enum, resolver, metadata model, and no-network resolver helpers.
- `src/muse/runtime_defaults.py`: add `MUSE_SEARCH_MODE`.
- `src/muse/middleware.py`: accept search mode, merge resolved context, serialize search metadata.
- `src/muse/mcp_server.py`: expose `search_mode`.
- `src/muse/mcp_smoke.py`: add `--search-mode`.
- `tests/test_search_context.py`: resolver and metadata behavior.
- `tests/test_middleware.py`, `tests/test_mcp_server.py`, `tests/test_mcp_smoke.py`: request/default serialization.
- `tests/test_mcp_config_packs.py`, `README.md`, `docs/integrations/mcp-agent-hosts.md`, `docs/integrations/agent-dogfood-playbook.md`: documentation contract.

## Verification

Tests must prove:

- Omitted search mode defaults to `off`.
- `MUSE_SEARCH_MODE` is honored only when the caller omits `search_mode`.
- Explicit `search_mode` overrides env defaults.
- Invalid search modes fail as structured request/configuration errors.
- `light` or `deep` without approval skips search and reports why.
- Deterministic/fake search context can be merged into the task and reflected in finalists/workflow metadata.
- MCP and smoke expose search mode without breaking existing positional compatibility.
- Docs make opt-in search, approval, and privacy behavior clear.

## Rationale

This is the right next V3 slice because it improves real agent-facing output quality while preserving the architecture decision that agents supply repo context and MCP stays a thin planning middleware. It uses search infrastructure already present in the repo, but it does not make search automatic, expensive, or privacy-surprising.
