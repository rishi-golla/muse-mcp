from __future__ import annotations

import json

import pytest

from creativity_layer.budget import BudgetController
from creativity_layer.deterministic import DeterministicCreativeProvider
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import (
    FramedTask,
    OperationTrace,
    RunConfig,
    TaskContext,
    TokenUsage,
)
from creativity_layer.providers import MeteredResponse, OperationQuote


def _engine(provider: DeterministicCreativeProvider) -> CreativeEngine:
    return CreativeEngine(
        framer=provider,
        seeder=provider,
        transformer=provider,
        evaluator=provider,
    )


def _config(**updates: object) -> RunConfig:
    return RunConfig(
        max_cost_usd=1.0,
        max_calls=20,
        max_generations=0,
        seed_count=2,
        finalist_count=1,
        framing_reserve_usd=0.01,
        finalization_reserve_usd=0,
    ).model_copy(update=updates)


class MeteredFramer(DeterministicCreativeProvider):
    def __init__(
        self,
        *,
        quote_cost: float = 0.02,
        actual_cost: float = 0.015,
        response_provider: str | None = None,
        invalid_payload: bool = False,
        raise_frame: bool = False,
    ) -> None:
        self.quote_cost = quote_cost
        self.actual_cost = actual_cost
        self.response_provider = response_provider
        self.invalid_payload = invalid_payload
        self.raise_frame = raise_frame
        self.frame_called = False

    def quote_frame(self, task: TaskContext) -> OperationQuote:
        return OperationQuote(max_cost_usd=self.quote_cost)

    def frame(self, task: TaskContext) -> MeteredResponse[FramedTask]:
        self.frame_called = True
        if self.raise_frame:
            raise RuntimeError("framing failed")
        response = super().frame(task)
        value: object = response.value
        if self.invalid_payload:
            value = {"context": task.model_dump(mode="python"), "assumptions": ()}
        return response.model_copy(
            update={
                "value": value,
                "provider": self.response_provider or self.name,
                "model": "economy-test-model",
                "cost_usd": self.actual_cost,
                "latency_ms": 17,
                "usage": TokenUsage(input_tokens=21, output_tokens=8),
                "pricing_version": "test-2026-06-23",
                "cost_is_estimated": True,
                "request_id": "req_frame",
                "operation_trace": OperationTrace.from_payload(
                    request={"operation": "frame"},
                    response={"status": "complete"},
                ),
            }
        )


def test_framing_is_quoted_charged_and_traced() -> None:
    provider = MeteredFramer()

    result = _engine(provider).run(
        TaskContext(goal="Invent a quieter coordination mechanism."),
        _config(),
    )

    framing = result.spend_records[0]
    assert framing.stage == "framing"
    assert framing.provider == provider.name
    assert framing.model == "economy-test-model"
    assert framing.cost_usd == 0.015
    assert framing.latency_ms == 17
    assert framing.usage == TokenUsage(input_tokens=21, output_tokens=8)
    assert framing.pricing_version == "test-2026-06-23"
    assert framing.cost_is_estimated is True
    assert framing.request_id == "req_frame"
    assert json.loads(framing.operation_trace.request_json)["operation"] == "frame"


def test_unaffordable_framing_stops_before_provider_call() -> None:
    provider = MeteredFramer(quote_cost=0.2)

    result = _engine(provider).run(
        TaskContext(goal="Test"),
        _config(
            max_cost_usd=0.1,
            max_calls=10,
            framing_reserve_usd=0,
        ),
    )

    assert provider.frame_called is False
    assert result.spend_records == ()
    assert result.stopped_reason == "budget_exhausted"
    assert result.errors[-1].category == "budget_error"
    assert result.errors[-1].cost_incurred is False


def test_successful_framing_releases_capacity_for_exploration() -> None:
    provider = MeteredFramer(quote_cost=0.0, actual_cost=0.0)

    result = _engine(provider).run(
        TaskContext(goal="Test"),
        _config(
            max_cost_usd=0.02,
            max_calls=4,
            framing_reserve_usd=0.02,
        ),
    )

    assert [record.stage for record in result.spend_records] == [
        "framing",
        "seeding",
        "evaluation",
        "evaluation",
    ]
    assert result.stopped_reason == "generation_limit"


def test_framing_reserve_release_is_idempotent() -> None:
    budget = BudgetController(
        _config(
            max_cost_usd=1.0,
            framing_reserve_usd=0.1,
            finalization_reserve_usd=0.2,
        )
    )

    assert budget.available_for_exploration_usd == pytest.approx(0.7)

    budget.release_framing_reserve()
    budget.release_framing_reserve()

    assert budget.available_for_exploration_usd == pytest.approx(0.8)


def test_failed_framing_does_not_release_framing_reserve() -> None:
    provider = MeteredFramer(quote_cost=0.0, actual_cost=0.0, raise_frame=True)
    budget = BudgetController(
        _config(
            max_cost_usd=1.0,
            framing_reserve_usd=0.1,
            finalization_reserve_usd=0.2,
        )
    )

    framed, stopped_reason = _engine(provider)._frame(
        TaskContext(goal="Test"),
        budget,
        [],
        _engine(provider)._providers,
    )

    assert framed.obvious_solution == "Unavailable: task framing failed."
    assert stopped_reason == "provider_error"
    assert budget.available_for_exploration_usd == pytest.approx(0.7)


def test_framing_overage_records_actual_cost_and_stops_truthfully() -> None:
    provider = MeteredFramer(quote_cost=0.01, actual_cost=0.02)

    result = _engine(provider).run(TaskContext(goal="Test"), _config())

    assert result.spend_records[0].cost_usd == 0.02
    assert result.errors[-1].category == "overage_error"
    assert result.errors[-1].cost_incurred is True
    assert result.stopped_reason == "provider_error"


def test_framing_provider_identity_mismatch_is_charged_then_rejected() -> None:
    provider = MeteredFramer(response_provider="forged-provider")

    result = _engine(provider).run(TaskContext(goal="Test"), _config())

    assert result.spend_records[0].provider == provider.name
    assert result.errors[-1].category == "provider_error"
    assert result.errors[-1].message == "provider identity mismatch"
    assert result.errors[-1].cost_incurred is True
    assert result.stopped_reason == "provider_error"


def test_invalid_framing_payload_is_charged_before_validation_failure() -> None:
    provider = MeteredFramer(invalid_payload=True)

    result = _engine(provider).run(TaskContext(goal="Test"), _config())

    assert result.spend_records[0].stage == "framing"
    assert result.errors[-1].category == "validation_error"
    assert result.errors[-1].cost_incurred is True
    assert result.framed_task.obvious_solution == "Unavailable: task framing failed."
    assert result.stopped_reason == "provider_error"
