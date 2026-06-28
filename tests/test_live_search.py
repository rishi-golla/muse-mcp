from __future__ import annotations

import os

import pytest
from pydantic import SecretStr

from creativity_layer.brave_search import BraveSearchProvider
from creativity_layer.exa_search import ExaSearchProvider
from creativity_layer.live_search_config import (
    BraveSearchCredentials,
    ExaSearchCredentials,
    LiveSearchRuntime,
    OpenAIWebSearchConfig,
)
from creativity_layer.openai_web_search import OpenAIWebSearchProvider
from creativity_layer.search import SearchPurpose, SearchQuery

pytestmark = pytest.mark.live_search


def _skip_unless_live_search_approved(*required_env: str) -> None:
    if os.getenv("CREATIVITY_LAYER_LIVE_SEARCH_APPROVED") != "1":
        pytest.skip("live search smoke tests are not explicitly approved")
    missing = [name for name in required_env if not os.getenv(name)]
    if missing:
        pytest.skip(f"live search environment is missing: {', '.join(missing)}")


def _small_query() -> SearchQuery:
    return SearchQuery(
        text="reversible team decision process",
        purpose=SearchPurpose.EVIDENCE,
        limit=1,
    )


def test_live_exa_search_smoke() -> None:
    _skip_unless_live_search_approved("EXA_API_KEY")
    provider = ExaSearchProvider(
        credentials=ExaSearchCredentials(
            api_key=SecretStr(os.environ["EXA_API_KEY"].strip())
        ),
        runtime=LiveSearchRuntime(max_results=1),
    )

    response = provider.search(_small_query())

    assert len(response.results) <= 1


def test_live_brave_search_smoke() -> None:
    _skip_unless_live_search_approved("BRAVE_SEARCH_API_KEY")
    provider = BraveSearchProvider(
        credentials=BraveSearchCredentials(
            api_key=SecretStr(os.environ["BRAVE_SEARCH_API_KEY"].strip())
        ),
        runtime=LiveSearchRuntime(max_results=1),
    )

    response = provider.search(_small_query())

    assert len(response.results) <= 1


def test_live_openai_web_search_smoke() -> None:
    _skip_unless_live_search_approved("OPENAI_API_KEY", "OPENAI_WEB_SEARCH_MODEL")
    from openai import OpenAI

    provider = OpenAIWebSearchProvider(
        client=OpenAI(),
        config=OpenAIWebSearchConfig(model=os.environ["OPENAI_WEB_SEARCH_MODEL"].strip()),
        runtime=LiveSearchRuntime(max_results=1),
    )

    response = provider.search(_small_query())

    assert len(response.results) <= 1
