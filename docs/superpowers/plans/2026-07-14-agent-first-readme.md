# Muse Agent-First README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the public README as a concise, agent-first onboarding experience for Muse's live MCP workflow.

**Architecture:** Keep all product behavior unchanged. Add one documentation contract test in the existing open-source-readiness suite, then replace the README's ordering and copy with a public quickstart first and maintainer/reference material later.

**Tech Stack:** Markdown, pytest, Ruff.

## Global Constraints

- The public onboarding path describes live OpenAI MCP usage only.
- Do not expose public seed, generation, or budget controls.
- Keep real secrets out of documentation and preserve existing tested commands and quality-evidence language.
- Keep deterministic tooling explicitly maintainer-only.
- Use Windows/PowerShell syntax for the primary setup examples.

---

### Task 1: Lock the agent-first documentation contract

**Files:**
- Modify: `tests/test_open_source_readiness.py`

**Interfaces:**
- Consumes: `_read_text("README.md")` and the existing public-docs readiness suite.
- Produces: a regression test requiring the public README to contain the agent-first onboarding block, the two public modes, the no-secret policy, and links to setup and benchmark evidence.

- [ ] **Step 1: Write the failing test**

Add this test after `test_public_docs_include_copy_pasteable_first_run_path`:

```python
def test_readme_leads_with_agent_first_live_mcp_onboarding() -> None:
    readme = _read_text("README.md").casefold()

    for phrase in (
        "paste this into your coding agent",
        "agent-first quickstart",
        "live openai",
        "muse_plan",
        "normal",
        "extensive",
        "never commit secrets",
        "docs/integrations/mcp-agent-hosts.md",
        "docs/quality/benchmarking.md",
    ):
        assert phrase in readme
```

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```powershell
python -m pytest -q tests/test_open_source_readiness.py::test_readme_leads_with_agent_first_live_mcp_onboarding
```

Expected: FAIL because the current README does not contain the agent-first headings and safety wording.

- [ ] **Step 3: Commit the RED test**

```powershell
git add tests/test_open_source_readiness.py
git commit -m "test: define agent-first README contract"
```

### Task 2: Rebuild the public README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the contract from Task 1, existing console-script names in `pyproject.toml`, and public integration guides.
- Produces: a centered Muse identity, agent-first onboarding, manual PowerShell quickstart, public mode explanation, concise expected output, reference links, and maintainer-only notes below the public path.

- [ ] **Step 1: Replace the README opening and public workflow**

Use this order:

```markdown
<p align="center">
  <strong>Muse</strong>
</p>

<p align="center">
  Creative planning infrastructure for AI coding agents.
</p>

## Agent-first Quickstart

### Paste this into your coding agent

```text
Read this README and set up Muse for this project. Install the package, verify
the live OpenAI configuration with muse-mcp-doctor --json, generate the MCP
configuration and agent instructions, restart the host, then use muse_plan when
the task needs exploration or non-obvious planning. Never commit secrets.
```
```

Continue with manual PowerShell setup, an explanation that Muse runs behind
the agent rather than replacing it, and the exact supported commands:
`muse-mcp-doctor --json`, `muse-mcp-config --host codex`,
`muse-agent-instructions --target agents-md`, and `muse-project-init`.

- [ ] **Step 2: Add concise public-use and reference sections**

Include sections named `What Muse Adds`, `Use Muse Through Your Agent`,
`Expected Output`, `Privacy and Live Configuration`, `Quality Evidence`,
`Roadmap`, `Contributing`, `Development`, and `License`.

The mode section must describe only `normal` and `extensive`, use the phrase
`mode: "normal"`, and state that repository observation and verification remain
the calling agent's responsibility. Link these existing files exactly:

```markdown
[MCP host guide](docs/integrations/mcp-agent-hosts.md)
[Agent dogfood playbook](docs/integrations/agent-dogfood-playbook.md)
[Benchmarking guide](docs/quality/benchmarking.md)
[Contributing guide](CONTRIBUTING.md)
[Security policy](SECURITY.md)
```

Keep internal deterministic fixture, compare, calibration, and smoke-command
material out of the public onboarding path; mention their maintainer status in
the development/reference material only.

- [ ] **Step 3: Run focused tests to verify GREEN**

Run:

```powershell
python -m pytest -q tests/test_open_source_readiness.py tests/test_mcp_config_packs.py tests/test_agent_loop_proof.py
```

Expected: PASS.

- [ ] **Step 4: Run repository verification**

Run:

```powershell
python -m pytest -q
python -m ruff check .
git diff --check
```

Expected: tests pass, Ruff reports `All checks passed!`, and `git diff --check`
is silent.

- [ ] **Step 5: Commit the README**

```powershell
git add README.md tests/test_open_source_readiness.py
git commit -m "docs: make README agent-first"
```

## Plan Self-Review

- Spec coverage: Task 1 enforces the agent-first path and Task 2 covers every
  required public and reference section.
- Placeholder scan: no placeholders or deferred implementation steps remain.
- Consistency: the command names and guide paths are taken from existing public
  project contracts.
