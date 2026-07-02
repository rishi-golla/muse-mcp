# MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a transport-neutral middleware runner and expose it through an MCP stdio server for agent workflow integration.

**Architecture:** `CreativeMiddlewareRunner` owns the stable request/result contract and engine orchestration. `mcp_server.py` only registers a `muse_plan` tool and delegates to the runner.

**Tech Stack:** Python 3.12, Pydantic v2, existing `CreativeEngine`, official `mcp` Python SDK, pytest, Ruff.

---

## File Map

- Create `src/muse/middleware.py`: request/result models, runner defaults, JSON-safe finalist serialization.
- Create `src/muse/mcp_server.py`: MCP server factory, pure tool function, console entry point.
- Create `tests/test_middleware.py`: runner behavior and JSON contract tests.
- Create `tests/test_mcp_server.py`: MCP adapter behavior and default-runner wiring tests.
- Modify `pyproject.toml`: add `mcp` dependency and `muse-mcp` script.
- Modify `README.md`: document MCP integration for agents.

## Task 1: Middleware Runner Contract

**Files:**
- Create: `tests/test_middleware.py`
- Create: `src/muse/middleware.py`

- [ ] **Step 1: Write failing tests**

```python
from muse.middleware import CreativePlanRequest, CreativeMiddlewareRunner


def test_runner_returns_json_safe_operational_plan_from_repo_signals():
    request = CreativePlanRequest(
        goal="Design a debugging workflow for a TypeScript monorepo with flaky CI",
        repo_signals={
            "file_paths": ("pnpm-workspace.yaml", "apps/web/package.json"),
            "changed_files": ("packages/ui/src/Button.tsx",),
            "test_commands": ("pnpm test --filter apps/web -- --shard=2/4",),
            "ci_logs": ("Vitest shard 2 failed after Playwright smoke tests",),
            "dependency_hints": ("apps/web depends on packages/ui",),
            "detected_languages": ("TypeScript",),
            "detected_frameworks": ("Vitest", "Playwright"),
        },
        seed_count=4,
        finalist_count=2,
        max_generations=1,
        budget_usd=0.35,
    )

    result = CreativeMiddlewareRunner.deterministic().run(request)

    assert result["stopped_reason"] == "generation_limit"
    assert result["generated_count"] >= 4
    assert result["finalist_count"] == 2
    assert result["context_tags"] == ["typescript", "vitest", "playwright"]
    assert "test shards" in result["finalists"][0]["agent_workflow"][1]
    assert result["finalists"][0]["verification_strategy"]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_middleware.py -q`
Expected: FAIL because `muse.middleware` does not exist.

- [ ] **Step 3: Implement minimal runner**

Create request defaults, instantiate deterministic providers, build `RepoSignals`, call `build_task_context`, run `CreativeEngine`, and return a JSON-safe dict.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_middleware.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src\muse\middleware.py tests\test_middleware.py
git commit -m "feat: add middleware runner"
```

## Task 2: MCP Adapter

**Files:**
- Create: `tests/test_mcp_server.py`
- Create: `src/muse/mcp_server.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing tests**

```python
from muse.mcp_server import build_mcp_server, muse_plan


def test_muse_plan_tool_delegates_to_middleware_runner():
    result = muse_plan(
        goal="Design a backend middleware planning hook for arbitrary repos",
        repo_signals={"detected_languages": ("Python",)},
        seed_count=2,
        finalist_count=1,
        max_generations=0,
        budget_usd=0.20,
    )

    assert result["finalist_count"] == 1
    assert result["finalists"][0]["inputs_required"]
    assert result["context_tags"] == ["python"]


def test_build_mcp_server_returns_named_server():
    server = build_mcp_server()

    assert server is not None
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_mcp_server.py -q`
Expected: FAIL because `muse.mcp_server` does not exist.

- [ ] **Step 3: Implement adapter**

Add the `mcp` dependency, register `muse_plan`, expose `build_mcp_server()`, and add `main()` for stdio startup.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add pyproject.toml src\muse\mcp_server.py tests\test_mcp_server.py
git commit -m "feat: expose muse mcp server"
```

## Task 3: Agent-Facing Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write doc expectation test**

Add an assertion in `tests/test_package.py` or `tests/test_mcp_server.py` that `pyproject.toml` contains `muse-mcp`.

- [ ] **Step 2: Verify RED**

Run the targeted test and confirm it fails before docs/script metadata are complete.

- [ ] **Step 3: Update README**

Document `muse-mcp`, a generic MCP config snippet, and an example `muse_plan` payload with repo signals.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests/test_middleware.py tests/test_mcp_server.py -q
python -m ruff check .
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add README.md tests\test_mcp_server.py
git commit -m "docs: document agent mcp integration"
```

## Final Verification

- [ ] `python -m pytest -q`
- [ ] `python -m pytest --cov=muse --cov-fail-under=90`
- [ ] `python -m ruff check .`
- [ ] `git status --short`
- [ ] Push branch and open PR.
