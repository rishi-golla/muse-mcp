from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from muse.reliability import (
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
    execute_with_retries,
    is_retryable_openai_exception,
)


def _response(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return httpx.Response(status_code, request=request, headers=headers)


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/responses")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_retries", -1),
        ("max_retries", 6),
        ("max_retries", True),
        ("max_retries", 1.5),
        ("base_delay_seconds", -0.1),
        ("base_delay_seconds", 0),
        ("base_delay_seconds", float("nan")),
        ("base_delay_seconds", float("inf")),
        ("maximum_delay_seconds", -0.1),
        ("maximum_delay_seconds", 0),
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


def test_retry_executor_caps_final_jittered_delay() -> None:
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
    assert delays == [1.25, 2.0, 2.0]


@pytest.mark.parametrize(
    "jitter",
    [-0.1, 1.1, float("nan"), float("inf"), float("-inf")],
)
def test_retry_executor_rejects_invalid_jitter_before_sleep(jitter: float) -> None:
    delays: list[float] = []

    def operation() -> None:
        raise RateLimitError(
            "rate limited",
            response=_response(429),
            body=None,
        )

    with pytest.raises(ValueError, match="random_value"):
        execute_with_retries(
            operation,
            policy=RetryPolicy(max_retries=1),
            sleep=delays.append,
            random_value=lambda: jitter,
        )

    assert delays == []


def test_retry_after_milliseconds_header_takes_precedence() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError(
                "rate limited",
                response=_response(
                    429,
                    headers={
                        "retry-after-ms": "1500",
                        "Retry-After": "9",
                    },
                ),
                body=None,
            )
        return "ok"

    assert execute_with_retries(
        operation,
        policy=RetryPolicy(max_retries=1, maximum_delay_seconds=5.0),
        sleep=delays.append,
        random_value=lambda: pytest.fail("header delay used random jitter"),
    ) == "ok"
    assert delays == [1.5]


def test_retry_after_seconds_header_is_honored_and_capped() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError(
                "rate limited",
                response=_response(429, headers={"Retry-After": "9"}),
                body=None,
            )
        return "ok"

    assert execute_with_retries(
        operation,
        policy=RetryPolicy(max_retries=1, maximum_delay_seconds=2.0),
        sleep=delays.append,
        random_value=lambda: pytest.fail("header delay used random jitter"),
    ) == "ok"
    assert delays == [2.0]


def test_future_http_date_retry_after_is_honored() -> None:
    current = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    retry_at = current + timedelta(seconds=3)
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError(
                "rate limited",
                response=_response(
                    429,
                    headers={"Retry-After": format_datetime(retry_at, usegmt=True)},
                ),
                body=None,
            )
        return "ok"

    assert execute_with_retries(
        operation,
        policy=RetryPolicy(max_retries=1, maximum_delay_seconds=5.0),
        sleep=delays.append,
        random_value=lambda: pytest.fail("HTTP-date used local backoff"),
        now=lambda: current,
    ) == "ok"
    assert delays == [3.0]


def test_future_http_date_retry_after_is_capped() -> None:
    current = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    retry_at = current + timedelta(seconds=30)
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError(
                "rate limited",
                response=_response(
                    429,
                    headers={"Retry-After": format_datetime(retry_at, usegmt=True)},
                ),
                body=None,
            )
        return "ok"

    assert execute_with_retries(
        operation,
        policy=RetryPolicy(max_retries=1, maximum_delay_seconds=2.0),
        sleep=delays.append,
        random_value=lambda: pytest.fail("HTTP-date used local backoff"),
        now=lambda: current,
    ) == "ok"
    assert delays == [2.0]


def test_past_http_date_retry_after_requests_immediate_retry() -> None:
    current = datetime(2026, 6, 23, 12, 0, tzinfo=UTC)
    retry_at = current - timedelta(seconds=30)
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError(
                "rate limited",
                response=_response(
                    429,
                    headers={"Retry-After": format_datetime(retry_at, usegmt=True)},
                ),
                body=None,
            )
        return "ok"

    assert execute_with_retries(
        operation,
        policy=RetryPolicy(max_retries=1),
        sleep=delays.append,
        random_value=lambda: pytest.fail("HTTP-date used local backoff"),
        now=lambda: current,
    ) == "ok"
    assert delays == [0.0]


def test_malformed_http_date_retry_after_uses_local_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError(
                "rate limited",
                response=_response(
                    429,
                    headers={"Retry-After": "Tuesday, definitely not a date"},
                ),
                body=None,
            )
        return "ok"

    assert execute_with_retries(
        operation,
        policy=RetryPolicy(
            max_retries=1,
            base_delay_seconds=0.4,
            maximum_delay_seconds=2.0,
        ),
        sleep=delays.append,
        random_value=lambda: 0.0,
        now=lambda: pytest.fail("malformed HTTP-date used injected clock"),
    ) == "ok"
    assert delays == [0.4]


@pytest.mark.parametrize(
    "headers",
    [
        {"retry-after-ms": "malformed", "Retry-After": "-1"},
        {"retry-after-ms": "-10"},
        {"Retry-After": "nan"},
        {"Retry-After": "inf"},
    ],
)
def test_invalid_retry_headers_fall_back_to_local_backoff(
    headers: dict[str, str],
) -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RateLimitError(
                "rate limited",
                response=_response(429, headers=headers),
                body=None,
            )
        return "ok"

    assert execute_with_retries(
        operation,
        policy=RetryPolicy(
            max_retries=1,
            base_delay_seconds=0.4,
            maximum_delay_seconds=2.0,
        ),
        sleep=delays.append,
        random_value=lambda: 0.0,
    ) == "ok"
    assert delays == [0.4]


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


@pytest.mark.parametrize("status_code", [408, 409, 500, 503, 599])
def test_transient_api_status_errors_are_retryable(status_code: int) -> None:
    error = APIStatusError(
        "transient status",
        response=_response(status_code),
        body=None,
    )

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
        PermissionDeniedError(
            "forbidden",
            response=_response(403),
            body=None,
        ),
        NotFoundError(
            "missing",
            response=_response(404),
            body=None,
        ),
        UnprocessableEntityError(
            "invalid",
            response=_response(422),
            body=None,
        ),
        APIStatusError(
            "other client error",
            response=_response(418),
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
        policy=RetryPolicy(max_retries=1, base_delay_seconds=0.01),
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
            policy=RetryPolicy(max_retries=1, base_delay_seconds=0.01),
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


def test_record_success_closes_an_open_circuit() -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    breaker.record_failure()

    breaker.record_success()

    assert breaker.is_open is False
    breaker.before_call()


def test_threshold_one_retry_then_success_keeps_circuit_closed() -> None:
    breaker = CircuitBreaker(failure_threshold=1)
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
        policy=RetryPolicy(max_retries=1, base_delay_seconds=0.01),
        breaker=breaker,
        sleep=lambda _: None,
    ) == "ok"

    assert breaker.is_open is False


def test_exhausted_operation_records_one_logical_failure() -> None:
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
            policy=RetryPolicy(max_retries=2, base_delay_seconds=0.01),
            breaker=breaker,
            sleep=lambda _: None,
        )

    assert breaker.is_open is False
    breaker.before_call()


def test_circuit_opens_after_threshold_exhausted_operations() -> None:
    breaker = CircuitBreaker(failure_threshold=2)
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise RateLimitError(
            "rate limited",
            response=_response(429),
            body=None,
        )

    for _ in range(2):
        with pytest.raises(RateLimitError):
            execute_with_retries(
                operation,
                policy=RetryPolicy(max_retries=1, base_delay_seconds=0.01),
                breaker=breaker,
                sleep=lambda _: None,
            )

    assert calls == 4
    assert breaker.is_open is True


def test_nonretryable_exception_does_not_count_as_circuit_failure() -> None:
    breaker = CircuitBreaker(failure_threshold=1)

    def operation() -> None:
        raise AuthenticationError(
            "invalid key",
            response=_response(401),
            body=None,
        )

    with pytest.raises(AuthenticationError):
        execute_with_retries(
            operation,
            policy=RetryPolicy(),
            breaker=breaker,
        )

    assert breaker.is_open is False
    breaker.before_call()


def test_retry_policy_requires_maximum_delay_at_least_base_delay() -> None:
    with pytest.raises(ValueError, match="maximum_delay_seconds"):
        RetryPolicy(
            base_delay_seconds=2.0,
            maximum_delay_seconds=1.0,
        )


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
