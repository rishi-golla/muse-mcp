# Provider Posture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MCP/smoke usage live-first by default while preserving deterministic as an explicit test provider.

**Architecture:** Add a small runtime-defaults module that reads environment defaults. MCP and smoke tooling use those defaults only when callers omit values. The core middleware keeps explicit provider validation and deterministic support, so tests and CI remain free and reproducible.

**Tech Stack:** Python 3.12, Pydantic-compatible validation, FastMCP, pytest, Markdown.

---

## File Map

- Create `src/creativity_layer/runtime_defaults.py`: environment parsing helpers.
- Create `tests/test_runtime_defaults.py`: direct parser tests.
- Modify `src/creativity_layer/mcp_server.py`: default omitted provider/effort/privacy/budget from runtime defaults.
- Modify `src/creativity_layer/mcp_smoke.py`: same defaults for smoke command.
- Modify `tests/test_mcp_server.py`: omitted provider should be live-first; explicit deterministic still works.
- Modify `tests/test_mcp_smoke.py`: omitted provider/env override tests.
- Modify docs in `README.md`, `docs/integrations/mcp-agent-hosts.md`, and `docs/integrations/agent-dogfood-playbook.md`.
- Modify `tests/test_mcp_config_packs.py`: docs posture tests.

## Task 1: Runtime Defaults Parser

**Files:**
- Create: `tests/test_runtime_defaults.py`
- Create: `src/creativity_layer/runtime_defaults.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert absent env resolves to provider `live_openai`, effort `quick`, privacy `research`, no budget override; env values override those fields; invalid budget raises a clear `ValueError`; blank env values are ignored.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_runtime_defaults.py -q`
Expected: FAIL because `runtime_defaults` does not exist.

- [ ] **Step 3: Implement parser**

Create `RuntimeDefaults` frozen dataclass and `RuntimeDefaults.from_environment(environ=os.environ)` that reads:

```text
CREATIVITY_LAYER_PROVIDER_MODE
CREATIVITY_LAYER_EFFORT
CREATIVITY_LAYER_PRIVACY
CREATIVITY_LAYER_BUDGET_USD
```

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_runtime_defaults.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\creativity_layer\runtime_defaults.py tests\test_runtime_defaults.py
git commit -m "feat: add runtime provider defaults"
```

## Task 2: MCP and Smoke Live-First Defaults

**Files:**
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_smoke.py`
- Modify: `src/creativity_layer/mcp_server.py`
- Modify: `src/creativity_layer/mcp_smoke.py`

- [ ] **Step 1: Write failing tests**

Add tests that omitted MCP/smoke provider mode returns `provider_mode: live_openai` with `configuration_error` when OpenAI env is absent; explicit deterministic still returns finalists; env provider mode `deterministic` makes omitted smoke/MCP deterministic; env effort/budget defaults are reflected in the payload.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_mcp_server.py tests/test_mcp_smoke.py -q`
Expected: FAIL because omitted provider still defaults deterministic and env defaults are unused.

- [ ] **Step 3: Implement defaults wiring**

Use `RuntimeDefaults.from_environment()` in MCP and smoke when args are omitted. Keep explicit call arguments highest priority.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_mcp_server.py tests/test_mcp_smoke.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\creativity_layer\mcp_server.py src\creativity_layer\mcp_smoke.py tests\test_mcp_server.py tests\test_mcp_smoke.py
git commit -m "feat: make mcp defaults live first"
```

## Task 3: Documentation Posture

**Files:**
- Modify: `tests/test_mcp_config_packs.py`
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`
- Modify: `docs/integrations/agent-dogfood-playbook.md`

- [ ] **Step 1: Write failing docs tests**

Add tests that README and MCP docs mention live-first defaults, deterministic test provider, runtime env variables, and explicit deterministic test usage.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`
Expected: FAIL because docs still frame deterministic as the common default.

- [ ] **Step 3: Update docs**

Document live-first setup, deterministic test mode, and env defaults.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests\test_mcp_config_packs.py README.md docs\integrations\mcp-agent-hosts.md docs\integrations\agent-dogfood-playbook.md
git commit -m "docs: document live first provider posture"
```

## Final Verification

- [ ] `python -m pytest -q`
- [ ] `python -m pytest --cov=creativity_layer --cov-fail-under=90`
- [ ] `python -m ruff check .`
- [ ] `git diff --check`
- [ ] Request code review.
- [ ] Push branch and create PR.
