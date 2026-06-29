import json
import os
from uuid import UUID

import pytest
from pydantic import ValidationError

from creativity_layer.calibration_packets import (
    ReviewPacket,
    ReviewPacketStore,
    build_review_packet,
)
from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    OperationTrace,
    ProviderIdentity,
    RunConfig,
    RunProviders,
    RunResult,
    SpendRecord,
    TaskContext,
)


def run_result() -> RunResult:
    parent_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    first = IdeaGenome(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        generation=1,
        title="Quiet launch room",
        core_mechanism="Route launch decisions through a small reversible rehearsal.",
        problem_framing="Launch risk is treated as certainty instead of uncertainty.",
        assumptions_challenged=("launches need a single go/no-go meeting",),
        task_value="Teams see reversible risks before deciding.",
        distinguishing_features=("uses rehearsal notes as decision inputs",),
        source_urls=("https://leaky.example/source-one",),
        first_order_effects=("slower first pass",),
        second_order_effects=("better shared judgment",),
        feasibility_assumptions=("team can schedule a rehearsal",),
        uncertainties=("reviewer availability",),
        weaknesses=("adds coordination overhead",),
        parent_ids=(parent_id,),
        scores=EvaluationScores(
            originality=0.91,
            usefulness=0.82,
            coherence=0.73,
            feasibility=0.64,
            user_fit=0.55,
        ),
        branch_cost_usd=12.34,
        branch_latency_ms=9876.0,
    )
    second = IdeaGenome(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        generation=1,
        title="Decision shadow board",
        core_mechanism="Keep a shadow board of discarded options and revisit triggers.",
        problem_framing="Discarded options disappear too early.",
        assumptions_challenged=("teams only need the winning option",),
        task_value="Teams can recover a better fit when conditions change.",
        distinguishing_features=("links reversals to explicit triggers",),
        source_urls=("https://leaky.example/source-two",),
        first_order_effects=("clearer alternatives",),
        second_order_effects=("less sunk-cost pressure",),
        feasibility_assumptions=("team can maintain triggers",),
        uncertainties=("trigger quality",),
        weaknesses=("may over-document choices",),
        parent_ids=(parent_id,),
        scores=EvaluationScores(
            originality=0.44,
            usefulness=0.53,
            coherence=0.62,
            feasibility=0.71,
            user_fit=0.80,
        ),
        branch_cost_usd=56.78,
        branch_latency_ms=1234.0,
    )
    return RunResult(
        config=RunConfig(seed_count=2, finalist_count=2),
        providers=RunProviders(
            framer=ProviderIdentity(name="leaky-framer", version="1"),
            seeder=ProviderIdentity(name="leaky-seeder", version="1"),
            transformer=ProviderIdentity(name="leaky-transformer", version="1"),
            evaluator=ProviderIdentity(name="leaky-evaluator", version="1"),
        ),
        operator_schedule=("invert", "combine"),
        framed_task=FramedTask(
            context=TaskContext(
                goal="Test creativity",
                audience="Product team",
                constraints=("two-week pilot",),
                preferences=("low ceremony",),
                risk_tolerance=0.25,
            ),
            assumptions=("launch risk is knowable",),
            obvious_solution="Run a standard launch review.",
        ),
        finalists=(first, second),
        all_candidates=(first, second),
        spend_records=(
            SpendRecord(
                stage="evaluate",
                provider="leaky-spend-provider",
                model="leaky-model",
                cost_usd=99.99,
                latency_ms=4321,
                operation_trace=OperationTrace.from_payload(
                    request={"provider": "leaky-trace-provider"},
                    response={"source_url": "https://leaky.example/trace"},
                ),
            ),
        ),
        stopped_reason="generation_limit",
    )


def test_build_review_packet_blinds_and_scores_finalists() -> None:
    packet = build_review_packet(run_result(), shuffle_seed=17)

    assert packet.packet_version == "review-packet-v1"
    assert tuple(candidate.label for candidate in packet.candidates) == ("A", "B")
    assert packet.task.goal == "Test creativity"
    assert packet.task.audience == "Product team"
    assert packet.task.constraints == ("two-week pilot",)
    assert packet.task.preferences == ("low ceremony",)
    assert packet.task.risk_tolerance == 0.25
    assert packet.metadata.candidate_count == 2
    assert not hasattr(packet.candidates[0], "candidate_id")
    assert not hasattr(packet.candidates[0], "source_urls")
    assert not hasattr(packet.candidates[0], "parent_ids")
    assert not hasattr(packet.candidates[0], "system_scores")


def test_review_packet_json_excludes_hidden_candidate_and_trace_data() -> None:
    packet = build_review_packet(run_result(), shuffle_seed=17)
    packet_json = packet.model_dump_json()
    packet_payload = json.loads(packet_json)

    assert "rubric" in packet_payload
    assert "candidates" in packet_payload
    assert set(packet_payload["metadata"]) == {"candidate_count"}
    for forbidden in (
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "https://leaky.example/source-one",
        "https://leaky.example/source-two",
        "https://leaky.example/trace",
        "leaky-framer",
        "leaky-seeder",
        "leaky-transformer",
        "leaky-evaluator",
        "leaky-spend-provider",
        "leaky-trace-provider",
        "branch_cost_usd",
        "branch_latency_ms",
        "operation_trace",
        "source_urls",
        "parent_ids",
        "system_scores",
        "run_id",
        "stopped_reason",
        "shuffle_seed",
        "run_fingerprint",
        run_result().reproducibility_fingerprint,
        "providers",
        "all_candidates",
        "spend_records",
        '"generation"',
        "0.91",
        "0.82",
    ):
        assert forbidden not in packet_json


def test_review_packet_shuffle_and_packet_id_are_deterministic() -> None:
    result = run_result()
    first = build_review_packet(result, shuffle_seed=17)
    second = build_review_packet(result, shuffle_seed=17)

    assert first == second
    assert first.packet_id == second.packet_id

    base_order = tuple(candidate.title for candidate in first.candidates)
    changed_order = next(
        tuple(
            candidate.title
            for candidate in build_review_packet(
                result, shuffle_seed=seed
            ).candidates
        )
        for seed in range(18, 50)
        if tuple(
            candidate.title
            for candidate in build_review_packet(
                result, shuffle_seed=seed
            ).candidates
        )
        != base_order
    )

    assert changed_order != base_order


def test_review_packet_models_are_immutable() -> None:
    packet = build_review_packet(run_result(), shuffle_seed=17)

    with pytest.raises(ValidationError):
        packet.metadata.candidate_count = 99


def test_packet_id_uses_version_fingerprint_and_seed_only() -> None:
    result = run_result()
    original = build_review_packet(result, shuffle_seed=17)
    changed_candidate_text = result.model_copy(
        update={
            "finalists": (
                result.finalists[0].model_copy(update={"title": "Changed title"}),
                result.finalists[1],
            ),
            "all_candidates": (
                result.finalists[0].model_copy(update={"title": "Changed title"}),
                result.finalists[1],
            ),
        }
    )

    changed = build_review_packet(changed_candidate_text, shuffle_seed=17)

    assert changed.packet_id == original.packet_id


def test_review_packet_rejects_empty_candidate_content() -> None:
    packet = build_review_packet(run_result(), shuffle_seed=17)
    payload = packet.model_dump(mode="json")
    payload["candidates"] = []
    payload["metadata"]["candidate_count"] = 0

    with pytest.raises(ValidationError):
        ReviewPacket.model_validate(payload)


def test_review_packet_store_writes_stable_json(tmp_path, monkeypatch) -> None:
    packet = build_review_packet(run_result(), shuffle_seed=17)
    replaced_from = []
    fsynced = []
    real_replace = os.replace
    real_fsync = os.fsync

    def record_replace(source, destination) -> None:
        replaced_from.append((source, destination))
        real_replace(source, destination)

    def record_fsync(file_descriptor) -> None:
        fsynced.append(file_descriptor)
        real_fsync(file_descriptor)

    monkeypatch.setattr(os, "replace", record_replace)
    monkeypatch.setattr(os, "fsync", record_fsync)

    packet_root = tmp_path / "packets"
    store = ReviewPacketStore(packet_root)
    path = store.save(packet)
    first_bytes = path.read_bytes()
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text("stale packet", encoding="utf-8")

    overwritten_path = store.save(packet)

    assert path == packet_root / f"{packet.packet_id}.review-packet.json"
    assert path.name == f"{packet.packet_id}.review-packet.json"
    assert payload == packet.model_dump(mode="json")
    assert first_bytes == json.dumps(packet.model_dump(mode="json"), indent=2).encode(
        "utf-8"
    )
    assert overwritten_path == path
    assert overwritten_path.read_bytes() == first_bytes
    assert len(fsynced) == 2
    assert len(replaced_from) == 2
    assert replaced_from[0][0] != replaced_from[1][0]
    assert all(source.parent == packet_root for source, _ in replaced_from)
    assert all(destination == path for _, destination in replaced_from)
    assert list(packet_root.iterdir()) == [path]
