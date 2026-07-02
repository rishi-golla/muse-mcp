# V4-C Quality Warnings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add advisory quality warning fields to middleware/MCP creative plan responses.

**Architecture:** Extract reusable pure quality gate helpers into `src/creativity_layer/quality_warnings.py`. Reuse them from dogfood quality checks and middleware serialization so agent hosts see the same warning vocabulary without invoking the dogfood CLI.

**Tech Stack:** Python 3.12+, Pydantic, pytest, Ruff

---

### Task 1: Document The Slice

**Files:**
- Create: `docs/superpowers/specs/2026-07-02-v4c-quality-warnings-design.md`
- Create: `docs/superpowers/plans/2026-07-02-v4c-quality-warnings.md`

- [ ] **Step 1: Save the design doc**

Write the approved design to `docs/superpowers/specs/2026-07-02-v4c-quality-warnings-design.md`.

- [ ] **Step 2: Save this implementation plan**

Write this plan to `docs/superpowers/plans/2026-07-02-v4c-quality-warnings.md`.

- [ ] **Step 3: Commit docs**

Run:

```powershell
git add docs\superpowers\specs\2026-07-02-v4c-quality-warnings-design.md docs\superpowers\plans\2026-07-02-v4c-quality-warnings.md
git commit -m "docs: plan v4c quality warnings"
```

Expected: one docs commit.

### Task 2: Add RED Tests For Shared Quality Warnings

**Files:**
- Create: `tests/test_quality_warnings.py`
- Modify: `tests/test_dogfood_quality.py`

- [ ] **Step 1: Add pure helper tests**

Create `tests/test_quality_warnings.py` with tests for:

```python
from creativity_layer.quality_warnings import (
    finalist_quality_warnings,
    summarize_quality_warnings,
)


def test_finalist_quality_warnings_flags_generic_title_mechanism_and_empty_contract() -> None:
    finalist = {
        "title": "Decision garden",
        "core_mechanism": "People allocate reversible confidence rather than binary votes.",
        "inputs_required": [],
        "outputs_produced": ["next action"],
        "agent_workflow": ["collect evidence"],
        "decision_policy": "choose bounded action",
        "integration_points": ["planning step"],
        "verification_strategy": "run tests",
        "failure_modes": ["ambiguous evidence"],
    }

    warnings = finalist_quality_warnings(finalist)

    assert warnings == (
        "generic_title",
        "generic_mechanism",
        "missing_operational_field",
    )


def test_finalist_quality_warnings_flags_missing_required_terms() -> None:
    finalist = {
        "title": "Shard replay",
        "core_mechanism": "Replay the failing shard and compare verification output.",
        "inputs_required": ["test command"],
        "outputs_produced": ["report"],
        "agent_workflow": ["run failing shard"],
        "decision_policy": "stop after repeated failure",
        "integration_points": ["agent planning step"],
        "verification_strategy": "run the shard",
        "failure_modes": ["environment mismatch"],
    }

    assert finalist_quality_warnings(finalist, required_terms=("pytest", "retry")) == (
        "missing_required_terms",
    )


def test_summarize_quality_warnings_counts_unique_finalists() -> None:
    summary = summarize_quality_warnings(
        [
            ("generic_title", "generic_mechanism"),
            ("generic_title",),
            (),
        ]
    )

    assert summary == {
        "warning_count": 3,
        "finalist_warning_count": 2,
        "warnings": {"generic_mechanism": 1, "generic_title": 2},
    }
```

- [ ] **Step 2: Add dogfood reuse assertion**

Extend `tests/test_dogfood_quality.py` so generic deterministic output still
returns `generic_title`, `generic_mechanism`, and `missing_required_terms` after
the logic is extracted.

- [ ] **Step 3: Run tests to verify RED**

Run:

```powershell
python -m pytest tests\test_quality_warnings.py tests\test_dogfood_quality.py::test_quality_gates_flag_generic_deterministic_output -q
```

Expected: FAIL because `creativity_layer.quality_warnings` does not exist.

### Task 3: Implement Shared Quality Warnings

**Files:**
- Create: `src/creativity_layer/quality_warnings.py`
- Modify: `src/creativity_layer/dogfood_quality.py`

- [ ] **Step 1: Add implementation**

Implement constants and pure helpers in `quality_warnings.py`, then import them
from `dogfood_quality.py` instead of duplicating constants and helper logic.

- [ ] **Step 2: Run focused tests to verify GREEN**

Run:

```powershell
python -m pytest tests\test_quality_warnings.py tests\test_dogfood_quality.py -q
python -m ruff check src\creativity_layer\quality_warnings.py src\creativity_layer\dogfood_quality.py tests\test_quality_warnings.py tests\test_dogfood_quality.py
```

Expected: tests pass and Ruff is clean.

- [ ] **Step 3: Commit shared helper**

Run:

```powershell
git add src\creativity_layer\quality_warnings.py src\creativity_layer\dogfood_quality.py tests\test_quality_warnings.py tests\test_dogfood_quality.py
git commit -m "feat: extract shared quality warnings"
```

Expected: one implementation commit.

### Task 4: Surface Warnings In Middleware And MCP

**Files:**
- Modify: `src/creativity_layer/middleware.py`
- Modify: `tests/test_middleware.py`
- Modify: `tests/test_mcp_server.py`

- [ ] **Step 1: Add RED middleware/MCP tests**

Add tests asserting:

- middleware result contains top-level `quality_warnings` and `quality_summary`;
- finalist dictionaries contain `quality_warnings`;
- configuration-error responses contain empty warning fields;
- FastMCP structured output includes these fields.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest tests\test_middleware.py::test_runner_returns_quality_warnings_for_generic_finalists tests\test_middleware.py::test_configuration_error_includes_empty_quality_warning_fields tests\test_mcp_server.py::test_fastmcp_server_exposes_quality_warnings -q
```

Expected: FAIL because the response fields do not exist.

- [ ] **Step 3: Implement middleware serialization**

Use `finalist_quality_warnings` and `summarize_quality_warnings` from
`quality_warnings.py` during `_serialize_result`. Derive required terms from
`result.framed_task.context.context_bundle.tags`.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```powershell
python -m pytest tests\test_middleware.py tests\test_mcp_server.py -q
python -m ruff check src\creativity_layer\middleware.py tests\test_middleware.py tests\test_mcp_server.py
```

Expected: tests pass and Ruff is clean.

- [ ] **Step 5: Commit middleware/MCP change**

Run:

```powershell
git add src\creativity_layer\middleware.py tests\test_middleware.py tests\test_mcp_server.py
git commit -m "feat: surface quality warnings in mcp responses"
```

Expected: one implementation commit.

### Task 5: Document And Verify

**Files:**
- Modify: `README.md`
- Modify: `docs/integrations/agent-dogfood-playbook.md`
- Modify: `tests/test_mcp_config_packs.py`

- [ ] **Step 1: Add docs test**

Extend docs tests to require `quality_warnings`, `quality_summary`, and `V4-C`
in README/playbook documentation.

- [ ] **Step 2: Run docs test to verify RED**

Run:

```powershell
python -m pytest tests\test_mcp_config_packs.py -q
```

Expected: FAIL until docs are updated.

- [ ] **Step 3: Update docs**

Document that agents should treat warnings as advisory quality signals, not as
hard rejection or proof of failure.

- [ ] **Step 4: Run full verification**

Run:

```powershell
python -m pytest -q
python -m ruff check .
creativity-layer-mcp-smoke "Design a retry strategy for AI coding agents" --provider-mode deterministic --repo-language Python
```

Expected: tests pass, Ruff is clean, and smoke returns JSON with quality warning
fields.

- [ ] **Step 5: Commit docs**

Run:

```powershell
git add README.md docs\integrations\agent-dogfood-playbook.md tests\test_mcp_config_packs.py
git commit -m "docs: document v4c quality warnings"
```

Expected: one docs commit.

- [ ] **Step 6: Push and open PR**

Run:

```powershell
git push -u origin codex/v4c-quality-warnings
Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
gh pr create --base main --head codex/v4c-quality-warnings --title "V4-C: surface quality warnings in MCP responses" --body-file pr-body.md
```

Expected: GitHub returns a PR URL.
