# V5-C Host Config Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `muse-mcp-config` command that prints host-specific MCP snippets for onboarding.

**Architecture:** Create `src/muse/mcp_config.py` for pure snippet generation and `src/muse/mcp_config_cli.py` for argument parsing and output. Keep docs config packs as static examples, but make tests compare generated snippets to the same public contract.

**Tech Stack:** Python 3.12, stdlib `json`, pytest, Ruff.

---

### Task 1: Pure Config Generator

**Files:**
- Create: `src/muse/mcp_config.py`
- Test: `tests/test_mcp_config_cli.py`

- [ ] Write failing tests for Codex TOML, Claude JSON with env placeholders, and generic JSON without env.
- [ ] Run focused tests and confirm import/behavior failures.
- [ ] Implement pure snippet generation.
- [ ] Run focused tests and confirm pass.

### Task 2: CLI Entrypoint

**Files:**
- Create: `src/muse/mcp_config_cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_mcp_config_cli.py`

- [ ] Write failing tests for CLI JSON/text output and console script registration.
- [ ] Run focused tests and confirm failures.
- [ ] Implement CLI parser and script registration.
- [ ] Run focused tests and confirm pass.

### Task 3: Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`
- Modify: `tests/test_mcp_config_packs.py`
- Modify: `tests/test_open_source_readiness.py`

- [ ] Write failing docs assertions for `muse-mcp-config`.
- [ ] Run focused docs tests and confirm failures.
- [ ] Update onboarding docs to include doctor, config generator, then smoke.
- [ ] Run focused docs tests and confirm pass.

### Task 4: Verification

**Files:**
- No new files.

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check .`.
- [ ] Run `git diff --check`.
- [ ] Run `python -m muse.mcp_config_cli --host codex` as a smoke check.
