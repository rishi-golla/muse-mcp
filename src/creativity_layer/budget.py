from __future__ import annotations

from creativity_layer.models import RunConfig, SpendRecord


class BudgetExceeded(RuntimeError):
    """Raised when a run would exceed its configured budget."""


class BudgetController:
    def __init__(self, config: RunConfig) -> None:
        self._config = config
        self._records: list[SpendRecord] = []

    @property
    def records(self) -> tuple[SpendRecord, ...]:
        return tuple(self._records)

    @property
    def spent_usd(self) -> float:
        return sum(record.cost_usd for record in self._records)

    @property
    def calls_used(self) -> int:
        return len(self._records)

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self._config.max_cost_usd - self.spent_usd)

    @property
    def available_for_exploration_usd(self) -> float:
        return max(0.0, self.remaining_usd - self._config.finalization_reserve_usd)

    def can_afford(self, cost_usd: float, *, preserve_finalization: bool) -> bool:
        available = (
            self.available_for_exploration_usd
            if preserve_finalization
            else self.remaining_usd
        )
        return self.calls_used < self._config.max_calls and cost_usd <= available + 1e-9

    def charge(
        self,
        stage: str,
        provider: str,
        cost_usd: float,
        latency_ms: int,
    ) -> SpendRecord:
        if self.calls_used >= self._config.max_calls:
            raise BudgetExceeded("call limit exceeded")
        if cost_usd > self.remaining_usd + 1e-9:
            raise BudgetExceeded("cost limit exceeded")

        record = SpendRecord(
            stage=stage,
            provider=provider,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
        self._records.append(record)
        return record
