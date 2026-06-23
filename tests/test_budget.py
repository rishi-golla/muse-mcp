import json
from decimal import Decimal

import pytest

from creativity_layer.budget import (
    BudgetController,
    BudgetExceeded,
    BudgetReservation,
)
from creativity_layer.engine import CreativeEngine
from creativity_layer.models import OperationTrace, RunConfig, RunError, TokenUsage
from creativity_layer.providers import MeteredResponse, OperationQuote


def test_budget_reserves_finalization_capacity() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1.0,
            max_calls=5,
            framing_reserve_usd=0.1,
            finalization_reserve_usd=0.2,
        )
    )

    budget.charge("seeding", "local", 0.69, 20)

    assert budget.available_for_exploration_usd == pytest.approx(0.01)
    assert budget.can_afford(0.02, preserve_finalization=True) is False
    assert budget.can_afford(0.2, preserve_finalization=False) is True


def test_framing_reserve_reduces_exploration_and_remains_unconsumed() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1.0,
            max_calls=3,
            framing_reserve_usd=0.1,
            finalization_reserve_usd=0.2,
        )
    )

    assert budget.available_for_exploration_usd == pytest.approx(0.7)
    assert budget.can_afford(0.7, preserve_finalization=True) is True
    assert budget.can_afford(0.71, preserve_finalization=True) is False

    with budget.reserve(
        0.7,
        required_calls=1,
        preserve_finalization=True,
    ) as reservation:
        reservation.charge("seed", "local", 0.7, 1)

    assert budget.available_for_exploration_usd == 0
    assert budget.remaining_usd == pytest.approx(0.3)


def test_budget_rejects_cost_or_call_overruns() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=0.5,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    budget.charge("seed", "local", 0.4, 1)

    with pytest.raises(BudgetExceeded, match="call limit"):
        budget.charge("transform", "local", 0.01, 1)


def test_budget_allows_exact_cost_exhaustion() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=0.3,
            max_calls=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    budget.charge("seed", "local", 0.1, 1)
    budget.charge("evaluate", "local", 0.2, 1)

    assert budget.remaining_usd == 0.0


def test_budget_rejects_a_tiny_exact_overspend() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=0.3,
            max_calls=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )
    budget.charge("seed", "local", 0.1, 1)

    with pytest.raises(BudgetExceeded, match="cost limit"):
        budget.charge("evaluate", "local", 0.20000000000000004, 1)


@pytest.mark.parametrize("cost_usd", [-0.01, float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("method_name", ["can_afford", "charge"])
def test_budget_methods_reject_invalid_costs(
    cost_usd: float,
    method_name: str,
) -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with pytest.raises(ValueError, match="finite non-negative"):
        if method_name == "can_afford":
            budget.can_afford(cost_usd, preserve_finalization=False)
        else:
            budget.charge("seed", "local", cost_usd, 1)


def test_rejected_charge_does_not_create_a_record() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=0.1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with pytest.raises(BudgetExceeded, match="cost limit"):
        budget.charge("seed", "local", 0.2, 1)

    assert budget.records == ()


def test_direct_exploration_charge_preserves_finalization_reserve() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=3,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.2,
        )
    )
    budget.charge("seed", "local", 0.8, 1, preserve_finalization=True)

    with pytest.raises(BudgetExceeded, match="cost limit"):
        budget.charge("transform", "local", 0.01, 1, preserve_finalization=True)

    assert len(budget.records) == 1


def test_affordability_and_reservation_require_two_call_capacity() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    assert (
        budget.can_afford(
            0.1,
            preserve_finalization=True,
            required_calls=2,
        )
        is False
    )
    with pytest.raises(BudgetExceeded, match="call limit"):
        budget.reserve(0.1, required_calls=2, preserve_finalization=True)


def test_reservation_atomically_holds_cost_and_calls_for_a_sequence() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=3,
            framing_reserve_usd=0,
            finalization_reserve_usd=0.2,
        )
    )

    with budget.reserve(
        0.7,
        required_calls=2,
        preserve_finalization=True,
    ) as reservation:
        with pytest.raises(BudgetExceeded, match="cost limit"):
            budget.charge(
                "competing-exploration",
                "local",
                0.11,
                1,
                preserve_finalization=True,
            )

        reservation.charge("transform", "local", 0.3, 1)
        reservation.charge("evaluate", "local", 0.4, 1)

    budget.charge("finalize", "local", 0.2, 1)

    assert [record.stage for record in budget.records] == [
        "transform",
        "evaluate",
        "finalize",
    ]


@pytest.mark.parametrize("cost_usd", [-0.01, float("nan"), float("inf"), -float("inf")])
def test_reservation_rejects_invalid_costs(cost_usd: float) -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with pytest.raises(ValueError, match="finite non-negative"):
        budget.reserve(cost_usd, required_calls=2, preserve_finalization=True)


@pytest.mark.parametrize("cost_usd", [-0.01, float("nan"), float("inf"), -float("inf")])
def test_reserved_charge_rejects_invalid_costs(cost_usd: float) -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with (
        budget.reserve(
            0.1,
            required_calls=1,
            preserve_finalization=True,
        ) as reservation,
        pytest.raises(ValueError, match="finite non-negative"),
    ):
        reservation.charge("transform", "local", cost_usd, 1)

    assert budget.records == ()


def test_forged_reservation_cannot_charge_controller() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )
    forged = BudgetReservation(budget, Decimal("1"), 2)

    with pytest.raises(RuntimeError, match="not active"):
        forged.charge("forged", "local", 1.0, 1)

    assert budget.records == ()
    assert budget.remaining_usd == 1.0


def test_forged_reservation_cannot_release_controller_capacity() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )
    reservation = budget.reserve(
        0.5,
        required_calls=1,
        preserve_finalization=False,
    )
    forged = BudgetReservation(budget, Decimal("0.5"), 1)

    with pytest.raises(RuntimeError, match="not active"):
        forged.release()

    assert budget._reserved_cost == Decimal("0.5")
    assert budget._reserved_calls == 1
    with pytest.raises(BudgetExceeded, match="cost limit"):
        budget.charge("overspend", "local", 0.6, 1)

    reservation.release()
    assert budget._reserved_cost == Decimal("0")
    assert budget._reserved_calls == 0
    budget.charge("valid", "local", 1.0, 1)

    assert [record.stage for record in budget.records] == ["valid"]


@pytest.mark.parametrize("method_name", ["can_afford", "charge", "reserve"])
def test_public_budget_methods_reject_string_costs(method_name: str) -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=2,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with pytest.raises(ValueError, match="int or float"):
        if method_name == "can_afford":
            budget.can_afford("0.1", preserve_finalization=False)  # type: ignore[arg-type]
        elif method_name == "charge":
            budget.charge("seed", "local", "0.1", 1)  # type: ignore[arg-type]
        else:
            budget.reserve(  # type: ignore[arg-type]
                "0.1",
                required_calls=1,
                preserve_finalization=False,
            )


def test_reserved_charge_rejects_string_cost() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with (
        budget.reserve(
            0.1,
            required_calls=1,
            preserve_finalization=False,
        ) as reservation,
        pytest.raises(ValueError, match="int or float"),
    ):
        reservation.charge(  # type: ignore[arg-type]
            "transform",
            "local",
            "0.1",
            1,
        )


def test_audited_overage_records_actual_cost_beyond_budget() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=0.1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with budget.reserve(
        0.1,
        required_calls=1,
        preserve_finalization=False,
    ) as reservation:
        budget.record_audited_overage(
            reservation,
            "seed",
            "misquoting-provider",
            0.12,
            4,
            quoted_cost_usd=0.1,
        )

    assert budget.spent_usd == 0.12
    assert budget.calls_used == 1
    assert budget.remaining_usd == 0
    assert budget.records[0].cost_usd == 0.12


def test_audited_overage_cannot_authorize_an_in_quote_charge() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with (
        budget.reserve(
            0.1,
            required_calls=1,
            preserve_finalization=False,
        ) as reservation,
        pytest.raises(ValueError, match="exceed quoted cost"),
    ):
        budget.record_audited_overage(
            reservation,
            "seed",
            "local",
            0.1,
            1,
            quoted_cost_usd=0.1,
        )

    assert budget.records == ()


def _live_metadata() -> dict[str, object]:
    return {
        "model": "economy-test-model",
        "usage": TokenUsage(input_tokens=10, output_tokens=4),
        "pricing_version": "test",
        "cost_is_estimated": True,
        "request_id": "req_test",
        "operation_trace": OperationTrace.from_payload(
            request={"operation": "seed"},
            response={"status": "complete"},
        ),
    }


def test_direct_charge_preserves_live_metadata() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    record = budget.charge("seed", "openai", 0.01, 2, **_live_metadata())

    assert record.model == "economy-test-model"
    assert record.usage == TokenUsage(input_tokens=10, output_tokens=4)
    assert json.loads(record.operation_trace.response_json)["status"] == "complete"


def test_reserved_charge_preserves_live_metadata() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with budget.reserve(
        0.01,
        required_calls=1,
        preserve_finalization=False,
    ) as reservation:
        record = reservation.charge(
            "seed",
            "openai",
            0.01,
            2,
            **_live_metadata(),
        )

    assert record.request_id == "req_test"
    assert record.pricing_version == "test"
    assert record.cost_is_estimated is True


def test_audited_overage_preserves_live_metadata() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )

    with budget.reserve(
        0.01,
        required_calls=1,
        preserve_finalization=False,
    ) as reservation:
        record = budget.record_audited_overage(
            reservation,
            "seed",
            "openai",
            0.02,
            2,
            quoted_cost_usd=0.01,
            **_live_metadata(),
        )

    assert record.model == "economy-test-model"
    assert record.request_id == "req_test"


@pytest.mark.parametrize(
    ("response_cost", "quote_cost", "expected_charged"),
    [(0.01, 0.01, True), (0.02, 0.01, False)],
)
def test_engine_charge_response_propagates_all_live_metadata(
    response_cost: float,
    quote_cost: float,
    expected_charged: bool,
) -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1,
            max_calls=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        )
    )
    response = MeteredResponse(
        value="result",
        provider="openai",
        cost_usd=response_cost,
        latency_ms=2,
        **_live_metadata(),
    )
    errors: list[RunError] = []

    with budget.reserve(
        quote_cost,
        required_calls=1,
        preserve_finalization=False,
    ) as reservation:
        charged = CreativeEngine._charge_response(
            response,
            OperationQuote(max_cost_usd=quote_cost),
            reservation,
            budget,
            stage="seed",
            expected_provider="openai",
            errors=errors,
        )

    assert charged is expected_charged
    if expected_charged:
        assert errors == []
    else:
        assert errors[-1].category == "overage_error"
    assert budget.records[0].model == response.model
    assert budget.records[0].usage == response.usage
    assert budget.records[0].pricing_version == response.pricing_version
    assert budget.records[0].cost_is_estimated == response.cost_is_estimated
    assert budget.records[0].request_id == response.request_id
    assert budget.records[0].operation_trace == response.operation_trace
