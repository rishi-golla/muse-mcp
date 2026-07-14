# V5-G Agent-Native Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace public low-level MCP tuning with agent-native `normal` and `extensive` modes.

**Architecture:** Add an `AgentMode` enum to middleware and map modes to existing effort presets. Keep engine run-shape controls internal, simplify the MCP signature, and update generated instructions/docs to make `muse-project-init` plus backend `muse_plan` calls the normal workflow.

**Tech Stack:** Python 3.12, Pydantic models, FastMCP, pytest, ruff.

---

### Task 1: Middleware mode contract

**Files:**
- Modify: `src/muse/middleware.py`
- Test: `tests/test_middleware.py`

- [ ] **Step 1: Write failing tests for `normal` and `extensive` modes**
- [ ] **Step 2: Verify RED with `python -m pytest tests/test_middleware.py -q`**
- [ ] **Step 3: Implement `AgentMode` and mode-to-run-shape mapping**
- [ ] **Step 4: Verify GREEN with `python -m pytest tests/test_middleware.py -q`**

### Task 2: MCP tool surface

**Files:**
- Modify: `src/muse/mcp_server.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing MCP tests for mode support and signature cleanup**
- [ ] **Step 2: Verify RED with `python -m pytest tests/test_mcp_server.py -q`**
- [ ] **Step 3: Replace public effort/budget/seed arguments with `mode`**
- [ ] **Step 4: Verify GREEN with `python -m pytest tests/test_mcp_server.py -q`**

### Task 3: Agent instructions and docs

**Files:**
- Modify: `src/muse/agent_instructions.py`
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`
- Modify: `docs/integrations/agent-dogfood-playbook.md`
- Test: `tests/test_agent_instructions_cli.py`
- Test: `tests/test_mcp_config_packs.py`

- [ ] **Step 1: Write failing assertions for agent-native instructions/docs**
- [ ] **Step 2: Verify RED with focused docs tests**
- [ ] **Step 3: Update generated instructions and public docs**
- [ ] **Step 4: Verify GREEN with focused docs tests**

### Task 4: Final verification and PR

**Files:**
- All files changed in this slice.

- [ ] **Step 1: Run focused tests**
- [ ] **Step 2: Run `python -m pytest`**
- [ ] **Step 3: Run `python -m ruff check .`**
- [ ] **Step 4: Commit, push, and open PR**
