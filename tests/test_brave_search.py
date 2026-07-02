from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import SecretStr

from muse.brave_search import BraveSearchProvider
from muse.live_search_config import (
    BraveSearchCredentials,
    LiveSearchRuntime,
    SearchProviderError,
)
from muse.search import SearchPurpose, SearchQuery


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.raise_for_status_calls = 0

    def raise_for_status(self) -> None:
        self.raise_for_status_calls += 1

    def json(self) -> object:
        return self.payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, object],
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append(
            (
                url,
                {
                    "params": params,
                    "headers": headers,
                    "timeout": timeout,
                },
            )
        )
        return self.response


def _provider(
    http_client: object,
    *,
    runtime: LiveSearchRuntime | None = None,
) -> BraveSearchProvider:
    return BraveSearchProvider(
        credentials=BraveSearchCredentials(api_key=SecretStr("brave-secret")),
        http_client=http_client,
        runtime=runtime or LiveSearchRuntime(),
    )


def _query(*, limit: int = 3) -> SearchQuery:
    return SearchQuery(
        text="Reversible team decisions",
        purpose=SearchPurpose.EVIDENCE,
        limit=limit,
        freshness_bucket="recent",
        domain_hints=("example.com",),
    )


def test_brave_search_maps_web_results_and_sanitizes_trace() -> None:
    response_payload = {
        "web": {
            "results": [
                {
                    "title": "Decision gardens",
                    "url": "https://example.com/decision-gardens",
                    "description": "Teams use reversible claims.",
                    "extra": {"raw": "not traced"},
                }
            ]
        }
    }
    fake_response = FakeResponse(response_payload)
    client = FakeHttpClient(fake_response)
    provider = _provider(
        client,
        runtime=LiveSearchRuntime(timeout_seconds=3.5, max_results=2),
    )
    query = _query(limit=3)

    search_response = provider.search(query)

    assert client.calls == [
        (
            "https://api.search.brave.com/res/v1/web/search",
            {
                "params": {
                    "q": "Reversible team decisions",
                    "count": 2,
                    "search_lang": "en",
                },
                "headers": {"X-Subscription-Token": "brave-secret"},
                "timeout": 3.5,
            },
        )
    ]
    assert fake_response.raise_for_status_calls == 1
    assert provider.name == "brave"
    assert provider.version.startswith("brave-search-")
    assert provider.quote_search(query).max_cost_usd == 0.0
    assert search_response.provider_name == "brave"
    assert search_response.usage.result_count == 1
    assert search_response.usage.cost_usd == 0.0

    result = search_response.results[0]
    assert result.provider == "brave"
    assert result.rank == 1
    assert result.title == "Decision gardens"
    assert str(result.url) == "https://example.com/decision-gardens"
    assert result.snippet == "Teams use reversible claims."
    assert result.bounded_excerpt == "Teams use reversible claims."
    assert result.retrieved_at.tzinfo is not None

    request_trace = json.loads(search_response.trace.request_json)
    response_trace = json.loads(search_response.trace.response_json)
    assert request_trace == {
        "operation": "search",
        "provider": "brave",
        "provider_version": provider.version,
        "search": {
            "normalized_text": "reversible team decisions",
            "purpose": "evidence",
            "limit": 3,
            "effective_limit": 2,
            "freshness_bucket": "recent",
            "domain_hints": ["example.com"],
        },
    }
    assert response_trace == {
        "operation": "search",
        "provider": "brave",
        "source_ids": [result.source_id],
        "result_count": 1,
        "skipped_count": 0,
    }
    trace_text = search_response.trace.request_json + search_response.trace.response_json
    assert "brave-secret" not in trace_text
    assert "headers" not in trace_text
    assert "raw" not in trace_text
    assert "Decision gardens" not in trace_text


def test_brave_search_skips_malformed_results_and_tracks_skipped_count() -> None:
    provider = _provider(
        FakeHttpClient(
            FakeResponse(
                {
                    "web": {
                        "results": [
                            {"title": "Missing URL", "description": "snippet"},
                            {
                                "title": "Valid",
                                "url": "https://example.com/valid",
                                "description": "snippet",
                            },
                            {"url": "https://example.com/missing-title"},
                            {
                                "title": "Missing snippet",
                                "url": "https://example.com/missing-snippet",
                            },
                        ]
                    }
                }
            )
        )
    )

    response = provider.search(_query())

    assert len(response.results) == 1
    assert response.results[0].title == "Valid"
    assert response.usage.result_count == 1
    assert json.loads(response.trace.response_json)["skipped_count"] == 3


def test_brave_search_bounds_snippets_and_excerpts() -> None:
    long_description = "x" * 200
    provider = _provider(
        FakeHttpClient(
            FakeResponse(
                {
                    "web": {
                        "results": [
                            {
                                "title": "Long source",
                                "url": "https://example.com/long",
                                "description": long_description,
                            }
                        ]
                    }
                }
            )
        ),
        runtime=LiveSearchRuntime(snippet_chars=80),
    )

    response = provider.search(_query(limit=1))

    assert response.results[0].snippet == "x" * 80
    assert response.results[0].bounded_excerpt == "x" * 80


def test_brave_search_uses_stable_deterministic_source_ids() -> None:
    client = FakeHttpClient(
        FakeResponse(
            {
                "web": {
                    "results": [
                        {
                            "title": "Stable source",
                            "url": "https://example.com/stable",
                            "description": "snippet",
                        }
                    ]
                }
            }
        )
    )
    provider = _provider(client)

    first = provider.search(_query(limit=1))
    second = provider.search(_query(limit=1))

    expected = "brave-" + hashlib.sha256(
        b"https://example.com/stable"
    ).hexdigest()[:16]
    assert first.results[0].source_id == expected
    assert second.results[0].source_id == expected


def test_brave_search_sanitizes_provider_errors_comprehensively() -> None:
    class RaisingHttpClient:
        def get(
            self,
            url: str,
            *,
            params: dict[str, object],
            headers: dict[str, str],
            timeout: float,
        ) -> object:
            raise RuntimeError("upstream failure with brave-secret")

    provider = _provider(RaisingHttpClient())

    with pytest.raises(SearchProviderError) as exc_info:
        provider.search(_query(limit=1))

    error = exc_info.value
    assert error.provider == "brave"
    assert error.category == "search_error"
    assert "brave-secret" not in str(error)
    assert "brave-secret" not in repr(error)
    assert "brave-secret" not in repr(error.args)
    assert "brave-secret" not in error.message
    assert "brave-secret" not in repr(error.__dict__)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_brave_search_lazy_default_client_reports_sanitized_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "httpx":
            raise ImportError("missing httpx with brave-secret")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    provider = BraveSearchProvider(
        credentials=BraveSearchCredentials(api_key=SecretStr("brave-secret")),
    )

    with pytest.raises(SearchProviderError) as exc_info:
        provider.search(_query(limit=1))

    error = exc_info.value
    assert error.provider == "brave"
    assert error.category == "configuration_error"
    assert "httpx" in str(error)
    assert "brave-secret" not in str(error)
    assert "brave-secret" not in repr(error)
    assert "brave-secret" not in repr(error.args)
    assert "brave-secret" not in repr(error.__dict__)
    assert error.__cause__ is None
    assert error.__context__ is None
