# V6-A Final-Review Hardening Design

## Scope

Harden the provider-neutral quality benchmark against five evidence-integrity
failures: order-dependent blinding, repetition-weighted confidence intervals,
label leakage, lost judge failures, and opaque run accounting.

## Contracts and data flow

- `BenchmarkCorpus` carries a required deterministic version string.
- `RunMetadata` records `random_seed`, `repetitions`, corpus version, and the
  three adapter identifiers. It is part of every `BenchmarkReport` and contains
  no wall-clock or generated identifiers, so the same inputs produce the same
  metadata.
- Candidate assignment is a pure function of the seed, task name, and
  repetition. The runner calls it for every completed cell, so a failed earlier
  cell cannot shift any later A/B assignment.
- `JudgeArtifact` remains content-only. Before the judge is called, each
  generated artifact is checked against configured system/provider labels using
  case-insensitive token matching. A leak is recorded as an artifact failure and
  that cell is not sent to the judge.
- `JudgeAttempt` contains exactly one of a `PairwiseJudgment` or sanitized
  `JudgeFailure`, plus judge `cost_usd` and `latency_ms`. Exceptions are captured
  into the same typed record, preserving generation and assignment data already
  collected for the cell.
- Each task is reduced to one decisive outcome after all successful repetitions:
  Muse wins only when its decisive repetition majority exceeds the baseline;
  baseline wins only when the reverse is true; otherwise the task is a tie or
  unresolved. Wilson bounds use task-level decisive outcomes, never repetition
  rows. Raw repetition judgments remain in the report for auditability.
- Generation and judge telemetry are summed independently into report totals;
  judge failures still contribute non-negative telemetry supplied by the judge
  attempt or exception wrapper.

## Error handling

Generation exceptions and label leaks are sanitized to type plus a bounded,
single-line message. Judge exceptions are sanitized the same way. No exception
from an individual cell aborts the benchmark or discards records from earlier
cells.

## Verification

Tests first prove each finding with minimal deterministic fakes, including an
earlier failed cell, repeated task aggregation, configured-label leaks, judge
exceptions, and cost/latency totals. Documentation tests assert that the
maintainer workflow explains metadata, aggregation, and judge telemetry. The
focused benchmark tests, full non-live pytest suite, and Ruff must pass before
the final commit.
