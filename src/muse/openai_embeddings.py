from __future__ import annotations

import re
import time
from collections.abc import Callable
from math import isfinite
from numbers import Real
from typing import Any

from muse.embeddings import EmbeddingBatch
from muse.live_config import LiveModelConfig
from muse.models import OperationTrace, TokenUsage
from muse.pricing import PricingTable
from muse.providers import MeteredResponse, OperationQuote
from muse.reliability import CircuitBreaker, RetryPolicy, execute_with_retries

SECRET_VALUE_PATTERN = re.compile(
    r"(?:\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{10,})",
    re.IGNORECASE,
)


class OpenAIEmbeddingProvider:
    name = "openai"
    version = "embeddings-v1"

    def __init__(
        self,
        *,
        client: Any,
        config: LiveModelConfig,
        pricing: PricingTable,
        retry_policy: RetryPolicy,
        breaker: CircuitBreaker,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._pricing = pricing
        self._retry_policy = retry_policy
        self._breaker = breaker
        self._monotonic = monotonic
        self._sleep = sleep
        self._random_value = random_value

    def quote_embeddings(self, texts: tuple[str, ...]) -> OperationQuote:
        _validate_texts(texts)
        estimate = self._pricing.estimate_embeddings(
            self._config.embedding_model,
            self._config.embedding_max_input_tokens,
        )
        return OperationQuote(max_cost_usd=estimate.estimated_cost_usd)

    def embed(self, texts: tuple[str, ...]) -> MeteredResponse[EmbeddingBatch]:
        _validate_texts(texts)
        start = self._monotonic()
        try:
            response = self._execute_create(texts)
        except Exception as error:
            raise RuntimeError(
                _safe_error_message(operation="embeddings", error=error)
            ) from error
        batch = _embedding_batch(response, input_count=len(texts))
        end = self._monotonic()
        usage = _usage(response)
        estimate = self._pricing.estimate_embeddings(
            self._config.embedding_model,
            usage.input_tokens,
        )
        trace = OperationTrace.from_payload(
            request={
                "operation": "embeddings",
                "model": self._config.embedding_model,
                "input_count": len(texts),
            },
            response={
                "request_id": _request_id(response),
                "embedding_count": len(batch.vectors),
                "dimensions": batch.dimensions,
                "usage": {
                    "input_tokens": usage.input_tokens,
                },
            },
        )
        return MeteredResponse(
            value=batch,
            provider=self.name,
            model=self._config.embedding_model,
            cost_usd=estimate.estimated_cost_usd,
            latency_ms=max(0, round((end - start) * 1_000)),
            usage=usage,
            pricing_version=estimate.pricing_version,
            cost_is_estimated=estimate.is_estimated,
            request_id=_request_id(response),
            operation_trace=trace,
        )

    def _execute_create(self, texts: tuple[str, ...]) -> object:
        kwargs: dict[str, object] = {
            "model": self._config.embedding_model,
            "input": list(texts),
        }

        def operation() -> object:
            return self._client.embeddings.create(**kwargs)

        retry_kwargs: dict[str, object] = {
            "policy": self._retry_policy,
            "breaker": self._breaker,
            "sleep": self._sleep,
        }
        if self._random_value is not None:
            retry_kwargs["random_value"] = self._random_value
        return execute_with_retries(operation, **retry_kwargs)


def _validate_texts(texts: tuple[str, ...]) -> None:
    if not texts:
        raise ValueError("embedding input must not be empty")
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("embedding input text must not be blank")


def _embedding_batch(response: object, *, input_count: int) -> EmbeddingBatch:
    data = tuple(getattr(response, "data", ()))
    if len(data) != input_count:
        raise ValueError("embedding count does not match input count")

    vectors_by_index: dict[int, tuple[float, ...]] = {}
    for item in data:
        index = getattr(item, "index", None)
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("embedding indices do not match input order")
        if index < 0 or index >= input_count or index in vectors_by_index:
            raise ValueError("embedding indices do not match input order")
        vector = _validated_vector(getattr(item, "embedding", ()))
        vectors_by_index[index] = vector

    if tuple(sorted(vectors_by_index)) != tuple(range(input_count)):
        raise ValueError("embedding indices do not match input order")

    vectors = tuple(vectors_by_index[index] for index in range(input_count))
    dimensions = len(vectors[0])
    if dimensions == 0 or any(len(vector) != dimensions for vector in vectors):
        raise ValueError("embedding dimensions are inconsistent")

    return EmbeddingBatch(vectors=vectors, dimensions=dimensions)


def _validated_vector(value: object) -> tuple[float, ...]:
    try:
        raw_vector = tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise RuntimeError(
            "openai embeddings failed: embedding vector values are invalid"
        ) from error
    vector: list[float] = []
    for item in raw_vector:
        if isinstance(item, bool) or not isinstance(item, Real) or not isfinite(item):
            raise RuntimeError(
                "openai embeddings failed: embedding vector values are invalid"
            )
        vector.append(float(item))
    return tuple(vector)


def _usage(response: object) -> TokenUsage:
    raw_usage = getattr(response, "usage", None)
    return TokenUsage(
        input_tokens=getattr(raw_usage, "prompt_tokens", 0) or 0,
    )


def _request_id(response: object) -> str | None:
    value = getattr(response, "_request_id", None)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _safe_error_message(*, operation: str, error: BaseException) -> str:
    detail = type(error).__name__
    detail = SECRET_VALUE_PATTERN.sub("[REDACTED]", detail)
    return f"openai {operation} failed: {detail}"
