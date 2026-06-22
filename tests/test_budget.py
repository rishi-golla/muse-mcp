import pytest

from creativity_layer.budget import BudgetController, BudgetExceeded
from creativity_layer.models import RunConfig


def test_budget_reserves_finalization_capacity() -> None:
    budget = BudgetController(
        RunConfig(
            max_cost_usd=1.0,
            max_calls=5,
            framing_reserve_usd=0.1,
            finalization_reserve_usd=0.2,
        )
    )

    budget.charge("framing", "local", 0.1, 10)
    budget.charge("seeding", "local", 0.69, 20)

    assert budget.available_for_exploration_usd == pytest.approx(0.01)
    assert budget.can_afford(0.02, preserve_finalization=True) is False
    assert budget.can_afford(0.2, preserve_finalization=False) is True


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
