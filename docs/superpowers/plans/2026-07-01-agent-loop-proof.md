# Agent Loop Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic proof that an agent loop can call the MCP tool, use repo signals, apply one bounded code fix, and verify it.

**Architecture:** The proof harness creates a tiny external sample repo, runs pytest to capture failure evidence, invokes the FastMCP `muse_plan` tool in-process, applies a narrow repair to one sample file, and reruns the same verification command. It returns structured Python data so tests, docs, and future middleware probes can consume it without scraping stdout.

**Tech Stack:** Python 3.12, FastMCP in-process calls, pytest subprocess verification, Pydantic-compatible JSON-safe dictionaries, Markdown docs.

---

## File Map

- Create `src/muse/agent_loop_proof.py`: proof harness and optional proof-only CLI entrypoint.
- Create `tests/test_agent_loop_proof.py`: RED/GREEN tests for sample failure, MCP invocation, repair, and structured output.
- Modify `pyproject.toml`: register `muse-agent-proof` if a local proof command is added.
- Create `docs/integrations/agent-loop-proof.md`: proof usage and interpretation guide.
- Modify `README.md`: link to the proof guide from Agent MCP integration.

## Task 1: Failing Sample Repo and Verification Runner

**Files:**
- Create: `tests/test_agent_loop_proof.py`
- Create: `src/muse/agent_loop_proof.py`

- [ ] **Step 1: Write the failing tests**

Add tests that create a sample repo and assert `run_verification(repo_path)` fails before any repair:

```python
def test_sample_repo_starts_with_failing_verification(tmp_path):
    repo_path = create_sample_retry_repo(tmp_path / "sample-repo")

    result = run_verification(repo_path)

    assert result.exit_code != 0
    assert result.command == (sys.executable, "-m", "pytest", "-q")
    assert "test_retry_delay_increases" in result.combined_output
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_agent_loop_proof.py::test_sample_repo_starts_with_failing_verification -q`
Expected: FAIL because `muse.agent_loop_proof` does not exist.

- [ ] **Step 3: Implement minimal sample repo and runner**

Create a module that writes `retry_policy.py` and `test_retry_policy.py` into a caller-provided directory. The initial implementation should return a constant retry delay so the test fails. `run_verification` should execute `python -m pytest -q` in the sample repo and capture stdout/stderr.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_agent_loop_proof.py::test_sample_repo_starts_with_failing_verification -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\muse\agent_loop_proof.py tests\test_agent_loop_proof.py
git commit -m "test: add agent loop sample verification proof"
```

## Task 2: MCP Call and Bounded Repair

**Files:**
- Modify: `tests/test_agent_loop_proof.py`
- Modify: `src/muse/agent_loop_proof.py`

- [ ] **Step 1: Write failing MCP proof tests**

Add tests that call `run_agent_loop_proof(tmp_path / "workspace")` and assert:

```python
assert result["passed"] is True
assert result["initial_verification"]["exit_code"] != 0
assert result["final_verification"]["exit_code"] == 0
assert result["mcp_result"]["provider_mode"] == "deterministic"
assert "python" in result["mcp_result"]["context_tags"]
assert "pytest" in result["mcp_result"]["context_tags"]
assert result["repair"]["changed_files"] == ["retry_policy.py"]
assert result["selected_plan"]["agent_workflow"]
assert result["selected_plan"]["verification_strategy"]
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_agent_loop_proof.py -q`
Expected: FAIL because `run_agent_loop_proof` and repair behavior do not exist.

- [ ] **Step 3: Implement MCP invocation and repair**

Build repo signals from the sample repo, call `build_mcp_server().call_tool("muse_plan", ...)`, extract the first finalist, replace only `retry_policy.py` with an exponential capped retry delay, and rerun verification.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_agent_loop_proof.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src\muse\agent_loop_proof.py tests\test_agent_loop_proof.py
git commit -m "feat: prove agent loop through mcp planning"
```

## Task 3: Proof Runner and Documentation

**Files:**
- Modify: `src/muse/agent_loop_proof.py`
- Modify: `pyproject.toml`
- Create: `docs/integrations/agent-loop-proof.md`
- Modify: `README.md`
- Modify: `tests/test_agent_loop_proof.py`

- [ ] **Step 1: Write failing docs and script tests**

Add tests that assert `pyproject.toml` registers `muse-agent-proof`, the proof doc exists, the doc mentions MCP, deterministic mode, bounded repair, and README links to the doc.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_agent_loop_proof.py -q`
Expected: FAIL because the script entry and docs are missing.

- [ ] **Step 3: Add proof runner and docs**

Add a `main()` that prints the structured proof result as JSON, register it in `pyproject.toml`, document usage, and link the proof doc in README.

- [ ] **Step 4: Run GREEN and local script smoke**

Run:

```powershell
python -m pytest tests/test_agent_loop_proof.py -q
muse-agent-proof --workspace .agent-proof-tmp
```

Expected: tests PASS and the proof command prints JSON with `"passed": true`.

- [ ] **Step 5: Commit**

```powershell
git add src\muse\agent_loop_proof.py tests\test_agent_loop_proof.py pyproject.toml docs\integrations\agent-loop-proof.md README.md
git commit -m "docs: add agent loop proof runner"
```

## Final Verification

- [ ] `python -m pytest -q`
- [ ] `python -m pytest --cov=muse --cov-fail-under=90`
- [ ] `python -m ruff check .`
- [ ] `git diff --check`
- [ ] Request code review.
- [ ] Push branch and create PR.
