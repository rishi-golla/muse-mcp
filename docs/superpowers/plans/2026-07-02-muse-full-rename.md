# Muse Full Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Muse the only project, package, console script, MCP tool, docs, and test identity.

**Architecture:** This is a mechanical rename plus contract updates. The implementation keeps behavior unchanged while making `src/muse` the only source package, updating imports, changing console scripts, and making `muse_plan` the MCP planning tool.

**Tech Stack:** Python 3.12, pyproject/setuptools, pytest, Ruff, FastMCP.

---

### Task 1: Add Rename Contract Tests

**Files:**
- Modify: `tests/test_package.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_config_packs.py`

- [ ] Write tests expecting `import muse`, `usage: muse`, FastMCP tool
  `muse_plan`, and docs/config examples that use Muse names.
- [ ] Run focused tests and confirm they fail before the rename.

### Task 2: Rename Package and Imports

**Files:**
- Move: the pre-rename source package -> `src/muse`
- Modify: all Python imports under `src/` and `tests/`
- Modify: `pyproject.toml`

- [ ] Move the package directory with `git mv`.
- [ ] Replace pre-rename imports with `muse`.
- [ ] Change package name and package discovery to `muse`.
- [ ] Run package, CLI, and core tests.

### Task 3: Rename Commands and MCP Tool

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/muse/cli.py`
- Modify: `src/muse/mcp_server.py`
- Modify: `src/muse/mcp_smoke.py`
- Modify: `src/muse/agent_loop_proof.py`
- Modify: tests using console scripts or MCP tool names.

- [ ] Rename console scripts to Muse command names.
- [ ] Rename the MCP planning tool to `muse_plan`.
- [ ] Update smoke/proof/dogfood callers to call `muse_plan`.
- [ ] Run MCP and smoke tests.

### Task 4: Rename Docs and Config Examples

**Files:**
- Modify: `README.md`
- Modify: `docs/**`
- Modify: docs tests.

- [ ] Replace old product names, command names, package paths, and MCP tool
  names with Muse equivalents.
- [ ] Rename old spec filenames that contain the previous product name.
- [ ] Run docs/config tests.

### Task 5: Full Verification and PR

- [ ] `python -m pip install -e .`
- [ ] `python -m pytest -q`
- [ ] `python -m ruff check .`
- [ ] `muse-mcp-smoke "Design a retry strategy for AI coding agents" --provider-mode deterministic --repo-language Python`
- [ ] Repository search confirms no old names remain in active tracked files.
- [ ] Commit, push, and open PR.
