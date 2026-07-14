# V6-B Final Review Fix Report

## 2026-07-14 hardening pass

Requirements source: `.superpowers/sdd/final-review-findings.md`

Status: all five Critical and Important findings are fixed in implementation commit
`2252765` (`fix: close v6b blockers`). The worktree was clean before this pass, so every
changed file listed below belongs to this fix.

### Baseline

- Focused baseline before new tests:
  `python -m pytest -q tests/test_openai_provider.py tests/test_engine.py tests/test_middleware.py tests/test_mcp_server.py tests/test_transforms.py`
  -> `140 passed`.
- Full baseline before new tests: `python -m pytest -q` -> `853 passed, 4 deselected`.

### Finding 1: executable public mode defaults

RED command:

```text
python -m pytest -q tests/test_mcp_server.py::test_muse_plan_public_signature_uses_modes_instead_of_low_level_run_knobs tests/test_middleware.py::test_extensive_public_defaults_reach_live_seeding_at_default_call_ceilings
```

RED result: `2 failed`. The MCP signature still exposed `max_calls`, and extensive mode
resolved `request.max_calls` to `20` rather than the required worst-case call ceiling.

GREEN result from the same command: `2 passed`.

Fix: public MCP callers continue to select only `mode=normal|extensive` for creative run
shape. `max_calls` is now internal and derived from the preset's complete logical operation
count multiplied by the default repair and transport-retry ceilings. The resulting quick,
standard/normal, and deep/extensive ceilings are 30, 102, and 222 calls. The integration
regression proves extensive live-provider defaults reserve successfully and invoke seeding.

### Finding 2: terminal branch failure metering

RED command:

```text
python -m pytest -q tests/test_openai_provider.py::test_first_seed_branch_terminal_repair_failure_preserves_its_metering tests/test_openai_provider.py::test_later_seed_branch_terminal_repair_failure_includes_own_metering tests/test_engine.py::test_engine_charges_first_branch_terminal_failure_exactly_once
```

RED result: `2 failed, 1 passed`. A first-branch terminal repair raised a plain
`RuntimeError`; a later failed branch reported only one earlier call instead of all three
incurred calls.

GREEN result from the same command: `3 passed`. The same regressions were rerun after retry
accounting was added and remained `3 passed`.

Fix: `_call_structured` now emits the existing provider-neutral `MeteredProviderFailure`
whenever a transport call or provider response was incurred. Its partial envelope retains
sanitized failure text, every retained response's usage and cost, exact calls, latency,
request identity, and operation trace. Seed aggregation combines prior successful branch
evidence with the failed branch's own evidence. The engine validates and charges that
aggregate once, then returns no candidates, preserving all-or-nothing seed cardinality.

### Finding 3: exact transport retry accounting

RED command:

```text
python -m pytest -q tests/test_openai_provider.py::test_openai_quotes_include_possible_repair_attempts tests/test_openai_provider.py::test_exhausted_transport_retries_emit_metered_failure_attempts tests/test_openai_provider.py::test_rate_limits_and_timeouts_use_retry_policy tests/test_openai_provider.py::test_transport_retries_and_repairs_are_counted_once_each
```

RED result: `4 failed`. The quote reported 4 calls instead of 12; exhausted retries escaped
without a metered partial; a retry-success envelope reported 1 call instead of 3; and a
repair plus transport retries reported 2 calls instead of 4.

GREEN result from the same command: `4 passed`.

Fix: calls are counted immediately around each actual client transport invocation inside the
retry executor. The count survives both success and terminal transport failure. Quotes use
`(repair_attempts + 1) * (max_retries + 1) * logical_operation_count`, so repair and retry
ceilings are reserved once each without double-counting. Usage and cost continue to include
only provider responses that exist; failed invocations with no response still carry exact
call evidence with zero fabricated usage.

### Finding 4: transformed branch provenance

RED command:

```text
python -m pytest -q tests/test_transforms.py::test_deterministic_unary_transform_preserves_parent_branch_strategy tests/test_transforms.py::test_deterministic_combine_uses_first_parent_branch_strategy tests/test_openai_provider.py::test_openai_unary_transform_preserves_parent_branch_strategy
```

RED result: `3 failed`; transformed candidates fell back to
`constraint_inversion` instead of retaining ancestry.

GREEN result from the same command: `3 passed`.

Additional boundary RED/GREEN:
`tests/test_transforms.py::test_transform_validation_rejects_inconsistent_branch_provenance`
failed with `DID NOT RAISE`, then passed after provider-boundary validation was added.

Fix: `transformed_branch_strategy(parents)` centralizes provenance. Unary transforms preserve
their sole parent's strategy. Ordered multi-parent transforms preserve the first parent's
strategy, matching the existing ordered-parent and first-history combine semantics. Both
deterministic and OpenAI constructors apply the policy, and the engine boundary rejects a
provider candidate that forges it.

### Finding 5: strict agent-facing trace evidence

RED command:

```text
python -m pytest -q tests/test_middleware.py::test_runner_reports_only_evidenced_completed_branches_after_seed_failure tests/test_middleware.py::test_runner_rejects_placeholder_reordered_and_nonprefix_branch_evidence tests/test_middleware.py::test_runner_rejects_forged_nested_branch_directive tests/test_middleware.py::test_runner_rejects_branch_trace_accounting_inconsistent_with_spend
```

RED result: `3 failed, 1 passed`; placeholders/reordered or non-prefix schedules, nested
forgeries, and accounting mismatches were accepted as one completed branch.

GREEN result from the same command: `4 passed`.

Documentation RED/GREEN:
`tests/test_middleware.py::test_branch_generation_docs_distinguish_live_trajectories_from_fixtures`
failed because the ordered-prefix evidence contract was absent, then passed after README and
benchmarking documentation were updated.

Self-review edge-case RED/GREEN:
boolean branch indexes and empty successful `parsed` payloads were added to
`test_runner_rejects_placeholder_reordered_and_nonprefix_branch_evidence`; the focused test
initially failed one case, then passed after strict type and non-empty payload checks.

Fix: branch evidence must be an ordered prefix of `branch_directives(seed_count)`. Every
outer and nested index/strategy must agree; nested request directives need a non-empty
instruction; nested responses need structurally valid attempts, success/failure state,
parsed/error state, calls, request IDs, and token usage. Nested calls and usage, aggregate
trace calls/usage/request IDs, and the charged `SpendRecord` must reconcile exactly.
Placeholder, reordered, duplicate, forged, over-scheduled, and inconsistent traces report
zero evidenced independent calls.

### Changed files

Production:

- `src/muse/live_config.py`
- `src/muse/mcp_server.py`
- `src/muse/middleware.py`
- `src/muse/openai_provider.py`
- `src/muse/openai_schemas.py`
- `src/muse/deterministic.py`
- `src/muse/operation.py`
- `src/muse/transforms.py`

Tests:

- `tests/test_engine.py`
- `tests/test_mcp_server.py`
- `tests/test_middleware.py`
- `tests/test_openai_provider.py`
- `tests/test_transforms.py`

Documentation and workflow evidence:

- `README.md`
- `docs/quality/benchmarking.md`
- `docs/superpowers/plans/2026-07-14-v6b-final-review-fixes.md`
- `.superpowers/sdd/final-review-fix-report.md`

### Design decisions and compatibility

- Kept `MeteredProviderFailure` unchanged as the provider-neutral contract; the OpenAI
  adapter now supplies complete evidence instead of introducing provider-specific errors.
- Kept normal/extensive MCP controls and removed only the leaked low-level `max_calls` knob.
  Middleware and direct engine APIs retain their existing internal controls.
- Preserved secret redaction and generic engine error messages. Tests cover API-key-like
  values in terminal transport and repair failures.
- Preserved quote and budget enforcement by making quotes more conservative at the actual
  retry ceiling; no reservation bypasses were introduced.
- Preserved exact accounting by separating invocation counts from response-derived usage and
  charging the aggregate failed seed envelope exactly once.
- Preserved all-or-nothing candidate cardinality: successful branch values may exist only as
  internal failure evidence, while the engine result exposes zero seed candidates on any
  branch failure.
- Used first-parent provenance for multi-parent transforms because parent order already has
  semantic meaning in IDs, requests, and transformation-history merging.

### Verification

- Changed-path suite:
  `python -m pytest -q tests/test_openai_provider.py tests/test_engine.py tests/test_middleware.py tests/test_mcp_server.py tests/test_transforms.py tests/test_live_config.py`
  -> `228 passed in 6.88s`.
- Full suite: `python -m pytest -q` -> `866 passed, 4 deselected in 16.67s`.
- Ruff: `python -m ruff check .` -> `All checks passed!`.
- Whitespace: `git diff --check` -> exit 0.
- Implementation commit: `2252765` (`fix: close v6b blockers`).

### Self-review

The final diff was reviewed finding-by-finding against the requirements source. The review
confirmed that mode-derived calls cover the full default logical run shape at configured
default retry/repair ceilings; failed branch calls and response usage flow into one charged
spend record; retry quotes and envelopes use the same count model; provenance is constructed
and validated consistently; and only spend-reconciled ordered live branch traces can affect
agent-facing independent-call claims. Existing provider-neutral interfaces, sanitized error
surfaces, budget checks, exact spend accounting, and no-partial-candidate behavior remain in
place.

### Concerns

No V6-B blocker remains. The test runs emit the repository's existing `pytest-asyncio`
deprecation warning because `asyncio_default_fixture_loop_scope` is unset; it does not affect
test results and is outside this fix's scope.
