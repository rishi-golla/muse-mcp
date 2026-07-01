# Agent Dogfood Ergonomics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cheap MCP effort presets, top-level agent guidance, and a dogfood playbook for using creativity-layer while coding normally.

**Architecture:** Effort presets resolve inside middleware before `RunConfig` is built, so MCP and future API callers share the same behavior. MCP and smoke tooling expose the preset as a simple optional argument. Documentation explains how an agent should call the tool without making the CLI the primary product.

**Tech Stack:** Python 3.12, Pydantic v2, FastMCP, pytest, Markdown.

---

## File Map

- Modify `src/creativity_layer/middleware.py`: add `EffortPreset`, preset resolution, guidance serialization.
- Modify `src/creativity_layer/mcp_server.py`: add `effort` argument.
- Modify `src/creativity_layer/mcp_smoke.py`: add `--effort`.
- Modify `tests/test_middleware.py`: request defaults, override behavior, guidance assertions.
- Modify `tests/test_mcp_server.py`: MCP tool effort behavior.
- Modify `tests/test_mcp_smoke.py`: smoke CLI forwards effort.
- Create `docs/integrations/agent-dogfood-playbook.md`: coding-loop playbook.
- Modify `README.md` and `docs/integrations/mcp-agent-hosts.md`: link playbook and mention presets.

## Task 1: Middleware Effort Presets and Guidance

**Files:**
- Modify: `tests/test_middleware.py`
- Modify: `src/creativity_layer/middleware.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert default `CreativePlanRequest(goal=...)` resolves to effort `quick`, budget `0.20`, seed count `2`, finalist count `1`, and max generations `0`; `effort="standard"` resolves to `0.35/4/2/1`; `effort="deep"` resolves to `0.75/6/3/2`; explicit numeric values override a preset; and results include `agent_guidance` with `recommended_agent_loop`, `verification_required`, and `escalation_policy`.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_middleware.py -q`
Expected: FAIL because `effort` and `agent_guidance` do not exist.

- [ ] **Step 3: Implement presets and guidance**

Add `EffortPreset`, a before validator that fills omitted config fields from the selected preset, include `effort` in `config`, and add top-level `agent_guidance` in `_serialize_result` and configuration-error results.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_middleware.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\creativity_layer\middleware.py tests\test_middleware.py
git commit -m "feat: add agent effort presets"
```

## Task 2: MCP and Smoke Ergonomics

**Files:**
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_smoke.py`
- Modify: `src/creativity_layer/mcp_server.py`
- Modify: `src/creativity_layer/mcp_smoke.py`

- [ ] **Step 1: Write failing tests**

Add tests that call `creative_plan(..., effort="deep")` and assert `config.effort == "deep"` with deep preset values, that default MCP calls use quick values, and that `run_smoke(["goal", "--effort", "standard"])` forwards standard effort into printed JSON.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_mcp_server.py tests/test_mcp_smoke.py -q`
Expected: FAIL because MCP and smoke do not accept `effort`.

- [ ] **Step 3: Implement MCP/smoke arguments**

Add `effort` to `creative_plan` and `mcp_smoke` parser/payload. Keep explicit numeric arguments supported.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_mcp_server.py tests/test_mcp_smoke.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\creativity_layer\mcp_server.py src\creativity_layer\mcp_smoke.py tests\test_mcp_server.py tests\test_mcp_smoke.py
git commit -m "feat: expose mcp effort presets"
```

## Task 3: Dogfood Playbook Docs

**Files:**
- Modify: `tests/test_mcp_config_packs.py` or create a focused docs test.
- Create: `docs/integrations/agent-dogfood-playbook.md`
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`

- [ ] **Step 1: Write failing docs tests**

Add tests that assert the playbook exists, mentions `quick`, `standard`, and `deep`, describes before-edit/after-failure/after-fix call points, and is linked from README and MCP host docs.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`
Expected: FAIL because the playbook does not exist.

- [ ] **Step 3: Add docs**

Write the playbook and links. Keep language explicit that MCP is the workflow surface and the CLI/smoke runner is only local verification.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests\test_mcp_config_packs.py docs\integrations\agent-dogfood-playbook.md docs\integrations\mcp-agent-hosts.md README.md
git commit -m "docs: add agent dogfood playbook"
```

## Final Verification

- [ ] `python -m pytest -q`
- [ ] `python -m pytest --cov=creativity_layer --cov-fail-under=90`
- [ ] `python -m ruff check .`
- [ ] `git diff --check`
- [ ] Request code review.
- [ ] Push branch and create PR.
