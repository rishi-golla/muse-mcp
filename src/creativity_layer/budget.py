from __future__ import annotations

from decimal import Decimal, InvalidOperation
from types import TracebackType

from creativity_layer.models import RunConfig, SpendRecord


class BudgetExceeded(RuntimeError):
    """Raised when a run would exceed its configured budget."""


def _money(value: float) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("cost_usd must be a finite non-negative number")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("cost_usd must be a finite non-negative number") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("cost_usd must be a finite non-negative number")
    return amount


def _call_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("required_calls must be a positive integer")
    return value


class BudgetController:
    def __init__(self, config: RunConfig) -> None:
        self._config = config
        self._records: list[SpendRecord] = []
        self._spent = Decimal("0")
        self._reserved_cost = Decimal("0")
        self._reserved_calls = 0
        self._max_cost = _money(config.max_cost_usd)
        # Framing is unmetered here; only finalization capacity is protected.
        self._finalization_reserve = _money(config.finalization_reserve_usd)

    @property
    def records(self) -> tuple[SpendRecord, ...]:
        return tuple(self._records)

    @property
    def spent_usd(self) -> float:
        return float(self._spent)

    @property
    def calls_used(self) -> int:
        return len(self._records)

    @property
    def remaining_usd(self) -> float:
        return float(max(Decimal("0"), self._max_cost - self._spent))

    @property
    def available_for_exploration_usd(self) -> float:
        return float(
            max(
                Decimal("0"),
                self._max_cost
                - self._spent
                - self._reserved_cost
                - self._finalization_reserve,
            )
        )

    def can_afford(
        self,
        cost_usd: float,
        *,
        preserve_finalization: bool,
        required_calls: int = 1,
    ) -> bool:
        cost = _money(cost_usd)
        calls = _call_count(required_calls)
        available = (
            self._max_cost
            - self._spent
            - self._reserved_cost
            - self._finalization_reserve
            if preserve_finalization
            else self._max_cost - self._spent - self._reserved_cost
        )
        calls_available = (
            self._config.max_calls - self.calls_used - self._reserved_calls
        )
        return calls <= calls_available and cost <= available

    def reserve(
        self,
        cost_usd: float,
        *,
        required_calls: int,
        preserve_finalization: bool,
    ) -> BudgetReservation:
        cost = _money(cost_usd)
        calls = _call_count(required_calls)
        calls_available = (
            self._config.max_calls - self.calls_used - self._reserved_calls
        )
        if calls > calls_available:
            raise BudgetExceeded("call limit exceeded")

        available = (
            self._max_cost
            - self._spent
            - self._reserved_cost
            - self._finalization_reserve
            if preserve_finalization
            else self._max_cost - self._spent - self._reserved_cost
        )
        if cost > available:
            raise BudgetExceeded("cost limit exceeded")

        self._reserved_cost += cost
        self._reserved_calls += calls
        return BudgetReservation(self, cost, calls)

    def charge(
        self,
        stage: str,
        provider: str,
        cost_usd: float,
        latency_ms: int,
        *,
        preserve_finalization: bool = False,
    ) -> SpendRecord:
        cost = _money(cost_usd)
        calls_available = (
            self._config.max_calls - self.calls_used - self._reserved_calls
        )
        if calls_available < 1:
            raise BudgetExceeded("call limit exceeded")
        available = self._max_cost - self._spent - self._reserved_cost
        if preserve_finalization:
            available -= self._finalization_reserve
        if cost > available:
            raise BudgetExceeded("cost limit exceeded")

        return self._append_record(stage, provider, cost_usd, latency_ms, cost)

    def _append_record(
        self,
        stage: str,
        provider: str,
        cost_usd: float,
        latency_ms: int,
        cost: Decimal,
    ) -> SpendRecord:
        record = SpendRecord(
            stage=stage,
            provider=provider,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
        self._records.append(record)
        self._spent += cost
        return record

    def _charge_reservation(
        self,
        reservation: BudgetReservation,
        stage: str,
        provider: str,
        cost_usd: float,
        latency_ms: int,
        cost: Decimal,
    ) -> SpendRecord:
        record = self._append_record(stage, provider, cost_usd, latency_ms, cost)
        self._reserved_cost -= cost
        self._reserved_calls -= 1
        reservation._remaining_cost -= cost
        reservation._remaining_calls -= 1
        return record

    def _release_reservation(self, reservation: BudgetReservation) -> None:
        self._reserved_cost -= reservation._remaining_cost
        self._reserved_calls -= reservation._remaining_calls
        reservation._remaining_cost = Decimal("0")
        reservation._remaining_calls = 0


class BudgetReservation:
    def __init__(
        self,
        controller: BudgetController,
        cost: Decimal,
        calls: int,
    ) -> None:
        self._controller = controller
        self._remaining_cost = cost
        self._remaining_calls = calls
        self._closed = False

    def __enter__(self) -> BudgetReservation:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def charge(
        self,
        stage: str,
        provider: str,
        cost_usd: float,
        latency_ms: int,
    ) -> SpendRecord:
        cost = _money(cost_usd)
        if self._closed:
            raise RuntimeError("reservation is closed")
        if self._remaining_calls < 1:
            raise BudgetExceeded("reservation call limit exceeded")
        if cost > self._remaining_cost:
            raise BudgetExceeded("reservation cost limit exceeded")
        return self._controller._charge_reservation(
            self,
            stage,
            provider,
            cost_usd,
            latency_ms,
            cost,
        )

    def release(self) -> None:
        if self._closed:
            return
        self._controller._release_reservation(self)
        self._closed = True
