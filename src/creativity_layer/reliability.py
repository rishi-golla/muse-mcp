from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from openai import APIConnectionError, APITimeoutError, RateLimitError

RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError)


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
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

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._open = True


def is_retryable_openai_exception(error: BaseException) -> bool:
    return isinstance(error, RETRYABLE)


def _non_negative_finite(value: object, *, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} must be an int or float")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    base_delay_seconds: float = 0.25
    maximum_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int):
            raise TypeError("max_retries must be an integer")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        _non_negative_finite(
            self.base_delay_seconds,
            name="base_delay_seconds",
        )
        _non_negative_finite(
            self.maximum_delay_seconds,
            name="maximum_delay_seconds",
        )


def execute_with_retries[T](
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    breaker: CircuitBreaker | None = None,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
) -> T:
    if breaker is not None:
        breaker.before_call()
    for attempt in range(policy.max_retries + 1):
        try:
            result = operation()
        except Exception as error:
            if not is_retryable_openai_exception(error):
                raise
            if breaker is not None:
                breaker.record_failure()
            if attempt >= policy.max_retries:
                raise
            base = min(
                policy.maximum_delay_seconds,
                policy.base_delay_seconds * (2**attempt),
            )
            sleep(base + base * 0.25 * random_value())
        else:
            if breaker is not None:
                breaker.record_success()
            return result
    raise RuntimeError("unreachable")
