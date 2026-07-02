# V4-D Quality Action Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add machine-readable action guidance for quality warnings in MCP/middleware responses.

**Architecture:** Extend the pure quality warning module with a JSON-safe policy builder, then serialize that policy into normal and configuration-error middleware results. Keep the policy advisory and separate from finalist ranking.

**Tech Stack:** Python 3.12+, pytest, Ruff

---

### Task 1: Document The Slice

**Files:**
- Create: `docs/superpowers/specs/2026-07-02-v4d-quality-action-policy-design.md`
- Create: `docs/superpowers/plans/2026-07-02-v4d-quality-action-policy.md`

- [ ] **Step 1: Save the design doc**

Write the design to `docs/superpowers/specs/2026-07-02-v4d-quality-action-policy-design.md`.

- [ ] **Step 2: Save this implementation plan**

Write this plan to `docs/superpowers/plans/2026-07-02-v4d-quality-action-policy.md`.

- [ ] **Step 3: Commit docs**

Run:

```powershell
git add docs\superpowers\specs\2026-07-02-v4d-quality-action-policy-design.md docs\superpowers\plans\2026-07-02-v4d-quality-action-policy.md
git commit -m "docs: plan v4d quality action policy"
```

Expected: one docs commit.

### Task 2: Add RED Tests For Pure Policy Helper

**Files:**
- Modify: `tests/test_quality_warnings.py`

- [ ] **Step 1: Add failing tests**

Add tests for `quality_action_policy`:

```python
def test_quality_action_policy_is_clear_without_warnings() -> None:
    policy = quality_action_policy((), effort="quick")

    assert policy == {
        "status": "clear",
        "escalate_effort_to": None,
        "recommended_actions": [],
        "warning_actions": {},
    }


def test_quality_action_policy_recommends_retry_for_missing_operational_detail() -> None:
    policy = quality_action_policy(
        ("generic_title", "missing_required_terms"),
        effort="quick",
    )

    assert policy["status"] == "needs_retry"
    assert policy["escalate_effort_to"] == "standard"
    assert "supply more repo signals" in policy["recommended_actions"]
    assert "missing_required_terms" in policy["warning_actions"]


def test_quality_action_policy_stops_effort_escalation_at_deep() -> None:
    policy = quality_action_policy(("generic_mechanism",), effort="deep")

    assert policy["status"] == "review"
    assert policy["escalate_effort_to"] is None
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest tests\test_quality_warnings.py::test_quality_action_policy_is_clear_without_warnings tests\test_quality_warnings.py::test_quality_action_policy_recommends_retry_for_missing_operational_detail tests\test_quality_warnings.py::test_quality_action_policy_stops_effort_escalation_at_deep -q
```

Expected: FAIL because `quality_action_policy` does not exist.

### Task 3: Implement Pure Policy Helper

**Files:**
- Modify: `src/creativity_layer/quality_warnings.py`
- Modify: `tests/test_quality_warnings.py`

- [ ] **Step 1: Implement the helper**

Add `quality_action_policy(warnings: Sequence[str], *, effort: str) -> dict[str, object]`.

- [ ] **Step 2: Run focused tests to verify GREEN**

Run:

```powershell
python -m pytest tests\test_quality_warnings.py -q
python -m ruff check src\creativity_layer\quality_warnings.py tests\test_quality_warnings.py
```

Expected: tests pass and Ruff is clean.

- [ ] **Step 3: Commit helper**

Run:

```powershell
git add src\creativity_layer\quality_warnings.py tests\test_quality_warnings.py
git commit -m "feat: add quality action policy"
```

Expected: one implementation commit.

### Task 4: Serialize Policy In Middleware And MCP

**Files:**
- Modify: `src/creativity_layer/middleware.py`
- Modify: `tests/test_middleware.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Add RED response tests**

Add tests asserting normal middleware results include top-level
`quality_action_policy`, `agent_guidance["quality_action_policy"]`, and MCP
structured output includes the same policy. Add a configuration-error assertion
for the clear empty policy.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest tests\test_middleware.py::test_runner_returns_quality_action_policy_for_warning_results tests\test_middleware.py::test_configuration_error_includes_clear_quality_action_policy tests\test_mcp_server.py::test_fastmcp_server_exposes_quality_action_policy -q
```

Expected: FAIL because the response fields do not exist.

- [ ] **Step 3: Implement serialization**

Compute the policy from top-level `quality_warnings` and request effort, attach
it to the result, and pass it into agent guidance.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```powershell
python -m pytest tests\test_middleware.py tests\test_mcp_server.py -q
python -m ruff check src\creativity_layer\middleware.py tests\test_middleware.py tests\test_mcp_server.py
```

Expected: tests pass and Ruff is clean.

- [ ] **Step 5: Commit serialization**

Run:

```powershell
git add src\creativity_layer\middleware.py tests\test_middleware.py tests\test_mcp_server.py
git commit -m "feat: surface quality action policy in mcp responses"
```

Expected: one implementation commit.

### Task 5: Document And Verify

**Files:**
- Modify: `README.md`
- Modify: `docs/integrations/agent-dogfood-playbook.md`
- Modify: `tests/test_mcp_config_packs.py`

- [ ] **Step 1: Add docs test**

Extend docs tests to require `V4-D`, `quality_action_policy`, and
`escalate_effort_to`.

- [ ] **Step 2: Run docs test to verify RED**

Run:

```powershell
python -m pytest tests\test_mcp_config_packs.py::test_docs_describe_v4d_quality_action_policy -q
```

Expected: FAIL until docs are updated.

- [ ] **Step 3: Update docs**

Document the advisory action policy and clarify that it recommends, but does not
perform, effort escalation.

- [ ] **Step 4: Run full verification**

Run:

```powershell
python -m pytest -q
python -m ruff check .
creativity-layer-mcp-smoke "Design a retry strategy for AI coding agents" --provider-mode deterministic --repo-language Python
```

Expected: tests pass, Ruff is clean, and smoke output includes
`quality_action_policy`.

- [ ] **Step 5: Commit docs**

Run:

```powershell
git add README.md docs\integrations\agent-dogfood-playbook.md tests\test_mcp_config_packs.py
git commit -m "docs: document v4d quality action policy"
```

Expected: one docs commit.

- [ ] **Step 6: Push and open PR**

Run:

```powershell
git push -u origin codex/v4d-quality-action-policy
Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
gh pr create --base main --head codex/v4d-quality-action-policy --title "V4-D: add quality action policy" --body-file pr-body.md
```

Expected: GitHub returns a PR URL.
