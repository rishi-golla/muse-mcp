# V5-B Live Onboarding Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live OpenAI preflight and packaged pricing fallback so public Muse onboarding is simpler after V5-A.

**Architecture:** Create `src/muse/live_preflight.py` as the single local diagnostics and pricing-resolution module. Middleware imports its pricing resolver, while `src/muse/mcp_doctor.py` exposes a smoke-safe command that prints the same structured preflight report users can paste into issues.

**Tech Stack:** Python 3.12, Pydantic models, `importlib.resources`, pytest, Ruff.

---

### Task 1: Pricing Fallback And Preflight Model

**Files:**
- Create: `src/muse/live_preflight.py`
- Create: `src/muse/openai-pricing.example.json`
- Test: `tests/test_live_preflight.py`

- [ ] Write failing tests for bundled pricing fallback, invalid override pricing file, missing API key, and valid env report.
- [ ] Run `python -m pytest tests/test_live_preflight.py -q` and confirm import/behavior failures.
- [ ] Implement immutable report/check models and pricing resolver.
- [ ] Run `python -m pytest tests/test_live_preflight.py -q` and confirm pass.

### Task 2: Middleware Reuse

**Files:**
- Modify: `src/muse/middleware.py`
- Test: `tests/test_middleware.py`

- [ ] Write failing middleware tests showing live provider construction no longer requires `OPENAI_PRICING_FILE`.
- [ ] Run the focused test and confirm failure.
- [ ] Replace the middleware-local pricing loader with the shared preflight resolver.
- [ ] Run focused middleware/preflight tests and confirm pass.

### Task 3: Doctor Command And Docs

**Files:**
- Create: `src/muse/mcp_doctor.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/integrations/mcp-agent-hosts.md`
- Test: `tests/test_mcp_doctor.py`
- Test: `tests/test_open_source_readiness.py`

- [ ] Write failing tests for `muse-mcp-doctor --json`, console script registration, and docs mentioning doctor setup.
- [ ] Run focused tests and confirm failures.
- [ ] Implement the doctor CLI and docs.
- [ ] Run focused tests and confirm pass.

### Task 4: Verification

**Files:**
- No new files.

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check .`.
- [ ] Run `git diff --check`.
- [ ] Run a no-secret doctor smoke and confirm JSON-safe diagnostics.
