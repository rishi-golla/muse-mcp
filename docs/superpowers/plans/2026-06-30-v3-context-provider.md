# V3-C Context Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-neutral context retrieval layer that converts caller-supplied repo/task facts into `ContextBundle` for middleware-style engine usage.

**Architecture:** Implement a new `context_provider.py` module with immutable request/signal models, a zero-cost deterministic provider, and a helper that builds `TaskContext` from a provider result. Keep filesystem/JSON handling at CLI edges only.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, Ruff, existing `ContextBundle`, `MeteredResponse`, and `OperationQuote` models

---

## Task 1: Context Provider Models

**Files:**
- Create: `src/muse/context_provider.py`
- Create: `tests/test_context_provider.py`

- [ ] Write failing tests for `RepoSignals`, `ContextRequest`, provider quote, and deterministic provider output.
- [ ] Run focused tests and verify RED.
- [ ] Implement minimal models, protocol, and deterministic provider.
- [ ] Run focused tests and verify GREEN.
- [ ] Commit: `feat: add context provider contract`.

## Task 2: Repo-Agnostic Signal Behavior

**Files:**
- Modify: `src/muse/context_provider.py`
- Modify: `tests/test_context_provider.py`

- [ ] Write failing tests for TypeScript monorepo, Python repo, and arbitrary middleware/GraphQL behavior.
- [ ] Verify RED.
- [ ] Implement signal-to-snippet summarization helpers.
- [ ] Verify GREEN.
- [ ] Commit: `feat: derive context from repo signals`.

## Task 3: Engine-Facing Helper

**Files:**
- Modify: `src/muse/context_provider.py`
- Modify: `tests/test_context_provider.py`

- [ ] Write failing tests for helper merging provider context with existing `TaskContext`.
- [ ] Verify RED.
- [ ] Implement `build_task_context(...)`.
- [ ] Verify GREEN.
- [ ] Commit: `feat: add context resolution helper`.

## Task 4: CLI Harness

**Files:**
- Modify: `src/muse/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_live_cli.py`
- Modify: `README.md`

- [ ] Write failing tests for `--repo-signals-file` on deterministic and live paths.
- [ ] Verify RED.
- [ ] Implement JSON edge parser into `RepoSignals` and deterministic context provider.
- [ ] Document the harness.
- [ ] Verify GREEN.
- [ ] Commit: `feat: add repo signals CLI harness`.

## Task 5: Final Review

**Files:**
- Modify only if verification exposes issues.

- [ ] Run `python -m pytest -m "not live_openai" -q --cov=muse --cov-report=term-missing -p no:cacheprovider --basetemp=.pytest-tmp-v3c-final`.
- [ ] Run `python -m ruff check .`.
- [ ] Run `git diff --check origin/main...HEAD`.
- [ ] Request subagent review.
- [ ] Fix any blocking findings with tests.

## Success Checklist

- [ ] No core engine filesystem reads.
- [ ] Middleware can call provider/helper directly.
- [ ] CLI JSON is edge-only.
- [ ] TypeScript and Python repo signals produce distinct context.
- [ ] GraphQL is not invented for arbitrary middleware.
- [ ] Full offline verification passes.
