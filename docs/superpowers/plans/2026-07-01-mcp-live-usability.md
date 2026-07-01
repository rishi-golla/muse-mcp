# MCP Live Usability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let MCP callers opt into live OpenAI runs with cheap defaults and structured configuration errors.

**Architecture:** Middleware owns provider selection and live OpenAI construction. MCP remains a thin tool adapter. A smoke command probes FastMCP registration and invocation without launching stdio.

**Tech Stack:** Python 3.12, Pydantic v2, OpenAI Responses provider already in the repo, FastMCP, pytest, Ruff.

---

## File Map

- Modify `src/creativity_layer/middleware.py`: provider mode, live runner construction, pricing loading, structured error response.
- Modify `src/creativity_layer/mcp_server.py`: expose `provider_mode` and `privacy` tool inputs.
- Create `src/creativity_layer/mcp_smoke.py`: in-process FastMCP smoke command.
- Modify `pyproject.toml`: add `creativity-layer-mcp-smoke` script.
- Modify `README.md`: document deterministic/live MCP usage and env setup.
- Modify `tests/test_middleware.py`: middleware mode and live configuration tests.
- Modify `tests/test_mcp_server.py`: MCP provider mode and structured error tests.
- Create `tests/test_mcp_smoke.py`: smoke command test.

## Task 1: Middleware Provider Modes

**Files:**
- Modify `tests/test_middleware.py`
- Modify `src/creativity_layer/middleware.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert default `provider_mode` is deterministic, `live_openai` returns a structured configuration error when environment variables are missing, and fake injected live providers can run through `CreativeMiddlewareRunner.live_openai(...)`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_middleware.py -q`
Expected: FAIL because `provider_mode`, `run_creative_plan`, and live constructors do not exist.

- [ ] **Step 3: Implement middleware**

Add `ProviderMode`, `ConfigurationError`, `run_creative_plan`, `CreativeMiddlewareRunner.live_openai(...)`, pricing-file loading, and result serialization with `provider_mode`.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_middleware.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src\creativity_layer\middleware.py tests\test_middleware.py
git commit -m "feat: add live provider mode to middleware"
```

## Task 2: MCP Tool Inputs and Structured Errors

**Files:**
- Modify `tests/test_mcp_server.py`
- Modify `src/creativity_layer/mcp_server.py`

- [ ] **Step 1: Write failing tests**

Add tests that call `creative_plan(provider_mode="live_openai")` with missing env and assert `stopped_reason == "configuration_error"`. Add a FastMCP invocation test that passes `provider_mode`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_mcp_server.py -q`
Expected: FAIL because the MCP tool does not expose provider mode.

- [ ] **Step 3: Implement MCP adapter changes**

Add `provider_mode` and `privacy` parameters, and delegate to `run_creative_plan`.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src\creativity_layer\mcp_server.py tests\test_mcp_server.py
git commit -m "feat: add mcp live mode inputs"
```

## Task 3: MCP Smoke Harness and Docs

**Files:**
- Create `src/creativity_layer/mcp_smoke.py`
- Create `tests/test_mcp_smoke.py`
- Modify `pyproject.toml`
- Modify `README.md`

- [ ] **Step 1: Write failing smoke test**

Add a test that calls the smoke command with deterministic defaults and asserts it returns a JSON payload with a finalist.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_mcp_smoke.py -q`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement smoke harness and docs**

Add the smoke module, script entry point, and README instructions for deterministic and live MCP testing.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/test_mcp_smoke.py tests/test_mcp_server.py tests/test_middleware.py -q
python -m ruff check .
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src\creativity_layer\mcp_smoke.py tests\test_mcp_smoke.py pyproject.toml README.md
git commit -m "docs: add mcp live smoke workflow"
```

## Final Verification

- [ ] `python -m pytest -q`
- [ ] `python -m pytest --cov=creativity_layer --cov-fail-under=90`
- [ ] `python -m ruff check .`
- [ ] `git diff --check`
- [ ] Request code review.
- [ ] Push branch and create PR.
