# V4-B Live Quality Pressure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make live OpenAI seed, transform, and evaluation prompts explicitly optimize against the dogfood quality gates.

**Architecture:** Add a static prompt-pressure block beside existing OpenAI developer instructions and compose it into seed, transform, and evaluate instructions. Keep dogfood runtime code independent from the live provider; the link is contractual vocabulary, not an import.

**Tech Stack:** Python 3.12+, Pydantic, pytest, Ruff

---

### Task 1: Document The Slice

**Files:**
- Create: `docs/superpowers/specs/2026-07-02-v4b-live-quality-pressure-design.md`
- Create: `docs/superpowers/plans/2026-07-02-v4b-live-quality-pressure.md`

- [ ] **Step 1: Write the design doc**

Save the approved design in `docs/superpowers/specs/2026-07-02-v4b-live-quality-pressure-design.md`.

- [ ] **Step 2: Write this implementation plan**

Save this plan in `docs/superpowers/plans/2026-07-02-v4b-live-quality-pressure.md`.

- [ ] **Step 3: Commit docs**

Run:

```powershell
git add docs\superpowers\specs\2026-07-02-v4b-live-quality-pressure-design.md docs\superpowers\plans\2026-07-02-v4b-live-quality-pressure.md
git commit -m "docs: plan v4b live quality pressure"
```

Expected: one docs commit.

### Task 2: Add Failing Prompt-Contract Tests

**Files:**
- Modify: `tests/test_openai_provider.py`

- [ ] **Step 1: Add the failing tests**

Add tests that import `DOGFOOD_QUALITY_PROMPT_BLOCK` from `muse.openai_provider` and assert:

```python
def test_dogfood_quality_prompt_block_names_quality_gates() -> None:
    block = DOGFOOD_QUALITY_PROMPT_BLOCK

    assert "dogfood quality gates" in block
    assert "generic_title" in block
    assert "generic_mechanism" in block
    assert "missing_required_terms" in block
    assert "missing_operational_field" in block
    assert "arbitrary stack" in block
    assert "Decision garden" in block


def test_live_generation_prompts_include_dogfood_quality_pressure() -> None:
    for operation in ("seed", "transform", "evaluate"):
        instruction = DEVELOPER_INSTRUCTIONS[operation]
        assert DOGFOOD_QUALITY_PROMPT_BLOCK in instruction
        assert "missing_required_terms" in instruction
        assert "generic_mechanism" in instruction
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```powershell
python -m pytest tests\test_openai_provider.py::test_dogfood_quality_prompt_block_names_quality_gates tests\test_openai_provider.py::test_live_generation_prompts_include_dogfood_quality_pressure -q
```

Expected: FAIL because `DOGFOOD_QUALITY_PROMPT_BLOCK` is not defined.

### Task 3: Implement Shared Live Quality Pressure

**Files:**
- Modify: `src/muse/openai_provider.py`
- Modify: `tests/test_openai_provider.py`

- [ ] **Step 1: Add the minimal implementation**

Define `DOGFOOD_QUALITY_PROMPT_BLOCK` near `SYSTEM_INSTRUCTIONS` and compose it into seed, transform, and evaluate instructions. Keep frame unchanged.

- [ ] **Step 2: Run focused tests to verify GREEN**

Run:

```powershell
python -m pytest tests\test_openai_provider.py::test_dogfood_quality_prompt_block_names_quality_gates tests\test_openai_provider.py::test_live_generation_prompts_include_dogfood_quality_pressure tests\test_openai_provider.py::test_openai_generation_prompts_require_operational_contracts tests\test_openai_provider.py::test_openai_generation_prompts_require_context_grounding -q
```

Expected: PASS.

- [ ] **Step 3: Commit implementation**

Run:

```powershell
git add src\muse\openai_provider.py tests\test_openai_provider.py
git commit -m "feat: align live prompts with dogfood quality gates"
```

Expected: one implementation commit.

### Task 4: Document V4-B Dogfood Usage

**Files:**
- Modify: `docs/integrations/agent-dogfood-playbook.md`
- Modify: `tests/test_mcp_config_packs.py`

- [ ] **Step 1: Add a failing docs test**

Extend the dogfood playbook docs test so it requires the playbook to mention
`V4-B`, `live prompt pressure`, and `dogfood quality gates`.

- [ ] **Step 2: Run the docs test to verify RED**

Run:

```powershell
python -m pytest tests\test_mcp_config_packs.py -q
```

Expected: FAIL until the playbook is updated.

- [ ] **Step 3: Update the playbook**

Add a short `V4-B live prompt pressure` section explaining that dogfood gate
names are now embedded in live provider prompts, while live quality claims still
require live OpenAI runs.

- [ ] **Step 4: Run docs test to verify GREEN**

Run:

```powershell
python -m pytest tests\test_mcp_config_packs.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit docs**

Run:

```powershell
git add docs\integrations\agent-dogfood-playbook.md tests\test_mcp_config_packs.py
git commit -m "docs: document v4b live quality pressure"
```

Expected: one docs/test commit.

### Task 5: Verify And Open PR

**Files:**
- No code changes.

- [ ] **Step 1: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected: all non-live tests pass.

- [ ] **Step 2: Run Ruff**

Run:

```powershell
python -m ruff check .
```

Expected: all checks pass.

- [ ] **Step 3: Run deterministic dogfood smoke**

Run:

```powershell
muse-dogfood-quality --provider-mode deterministic --case agent-retry-python --variant search-off --json
```

Expected: command returns JSON report. Deterministic quality gates may fail because deterministic mode is fixture-like.

- [ ] **Step 4: Push and create PR**

Run:

```powershell
git push -u origin codex/v4b-live-quality-pressure
Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
gh pr create --base main --head codex/v4b-live-quality-pressure --title "V4-B: align live prompts with dogfood quality gates" --body-file pr-body.md
```

Expected: GitHub returns a PR URL.
