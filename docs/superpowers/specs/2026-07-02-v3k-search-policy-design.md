# V3-K Search Policy and Query Planning Design

## Purpose

V3-J added an opt-in search context pipe for MCP. V3-K makes that pipe useful by adding explicit search provider policy, strict/non-strict behavior, richer query planning from repo signals, and more auditable search metadata.

The narrow claim:

> An agent can request search context with clear provider policy and receive query-aware metadata, while search remains opt-in, bounded, and non-crawling.

## Design

Add two request fields:

- `search_provider`: `auto`, `deterministic`, `exa`, or `brave`.
- `search_strict`: boolean, default `false`.

`search_provider` chooses which search provider the resolver should use. `auto` keeps current production preference: Exa when configured, then Brave, with deterministic only for deterministic provider mode and tests. Explicit `exa` or `brave` should report configuration metadata if that provider is unavailable.

`search_strict` controls failure behavior:

- `false`: keep V3-J behavior. Search failures are non-fatal metadata and planning continues.
- `true`: requested search must produce context. Missing approval, missing provider, provider errors, or empty results return a structured configuration error before creative generation.

Improve query planning in `SearchContextResolver`:

- Always include a task-goal evidence query.
- Add a stack/repo query when language, framework, package, or dependency signals exist.
- Add a failure/log query when CI logs or test commands exist.
- For `deep`, add a prior-art query and an analogy query.

Return richer metadata:

- selected provider,
- provider policy,
- strict flag,
- attempted query texts and purposes,
- per-query source counts,
- skipped reason and sanitized errors.

## Boundaries

Included:

- Search provider policy on middleware/MCP/smoke.
- Strict search behavior.
- Query planning from existing `RepoSignals`.
- Query-aware metadata.
- No-network deterministic tests.
- Docs for provider policy and strict mode.

Excluded:

- No repo crawling.
- No new hosted API or daemon.
- No persistent cache changes.
- No mandatory live provider tests.
- No claim that search proves originality.

## Error Handling

Invalid provider policy should return a structured configuration error. In non-strict mode, search problems stay in `search_context` metadata and creative planning proceeds. In strict mode, search problems become a top-level configuration error with the same `search_context` metadata so agents can explain exactly why planning did not run.

## Files

- `src/creativity_layer/search_context.py`: provider policy, strict behavior, query planner, metadata.
- `src/creativity_layer/runtime_defaults.py`: `CREATIVITY_LAYER_SEARCH_PROVIDER` and `CREATIVITY_LAYER_SEARCH_STRICT`.
- `src/creativity_layer/middleware.py`: request fields, strict search short-circuit, provider policy resolver.
- `src/creativity_layer/mcp_server.py`: expose provider and strict fields.
- `src/creativity_layer/mcp_smoke.py`: add flags.
- Tests in `tests/test_search_context.py`, `tests/test_runtime_defaults.py`, `tests/test_middleware.py`, `tests/test_mcp_server.py`, `tests/test_mcp_smoke.py`, and `tests/test_mcp_config_packs.py`.
- Docs in `README.md`, `docs/integrations/mcp-agent-hosts.md`, and `docs/integrations/agent-dogfood-playbook.md`.

## Verification

Tests must prove:

- Defaults are `search_provider: auto` and `search_strict: false`.
- Explicit values override runtime defaults.
- Strict mode short-circuits when search is requested but skipped.
- Query metadata includes stack/failure/prior-art query planning when repo signals exist.
- MCP and smoke forward fields without breaking existing positional arguments.
- Docs describe provider policy, strict mode, and no repo crawling.
