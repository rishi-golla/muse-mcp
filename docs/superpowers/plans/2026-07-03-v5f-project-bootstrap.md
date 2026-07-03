# V5-F Project Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe `muse-project-init` command that writes Muse MCP onboarding artifacts into any target repository.

**Architecture:** A small API module computes target paths, renders existing MCP config and agent instruction documents, checks local live readiness, and writes files with overwrite protection. A CLI module handles argument parsing, JSON/text output, and strict-live exit behavior.

**Tech Stack:** Python 3.12, Pydantic models, argparse, pytest, ruff.

---

### Task 1: Project bootstrap API

**Files:**
- Create: `src/muse/project_bootstrap.py`
- Test: `tests/test_project_bootstrap.py`

- [ ] **Step 1: Write failing API tests**

Create tests for writing `.mcp.json` plus `AGENTS.md`, dry-run behavior,
overwrite protection, `--force`, and Codex/Cursor paths.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_project_bootstrap.py -q`
Expected: collection fails because `muse.project_bootstrap` does not exist.

- [ ] **Step 3: Implement API**

Add `ProjectBootstrapReport` and `run_project_bootstrap` with safe file writes,
target path selection, live preflight reporting, and no provider calls.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_project_bootstrap.py -q`
Expected: all tests pass.

### Task 2: Project bootstrap CLI

**Files:**
- Create: `src/muse/project_bootstrap_cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_project_bootstrap_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create tests for JSON output, strict-live failure, and console script exposure.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_project_bootstrap_cli.py -q`
Expected: collection fails because `muse.project_bootstrap_cli` does not exist.

- [ ] **Step 3: Implement CLI**

Add argparse support for `--project`, `--host`, `--instruction-target`,
`--include-env`, `--dry-run`, `--force`, `--json`, and `--strict-live`.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_project_bootstrap_cli.py -q`
Expected: all tests pass.

### Task 3: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`
- Modify: `tests/test_mcp_config_packs.py`

- [ ] **Step 1: Write docs assertions**

Assert README and the MCP host guide mention `muse-project-init`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`
Expected: failure because docs do not mention the new command yet.

- [ ] **Step 3: Update docs**

Add short copy-pasteable examples for initializing a real repo safely.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`
Expected: all tests pass.

### Task 4: Final verification

**Files:**
- All files changed in this slice.

- [ ] **Step 1: Run focused tests**

Run: `python -m pytest tests/test_project_bootstrap.py tests/test_project_bootstrap_cli.py tests/test_mcp_config_packs.py -q`

- [ ] **Step 2: Run full suite**

Run: `python -m pytest`

- [ ] **Step 3: Run lint**

Run: `python -m ruff check .`

- [ ] **Step 4: Commit**

Run: `git add ... && git commit -m "feat: add project bootstrap command"`
