from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import pytest

from muse.live_search_config import (
    LiveSearchRuntime,
    OpenAIWebSearchConfig,
    SearchProviderError,
)
from muse.openai_web_search import OpenAIWebSearchProvider
from muse.search import SearchPurpose, SearchQuery


class FakeResponses:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.payload


class FakeOpenAIClient:
    def __init__(self, payload: object) -> None:
        self.responses = FakeResponses(payload)


@dataclass(frozen=True)
class ObjectAnnotation:
    type: str
    title: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class ObjectContent:
    text: str
    annotations: tuple[ObjectAnnotation, ...]


@dataclass(frozen=True)
class ObjectOutput:
    content: tuple[ObjectContent, ...]


@dataclass(frozen=True)
class ObjectResponse:
    output: tuple[ObjectOutput, ...]


def _query(*, limit: int = 3) -> SearchQuery:
    return SearchQuery(
        text="Reversible team decisions",
        purpose=SearchPurpose.EVIDENCE,
        limit=limit,
        freshness_bucket="recent",
        domain_hints=("example.com",),
    )


def test_openai_web_search_uses_explicit_model_and_maps_dict_citations() -> None:
    client = FakeOpenAIClient(
        {
            "id": "raw-response-id",
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Decision gardens source with reversible claims.",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "title": "Decision gardens",
                                    "url": "https://example.com/decision-gardens",
                                }
                            ],
                        }
                    ]
                }
            ],
        }
    )
    provider = OpenAIWebSearchProvider(
        client=client,
        config=OpenAIWebSearchConfig(model="gpt-test-search"),
        runtime=LiveSearchRuntime(max_results=2),
    )
    query = _query(limit=3)

    response = provider.search(query)

    assert client.responses.calls == [
        {
            "model": "gpt-test-search",
            "input": "Reversible team decisions",
            "tools": [{"type": "web_search_preview"}],
        }
    ]
    assert provider.name == "openai-web-search"
    assert provider.version.startswith("openai-web-search-")
    assert provider.quote_search(query).max_cost_usd == 0.0
    assert response.provider_name == "openai-web-search"
    assert response.usage.result_count == 1
    assert response.usage.cost_usd == 0.0

    result = response.results[0]
    assert result.provider == "openai-web-search"
    assert result.rank == 1
    assert result.title == "Decision gardens"
    assert str(result.url) == "https://example.com/decision-gardens"
    assert result.snippet == "Decision gardens source with reversible claims."
    assert result.bounded_excerpt == "Decision gardens source with reversible claims."
    assert result.retrieved_at.tzinfo is not None
    assert result.provider_metadata == {"source": "openai-web-search"}

    request_trace = json.loads(response.trace.request_json)
    response_trace = json.loads(response.trace.response_json)
    assert request_trace == {
        "operation": "search",
        "provider": "openai-web-search",
        "provider_version": provider.version,
        "model": "gpt-test-search",
        "search": {
            "normalized_text": "reversible team decisions",
            "purpose": "evidence",
            "limit": 3,
            "effective_limit": 2,
            "freshness_bucket": "recent",
            "domain_hints": ["example.com"],
            "tool": {"type": "web_search_preview"},
        },
    }
    assert response_trace == {
        "operation": "search",
        "provider": "openai-web-search",
        "source_ids": [result.source_id],
        "result_count": 1,
        "skipped_count": 0,
    }
    trace_text = response.trace.request_json + response.trace.response_json
    assert "OPENAI_API_KEY" not in trace_text
    assert "headers" not in trace_text
    assert "raw-response-id" not in trace_text
    assert "Decision gardens source" not in trace_text


def test_openai_web_search_supports_object_like_response_shapes() -> None:
    provider = OpenAIWebSearchProvider(
        client=FakeOpenAIClient(
            ObjectResponse(
                output=(
                    ObjectOutput(
                        content=(
                            ObjectContent(
                                text="Decision records preserve context.",
                                annotations=(
                                    ObjectAnnotation(
                                        type="url_citation",
                                        title="Decision records",
                                        url="https://example.com/decision-records",
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
            )
        ),
        config=OpenAIWebSearchConfig(model="gpt-test-search"),
    )

    response = provider.search(_query(limit=1))

    result = response.results[0]
    assert result.title == "Decision records"
    assert str(result.url) == "https://example.com/decision-records"
    assert result.snippet == "Decision records preserve context."


def test_openai_web_search_skips_citations_without_url_and_tracks_skipped_count() -> None:
    provider = OpenAIWebSearchProvider(
        client=FakeOpenAIClient(
            {
                "output": [
                    {
                        "content": [
                            {
                                "text": "One skipped citation and one usable source.",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "title": "Missing URL",
                                    },
                                    {
                                        "type": "url_citation",
                                        "title": "Valid",
                                        "url": "https://example.com/valid",
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        ),
        config=OpenAIWebSearchConfig(model="gpt-test-search"),
    )

    response = provider.search(_query(limit=2))

    assert len(response.results) == 1
    assert response.results[0].title == "Valid"
    assert json.loads(response.trace.response_json)["skipped_count"] == 1


def test_openai_web_search_bounds_snippets_and_excerpts() -> None:
    long_text = "x" * 200
    provider = OpenAIWebSearchProvider(
        client=FakeOpenAIClient(
            {
                "output": [
                    {
                        "content": [
                            {
                                "text": long_text,
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "title": "Long source",
                                        "url": "https://example.com/long",
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ),
        config=OpenAIWebSearchConfig(model="gpt-test-search"),
        runtime=LiveSearchRuntime(snippet_chars=80),
    )

    response = provider.search(_query(limit=1))

    assert response.results[0].snippet == "x" * 80
    assert response.results[0].bounded_excerpt == "x" * 80


def test_openai_web_search_uses_stable_deterministic_source_ids() -> None:
    payload = {
        "output": [
            {
                "content": [
                    {
                        "text": "Stable source.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "title": "Stable source",
                                "url": "https://example.com/stable",
                            }
                        ],
                    }
                ]
            }
        ]
    }
    provider = OpenAIWebSearchProvider(
        client=FakeOpenAIClient(payload),
        config=OpenAIWebSearchConfig(model="gpt-test-search"),
    )

    first = provider.search(_query(limit=1))
    second = provider.search(_query(limit=1))

    expected = "openai-web-" + hashlib.sha256(
        b"https://example.com/stable"
    ).hexdigest()[:16]
    assert first.results[0].source_id == expected
    assert second.results[0].source_id == expected


def test_openai_web_search_sanitizes_provider_errors_comprehensively() -> None:
    class RaisingResponses:
        def create(self, **kwargs: object) -> object:
            raise RuntimeError("upstream failure with sk-secret1234567890")

    class RaisingClient:
        responses = RaisingResponses()

    provider = OpenAIWebSearchProvider(
        client=RaisingClient(),
        config=OpenAIWebSearchConfig(model="gpt-test-search"),
    )

    with pytest.raises(SearchProviderError) as exc_info:
        provider.search(_query(limit=1))

    error = exc_info.value
    secret = "sk-secret1234567890"
    assert error.provider == "openai-web-search"
    assert error.category == "search_error"
    assert secret not in str(error)
    assert secret not in repr(error)
    assert secret not in repr(error.args)
    assert secret not in error.message
    assert secret not in repr(error.__dict__)
    assert error.__cause__ is None
    assert error.__context__ is None
