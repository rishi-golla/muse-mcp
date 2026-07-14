# V6-B Final Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with RED-GREEN TDD because this session has no subagent dispatch tool.

**Goal:** Close all five V6-B final-review blockers without changing public mode controls, provider-neutral contracts, sanitization, budget enforcement, exact accounting, or all-or-nothing seed cardinality.

**Architecture:** Keep the existing engine/provider boundary and extend its metered failure evidence so every transport invocation and provider response survives success and terminal failure paths. Derive internal call ceilings from mode run shapes, preserve branch strategy in local transform construction, and validate branch evidence against the spend record rather than labels alone.

**Tech Stack:** Python 3.12, Pydantic 2, OpenAI Responses API adapter, pytest, Ruff.

## Global Constraints

- Public MCP callers control run depth with only `mode: normal` or `mode: extensive`; `max_calls` is internal.
- Every production edit follows a focused failing regression that fails for the intended missing behavior.
- Provider failures remain sanitized and provider-neutral.
- Quotes bound repair attempts and configured transport retries exactly once.
- Seed generation remains all-or-nothing for candidate cardinality while incurred work is charged exactly once.
- Agent-facing branch evidence must reconcile with canonical spend calls and usage.

---

### Task 1: Executable public mode call ceilings

**Files:**
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_middleware.py`
- Modify: `src/muse/mcp_server.py`
- Modify: `src/muse/middleware.py`

**Interfaces:**
- Produces: mode-derived internal `max_calls` values that cover each mode's complete default logical run shape at the live provider's default repair and retry ceilings.

- [x] Add an extensive-mode live-provider integration regression that reaches `seed`, and assert `max_calls` is absent from the public MCP signature.
- [x] Run the focused tests and capture the expected RED budget stop/signature failure.
- [x] Resolve `max_calls` from the normal/extensive preset and remove the public argument.
- [x] Run the focused tests and capture GREEN.

### Task 2: Meter terminal branch repair failures

**Files:**
- Modify: `tests/test_openai_provider.py`
- Modify: `tests/test_engine.py`
- Modify: `src/muse/openai_provider.py`
- Modify: `src/muse/providers.py` only if the provider-neutral failure contract requires clarification.

**Interfaces:**
- Produces: sanitized `MeteredProviderFailure` evidence for first- and later-branch terminal failures, including every retained response, and exactly-once engine charging.

- [x] Add first-branch and later-branch terminal repair regressions with non-zero usage and sanitized secrets.
- [x] Run the focused tests and capture the expected RED missing/partial metering.
- [x] Build failed structured-call metering from retained responses and aggregate it with prior successful branches.
- [x] Run provider and engine regressions and capture GREEN.

### Task 3: Count transport retry invocations

**Files:**
- Modify: `tests/test_openai_provider.py`
- Modify: `src/muse/openai_provider.py`

**Interfaces:**
- Produces: exact transport-attempt counts on successful envelopes and failure evidence; quotes reserve `(repair_attempts + 1) * (max_retries + 1)` calls per logical operation.

- [x] Add retry-success, retry-exhaustion, and quote regressions that distinguish transport retries from repair attempts.
- [x] Run the focused tests and capture RED underreported calls.
- [x] Count invocations at the transport boundary and carry counts through structured-call metering and failures.
- [x] Run focused tests and capture GREEN.

### Task 4: Preserve transform branch provenance

**Files:**
- Modify: `tests/test_transforms.py`
- Modify: `tests/test_openai_provider.py`
- Modify: `src/muse/transforms.py`
- Modify: `src/muse/openai_schemas.py`
- Modify: `src/muse/deterministic.py`

**Interfaces:**
- Produces: `transformed_branch_strategy(parents)` where unary transforms retain the parent strategy and multi-parent transforms deterministically retain the first parent's strategy.

- [x] Add unary and ordered multi-parent provenance regressions for local and OpenAI transform constructors.
- [x] Run focused tests and capture RED fallback to `constraint_inversion`.
- [x] Centralize and apply the deterministic provenance policy.
- [x] Run focused tests and capture GREEN.

### Task 5: Validate agent-facing branch evidence

**Files:**
- Modify: `tests/test_middleware.py`
- Modify: `src/muse/middleware.py`
- Modify: `src/muse/openai_provider.py`
- Modify: `README.md`
- Modify: `docs/quality/benchmarking.md`

**Interfaces:**
- Produces: strict ordered-prefix validation of nested branch request/response traces whose calls and token usage reconcile with each seeding `SpendRecord`.

- [x] Add regressions for empty placeholders, reordered/non-prefix/duplicate/forged entries, malformed nested traces, and calls/usage mismatches.
- [x] Run focused tests and capture RED accepted evidence.
- [x] Emit branch-local calls/usage in canonical traces and validate ordered structure plus spend reconciliation.
- [x] Run focused tests and capture GREEN.

### Task 6: Report, verify, self-review, and commit

**Files:**
- Append: `.superpowers/sdd/final-review-fix-report.md`

- [x] Run all changed-path focused tests.
- [x] Run `python -m pytest -q`.
- [x] Run `python -m ruff check .`.
- [x] Run `git diff --check`.
- [x] Review the full diff against all five findings and prior V6-B guarantees.
- [x] Append RED/GREEN evidence, changed files, design decisions, self-review, concerns, and the final commit SHA to the report.
- [x] Commit with a terse fix message.

### Task 7: Match the complete canonical branch directive

**Files:**
- Modify: `tests/test_middleware.py`
- Modify: `src/muse/middleware.py`
- Modify: `README.md`
- Modify: `docs/quality/benchmarking.md`
- Append: `.superpowers/sdd/final-review-fix-report.md`

**Interfaces:**
- Produces: branch evidence validation against the complete canonical `BranchDirective`, including the exact instruction.

- [x] Add a regression with the canonical index and strategy but a contradictory nonblank instruction, plus documentation contract assertions.
- [x] Run the focused tests and capture RED evidence that the contradictory directive is counted and the stricter contract is undocumented.
- [x] Preserve canonical `BranchDirective` objects through validation and require the parsed nested directive to equal the scheduled directive.
- [x] Document the complete-directive requirement and run the focused tests to capture GREEN.
- [x] Append evidence, run all required verification, self-review, and commit.
