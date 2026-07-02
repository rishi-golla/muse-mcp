# V4-A Open Source Release Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the public-release files, package metadata, examples, and docs needed to open source creativity-layer credibly.

**Architecture:** Keep this slice documentation and packaging focused. Add a single public-readiness test module that validates release files, metadata, example config, and README setup instructions. No runtime code paths change.

**Tech Stack:** Python 3.12, pytest, TOML/JSON parsing, existing `PricingTable`, Markdown/YAML text templates.

---

### Task 1: Public Readiness Tests

**Files:**
- Create: `tests/test_open_source_readiness.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert required release files exist, `pyproject.toml` has MIT license/classifiers/repository URLs, `.env.example` has safe expected variables, `openai-pricing.example.json` validates with `PricingTable`, README includes deterministic and live open-source quickstart commands, and GitHub templates mention test/quality evidence.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_open_source_readiness.py -q`

Expected: FAIL because release files and metadata are missing.

- [ ] **Step 3: Commit tests after RED**

Do not commit yet; add implementation in Task 2 first so each implementation commit is green.

### Task 2: Release Files and Metadata

**Files:**
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `.env.example`
- Create: `openai-pricing.example.json`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add release files**

Use MIT license, safe placeholders, concise contribution/security docs, and templates that ask for MCP/dogfood quality evidence.

- [ ] **Step 2: Run GREEN**

Run: `python -m pytest tests/test_open_source_readiness.py -q`

Expected: PASS.

- [ ] **Step 3: Commit**

Run:

```powershell
git add LICENSE CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md .env.example openai-pricing.example.json .github pyproject.toml tests\test_open_source_readiness.py
git commit -m "chore: add open source release foundation"
```

### Task 3: README First-Run Path

**Files:**
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`

- [ ] **Step 1: Write failing docs assertions**

Extend `tests/test_open_source_readiness.py` if needed so README must mention the open-source quickstart, deterministic no-key path, dogfood quality check, `.env.example`, and `openai-pricing.example.json`.

- [ ] **Step 2: Update docs**

Add a short open-source quickstart near the top of README and link the host guide to the examples.

- [ ] **Step 3: Run GREEN**

Run: `python -m pytest tests/test_open_source_readiness.py tests/test_mcp_config_packs.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```powershell
git add README.md docs\integrations\mcp-agent-hosts.md tests\test_open_source_readiness.py
git commit -m "docs: add open source quickstart"
```

### Final Verification

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check .`.
- [ ] Run deterministic MCP smoke command.
- [ ] Run deterministic dogfood quality command.
- [ ] Review `git diff origin/main...HEAD`.
- [ ] Push `codex/v4a-open-source-release`.
- [ ] Create PR.
