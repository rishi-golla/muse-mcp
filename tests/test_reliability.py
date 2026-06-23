from collections.abc import Callable

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from creativity_layer.reliability import (
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
    execute_with_retries,
    is_retryable_openai_exception,
)


def _response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return httpx.Response(status_code, request=request)


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/responses")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_retries", -1),
        ("max_retries", True),
        ("max_retries", 1.5),
        ("base_delay_seconds", -0.1),
        ("base_delay_seconds", float("nan")),
        ("base_delay_seconds", float("inf")),
        ("maximum_delay_seconds", -0.1),
        ("maximum_delay_seconds", float("nan")),
        ("maximum_delay_seconds", float("inf")),
    ],
)
def test_retry_policy_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        RetryPolicy(**{field: value})


def test_retry_executor_retries_rate_limits_with_exponential_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RateLimitError(
                "rate limited",
                response=_response(429),
                body=None,
            )
        return "ok"

    result = execute_with_retries(
        operation,
        policy=RetryPolicy(max_retries=2, base_delay_seconds=0.1),
        sleep=delays.append,
        random_value=lambda: 0.0,
    )

    assert result == "ok"
    assert attempts == 3
    assert delays == [0.1, 0.2]


def test_retry_executor_caps_backoff_and_applies_jitter() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise RateLimitError(
                "rate limited",
                response=_response(429),
                body=None,
            )
        return "ok"

    result = execute_with_retries(
        operation,
        policy=RetryPolicy(
            max_retries=3,
            base_delay_seconds=1.0,
            maximum_delay_seconds=2.0,
        ),
        sleep=delays.append,
        random_value=lambda: 1.0,
    )

    assert result == "ok"
    assert delays == [1.25, 2.5, 2.5]


@pytest.mark.parametrize(
    "error",
    [
        RateLimitError("rate limited", response=_response(429), body=None),
        APITimeoutError(_request()),
        APIConnectionError(request=_request()),
    ],
)
def test_retryable_openai_exception_classification(error: Exception) -> None:
    assert is_retryable_openai_exception(error) is True


@pytest.mark.parametrize(
    "error",
    [
        AuthenticationError(
            "invalid key",
            response=_response(401),
            body=None,
        ),
        BadRequestError(
            "bad request",
            response=_response(400),
            body=None,
        ),
        RuntimeError("local failure"),
    ],
)
def test_nonretryable_openai_exception_classification(error: Exception) -> None:
    assert is_retryable_openai_exception(error) is False


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: APITimeoutError(_request()),
        lambda: APIConnectionError(request=_request()),
    ],
)
def test_retry_executor_retries_connection_and_timeout_errors(
    error_factory: Callable[[], Exception],
) -> None:
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise error_factory()
        return "ok"

    assert execute_with_retries(
        operation,
        policy=RetryPolicy(max_retries=1, base_delay_seconds=0),
        sleep=lambda _: None,
    ) == "ok"
    assert attempts == 2


def test_authentication_errors_are_never_retried() -> None:
    attempts = 0
    error = AuthenticationError(
        "invalid key",
        response=_response(401),
        body=None,
    )

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise error

    with pytest.raises(AuthenticationError) as raised:
        execute_with_retries(
            operation,
            policy=RetryPolicy(max_retries=3),
            sleep=lambda _: pytest.fail("nonretryable error slept"),
        )

    assert raised.value is error
    assert attempts == 1


def test_retry_exhaustion_reraises_the_final_sdk_exception() -> None:
    final_error = RateLimitError(
        "final",
        response=_response(429),
        body=None,
    )
    errors = [
        RateLimitError("first", response=_response(429), body=None),
        final_error,
    ]

    def operation() -> None:
        raise errors.pop(0)

    with pytest.raises(RateLimitError) as raised:
        execute_with_retries(
            operation,
            policy=RetryPolicy(max_retries=1, base_delay_seconds=0),
            sleep=lambda _: None,
        )

    assert raised.value is final_error


@pytest.mark.parametrize("failure_threshold", [0, -1, True, 1.5])
def test_circuit_breaker_rejects_invalid_thresholds(
    failure_threshold: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        CircuitBreaker(failure_threshold=failure_threshold)


def test_circuit_opens_after_repeated_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=2)

    breaker.record_failure()
    assert breaker.is_open is False

    breaker.record_failure()
    assert breaker.is_open is True
    with pytest.raises(CircuitOpenError, match="provider circuit is open"):
        breaker.before_call()


def test_success_resets_consecutive_failure_count() -> None:
    breaker = CircuitBreaker(failure_threshold=2)

    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()

    assert breaker.is_open is False
    breaker.before_call()


def test_retry_success_resets_breaker_failure_count() -> None:
    breaker = CircuitBreaker(failure_threshold=2)
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError(
                "rate limited",
                response=_response(429),
                body=None,
            )
        return "ok"

    assert execute_with_retries(
        operation,
        policy=RetryPolicy(max_retries=1, base_delay_seconds=0),
        breaker=breaker,
        sleep=lambda _: None,
    ) == "ok"

    breaker.record_failure()
    assert breaker.is_open is False


def test_retry_exhaustion_records_failures_and_opens_circuit() -> None:
    breaker = CircuitBreaker(failure_threshold=2)

    def operation() -> None:
        raise RateLimitError(
            "rate limited",
            response=_response(429),
            body=None,
        )

    with pytest.raises(RateLimitError):
        execute_with_retries(
            operation,
            policy=RetryPolicy(max_retries=1, base_delay_seconds=0),
            breaker=breaker,
            sleep=lambda _: None,
        )

    assert breaker.is_open is True


def test_open_circuit_performs_no_provider_call() -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    breaker.record_failure()
    called = False

    def operation() -> None:
        nonlocal called
        called = True

    with pytest.raises(CircuitOpenError, match="provider circuit is open"):
        execute_with_retries(
            operation,
            policy=RetryPolicy(),
            breaker=breaker,
        )

    assert called is False
