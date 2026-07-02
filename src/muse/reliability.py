from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError)


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    """Synchronous consecutive-failure breaker without half-open cooldown behavior."""

    def __init__(self, failure_threshold: int) -> None:
        if isinstance(failure_threshold, bool) or not isinstance(failure_threshold, int):
            raise TypeError("failure_threshold must be an integer")
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        self._failure_threshold = failure_threshold
        self._failures = 0
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def before_call(self) -> None:
        if self._open:
            raise CircuitOpenError("provider circuit is open")

    def record_success(self) -> None:
        self._failures = 0
        self._open = False

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._open = True


def is_retryable_openai_exception(error: BaseException) -> bool:
    if isinstance(error, RETRYABLE):
        return True
    if isinstance(error, APIStatusError):
        status_code = error.status_code
        return status_code in (408, 409) or 500 <= status_code <= 599
    return False


def _positive_finite(value: object, *, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} must be an int or float")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def _valid_non_negative_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _http_date_delay(
    value: str | None,
    *,
    now: Callable[[], datetime],
) -> float | None:
    if value is None:
        return None
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None or retry_at.utcoffset() is None:
        return None
    return max(0.0, (retry_at - now()).total_seconds())


def _retry_header_delay(
    error: BaseException,
    *,
    maximum_delay_seconds: float,
    now: Callable[[], datetime],
) -> float | None:
    if not isinstance(error, APIStatusError):
        return None
    milliseconds = _valid_non_negative_float(
        error.response.headers.get("retry-after-ms")
    )
    if milliseconds is not None:
        return min(milliseconds / 1_000, maximum_delay_seconds)
    retry_after = error.response.headers.get("Retry-After")
    seconds = _valid_non_negative_float(retry_after)
    if seconds is not None:
        return min(seconds, maximum_delay_seconds)
    date_delay = _http_date_delay(retry_after, now=now)
    if date_delay is not None:
        return min(date_delay, maximum_delay_seconds)
    return None


def _local_backoff_delay(
    attempt: int,
    *,
    policy: RetryPolicy,
    random_value: Callable[[], float],
) -> float:
    jitter = random_value()
    if (
        isinstance(jitter, bool)
        or not isinstance(jitter, int | float)
        or not math.isfinite(jitter)
        or not 0 <= jitter <= 1
    ):
        raise ValueError("random_value must return a finite number within [0, 1]")
    base = policy.base_delay_seconds * (2**attempt)
    jittered = base + base * 0.25 * jitter
    return min(jittered, policy.maximum_delay_seconds)


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 0.25
    maximum_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int):
            raise TypeError("max_retries must be an integer")
        if not 0 <= self.max_retries <= 5:
            raise ValueError("max_retries must be between 0 and 5")
        _positive_finite(
            self.base_delay_seconds,
            name="base_delay_seconds",
        )
        _positive_finite(
            self.maximum_delay_seconds,
            name="maximum_delay_seconds",
        )
        if self.maximum_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                "maximum_delay_seconds must be at least base_delay_seconds"
            )


def execute_with_retries[T](
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    breaker: CircuitBreaker | None = None,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
    now: Callable[[], datetime] = _utc_now,
) -> T:
    if breaker is not None:
        breaker.before_call()
    for attempt in range(policy.max_retries + 1):
        try:
            result = operation()
        except Exception as error:
            if not is_retryable_openai_exception(error):
                raise
            if attempt >= policy.max_retries:
                if breaker is not None:
                    breaker.record_failure()
                raise
            delay = _retry_header_delay(
                error,
                maximum_delay_seconds=policy.maximum_delay_seconds,
                now=now,
            )
            if delay is None:
                delay = _local_backoff_delay(
                    attempt,
                    policy=policy,
                    random_value=random_value,
                )
            sleep(delay)
        else:
            if breaker is not None:
                breaker.record_success()
            return result
    raise RuntimeError("unreachable")
