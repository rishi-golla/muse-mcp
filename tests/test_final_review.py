from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from uuid import UUID

import pytest

import creativity_layer.cli as cli
import creativity_layer.engine as engine_module
from creativity_layer.budget import BudgetController
from creativity_layer.cli import run_cli
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
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
from creativity_layer.providers import MeteredResponse
from creativity_layer.transforms import TransformationRequest


def build_engine(provider: DeterministicCreativeProvider) -> CreativeEngine:
    return CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    )


def config(*, generations: int = 1) -> RunConfig:
    return RunConfig(
        max_cost_usd=1.0,
        max_calls=20,
        max_generations=generations,
        seed_count=2,
        finalist_count=1,
        framing_reserve_usd=0,
        finalization_reserve_usd=0,
    )


def review_packet_source_result() -> RunResult:
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


def test_run_result_is_self_contained_and_fingerprint_is_reproducible() -> None:
    provider = DeterministicCreativeProvider()
    task = TaskContext(goal="Invent a calmer decision process.")
    run_config = config()

    first = build_engine(provider).run(task, run_config)
    second = build_engine(provider).run(task, run_config)

    assert first.config == run_config
    assert first.providers.model_dump() == {
        "framer": {"name": "deterministic-local", "version": "1"},
        "seeder": {"name": "deterministic-local", "version": "1"},
        "transformer": {"name": "deterministic-local", "version": "1"},
        "evaluator": {"name": "deterministic-local", "version": "1"},
    }
    assert first.operator_schedule == ("invert", "reframe", "subtract", "contradict")
    assert first.errors == ()
    assert len(first.reproducibility_fingerprint) == 64
    assert first.run_id != second.run_id
    assert first.reproducibility_fingerprint == second.reproducibility_fingerprint


def test_trace_naturally_persists_reproducibility_fields(tmp_path: Path) -> None:
    from creativity_layer.tracing import JsonTraceStore

    result = build_engine(DeterministicCreativeProvider()).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(generations=0),
    )

    payload = json.loads(JsonTraceStore(tmp_path).save(result).read_text(encoding="utf-8"))

    assert payload["config"]["seed_count"] == 2
    assert payload["providers"]["evaluator"]["version"] == "1"
    assert payload["operator_schedule"] == ["invert", "reframe", "subtract", "contradict"]
    assert payload["errors"] == []
    assert payload["reproducibility_fingerprint"] == result.reproducibility_fingerprint


def test_run_result_normalizes_uppercase_fingerprint_hex() -> None:
    result = build_engine(DeterministicCreativeProvider()).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(generations=0),
    )
    payload = result.model_dump(mode="json")
    payload["reproducibility_fingerprint"] = result.reproducibility_fingerprint.upper()

    restored = RunResult.model_validate(payload)

    assert restored.reproducibility_fingerprint == result.reproducibility_fingerprint


def test_run_result_rejects_non_hex_fingerprint() -> None:
    result = build_engine(DeterministicCreativeProvider()).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(generations=0),
    )
    payload = result.model_dump(mode="json")
    payload["reproducibility_fingerprint"] = "g" * 64

    with pytest.raises(ValueError, match="SHA-256 hex digest"):
        RunResult.model_validate(payload)


def test_run_result_rejects_stale_fingerprint_after_payload_tampering() -> None:
    result = build_engine(DeterministicCreativeProvider()).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(generations=0),
    )
    payload = result.model_dump(mode="json")
    payload["stopped_reason"] = "tampered"

    with pytest.raises(ValueError, match="does not match canonical payload"):
        RunResult.model_validate(payload)


def test_review_packet_exports_do_not_expose_hidden_fields() -> None:
    from creativity_layer import ReviewPacket, ReviewPacketStore, build_review_packet

    result = review_packet_source_result()
    packet = build_review_packet(result, shuffle_seed=17)
    packet_text = packet.model_dump_json()
    packet_payload = json.loads(packet_text)

    assert ReviewPacket.__name__ == "ReviewPacket"
    assert ReviewPacketStore.__name__ == "ReviewPacketStore"
    assert isinstance(packet, ReviewPacket)
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
        "source_urls",
        "parent_ids",
        "branch_cost_usd",
        "branch_latency_ms",
        "operation_trace",
        "system_scores",
        "run_id",
        "stopped_reason",
        "shuffle_seed",
        "run_fingerprint",
        "reproducibility_fingerprint",
        result.reproducibility_fingerprint,
        "0.91",
        "0.82",
        "0.73",
        "0.64",
        "0.55",
    ):
        assert forbidden not in packet_text


class MalformedEvaluationProvider(DeterministicCreativeProvider):
    def evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]:
        response = super().evaluate(candidate, framed_task)
        malformed = EvaluationScores.model_construct(
            originality=2.0,
            usefulness=0.5,
            coherence=0.5,
            feasibility=0.5,
            user_fit=0.5,
        )
        return response.model_copy(update={"value": malformed})


def test_malformed_evaluator_scores_become_sanitized_structured_error() -> None:
    result = build_engine(MalformedEvaluationProvider()).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(generations=0),
    )

    assert result.stopped_reason == "provider_error"
    assert result.all_candidates == ()
    assert result.errors[-1].stage == "evaluation"
    assert result.errors[-1].provider == "deterministic-local"
    assert result.errors[-1].category == "validation_error"
    assert result.errors[-1].cost_incurred is True


def test_evaluation_scale_errors_are_safe_and_actionable() -> None:
    source = inspect.getsource(engine_module._evaluation_error_details)

    assert "provider returned evaluation scores outside 0..1" in source
    assert "score must be finite and between 0 and 1" in source
    assert "api_key" not in source.lower()
    assert "request_json" not in source


class InvalidSeedProvider(DeterministicCreativeProvider):
    def __init__(self, field: str) -> None:
        self.field = field

    def seed(
        self,
        framed_task: FramedTask,
        run_config: RunConfig,
    ) -> MeteredResponse[tuple[IdeaGenome, ...]]:
        response = super().seed(framed_task, run_config)
        updates = {
            "generation": {"generation": 1},
            "parents": {"parent_ids": (response.value[1].id,)},
            "transformations": {"transformations": ("invert",)},
        }[self.field]
        invalid = response.value[0].model_copy(update=updates)
        return response.model_copy(update={"value": (invalid, response.value[1])})


@pytest.mark.parametrize("field", ["generation", "parents", "transformations"])
def test_invalid_seed_genomes_are_rejected_before_evaluation(field: str) -> None:
    provider = InvalidSeedProvider(field)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(generations=0),
    )

    assert result.all_candidates == ()
    assert result.stopped_reason == "provider_error"
    assert [record.stage for record in result.spend_records] == [
        "framing",
        "seeding",
    ]
    assert result.errors[-1].stage == "seeding"
    assert result.errors[-1].category == "validation_error"
    assert result.errors[-1].cost_incurred is True


class InvalidTransformProvider(DeterministicCreativeProvider):
    def __init__(self, field: str) -> None:
        self.field = field

    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]:
        response = super().transform(request, parents)
        updates = {
            "generation": {"generation": parents[0].generation},
            "parents": {"parent_ids": ()},
            "operator": {"transformations": response.value.transformations + ("distill",)},
        }[self.field]
        return response.model_copy(update={"value": response.value.model_copy(update=updates)})


@pytest.mark.parametrize("field", ["generation", "parents", "operator"])
def test_invalid_transform_output_is_rejected_and_not_inserted(field: str) -> None:
    result = build_engine(InvalidTransformProvider(field)).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(),
    )

    assert len(result.all_candidates) == 2
    assert all(candidate.generation == 0 for candidate in result.all_candidates)
    assert result.stopped_reason == "provider_error"
    assert result.errors[-1].stage == "transformation"
    assert result.errors[-1].category == "validation_error"
    assert result.errors[-1].cost_incurred is True


class SecretFailureProvider(DeterministicCreativeProvider):
    def seed(
        self,
        framed_task: FramedTask,
        run_config: RunConfig,
    ) -> MeteredResponse[tuple[IdeaGenome, ...]]:
        raise RuntimeError("secret-token=do-not-persist")


def test_provider_exception_message_is_sanitized() -> None:
    result = build_engine(SecretFailureProvider()).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(generations=0),
    )

    error = result.errors[-1]
    assert error.stage == "seeding"
    assert error.provider == "deterministic-local"
    assert error.category == "provider_error"
    assert error.message == "provider operation failed"
    assert "secret-token" not in result.model_dump_json()
    assert error.cost_incurred is False


class SpoofingProvider(DeterministicCreativeProvider):
    def __init__(self, stage: str, *, overage: bool = False) -> None:
        self.stage = stage
        self.overage = overage

    def seed(
        self,
        framed_task: FramedTask,
        run_config: RunConfig,
    ) -> MeteredResponse[tuple[IdeaGenome, ...]]:
        response = super().seed(framed_task, run_config)
        if self.stage == "seeding":
            return response.model_copy(
                update={
                    "provider": "spoofed-provider",
                    "cost_usd": 0.02 if self.overage else response.cost_usd,
                }
            )
        return response

    def transform(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
    ) -> MeteredResponse[IdeaGenome]:
        response = super().transform(request, parents)
        if self.stage == "transformation":
            return response.model_copy(update={"provider": "spoofed-provider"})
        return response

    def evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]:
        response = super().evaluate(candidate, framed_task)
        if self.stage == "evaluation":
            return response.model_copy(update={"provider": "spoofed-provider"})
        return response


@pytest.mark.parametrize(
    ("stage", "expected_cost"),
    (
        ("seeding", 0.01),
        ("transformation", 0.01),
        ("evaluation", 0.005),
    ),
)
def test_metered_response_provider_spoofing_is_rejected_after_recording_actual_cost(
    stage: str,
    expected_cost: float,
) -> None:
    result = build_engine(SpoofingProvider(stage)).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(generations=1),
    )

    assert result.stopped_reason == "provider_error"
    assert result.spend_records[-1].stage == stage
    assert result.spend_records[-1].provider == "deterministic-local"
    assert result.spend_records[-1].cost_usd == expected_cost
    assert result.errors[-1].stage == stage
    assert result.errors[-1].provider == "deterministic-local"
    assert result.errors[-1].category == "provider_error"
    assert result.errors[-1].message == "provider identity mismatch"
    assert result.errors[-1].cost_incurred is True


def test_provider_spoofing_remains_provider_error_when_cost_exceeds_quote() -> None:
    result = build_engine(SpoofingProvider("seeding", overage=True)).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(generations=0),
    )

    assert len(result.spend_records) == 2
    assert result.spend_records[1].provider == "deterministic-local"
    assert result.spend_records[1].cost_usd == 0.02
    assert result.errors[-1].provider == "deterministic-local"
    assert result.errors[-1].category == "provider_error"
    assert result.errors[-1].message == "provider identity mismatch"


class InvalidMetadataProvider:
    def __init__(self, name: object, version: object) -> None:
        self.name = name
        self.version = version


@pytest.mark.parametrize(
    ("name", "version"),
    (
        ("", "1"),
        ("   ", "1"),
        ("provider", ""),
        ("provider", "   "),
        (None, "1"),
        ("provider", None),
        (123, "1"),
        ("provider", 1),
    ),
)
def test_engine_rejects_invalid_provider_metadata_at_construction(
    name: object,
    version: object,
) -> None:
    provider = InvalidMetadataProvider(name, version)

    with pytest.raises(ValueError, match="invalid provider metadata"):
        CreativeEngine(
            framer=provider,  # type: ignore[arg-type]
            seeder=provider,  # type: ignore[arg-type]
            transformer=provider,  # type: ignore[arg-type]
            evaluator=provider,  # type: ignore[arg-type]
        )


def test_branch_attribution_is_cumulative_across_seed_and_child_lineage() -> None:
    result = build_engine(DeterministicCreativeProvider()).run(
        TaskContext(goal="Invent a calmer decision process."),
        config(),
    )

    seeds = [candidate for candidate in result.all_candidates if candidate.generation == 0]
    children = [candidate for candidate in result.all_candidates if candidate.generation == 1]

    assert [seed.branch_cost_usd for seed in seeds] == pytest.approx([0.01, 0.01])
    assert [seed.branch_latency_ms for seed in seeds] == pytest.approx([1.5, 1.5])
    assert children
    assert children[0].branch_cost_usd == pytest.approx(0.025)
    assert children[0].branch_latency_ms == pytest.approx(3.5)
    assert all(candidate.branch_cost_usd > 0 for candidate in result.all_candidates)
    assert all(candidate.branch_latency_ms > 0 for candidate in result.all_candidates)


def test_audited_overage_recording_is_public() -> None:
    budget = BudgetController(config(generations=0))

    with budget.reserve(
        0.01,
        required_calls=1,
        preserve_finalization=False,
    ) as reservation:
        budget.record_audited_overage(
            reservation,
            "seeding",
            "misquoting-provider",
            0.02,
            1,
            quoted_cost_usd=0.01,
        )

    assert budget.spent_usd == 0.02


def test_deterministic_cli_disables_future_provider_reserves(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        run_cli(
            [
                "Invent a calmer decision process.",
                "--trace-dir",
                str(tmp_path),
                "--seed-count",
                "2",
                "--finalist-count",
                "1",
                "--generations",
                "0",
            ]
        )
        == 0
    )
    trace_path = Path(json.loads(capsys.readouterr().out)["trace_path"])
    payload = json.loads(trace_path.read_text(encoding="utf-8"))

    assert payload["config"]["framing_reserve_usd"] == 0
    assert payload["config"]["finalization_reserve_usd"] == 0


def test_compare_mode_does_not_reference_live_search_adapters() -> None:
    compare_source = inspect.getsource(cli._run_compare)

    assert "DeterministicSearchProvider()" in compare_source
    assert re.search(r"\b(?:Exa|Brave|OpenAI|LiveSearch)\b", compare_source) is None


def test_normal_test_markers_exclude_live_search_by_default() -> None:
    pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'addopts = "-ra -m \\"not live_openai and not live_search\\""' in pyproject_text
    assert '"live_openai: incurs a bounded real OpenAI API request"' in pyproject_text
    assert '"live_search: incurs bounded real search provider requests"' in pyproject_text
