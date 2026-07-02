from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
import pytest
from openai import APITimeoutError, AuthenticationError, RateLimitError
from pydantic import ValidationError

from muse.embeddings import EmbeddingBatch
from muse.live_config import LiveModelConfig
from muse.openai_embeddings import OpenAIEmbeddingProvider
from muse.pricing import EmbeddingPrice, PricingTable
from muse.reliability import CircuitBreaker, RetryPolicy


@dataclass
class FakeEmbedding:
    embedding: list[float]
    index: int


@dataclass
class FakeUsage:
    prompt_tokens: int = 0
    total_tokens: int = 0


class FakeEmbeddingResponse:
    def __init__(
        self,
        *,
        vectors: list[list[float]],
        prompt_tokens: int,
        indices: list[int] | None = None,
        request_id: str = "req_embed",
    ) -> None:
        resolved_indices = indices if indices is not None else list(range(len(vectors)))
        self.data = [
            FakeEmbedding(embedding=vector, index=index)
            for vector, index in zip(vectors, resolved_indices, strict=True)
        ]
        self.usage = FakeUsage(prompt_tokens=prompt_tokens, total_tokens=prompt_tokens)
        self._request_id = request_id


class FakeEmbeddings:
    def __init__(self, parent: FakeEmbeddingClient) -> None:
        self._parent = parent

    def create(self, **kwargs: object) -> FakeEmbeddingResponse:
        self._parent.call_count += 1
        self._parent.requests.append(kwargs)
        item = self._parent.next_item()
        if isinstance(item, BaseException):
            raise item
        return FakeEmbeddingResponse(
            vectors=item["vectors"],
            prompt_tokens=item["prompt_tokens"],
            indices=item.get("indices"),
            request_id=f"req_embed_{self._parent.call_count}",
        )


class FakeEmbeddingClient:
    def __init__(
        self,
        *,
        vectors: list[list[float]] | None = None,
        prompt_tokens: int = 0,
        indices: list[int] | None = None,
        sequence: list[dict[str, object] | BaseException] | None = None,
    ) -> None:
        initial = {
            "vectors": vectors or [],
            "prompt_tokens": prompt_tokens,
        }
        if indices is not None:
            initial["indices"] = indices
        self._sequence = list(sequence if sequence is not None else [initial])
        self.embeddings = FakeEmbeddings(self)
        self.requests: list[dict[str, object]] = []
        self.call_count = 0

    @property
    def last_request(self) -> dict[str, object]:
        return self.requests[-1]

    def next_item(self) -> dict[str, object] | BaseException:
        if len(self._sequence) > 1:
            return self._sequence.pop(0)
        return self._sequence[0]


class FakeClock:
    def __init__(self) -> None:
        self.values = [10.0, 10.025, 20.0, 20.025]

    def __call__(self) -> float:
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


def pricing_table() -> PricingTable:
    return PricingTable(
        version="test-pricing",
        models=(),
        embeddings={
            "embedding-test-model": EmbeddingPrice(input_per_million=0.02),
        },
    )


def build_embedding_provider(
    client: FakeEmbeddingClient,
    *,
    retry_policy: RetryPolicy | None = None,
    breaker: CircuitBreaker | None = None,
    clock: FakeClock | None = None,
) -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(
        client=client,
        config=LiveModelConfig(
            economy_model="economy-test-model",
            strong_model="strong-test-model",
            embedding_model="embedding-test-model",
        ),
        pricing=pricing_table(),
        retry_policy=retry_policy or RetryPolicy(max_retries=0),
        breaker=breaker or CircuitBreaker(failure_threshold=3),
        monotonic=clock or FakeClock(),
        sleep=lambda _: None,
        random_value=lambda: 0.0,
    )


def test_embedding_provider_preserves_input_order_and_usage() -> None:
    client = FakeEmbeddingClient(
        vectors=[[0.1, 0.2], [0.3, 0.4]],
        prompt_tokens=12,
    )
    provider = build_embedding_provider(client)

    response = provider.embed(("first", "second"))

    assert response.value.vectors == ((0.1, 0.2), (0.3, 0.4))
    assert response.value.dimensions == 2
    assert response.usage.input_tokens == 12
    assert client.last_request["model"] == "embedding-test-model"


def test_embedding_provider_rejects_wrong_vector_count() -> None:
    client = FakeEmbeddingClient(
        vectors=[[0.1, 0.2]],
        prompt_tokens=12,
    )
    provider = build_embedding_provider(client)

    try:
        provider.embed(("first", "second"))
    except ValueError as error:
        assert str(error) == "embedding count does not match input count"
    else:
        raise AssertionError("wrong vector count was accepted")


@pytest.mark.parametrize(
    "texts",
    [
        (),
        ("",),
        ("   ",),
        ("valid", "\t"),
    ],
)
def test_embedding_provider_rejects_empty_or_blank_inputs(
    texts: tuple[str, ...],
) -> None:
    client = FakeEmbeddingClient(vectors=[[0.1]], prompt_tokens=1)
    provider = build_embedding_provider(client)

    with pytest.raises(ValueError, match="embedding input"):
        provider.embed(texts)

    assert client.call_count == 0


def test_embedding_provider_reconstructs_response_index_order() -> None:
    client = FakeEmbeddingClient(
        vectors=[[0.3, 0.4], [0.1, 0.2]],
        indices=[1, 0],
        prompt_tokens=12,
    )
    provider = build_embedding_provider(client)

    response = provider.embed(("first", "second"))

    assert response.value.vectors == ((0.1, 0.2), (0.3, 0.4))


@pytest.mark.parametrize(
    ("vectors", "message"),
    [
        ([[0.1, 0.2], [0.3]], "embedding dimensions are inconsistent"),
        ([[0.1], []], "embedding dimensions are inconsistent"),
    ],
)
def test_embedding_provider_rejects_inconsistent_dimensions(
    vectors: list[list[float]],
    message: str,
) -> None:
    client = FakeEmbeddingClient(vectors=vectors, prompt_tokens=12)
    provider = build_embedding_provider(client)

    with pytest.raises(ValueError, match=message):
        provider.embed(("first", "second"))


def test_embedding_provider_rejects_duplicate_or_missing_indices() -> None:
    client = FakeEmbeddingClient(
        vectors=[[0.1, 0.2], [0.3, 0.4]],
        indices=[0, 0],
        prompt_tokens=12,
    )
    provider = build_embedding_provider(client)

    with pytest.raises(ValueError, match="embedding indices do not match input order"):
        provider.embed(("first", "second"))


def test_embedding_provider_quotes_with_embedding_pricing() -> None:
    client = FakeEmbeddingClient(vectors=[[0.1]], prompt_tokens=1)
    provider = build_embedding_provider(client)

    quote = provider.quote_embeddings(("first", "second"))

    assert quote.max_cost_usd == 0.00016
    assert client.call_count == 0


def test_embedding_batch_rejects_dimension_mismatch_when_constructed_directly() -> None:
    with pytest.raises(ValidationError):
        EmbeddingBatch(vectors=((0.1, 0.2), (0.3,)), dimensions=2)


def test_embedding_provider_meters_cost_latency_request_id_and_trace() -> None:
    client = FakeEmbeddingClient(
        vectors=[[0.1, 0.2], [0.3, 0.4]],
        prompt_tokens=12_345,
    )
    provider = build_embedding_provider(client)

    response = provider.embed(("first secret prompt", "second"))

    assert response.provider == "openai"
    assert response.model == "embedding-test-model"
    assert response.cost_usd == 0.0002469
    assert response.pricing_version == "test-pricing"
    assert response.cost_is_estimated is True
    assert response.latency_ms == 25
    assert response.request_id == "req_embed_1"
    assert response.operation_trace is not None
    request = json.loads(response.operation_trace.request_json)
    traced_response = json.loads(response.operation_trace.response_json)
    assert request == {
        "input_count": 2,
        "model": "embedding-test-model",
        "operation": "embeddings",
    }
    assert traced_response["dimensions"] == 2
    assert traced_response["embedding_count"] == 2
    assert "0.1" not in response.operation_trace.response_json
    assert "first secret prompt" not in response.operation_trace.request_json


def _http_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://api.openai.test/v1/embeddings"),
        headers={"x-request-id": "req_error"},
    )


def test_embedding_provider_retries_rate_limits_and_timeouts() -> None:
    client = FakeEmbeddingClient(
        sequence=[
            RateLimitError("slow down", response=_http_response(429), body=None),
            APITimeoutError(request=httpx.Request("POST", "https://api.openai.test")),
            {"vectors": [[0.1, 0.2]], "prompt_tokens": 12},
        ]
    )
    provider = build_embedding_provider(client, retry_policy=RetryPolicy(max_retries=2))

    response = provider.embed(("first",))

    assert response.value.vectors == ((0.1, 0.2),)
    assert client.call_count == 3


def test_embedding_provider_opens_breaker_after_exhausted_retryable_failure() -> None:
    breaker = CircuitBreaker(failure_threshold=1)
    client = FakeEmbeddingClient(
        sequence=[
            RateLimitError("slow down", response=_http_response(429), body=None),
        ]
    )
    provider = build_embedding_provider(
        client,
        retry_policy=RetryPolicy(max_retries=0),
        breaker=breaker,
    )

    with pytest.raises(RuntimeError, match="RateLimitError"):
        provider.embed(("first",))

    with pytest.raises(RuntimeError, match="CircuitOpenError"):
        provider.embed(("first",))


def test_embedding_provider_sanitizes_provider_exceptions() -> None:
    client = FakeEmbeddingClient(
        sequence=[
            AuthenticationError(
                "bad api key sk-secret123456 with prompt Sensitive proprietary prompt",
                response=_http_response(401),
                body=None,
            )
        ]
    )
    provider = build_embedding_provider(client, retry_policy=RetryPolicy(max_retries=2))

    with pytest.raises(RuntimeError) as error:
        provider.embed(("Sensitive proprietary prompt",))

    assert client.call_count == 1
    assert "sk-secret" not in str(error.value)
    assert "Sensitive proprietary prompt" not in str(error.value)
    assert "AuthenticationError" in str(error.value)


def test_embedding_provider_sanitizes_client_value_error_details() -> None:
    client = FakeEmbeddingClient(
        sequence=[
            ValueError(
                "bad request for input Embargoed roadmap detail sk-secret123456"
            )
        ]
    )
    provider = build_embedding_provider(client)

    with pytest.raises(RuntimeError) as error:
        provider.embed(("Embargoed roadmap detail",))

    assert "Embargoed roadmap detail" not in str(error.value)
    assert "sk-secret" not in str(error.value)
    assert "ValueError" in str(error.value)


@pytest.mark.parametrize(
    "bad_value",
    ["1.0", "sk-secret123456", float("nan"), float("inf")],
)
def test_embedding_provider_rejects_malformed_vector_values_safely(
    bad_value: object,
) -> None:
    client = FakeEmbeddingClient(
        vectors=[[bad_value]],  # type: ignore[list-item]
        prompt_tokens=1,
    )
    provider = build_embedding_provider(client)

    with pytest.raises(RuntimeError) as error:
        provider.embed(("Embargoed roadmap detail",))

    assert "embedding vector values are invalid" in str(error.value)
    assert "Embargoed roadmap detail" not in str(error.value)
    assert "sk-secret" not in str(error.value)
