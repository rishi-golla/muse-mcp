# V3-L Quality Dogfood Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable MCP dogfood quality suite that reports quality gates, search-mode comparisons, and cheap deterministic regression data.

**Architecture:** Add `src/muse/dogfood_quality.py` as the single implementation module. It calls the FastMCP `muse_plan` tool in-process, evaluates structured quality gates, and returns JSON-safe reports. Add `src/muse/dogfood_quality_cli.py` as a thin terminal harness.

**Tech Stack:** Python 3.12, Pydantic v2-style JSON-safe dictionaries, FastMCP, pytest, Ruff.

---

### Task 1: Dogfood Quality Core

**Files:**
- Create: `src/muse/dogfood_quality.py`
- Create: `tests/test_dogfood_quality.py`

- [ ] **Step 1: Write failing tests**

Add tests that import `DEFAULT_DOGFOOD_CASES`, `DEFAULT_SEARCH_VARIANTS`, `run_dogfood_quality_suite`, and `evaluate_quality_gates`. Tests should assert built-in cases are present, deterministic MCP execution returns a JSON-safe report, generic deterministic titles are flagged, and requested search that is not used is flagged.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_dogfood_quality.py -q`

Expected: FAIL because `muse.dogfood_quality` does not exist.

- [ ] **Step 3: Implement core module**

Implement:

- immutable dataclasses `DogfoodCase` and `SearchVariant`;
- defaults for four cases and three search variants;
- `run_dogfood_quality_suite(...)`;
- async MCP call helper using `build_mcp_server().call_tool("muse_plan", arguments)`;
- `evaluate_quality_gates(case, variant, result)`;
- JSON-safe report assembly.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_dogfood_quality.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src\muse\dogfood_quality.py tests\test_dogfood_quality.py
git commit -m "feat: add mcp dogfood quality suite"
```

### Task 2: Dogfood Quality CLI

**Files:**
- Create: `src/muse/dogfood_quality_cli.py`
- Modify: `pyproject.toml`
- Create: `tests/test_dogfood_quality_cli.py`

- [ ] **Step 1: Write failing tests**

Add tests that call the CLI `main(...)`, parse JSON output, assert filters are forwarded, and assert `--fail-on-gates` returns exit code `1` when deterministic generic output is flagged.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_dogfood_quality_cli.py -q`

Expected: FAIL because the CLI module/script does not exist.

- [ ] **Step 3: Implement CLI and script entry**

Implement argparse options:

- `--provider-mode`
- `--effort`
- `--privacy`
- `--budget-usd`
- `--search-provider`
- `--search-strict`
- `--case`
- `--variant`
- `--json`
- `--fail-on-gates`

Add `muse-dogfood-quality = "muse.dogfood_quality_cli:main"` to `pyproject.toml`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_dogfood_quality_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src\muse\dogfood_quality_cli.py tests\test_dogfood_quality_cli.py pyproject.toml
git commit -m "feat: add dogfood quality cli"
```

### Task 3: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/integrations/agent-dogfood-playbook.md`
- Modify: `tests/test_mcp_config_packs.py`

- [ ] **Step 1: Write failing docs test**

Add assertions that docs mention `muse-dogfood-quality`, `fail-on-gates`, search comparison, and V3-L as the last V3 validation slice.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`

Expected: FAIL until docs are updated.

- [ ] **Step 3: Update docs**

Document cheap deterministic dogfood usage and optional live usage. State that deterministic output can intentionally fail quality gates.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add README.md docs\integrations\agent-dogfood-playbook.md tests\test_mcp_config_packs.py
git commit -m "docs: document v3l dogfood quality checks"
```

### Final Verification

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check .`.
- [ ] Review `git diff origin/main...HEAD`.
- [ ] Push `codex/v3l-quality-dogfood`.
- [ ] Create PR.
