# V5-D Agent Instruction Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `muse-agent-instructions` command that prints host-appropriate project instruction blocks for using the Muse MCP tool.

**Architecture:** Create `src/muse/agent_instructions.py` as a pure renderer and `src/muse/agent_instructions_cli.py` as the command wrapper. Keep generated content static, explicit, and testable so docs and agent behavior do not drift from the MCP contract.

**Tech Stack:** Python 3.12, stdlib `json`, Pydantic model base already used in the repo, pytest, Ruff.

---

### Task 1: Instruction Renderer

**Files:**
- Create: `src/muse/agent_instructions.py`
- Test: `tests/test_agent_instructions_cli.py`

- [ ] Write failing tests for `agents-md`, `cursor-rules`, and generic instruction content.
- [ ] Run focused tests and confirm import/behavior failure.
- [ ] Implement the pure renderer with target metadata.
- [ ] Run focused tests and confirm pass.

### Task 2: CLI Entrypoint

**Files:**
- Create: `src/muse/agent_instructions_cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_agent_instructions_cli.py`

- [ ] Write failing tests for plain text and JSON CLI output plus script registration.
- [ ] Run focused tests and confirm failures.
- [ ] Implement the CLI and script entry.
- [ ] Run focused tests and confirm pass.

### Task 3: Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`
- Modify: `docs/integrations/agent-dogfood-playbook.md`
- Modify: `tests/test_mcp_config_packs.py`
- Modify: `tests/test_open_source_readiness.py`

- [ ] Write failing docs assertions for `muse-agent-instructions`.
- [ ] Run focused docs tests and confirm failures.
- [ ] Update onboarding docs to include config generation and instruction generation.
- [ ] Run focused docs tests and confirm pass.

### Task 4: Verification

**Files:**
- No new files.

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check .`.
- [ ] Run `git diff --check`.
- [ ] Run `python -m muse.agent_instructions_cli --target agents-md` as a smoke check.
