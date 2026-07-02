# V4-F Agent Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact `agent_handoff` envelope to MCP responses so coding agents can route the next step without re-deriving policy from multiple fields.

**Architecture:** `middleware.py` owns response serialization, so it will compute the handoff from already-derived finalists, `quality_action_policy`, `suggested_next_call`, and configuration-error state. The MCP server remains a thin adapter and inherits the new field from the middleware result.

**Tech Stack:** Python 3.12, Pydantic models already in repo, pytest, Ruff, FastMCP tests.

---

### Task 1: Add Middleware Contract Tests

**Files:**
- Modify: `tests/test_middleware.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting that warning results produce:

```python
handoff = result["agent_handoff"]
assert handoff["status"] == "retry_recommended"
assert handoff["recommended_action"] == "retry_muse_plan"
assert handoff["use_current_finalist"] is False
assert handoff["selected_finalist_id"] == result["finalists"][0]["id"]
assert handoff["suggested_next_call_available"] is True
assert handoff == result["agent_guidance"]["agent_handoff"]
```

Add a configuration-error assertion:

```python
assert result["agent_handoff"] == {
    "status": "blocked",
    "recommended_action": "fix_configuration",
    "use_current_finalist": False,
    "selected_finalist_id": None,
    "suggested_next_call_available": False,
    "verification_required": True,
}
```

- [ ] **Step 2: Run tests to verify RED**

Run:
`python -m pytest tests\test_middleware.py::test_runner_returns_agent_handoff_for_warning_results tests\test_middleware.py::test_configuration_error_includes_blocked_agent_handoff -q`

Expected: fail with missing `agent_handoff`.

### Task 2: Implement Handoff Serialization

**Files:**
- Modify: `src/muse/middleware.py`

- [ ] **Step 1: Add helper functions**

Add `_agent_handoff(...)` and `_configuration_error_handoff()` near the existing
agent guidance helpers. Derive retry/review/ready states from
`quality_action_policy["status"]` and `suggested_next_call`.

- [ ] **Step 2: Wire normal responses**

Compute `agent_handoff` in `_serialize_result`, include it top-level, and pass
it into `_agent_guidance`.

- [ ] **Step 3: Wire configuration errors**

Return `_configuration_error_handoff()` top-level and inside `_agent_guidance`.

- [ ] **Step 4: Run tests to verify GREEN**

Run:
`python -m pytest tests\test_middleware.py::test_runner_returns_agent_handoff_for_warning_results tests\test_middleware.py::test_configuration_error_includes_blocked_agent_handoff -q`

Expected: pass.

### Task 3: Add MCP Boundary Test

**Files:**
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Write failing FastMCP test**

Add a test that calls `muse_plan` through `build_mcp_server().call_tool(...)`
and asserts `structured_result["agent_handoff"]` exists and equals
`structured_result["agent_guidance"]["agent_handoff"]`.

- [ ] **Step 2: Run the test**

Run:
`python -m pytest tests\test_mcp_server.py::test_fastmcp_server_exposes_agent_handoff -q`

Expected after Task 2: pass.

### Task 4: Document V4-F

**Files:**
- Modify: `docs/integrations/agent-dogfood-playbook.md`
- Modify: `tests/test_mcp_config_packs.py`

- [ ] **Step 1: Add docs test**

Require `V4-F`, `agent_handoff`, `recommended_action`, and
`selected_finalist_id` in the playbook docs.

- [ ] **Step 2: Add playbook section**

Document that `agent_handoff` is the first field host agents should inspect for
routing, while the richer policy fields remain available for details.

- [ ] **Step 3: Run docs test**

Run:
`python -m pytest tests\test_mcp_config_packs.py::test_docs_describe_v4f_agent_handoff -q`

Expected: pass.

### Task 5: Verify and Finish

**Files:**
- All modified files

- [ ] **Step 1: Run focused suite**

Run:
`python -m pytest tests\test_middleware.py tests\test_mcp_server.py tests\test_mcp_config_packs.py -q`

- [ ] **Step 2: Run full verification**

Run:
`python -m pytest -q`
`python -m ruff check .`
`muse-mcp-smoke "Design a retry strategy for AI coding agents" --provider-mode deterministic --repo-language Python`

- [ ] **Step 3: Commit, push, and open PR**

Commit message:
`Add agent handoff guidance`
