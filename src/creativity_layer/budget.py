from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import TracebackType

from creativity_layer.models import (
    OperationTrace,
    RunConfig,
    SpendRecord,
    TokenUsage,
)


class BudgetExceeded(RuntimeError):
    """Raised when a run would exceed its configured budget."""


def _money(value: int | float) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("cost_usd must be an int or float")
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


@dataclass
class _ReservationState:
    reservation: BudgetReservation
    remaining_cost: Decimal
    remaining_calls: int


class BudgetController:
    def __init__(self, config: RunConfig) -> None:
        self._config = config
        self._records: list[SpendRecord] = []
        self._spent = Decimal("0")
        self._reserved_cost = Decimal("0")
        self._reserved_calls = 0
        self._reservations: dict[object, _ReservationState] = {}
        self._max_cost = _money(config.max_cost_usd)
        self._framing_reserve = _money(config.framing_reserve_usd)
        self._finalization_reserve = _money(config.finalization_reserve_usd)
        self._exploration_reserve = (
            self._framing_reserve + self._finalization_reserve
        )

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
                - self._exploration_reserve,
            )
        )

    def release_framing_reserve(self) -> None:
        if self._framing_reserve == 0:
            return
        self._exploration_reserve -= self._framing_reserve
        self._framing_reserve = Decimal("0")

    def can_afford(
        self,
        cost_usd: int | float,
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
            - self._exploration_reserve
            if preserve_finalization
            else self._max_cost - self._spent - self._reserved_cost
        )
        calls_available = (
            self._config.max_calls - self.calls_used - self._reserved_calls
        )
        return calls <= calls_available and cost <= available

    def reserve(
        self,
        cost_usd: int | float,
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
            - self._exploration_reserve
            if preserve_finalization
            else self._max_cost - self._spent - self._reserved_cost
        )
        if cost > available:
            raise BudgetExceeded("cost limit exceeded")

        self._reserved_cost += cost
        self._reserved_calls += calls
        token = object()
        reservation = BudgetReservation(self, cost, calls, _token=token)
        self._reservations[token] = _ReservationState(
            reservation=reservation,
            remaining_cost=cost,
            remaining_calls=calls,
        )
        return reservation

    def reserve_for_framing(
        self,
        cost_usd: int | float,
        *,
        required_calls: int,
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
        )
        if cost > available:
            raise BudgetExceeded("cost limit exceeded")

        self._reserved_cost += cost
        self._reserved_calls += calls
        token = object()
        reservation = BudgetReservation(self, cost, calls, _token=token)
        self._reservations[token] = _ReservationState(
            reservation=reservation,
            remaining_cost=cost,
            remaining_calls=calls,
        )
        return reservation

    def charge(
        self,
        stage: str,
        provider: str,
        cost_usd: int | float,
        latency_ms: int,
        *,
        preserve_finalization: bool = False,
        model: str | None = None,
        usage: TokenUsage | None = None,
        pricing_version: str | None = None,
        cost_is_estimated: bool = False,
        request_id: str | None = None,
        operation_trace: OperationTrace | None = None,
    ) -> SpendRecord:
        cost = _money(cost_usd)
        calls_available = (
            self._config.max_calls - self.calls_used - self._reserved_calls
        )
        if calls_available < 1:
            raise BudgetExceeded("call limit exceeded")
        available = self._max_cost - self._spent - self._reserved_cost
        if preserve_finalization:
            available -= self._exploration_reserve
        if cost > available:
            raise BudgetExceeded("cost limit exceeded")

        return self._append_record(
            stage,
            provider,
            cost_usd,
            latency_ms,
            cost,
            model=model,
            usage=usage,
            pricing_version=pricing_version,
            cost_is_estimated=cost_is_estimated,
            request_id=request_id,
            operation_trace=operation_trace,
        )

    def _append_record(
        self,
        stage: str,
        provider: str,
        cost_usd: int | float,
        latency_ms: int,
        cost: Decimal,
        *,
        model: str | None = None,
        usage: TokenUsage | None = None,
        pricing_version: str | None = None,
        cost_is_estimated: bool = False,
        request_id: str | None = None,
        operation_trace: OperationTrace | None = None,
    ) -> SpendRecord:
        record = SpendRecord(
            stage=stage,
            provider=provider,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            model=model,
            usage=usage if usage is not None else TokenUsage(),
            pricing_version=pricing_version,
            cost_is_estimated=cost_is_estimated,
            request_id=request_id,
            operation_trace=operation_trace,
        )
        self._records.append(record)
        self._spent += cost
        return record

    def _charge_reservation(
        self,
        reservation: BudgetReservation,
        stage: str,
        provider: str,
        cost_usd: int | float,
        latency_ms: int,
        cost: Decimal,
        *,
        model: str | None = None,
        usage: TokenUsage | None = None,
        pricing_version: str | None = None,
        cost_is_estimated: bool = False,
        request_id: str | None = None,
        operation_trace: OperationTrace | None = None,
    ) -> SpendRecord:
        state = self._active_reservation_state(reservation)
        if state.remaining_calls < 1:
            raise BudgetExceeded("reservation call limit exceeded")
        if cost > state.remaining_cost:
            raise BudgetExceeded("reservation cost limit exceeded")

        record = self._append_record(
            stage,
            provider,
            cost_usd,
            latency_ms,
            cost,
            model=model,
            usage=usage,
            pricing_version=pricing_version,
            cost_is_estimated=cost_is_estimated,
            request_id=request_id,
            operation_trace=operation_trace,
        )
        self._reserved_cost -= cost
        self._reserved_calls -= 1
        state.remaining_cost -= cost
        state.remaining_calls -= 1
        reservation._remaining_cost -= cost
        reservation._remaining_calls -= 1
        return record

    def record_audited_overage(
        self,
        reservation: BudgetReservation,
        stage: str,
        provider: str,
        cost_usd: int | float,
        latency_ms: int,
        *,
        quoted_cost_usd: int | float,
        model: str | None = None,
        usage: TokenUsage | None = None,
        pricing_version: str | None = None,
        cost_is_estimated: bool = False,
        request_id: str | None = None,
        operation_trace: OperationTrace | None = None,
    ) -> SpendRecord:
        """Record an incurred provider overage without authorizing new work."""
        cost = _money(cost_usd)
        quoted_cost = _money(quoted_cost_usd)
        if cost <= quoted_cost:
            raise ValueError("audited overage must exceed quoted cost")

        state = self._active_reservation_state(reservation)
        if state.remaining_calls < 1:
            raise BudgetExceeded("reservation call limit exceeded")
        if quoted_cost > state.remaining_cost:
            raise RuntimeError("quoted cost exceeds reservation capacity")

        record = self._append_record(
            stage,
            provider,
            cost_usd,
            latency_ms,
            cost,
            model=model,
            usage=usage,
            pricing_version=pricing_version,
            cost_is_estimated=cost_is_estimated,
            request_id=request_id,
            operation_trace=operation_trace,
        )
        self._reserved_cost -= quoted_cost
        self._reserved_calls -= 1
        state.remaining_cost -= quoted_cost
        state.remaining_calls -= 1
        reservation._remaining_cost -= quoted_cost
        reservation._remaining_calls -= 1
        return record

    def _release_reservation(self, reservation: BudgetReservation) -> None:
        state = self._active_reservation_state(reservation)
        self._reserved_cost -= state.remaining_cost
        self._reserved_calls -= state.remaining_calls
        del self._reservations[reservation._token]
        reservation._remaining_cost = Decimal("0")
        reservation._remaining_calls = 0

    def _active_reservation_state(
        self,
        reservation: BudgetReservation,
    ) -> _ReservationState:
        state = self._reservations.get(reservation._token)
        if state is None or state.reservation is not reservation:
            raise RuntimeError("reservation is not active")
        if (
            state.remaining_cost != reservation._remaining_cost
            or state.remaining_calls != reservation._remaining_calls
        ):
            raise RuntimeError("reservation state does not match controller registry")
        registered_cost = sum(
            (item.remaining_cost for item in self._reservations.values()),
            start=Decimal("0"),
        )
        registered_calls = sum(
            item.remaining_calls for item in self._reservations.values()
        )
        if (
            registered_cost != self._reserved_cost
            or registered_calls != self._reserved_calls
        ):
            raise RuntimeError("reservation registry is inconsistent")
        return state


class BudgetReservation:
    def __init__(
        self,
        controller: BudgetController,
        cost: Decimal,
        calls: int,
        *,
        _token: object | None = None,
    ) -> None:
        self._controller = controller
        self._remaining_cost = cost
        self._remaining_calls = calls
        self._token = _token if _token is not None else object()
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
        cost_usd: int | float,
        latency_ms: int,
        *,
        model: str | None = None,
        usage: TokenUsage | None = None,
        pricing_version: str | None = None,
        cost_is_estimated: bool = False,
        request_id: str | None = None,
        operation_trace: OperationTrace | None = None,
    ) -> SpendRecord:
        cost = _money(cost_usd)
        if self._closed:
            raise RuntimeError("reservation is closed")
        return self._controller._charge_reservation(
            self,
            stage,
            provider,
            cost_usd,
            latency_ms,
            cost,
            model=model,
            usage=usage,
            pricing_version=pricing_version,
            cost_is_estimated=cost_is_estimated,
            request_id=request_id,
            operation_trace=operation_trace,
        )

    def release(self) -> None:
        if self._closed:
            return
        self._controller._release_reservation(self)
        self._closed = True
