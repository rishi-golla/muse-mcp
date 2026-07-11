# V6 High-Fidelity Search Design

## Goal

V6 must establish and improve Muse's creative quality without changing its
agent-native MCP posture. Quality claims must be supported by blinded
comparisons against a direct strong-model baseline, not Muse's own scores.

## Architecture

V6 is delivered as seven independently reviewable stacked slices:

1. V6-A builds a provider-neutral blinded benchmark.
2. V6-B generates each seed through an independent strategy-bound call.
3. V6-C allocates research by branch and adds semantic novelty.
4. V6-D adds order-swapped pairwise judging and critique-repair.
5. V6-E adds elite retention, adaptive operators, crossover, and plateau stops.
6. V6-F synthesizes one recommendation and accepts execution feedback.
7. V6-G calibrates judges and enforces an evidence-based release gate.

Each component has typed, provider-neutral interfaces. Live adapters stay at
the boundary; ordinary tests use fakes and spend no provider budget.

## Data Flow

The target flow is:

repo evidence -> framing -> independent branches -> branch research -> semantic
novelty -> pairwise critique -> adaptive evolution -> synthesis -> agent
verification -> feedback

Search-isolated branches remain available so research does not collapse every
candidate onto the same prior art. Research-enabled branches receive different
source abstractions, and provenance remains attached to artifacts.

## Benchmark Contract

The benchmark corpus contains at least 30 domain-varied tasks. A run records the
task, repetition, anonymized artifacts, hidden system identity, judgments, cost,
latency, and failures. Candidate order is reproducibly randomized.

Judges compare originality, usefulness, operational specificity, and task fit.
They return a preference, confidence, concise rationale, and per-dimension
winners. Reports expose wins, losses, ties, preference rate, Wilson confidence
intervals, and raw records.

## Failure Handling

Provider failures are recorded per system and repetition rather than silently
converted into losses. Malformed judgments are rejected. A release cannot pass
with missing coverage, excessive failures, insufficient judge agreement, or a
confidence interval below the configured baseline threshold.

## Compatibility

The public MCP surface remains centered on muse_plan, mode normal, and mode
extensive. Low-level budgets and run-shape knobs remain internal. Deterministic
providers remain test fixtures only.

## Testing

Every slice follows RED-GREEN-REFACTOR. The full non-live suite and Ruff must
pass before every PR.

## Non-Goals

V6 does not add persistent identity, long-term taste profiles, autonomous repo
crawling, or a new user-facing CLI workflow.
