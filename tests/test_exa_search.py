from __future__ import annotations

import hashlib
import json
import sys
import types
from dataclasses import dataclass

import pytest
from pydantic import SecretStr

from muse.exa_search import ExaSearchProvider
from muse.live_search_config import (
    ExaSearchCredentials,
    LiveSearchRuntime,
    SearchProviderError,
)
from muse.search import SearchPurpose, SearchQuery


class FakeExaClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object]]] = []

    def search(self, query: str, **kwargs: object) -> object:
        self.calls.append((query, kwargs))
        return self.payload


@dataclass(frozen=True)
class ObjectResult:
    title: str
    url: str
    highlights: tuple[str, ...] = ()
    summary: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class ObjectResponse:
    results: tuple[ObjectResult, ...]


def test_exa_search_maps_highlights_to_search_results_without_leaking_secret() -> None:
    client = FakeExaClient(
        {
            "results": [
                {
                    "id": "exa-raw-1",
                    "title": "Decision gardens",
                    "url": "https://example.com/decision-gardens",
                    "highlights": ["Teams use reversible claims."],
                    "text": "Teams use reversible claims as evidence arrives.",
                }
            ]
        }
    )
    provider = ExaSearchProvider(
        credentials=ExaSearchCredentials(api_key=SecretStr("exa-secret")),
        client=client,
        runtime=LiveSearchRuntime(),
    )
    query = SearchQuery(
        text="Reversible team decisions",
        purpose=SearchPurpose.NOVELTY,
        limit=1,
    )

    response = provider.search(query)

    assert client.calls == [
        (
            "Reversible team decisions",
            {
                "num_results": 1,
                "contents": {"highlights": True, "text": True},
            },
        )
    ]
    assert provider.name == "exa"
    assert provider.version
    assert provider.quote_search(query).max_cost_usd == 0.0
    assert response.provider_name == "exa"
    assert response.results[0].provider == "exa"
    assert response.results[0].rank == 1
    assert response.results[0].title == "Decision gardens"
    assert str(response.results[0].url) == "https://example.com/decision-gardens"
    assert response.results[0].snippet == "Teams use reversible claims."
    assert response.results[0].bounded_excerpt == (
        "Teams use reversible claims as evidence arrives."
    )
    assert response.results[0].retrieved_at.tzinfo is not None
    assert response.usage.result_count == 1
    assert response.usage.cost_usd == 0.0
    assert "exa-secret" not in response.trace.request_json
    assert "exa-secret" not in response.trace.response_json
    assert json.loads(response.trace.response_json)["source_ids"] == (
        [response.results[0].source_id]
    )


def test_exa_search_skips_malformed_results_and_reports_empty_usage() -> None:
    provider = ExaSearchProvider(
        credentials=ExaSearchCredentials(api_key=SecretStr("exa-secret")),
        client=FakeExaClient({"results": [{"title": "missing url"}]}),
        runtime=LiveSearchRuntime(),
    )

    response = provider.search(
        SearchQuery(
            text="Reversible team decisions",
            purpose=SearchPurpose.ANALOGY,
            limit=1,
        )
    )

    assert response.results == ()
    assert response.usage.result_count == 0
    assert json.loads(response.trace.response_json)["result_count"] == 0


def test_exa_search_maps_object_like_results_from_summary_and_text() -> None:
    provider = ExaSearchProvider(
        credentials=ExaSearchCredentials(api_key=SecretStr("exa-secret")),
        client=FakeExaClient(
            ObjectResponse(
                results=(
                    ObjectResult(
                        title="Decision records",
                        url="https://example.com/decision-records",
                        summary="Structured decision logs.",
                        text="Structured decision logs preserve context.",
                    ),
                )
            )
        ),
        runtime=LiveSearchRuntime(),
    )

    response = provider.search(
        SearchQuery(
            text="Decision records",
            purpose=SearchPurpose.EVIDENCE,
            limit=1,
        )
    )

    result = response.results[0]
    assert result.snippet == "Structured decision logs."
    assert result.bounded_excerpt == "Structured decision logs preserve context."
    assert result.provider_metadata == {"source": "exa"}


def test_exa_search_bounds_snippets_and_uses_deterministic_source_ids() -> None:
    long_text = "x" * 200
    client = FakeExaClient(
        {
            "results": [
                {
                    "title": "Long source",
                    "url": "https://example.com/long",
                    "highlights": [long_text],
                    "text": long_text,
                }
            ]
        }
    )
    provider = ExaSearchProvider(
        credentials=ExaSearchCredentials(api_key=SecretStr("exa-secret")),
        client=client,
        runtime=LiveSearchRuntime(snippet_chars=80),
    )

    first = provider.search(
        SearchQuery(text="long source", purpose=SearchPurpose.PRIOR_ART, limit=10)
    )
    second = provider.search(
        SearchQuery(text="long source", purpose=SearchPurpose.PRIOR_ART, limit=10)
    )

    result = first.results[0]
    expected_id = "exa-" + hashlib.sha256(b"https://example.com/long").hexdigest()[:16]
    assert len(result.snippet) <= 80
    assert len(result.bounded_excerpt) <= 80
    assert result.source_id == expected_id
    assert second.results[0].source_id == expected_id
    assert client.calls[0][1]["num_results"] == 10


def test_exa_search_sanitizes_client_exceptions() -> None:
    class RaisingClient:
        def search(self, query: str, **kwargs: object) -> object:
            raise RuntimeError("upstream failure with exa-secret")

    provider = ExaSearchProvider(
        credentials=ExaSearchCredentials(api_key=SecretStr("exa-secret")),
        client=RaisingClient(),
        runtime=LiveSearchRuntime(),
    )

    with pytest.raises(SearchProviderError) as exc_info:
        provider.search(SearchQuery(text="x", purpose=SearchPurpose.EVIDENCE, limit=1))

    error = exc_info.value
    assert error.provider == "exa"
    assert error.category == "search_error"
    assert "exa-secret" not in str(error)
    assert "[REDACTED]" in str(error)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert "exa-secret" not in repr(error)
    assert all("exa-secret" not in repr(arg) for arg in error.args)


def test_exa_search_preserves_lazy_client_provider_errors() -> None:
    class MissingSdkProvider(ExaSearchProvider):
        def _build_default_client(self) -> object:
            raise SearchProviderError(
                provider="exa",
                category="configuration_error",
                message="missing SDK with exa-secret",
                secret_values=("exa-secret",),
            )

    provider = MissingSdkProvider(
        credentials=ExaSearchCredentials(api_key=SecretStr("exa-secret")),
        runtime=LiveSearchRuntime(),
    )

    with pytest.raises(SearchProviderError) as exc_info:
        provider.search(SearchQuery(text="x", purpose=SearchPurpose.EVIDENCE, limit=1))

    error = exc_info.value
    assert error.category == "configuration_error"
    assert "exa-secret" not in str(error)


def test_exa_search_requires_official_exa_py_sdk_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnknownExa:
        def __init__(self, api_key: str) -> None:
            raise AssertionError(f"fallback exa module received {api_key}")

    fake_exa_module = types.ModuleType("exa")
    fake_exa_module.Exa = UnknownExa
    monkeypatch.setitem(sys.modules, "exa_py", None)
    monkeypatch.setitem(sys.modules, "exa", fake_exa_module)

    provider = ExaSearchProvider(
        credentials=ExaSearchCredentials(api_key=SecretStr("exa-secret")),
        runtime=LiveSearchRuntime(),
    )

    with pytest.raises(SearchProviderError) as exc_info:
        provider.search(SearchQuery(text="x", purpose=SearchPurpose.EVIDENCE, limit=1))

    error = exc_info.value
    assert error.provider == "exa"
    assert error.category == "configuration_error"
    assert "exa_py" in str(error)
    assert "exa-secret" not in str(error)
    assert "exa-secret" not in repr(error)
    assert all("exa-secret" not in repr(arg) for arg in error.args)
    assert error.__cause__ is None
    assert error.__context__ is None
