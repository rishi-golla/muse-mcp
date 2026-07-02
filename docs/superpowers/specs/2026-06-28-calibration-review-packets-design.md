# Slice 2C-A Calibration Review Packets Design

## Goal

Slice 2C-A starts the calibration pilot by generating reviewer-ready packets from existing
`RunResult` traces. The packet is anonymized and randomized so a human reviewer can judge
candidate quality without seeing provider identities, source URLs, internal candidate IDs, run
fingerprints, or branch order.

This slice does not ingest ratings, measure agreement, fit weights, build the twenty-task set, or
produce budget comparison reports. Those remain later 2C slices.

## Context

Milestone 2C asks whether the originality estimate predicts human judgments. The first useful
software step is not calibration math; it is a stable artifact that reviewers can inspect. If the
packet leaks identity or ordering cues, later ratings become harder to trust.

## Approaches Considered

1. **Trace-only export:** Dump sanitized trace JSON for reviewers.
   - Simple, but too noisy and still exposes implementation details.

2. **Dedicated review packet model:** Convert a `RunResult` into a compact Pydantic packet with
   blinded candidate labels.
   - Slightly more code, but creates a clean contract for later rating ingestion.

3. **Full calibration bundle:** Generate packets, rating forms, ingestion, agreement metrics, and
   weight fitting together.
   - Too large for one reviewable slice and risks hiding packet-design mistakes under later math.

Recommended approach: dedicated review packet model.

## Architecture

Add a focused `calibration_packets` module. It owns immutable packet models, deterministic
candidate shuffling, anonymized candidate labels, and JSON writing. The rest of the engine stays
unchanged and continues to emit normal `RunResult` traces.

Add a `review-packet` CLI command that reads one or more trace files, validates them as
`RunResult`, builds packets, writes JSON files, and prints a small machine-readable summary.

## Packet Contract

Each packet contains:

- `packet_id`: deterministic SHA-256 digest of run fingerprint, packet version, and shuffle seed.
- `packet_version`: fixed version string for this schema.
- `task`: reviewer-visible task context with goal, audience, constraints, preferences, and risk
  tolerance.
- `rubric`: stable prompts for originality, usefulness, coherence, feasibility, user fit, and
  overall preference.
- `candidates`: randomized tuple of blinded candidates.
- `metadata`: reviewer-safe bookkeeping only, starting with candidate count. Run IDs,
  stop reasons, fingerprints, providers, costs, and shuffle seeds stay out of the packet.

Each candidate contains:

- `label`: `A`, `B`, `C`, ...
- `title`, `core_mechanism`, `problem_framing`, `task_value`
- bounded explanatory fields useful for human judgment

Each candidate must not contain:

- candidate UUIDs
- parent IDs
- source URLs
- provider names
- raw operation traces
- branch cost or latency
- run ordering position
- model-generated scores
- run fingerprints

## Randomization

The packet builder accepts an integer `shuffle_seed`. Candidate order is deterministic for the
same run and seed, and changes when the seed changes. Labels are assigned after shuffling, so
label `A` never encodes original rank.

The default seed is `0` to make CLI output reproducible unless the caller explicitly changes it.

## CLI Behavior

Command:

```powershell
python -m muse.cli review-packet --trace <trace.json> --output-dir <dir> --shuffle-seed 17
```

For multiple traces, pass `--trace` multiple times. The CLI writes one packet per trace as
`<packet_id>.review-packet.json` and prints:

```json
{
  "packet_count": 1,
  "packets": [
    {
      "packet_id": "...",
      "path": "C:/.../<packet_id>.review-packet.json",
      "candidate_count": 3
    }
  ]
}
```

Invalid trace files return exit code `2` with a concise argparse-style error and no traceback.
Filesystem write failures return exit code `1`.

## Testing

Tests must cover:

- packet models reject empty or malformed packet content
- builder excludes IDs, source URLs, provider identities, traces, costs, and latency
- builder is deterministic for the same seed and changes order for a different seed
- packet labels are assigned after shuffling
- JSON writer is stable and writes atomically enough for the existing local artifact style
- CLI writes packet files and summary JSON
- CLI reports invalid trace input without traceback
- final review regression ensures packet JSON does not expose hidden fields

## Out Of Scope

- human rating form ingestion
- reviewer identity
- inter-rater agreement
- calibration weight fitting
- held-out evaluation
- task-set generation
- budget comparison reports
- live provider execution

## Self-Review

- No placeholders remain.
- Scope is a single independently testable artifact generator.
- The design keeps reviewer-facing artifacts separate from internal traces.
- Later 2C slices can add ratings and calibration without changing the packet contract unless the
  schema version changes.
