# V3-K Search Policy and Query Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add provider policy, strict search behavior, and repo-signal-aware query planning to MCP search context.

**Architecture:** Extend the existing V3-J `SearchContextResolver` instead of creating a second search layer. Middleware owns strict short-circuit behavior and provider policy selection. MCP and smoke stay thin field-forwarding adapters.

**Tech Stack:** Python 3.12, Pydantic v2, existing search provider contracts, FastMCP, pytest, Ruff.

---

## Task 1: Search Policy and Query Metadata

**Files:**
- Modify: `src/muse/search_context.py`
- Modify: `tests/test_search_context.py`

- [ ] Write failing tests for `SearchProviderPolicy`, query planning from stack/failure signals, deep prior-art/analogy queries, provider policy metadata, and strict skipped result metadata.
- [ ] Run `python -m pytest tests/test_search_context.py -q` and confirm RED.
- [ ] Implement provider policy enum, strict metadata fields, query records, query planning helpers, and strict skipped result marker.
- [ ] Run `python -m pytest tests/test_search_context.py -q` and confirm GREEN.
- [ ] Commit `feat: add search query planning policy`.

## Task 2: Runtime Defaults and Middleware Strict Behavior

**Files:**
- Modify: `src/muse/runtime_defaults.py`
- Modify: `src/muse/middleware.py`
- Modify: `tests/test_runtime_defaults.py`
- Modify: `tests/test_middleware.py`

- [ ] Write failing tests for `MUSE_SEARCH_PROVIDER`, `MUSE_SEARCH_STRICT`, explicit override behavior, config serialization, and strict search short-circuit.
- [ ] Run `python -m pytest tests/test_runtime_defaults.py tests/test_middleware.py -q` and confirm RED.
- [ ] Add runtime defaults and middleware request fields.
- [ ] Make strict search failures return top-level `configuration_error` with `search_context` metadata.
- [ ] Run `python -m pytest tests/test_runtime_defaults.py tests/test_middleware.py tests/test_search_context.py -q` and confirm GREEN.
- [ ] Commit `feat: add strict search policy to middleware`.

## Task 3: MCP and Smoke Forwarding

**Files:**
- Modify: `src/muse/mcp_server.py`
- Modify: `src/muse/mcp_smoke.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_smoke.py`

- [ ] Write failing tests for `search_provider` and `search_strict` forwarding from MCP and smoke.
- [ ] Run `python -m pytest tests/test_mcp_server.py tests/test_mcp_smoke.py -q` and confirm RED.
- [ ] Add MCP function parameters and smoke flags while preserving old positional numeric arguments.
- [ ] Run `python -m pytest tests/test_mcp_server.py tests/test_mcp_smoke.py -q` and confirm GREEN.
- [ ] Commit `feat: expose search policy through mcp`.

## Task 4: Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`
- Modify: `docs/integrations/agent-dogfood-playbook.md`
- Modify: `tests/test_mcp_config_packs.py`

- [ ] Write failing docs test for provider policy and strict mode.
- [ ] Run `python -m pytest tests/test_mcp_config_packs.py -q` and confirm RED.
- [ ] Document `search_provider`, `search_strict`, env defaults, strict failure semantics, and no repo crawling.
- [ ] Run `python -m pytest tests/test_mcp_config_packs.py -q` and confirm GREEN.
- [ ] Commit `docs: document search policy controls`.

## Final Verification

- [ ] Run focused tests.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check .`.
- [ ] Run `git diff --check origin/main...HEAD`.
- [ ] Request code review and fix important findings.
- [ ] Push and create PR.
