from datetime import datetime
from decimal import Decimal
from math import inf, nan
from uuid import UUID

import pytest
from pydantic import ValidationError

from creativity_layer.models import (
    CostEstimate,
    EvaluationScores,
    IdeaGenome,
    InspirationKind,
    OperationTrace,
    RunConfig,
    SpendRecord,
    TaskContext,
    TokenUsage,
)


def test_task_context_requires_a_non_blank_goal() -> None:
    with pytest.raises(ValidationError):
        TaskContext(goal="   ")


def test_idea_genome_records_ancestry_and_separate_scores() -> None:
    parent = IdeaGenome(
        generation=0,
        title="Borrow time",
        core_mechanism="Trade scheduling rights instead of fixed calendar slots.",
        problem_framing="Coordination is treated as ownership of time.",
        task_value="Reduces scheduling negotiation.",
        distinguishing_features=("transferable scheduling rights",),
    )

    child = IdeaGenome(
        generation=1,
        title="Time market",
        core_mechanism="Let participants exchange priority tokens.",
        problem_framing="Coordination is a constrained allocation market.",
        task_value="Makes urgency explicit.",
        distinguishing_features=("priority tokens",),
        parent_ids=(parent.id,),
        transformations=("transfer",),
        inspiration_kind=InspirationKind.SYNTHESIZED,
        scores=EvaluationScores(
            originality=0.9,
            usefulness=0.7,
            coherence=0.8,
            feasibility=0.6,
            user_fit=0.75,
        ),
    )

    assert isinstance(child.id, UUID)
    assert child.parent_ids == (parent.id,)
    assert child.scores.originality == 0.9
    assert child.scores.usefulness == 0.7


def test_run_config_rejects_impossible_reservations() -> None:
    with pytest.raises(ValidationError):
        RunConfig(
            max_cost_usd=1,
            max_calls=4,
            framing_reserve_usd=0.6,
            finalization_reserve_usd=0.5,
        )


@pytest.mark.parametrize("value", [inf, -inf, nan])
@pytest.mark.parametrize(
    ("model", "field"),
    [
        (RunConfig, "max_cost_usd"),
        (SpendRecord, "cost_usd"),
    ],
)
def test_models_reject_non_finite_floats(
    model: type[RunConfig] | type[SpendRecord],
    field: str,
    value: float,
) -> None:
    values = (
        {
            "stage": "generation",
            "provider": "local",
            "latency_ms": 0,
            field: value,
        }
        if model is SpendRecord
        else {field: value}
    )

    with pytest.raises(ValidationError):
        model(**values)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (
            IdeaGenome,
            {
                "generation": True,
                "title": "Boolean generation",
                "core_mechanism": "Treat truth as an integer.",
                "problem_framing": "Boolean values are numeric in Python.",
                "task_value": "Protects domain semantics.",
            },
        ),
        (RunConfig, {"max_calls": True}),
        (
            SpendRecord,
            {
                "stage": "generation",
                "provider": "local",
                "cost_usd": True,
                "latency_ms": 0,
            },
        ),
        (
            SpendRecord,
            {
                "stage": "generation",
                "provider": "local",
                "cost_usd": 0.0,
                "latency_ms": False,
            },
        ),
    ],
)
def test_numeric_domain_fields_reject_bool(
    model: type[IdeaGenome] | type[RunConfig] | type[SpendRecord],
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model(**values)


@pytest.mark.parametrize(
    "field",
    ["title", "core_mechanism", "problem_framing", "task_value"],
)
def test_idea_genome_rejects_whitespace_only_required_text(field: str) -> None:
    values = {
        "generation": 0,
        "title": "Useful title",
        "core_mechanism": "A concrete mechanism.",
        "problem_framing": "A clear framing.",
        "task_value": "A useful outcome.",
        field: "   ",
    }

    with pytest.raises(ValidationError):
        IdeaGenome(**values)


def test_spend_record_requires_timezone_aware_created_at() -> None:
    with pytest.raises(ValidationError):
        SpendRecord(
            stage="generation",
            provider="local",
            cost_usd=0.1,
            latency_ms=10,
            created_at=datetime(2026, 6, 22, 12, 0),
        )


@pytest.mark.parametrize("field", ["stage", "provider"])
def test_spend_record_rejects_blank_labels(field: str) -> None:
    values = {
        "stage": "generation",
        "provider": "local",
        "cost_usd": 0.1,
        "latency_ms": 10,
        field: "   ",
    }

    with pytest.raises(ValidationError):
        SpendRecord(**values)


def test_spend_record_preserves_live_operation_metadata() -> None:
    trace = OperationTrace(
        request={"model_role": "economy"},
        response={"status": "complete"},
    )
    usage = TokenUsage(input_tokens=10, output_tokens=20)
    record = SpendRecord(
        stage="seeding",
        provider="openai",
        model="economy-test-model",
        cost_usd=0.001,
        latency_ms=25,
        usage=usage,
        pricing_version="test",
        cost_is_estimated=True,
        request_id="req_test",
        operation_trace=trace,
    )

    assert record.usage == usage
    assert record.model == "economy-test-model"
    assert record.pricing_version == "test"
    assert record.cost_is_estimated is True
    assert record.request_id == "req_test"
    assert record.operation_trace == trace


def test_cost_estimate_uses_exact_decimal_values() -> None:
    estimate = CostEstimate(
        estimated_cost_usd=Decimal("0.0000000000000000001"),
        pricing_version="test",
    )

    assert estimate.estimated_cost_usd == Decimal("0.0000000000000000001")


@pytest.mark.parametrize(
    "values",
    [
        {"input_tokens": -1},
        {"cached_input_tokens": -1},
        {"output_tokens": -1},
        {"reasoning_tokens": -1},
        {"input_tokens": True},
    ],
)
def test_token_usage_rejects_invalid_counts(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TokenUsage(**values)


def test_live_metadata_labels_reject_blank_text() -> None:
    with pytest.raises(ValidationError):
        CostEstimate(
            estimated_cost_usd=Decimal("0"),
            pricing_version=" ",
        )
    with pytest.raises(ValidationError):
        SpendRecord(
            stage="seeding",
            provider="openai",
            model=" ",
            cost_usd=0.0,
            latency_ms=0,
        )
