# Agent MCP Config Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship tested MCP config packs and a concise integration guide for real coding-agent hosts.

**Architecture:** Config packs live under `docs/integrations/config-packs/` and are parsed by tests. The guide links to those exact files and keeps host-specific claims narrow.

**Tech Stack:** Markdown, JSON, TOML, Python `json`/`tomllib`, pytest.

---

## File Map

- Create `tests/test_mcp_config_packs.py`: validates config pack syntax and guide links.
- Create `docs/integrations/config-packs/codex/config.toml`: Codex MCP fragment.
- Create `docs/integrations/config-packs/claude-code/.mcp.json`: Claude Code style project MCP JSON.
- Create `docs/integrations/config-packs/generic-mcp/mcp.json`: generic JSON MCP client config.
- Create `docs/integrations/mcp-agent-hosts.md`: installation and usage guide.
- Modify `README.md`: add a short link to the guide.

## Task 1: Config Pack Validation and Templates

**Files:**
- Create `tests/test_mcp_config_packs.py`
- Create config pack files under `docs/integrations/config-packs/`

- [ ] **Step 1: Write failing tests**

Add tests that parse the expected TOML/JSON files, assert `muse-mcp` command values, check Codex allows only `muse_plan`, and ensure no sample file contains a literal API key.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`
Expected: FAIL because the config pack files do not exist.

- [ ] **Step 3: Add config packs**

Create the Codex TOML fragment and two JSON MCP templates.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests\test_mcp_config_packs.py docs\integrations\config-packs
git commit -m "docs: add tested mcp config packs"
```

## Task 2: Integration Guide and README Link

**Files:**
- Modify `tests/test_mcp_config_packs.py`
- Create `docs/integrations/mcp-agent-hosts.md`
- Modify `README.md`

- [ ] **Step 1: Write failing guide tests**

Add tests that assert the guide exists, links all config pack files, mentions deterministic smoke testing, and README links to the guide.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_mcp_config_packs.py -q`
Expected: FAIL because the guide and README link are missing.

- [ ] **Step 3: Add guide and README link**

Document Codex, Claude Code style project config, generic JSON clients, deterministic smoke, and live OpenAI env setup.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
python -m pytest tests/test_mcp_config_packs.py -q
python -m ruff check .
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests\test_mcp_config_packs.py docs\integrations\mcp-agent-hosts.md README.md
git commit -m "docs: add agent mcp integration guide"
```

## Final Verification

- [ ] `python -m pytest -q`
- [ ] `python -m pytest --cov=muse --cov-fail-under=90`
- [ ] `python -m ruff check .`
- [ ] `git diff --check`
- [ ] Request code review.
- [ ] Push branch and create PR.
