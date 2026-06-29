# Calibration Review Packets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Slice 2C-A review-packet generation for anonymized, randomized human calibration packets from existing `RunResult` traces.

**Architecture:** Add a focused `calibration_packets` module with immutable packet models, deterministic candidate shuffling, hidden-field exclusion, and stable JSON writing. Wire a `review-packet` CLI command that validates trace files, writes one packet per trace, and reports concise JSON output.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, Ruff, existing `RunResult` and trace models.

---

## File Map

```text
src/creativity_layer/calibration_packets.py       Packet models, builder, JSON writer
src/creativity_layer/cli.py                       review-packet command
src/creativity_layer/__init__.py                  optional public exports
tests/test_calibration_packets.py                 Unit tests for packet contract and writer
tests/test_review_packet_cli.py                   CLI tests
tests/test_final_review.py                        Hidden-field regression
README.md                                        Review packet command docs
```

## Shared Rules

- Do not add rating ingestion, reviewer identity, agreement metrics, calibration fitting, task-set generation, or budget reports.
- Do not execute live providers.
- Review packet JSON must not expose candidate UUIDs, parent IDs, source URLs, provider identities, operation traces, branch costs, branch latency, model-generated scores, or reproducibility fingerprints.
- Use the run-level fingerprint only internally for deterministic packet IDs and shuffling.
- Shuffle candidates deterministically from `RunResult.finalists` by default.
- Assign labels only after shuffling.

## Task 1: Packet Models and Builder

**Files:**
- Create: `src/creativity_layer/calibration_packets.py`
- Create: `tests/test_calibration_packets.py`

- [ ] **Step 1: Write failing packet model and builder tests**

Add tests that construct a `RunResult` with scored finalists and assert:

```python
from creativity_layer.calibration_packets import build_review_packet

packet = build_review_packet(run_result(), shuffle_seed=17)
assert packet.packet_version == "review-packet-v1"
assert tuple(candidate.label for candidate in packet.candidates) == ("A", "B")
assert packet.task.goal == "Test creativity"
assert packet.candidates[0].candidate_id is None  # this attribute must not exist
```

Also assert serialized packet JSON does not contain the finalist UUID, parent UUID, source URL,
provider name, `branch_cost_usd`, `branch_latency_ms`, or `operation_trace`.

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_calibration_packets.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task1-red
```

Expected: FAIL because `creativity_layer.calibration_packets` does not exist.

- [ ] **Step 3: Implement packet models and builder**

Create:

```python
PACKET_VERSION = "review-packet-v1"

class ReviewTask(FrozenModel):
    goal: RequiredText
    audience: str | None = None
    constraints: tuple[str, ...] = ()
    preferences: tuple[str, ...] = ()
    risk_tolerance: float

class ReviewRubric(FrozenModel):
    originality_prompt: RequiredText
    usefulness_prompt: RequiredText
    coherence_prompt: RequiredText
    feasibility_prompt: RequiredText
    user_fit_prompt: RequiredText
    overall_prompt: RequiredText

class ReviewCandidate(FrozenModel):
    label: RequiredText
    title: RequiredText
    core_mechanism: RequiredText
    problem_framing: RequiredText
    task_value: RequiredText
    distinguishing_features: tuple[str, ...] = ()
    assumptions_challenged: tuple[str, ...] = ()
    first_order_effects: tuple[str, ...] = ()
    second_order_effects: tuple[str, ...] = ()
    feasibility_assumptions: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    inspiration_kind: str

class ReviewPacketMetadata(FrozenModel):
    candidate_count: int

class ReviewPacket(FrozenModel):
    packet_id: RequiredText
    packet_version: RequiredText
    task: ReviewTask
    rubric: ReviewRubric
    candidates: tuple[ReviewCandidate, ...]
    metadata: ReviewPacketMetadata

def build_review_packet(result: RunResult, *, shuffle_seed: int = 0) -> ReviewPacket:
    candidates = tuple(_candidate_from_genome(candidate, label=label) for label, candidate in _shuffled_finalists(result, shuffle_seed))
    return ReviewPacket(
        packet_id=_packet_id(result, shuffle_seed),
        packet_version=PACKET_VERSION,
        task=_review_task(result),
        rubric=DEFAULT_RUBRIC,
        candidates=candidates,
        metadata=ReviewPacketMetadata(candidate_count=len(candidates)),
    )
```

Use `random.Random(seed_material).shuffle()` where `seed_material` combines
`result.reproducibility_fingerprint` and `shuffle_seed`.

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_calibration_packets.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task1-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/calibration_packets.py tests/test_calibration_packets.py
git commit -m "feat: add calibration review packet models"
```

## Task 2: Stable Packet Writer

**Files:**
- Modify: `src/creativity_layer/calibration_packets.py`
- Modify: `tests/test_calibration_packets.py`

- [ ] **Step 1: Write failing writer tests**

Add tests for:

```python
from creativity_layer.calibration_packets import ReviewPacketStore

path = ReviewPacketStore(tmp_path).save(packet)
assert path.name == f"{packet.packet_id}.review-packet.json"
assert json.loads(path.read_text(encoding="utf-8"))["packet_id"] == packet.packet_id
```

Also test repeated saves are byte-stable and overwrite atomically enough for local files.

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_calibration_packets.py::test_review_packet_store_writes_stable_json -v -p no:cacheprovider --basetemp=.pytest-tmp-task2-red
```

Expected: FAIL because `ReviewPacketStore` does not exist.

- [ ] **Step 3: Implement writer**

Add `ReviewPacketStore(root: Path).save(packet: ReviewPacket) -> Path`. Follow the local
`JsonTraceStore` pattern: create root, write indented JSON to a temporary file, `fsync`, then
`os.replace`.

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_calibration_packets.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task2-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/calibration_packets.py tests/test_calibration_packets.py
git commit -m "feat: add review packet artifact store"
```

## Task 3: Review Packet CLI

**Files:**
- Modify: `src/creativity_layer/cli.py`
- Create: `tests/test_review_packet_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests that:

```python
exit_code = run_cli([
    "review-packet",
    "--trace",
    str(trace_path),
    "--output-dir",
    str(tmp_path / "packets"),
    "--shuffle-seed",
    "17",
])
assert exit_code == 0
summary = json.loads(capsys.readouterr().out)
assert summary["packet_count"] == 1
assert Path(summary["packets"][0]["path"]).exists()
```

Also test invalid trace JSON returns `2`, writes no traceback, and does not create packet files.

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_review_packet_cli.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task3-red
```

Expected: FAIL because `review-packet` is not a recognized command.

- [ ] **Step 3: Implement CLI**

Add `review-packet` to `COMMANDS` and parser. Required options:

```text
--trace <path>        repeatable, required
--output-dir <path>   default .review-packets
--shuffle-seed <int>  default 0
```

Implement `_run_review_packet(args) -> int`: load each trace as JSON, validate with
`RunResult.model_validate`, build packet, save with `ReviewPacketStore`, print JSON summary.
Validation and JSON parse errors return `2`; write errors return `1`.

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_review_packet_cli.py tests/test_calibration_packets.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task3-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/cli.py tests/test_review_packet_cli.py
git commit -m "feat: add review packet CLI"
```

## Task 4: Docs, Exports, and Final Review Regressions

**Files:**
- Modify: `src/creativity_layer/__init__.py`
- Modify: `tests/test_final_review.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing final review/export tests**

Add tests that:

```python
from creativity_layer import ReviewPacket
assert ReviewPacket.__name__ == "ReviewPacket"
```

and:

```python
packet_text = packet.model_dump_json()
for forbidden in ("source_urls", "parent_ids", "branch_cost_usd", "branch_latency_ms", "operation_trace"):
    assert forbidden not in packet_text
```

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_final_review.py::test_review_packet_exports_do_not_expose_hidden_fields -v -p no:cacheprovider --basetemp=.pytest-tmp-task4-red
```

Expected: FAIL until exports/final-review helper are added.

- [ ] **Step 3: Update exports and README**

Export `ReviewPacket`, `ReviewPacketStore`, and `build_review_packet` from `__init__.py`.
Add a concise README section named `Calibration review packets` with the CLI command and a note
that rating ingestion and calibration fitting are later 2C slices.

- [ ] **Step 4: Run final verification and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp-2ca-final
.\.venv\Scripts\python.exe -m ruff check .
git diff --check
git add src/creativity_layer/__init__.py tests/test_final_review.py README.md
git commit -m "test: add review packet final checks"
```

## Final Verification

Run before PR:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=creativity_layer --cov-report=term-missing -p no:cacheprovider --basetemp=.pytest-tmp-2ca-final-coverage
.\.venv\Scripts\python.exe -m ruff check .
git diff --check origin/main...HEAD
```
