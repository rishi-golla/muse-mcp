# V6-A Final-Review Hardening Plan

## Task 1: Lock down regression behavior with RED tests

Modify `tests/test_quality_benchmark.py` to use neutral candidate content and
add tests for:

1. assignment stability by `(random_seed, task, repetition)` despite an earlier
   generation failure;
2. task-level decisive majority counts and Wilson denominator;
3. configured label leaks being recorded without a judge call;
4. typed judge success/failure attempts, partial records, and judge telemetry;
5. deterministic self-describing metadata.

Update `tests/test_open_source_readiness.py` assertions as needed for the new
documentation language. Run `python -m pytest tests/test_quality_benchmark.py
-q` and record the expected RED failures before implementation.

## Task 2: Implement the benchmark hardening

Modify `src/muse/quality_benchmark.py` using the existing Pydantic frozen-model
style. Add `RunMetadata`, `JudgeFailure`, and `JudgeAttempt`; make corpus
versioning and judge adapter metadata explicit; isolate assignment derivation;
record label leaks and judge exceptions; aggregate task outcomes before Wilson;
and include judge telemetry in report totals. Preserve generation failure
records and the provider-neutral callable boundary.

Run the focused tests after each coherent RED-GREEN slice.

## Re-review follow-up

The final review additionally requires explicit-only blind-label configuration,
repository secret-pattern redaction for generation and judge failures, and
caller-supplied aware timestamps plus prompt/configuration versions in
`RunMetadata`. These follow-up contracts are covered by the regression tests in
`tests/test_quality_benchmark.py` and the maintainer documentation.

## Task 3: Align exports and maintainer documentation

Modify `src/muse/__init__.py` and `docs/quality/benchmarking.md` so the public
library-first example returns `JudgeAttempt`, supplies adapter identifiers, and
describes candidate-only judge input, label-leak rejection, task-level
aggregation, deterministic metadata, and complete generation/judge accounting.

Run documentation tests and the full non-live suite.

## Task 4: Verify, self-review, and commit

Run focused benchmark tests, full non-live pytest, and `ruff check src tests`.
Review the complete diff against the design and final-review findings, then
commit all changes as `fix: harden blinded benchmark evidence`.
