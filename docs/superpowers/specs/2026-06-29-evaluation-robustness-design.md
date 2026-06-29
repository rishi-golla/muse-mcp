# Slice 2D-A Evaluation Robustness Design

## Goal

Slice 2D-A hardens the live engine path we tested in production-like use. Live
framing and seeding already generate task-specific ideas, but evaluation can fail
when the provider returns scores on a 0-10 scale instead of the required 0-1
scale. Today one failed evaluation causes the engine to return zero finalists and
hides the actionable reason behind `provider operation failed`.

The goal is to preserve useful generated candidates, make evaluation repair more
reliable, and surface safe diagnostics so real workflow testing is possible before
building middleware.

## Evidence

The failing live run produced strong seed ideas for an interactive 3D portfolio,
then stopped at evaluation. A direct provider diagnostic showed the root cause:
`OpenAIEvaluation` rejected values such as `9.7`, `8.4`, and `9.2` because scores
must be finite floats between `0.0` and `1.0`.

## Approaches Considered

1. **Silently normalize 0-10 scores to 0-1.**
   - Fast, but hides provider drift and can reinterpret ambiguous values without
     evidence.

2. **Force repair and keep invalid candidates as unevaluated if repair fails.**
   - Preserves the trust boundary: scores must arrive on the documented scale.
     If repair fails, the generated candidate remains available for inspection
     without pretending it has calibrated scores.

3. **Abort the run on evaluation failure, but expose a better error.**
   - Improves debugging, but leaves production testing brittle.

Recommended approach: force repair and preserve partial results.

## Architecture

Keep the core engine shape intact. Evaluation remains a provider operation that
returns `EvaluationScores` on the 0-1 scale. The OpenAI provider should make that
scale explicit in schema metadata and repair prompts. The engine should treat
evaluation failure as candidate-level failure when generation has already
succeeded.

Generated candidates that cannot be evaluated should still be validated,
attributed with branch cost and latency, and included in `RunResult.all_candidates`
with `scores=None`. They should not be selected as finalists unless no scored
candidates exist. If no scored candidates exist, the CLI summary should still
show generated unevaluated candidates separately from finalists.

## Error Handling

Provider errors must remain secret-safe, but they should not erase the useful
diagnostic category. A validation failure caused by out-of-range evaluation scores
should be recorded as an evaluation validation error with a safe message such as
`provider returned evaluation scores outside 0..1`.

The engine should continue evaluating other seed candidates after one evaluation
fails. For transformation generations, a failed descendant evaluation should skip
that descendant and continue with other selected parents when possible.

## CLI Behavior

Existing summary fields remain stable:

- `run_id`
- `finalist_count`
- `stopped_reason`
- `trace_path`
- `finalists`

Add `generated_count` and `unevaluated_count`. Add `unevaluated_candidates` with
title-only summary entries so live testing surfaces useful generated work even
when evaluation fails.

## Testing

Tests must cover:

- OpenAI evaluation repair when the first response returns 0-10 scores and the
  repair response returns 0-1 scores.
- Safe diagnostic details for out-of-range evaluation scores.
- Seed candidates remain in `RunResult.all_candidates` when one or more
  evaluations fail.
- Scored candidates are preferred as finalists over unevaluated candidates.
- CLI summaries expose generated and unevaluated candidates without changing
  secret-safety behavior.

## Out Of Scope

- Middleware/API integration for host agents.
- Human rating ingestion or calibration fitting.
- Silent normalization of evaluation scores.
- Live provider execution in the normal test suite.
- Changing the review packet schema.

## Self-Review

- No placeholders remain.
- Scope is limited to evaluation robustness and inspectability.
- The design preserves the 0-1 score contract instead of weakening validation.
- Middleware remains deferred until the engine can survive realistic live
  provider behavior.
