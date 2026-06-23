from __future__ import annotations

import json
from pathlib import Path

import pytest

from creativity_layer.budget import BudgetController
from creativity_layer.cli import run_cli
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import EvaluationScores, FramedTask, IdeaGenome, RunConfig, TaskContext
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
    assert [record.stage for record in result.spend_records] == ["seeding"]
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
