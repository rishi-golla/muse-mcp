# Live Search Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Exa, Brave, and OpenAI web-search adapters behind the existing provider-neutral search contract, with mocked tests by default and opt-in live smoke tests.

**Architecture:** Keep core orchestration unchanged. Add a live-search config/error module and one adapter module per provider; each adapter accepts `SearchQuery`, returns `SearchProviderResponse`, bounds untrusted text, and keeps secrets out of traces.

**Tech Stack:** Python 3.12, Pydantic 2, httpx, OpenAI Python SDK, pytest, Ruff

---

## File Map

```text
src/muse/live_search_config.py       Search credentials, runtime config, adapter errors
src/muse/exa_search.py               Exa SearchProvider adapter
src/muse/brave_search.py             Brave SearchProvider adapter
src/muse/openai_web_search.py        OpenAI web-search SearchProvider adapter
src/muse/search.py                   Optional usage metadata extension only if tests require it
pyproject.toml                                   Add live_search pytest marker
README.md                                       Document live search setup and no-network defaults
tests/test_live_search_config.py                 Config/error tests
tests/test_exa_search.py                         Mocked Exa adapter tests
tests/test_brave_search.py                       Mocked Brave adapter tests
tests/test_openai_web_search.py                  Mocked OpenAI web-search tests
tests/test_live_search.py                        Env-gated provider smoke tests
tests/test_final_review.py                       No-network and secret-safety regression checks
```

## Shared Implementation Rules

- Do not change `SearchAwareEngine` or default `compare`.
- Do not make normal tests perform network calls.
- Use dependency injection for SDK/HTTP clients so mocked tests do not patch globals.
- Never include API keys, auth headers, cookies, raw request objects, or raw response objects in models, traces, exceptions, or provider metadata.
- Use `SearchProviderError` for provider/network failures; messages must be sanitized and should include provider and category, not raw payloads.
- Bound `snippet` and `bounded_excerpt` to at most 500 characters before constructing `SearchResult`.
- Stable source IDs should be `provider-prefix + sha256(url-or-title)[:16]`.

## Task 1: Live Search Config and Error Boundary

**Files:**
- Create: `src/muse/live_search_config.py`
- Create: `tests/test_live_search_config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing config tests**

```python
# tests/test_live_search_config.py
import pytest
from pydantic import SecretStr, ValidationError

from muse.live_search_config import (
    BraveSearchCredentials,
    ExaSearchCredentials,
    LiveSearchRuntime,
    OpenAIWebSearchConfig,
    SearchProviderError,
)


def test_exa_credentials_from_environment_strip_and_hide_secret(monkeypatch) -> None:
    monkeypatch.setenv("EXA_API_KEY", " exa-secret ")

    credentials = ExaSearchCredentials.from_environment()

    assert credentials.api_key.get_secret_value() == "exa-secret"
    assert "exa-secret" not in credentials.model_dump_json()


def test_brave_credentials_reject_missing_environment(monkeypatch) -> None:
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)

    with pytest.raises(ValueError, match="BRAVE_SEARCH_API_KEY"):
        BraveSearchCredentials.from_environment()


def test_openai_web_search_config_requires_explicit_model() -> None:
    with pytest.raises(ValidationError):
        OpenAIWebSearchConfig(model="")


def test_runtime_defaults_are_conservative() -> None:
    runtime = LiveSearchRuntime()

    assert runtime.timeout_seconds == 10.0
    assert runtime.max_results == 10
    assert runtime.snippet_chars == 500


def test_search_provider_error_redacts_secret_values() -> None:
    error = SearchProviderError(
        provider="exa",
        category="network_error",
        message="request failed with exa-secret",
        secret_values=("exa-secret",),
    )

    assert "exa-secret" not in str(error)
    assert "[REDACTED]" in str(error)
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_live_search_config.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task1-red
```

Expected: FAIL because `muse.live_search_config` does not exist.

- [ ] **Step 3: Implement config/error module and marker**

```python
# src/muse/live_search_config.py
from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic import Field, SecretStr

from muse.models import FrozenModel, RequiredText
from muse.privacy import REDACTED


class ExaSearchCredentials(FrozenModel):
    api_key: SecretStr

    @classmethod
    def from_environment(cls) -> ExaSearchCredentials:
        return cls(api_key=_secret_from_env("EXA_API_KEY"))


class BraveSearchCredentials(FrozenModel):
    api_key: SecretStr

    @classmethod
    def from_environment(cls) -> BraveSearchCredentials:
        return cls(api_key=_secret_from_env("BRAVE_SEARCH_API_KEY"))


class OpenAIWebSearchConfig(FrozenModel):
    model: RequiredText

    @classmethod
    def from_environment(cls) -> OpenAIWebSearchConfig:
        value = os.getenv("OPENAI_WEB_SEARCH_MODEL")
        if value is None or not value.strip():
            raise ValueError("OPENAI_WEB_SEARCH_MODEL is required")
        return cls(model=value.strip())


class LiveSearchRuntime(FrozenModel):
    timeout_seconds: float = Field(default=10.0, strict=True, gt=0)
    max_results: int = Field(default=10, strict=True, ge=1, le=10)
    snippet_chars: int = Field(default=500, strict=True, ge=80, le=2000)


@dataclass(frozen=True)
class SearchProviderError(RuntimeError):
    provider: str
    category: str
    message: str
    secret_values: tuple[str, ...] = ()

    def __str__(self) -> str:
        sanitized = self.message
        for secret in sorted((item for item in self.secret_values if item), key=len, reverse=True):
            sanitized = sanitized.replace(secret, REDACTED)
        return f"{self.provider} {self.category}: {sanitized}"


def _secret_from_env(name: str) -> SecretStr:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")
    return SecretStr(value.strip())
```

Add marker to `pyproject.toml`:

```toml
markers = [
  "live_openai: incurs a bounded real OpenAI API request",
  "live_search: incurs bounded real search provider requests",
]
```

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_live_search_config.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task1-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/muse/live_search_config.py tests/test_live_search_config.py pyproject.toml
git commit -m "feat: add live search configuration"
```

## Task 2: Exa Search Adapter

**Files:**
- Create: `src/muse/exa_search.py`
- Create: `tests/test_exa_search.py`

- [ ] **Step 1: Write failing Exa adapter tests**

```python
# tests/test_exa_search.py
from pydantic import SecretStr

from muse.exa_search import ExaSearchProvider
from muse.live_search_config import ExaSearchCredentials, LiveSearchRuntime
from muse.search import SearchPurpose, SearchQuery


class FakeExaClient:
    def __init__(self) -> None:
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return {
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


def test_exa_search_maps_highlights_to_search_results() -> None:
    client = FakeExaClient()
    provider = ExaSearchProvider(
        credentials=ExaSearchCredentials(api_key=SecretStr("exa-secret")),
        client=client,
        runtime=LiveSearchRuntime(),
    )
    query = SearchQuery(text="Reversible team decisions", purpose=SearchPurpose.NOVELTY, limit=1)

    response = provider.search(query)

    assert client.calls[0][0] == "Reversible team decisions"
    assert client.calls[0][1]["num_results"] == 1
    assert response.provider_name == "exa"
    assert response.results[0].provider == "exa"
    assert response.results[0].snippet == "Teams use reversible claims."
    assert "exa-secret" not in response.trace.request_json


def test_exa_search_skips_malformed_results() -> None:
    class MalformedClient:
        def search(self, query, **kwargs):
            return {"results": [{"title": "missing url"}]}

    provider = ExaSearchProvider(
        credentials=ExaSearchCredentials(api_key=SecretStr("exa-secret")),
        client=MalformedClient(),
        runtime=LiveSearchRuntime(),
    )

    response = provider.search(
        SearchQuery(text="Reversible team decisions", purpose=SearchPurpose.ANALOGY, limit=1)
    )

    assert response.results == ()
    assert response.usage.result_count == 0
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exa_search.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task2-red
```

Expected: FAIL because `muse.exa_search` does not exist.

- [ ] **Step 3: Implement Exa adapter**

Implement `ExaSearchProvider` with injected `client`, `quote_search()`, `search()`,
bounded snippets, deterministic source IDs, safe traces, and `SearchProviderError` on
client exceptions. The client call must be:

```python
self.client.search(
    query.text,
    num_results=min(query.limit, self.runtime.max_results),
    contents={"highlights": True, "text": True},
)
```

Normalize dict-like results and object-like results by reading `title`, `url`,
`highlights`, `summary`, and `text` via helper functions.

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exa_search.py tests/test_live_search_config.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task2-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/muse/exa_search.py tests/test_exa_search.py
git commit -m "feat: add Exa search adapter"
```

## Task 3: Brave Search Adapter

**Files:**
- Create: `src/muse/brave_search.py`
- Create: `tests/test_brave_search.py`

- [ ] **Step 1: Write failing Brave tests**

```python
# tests/test_brave_search.py
from pydantic import SecretStr

from muse.brave_search import BraveSearchProvider
from muse.live_search_config import BraveSearchCredentials, LiveSearchRuntime
from muse.search import SearchPurpose, SearchQuery


class FakeResponse:
    def __init__(self, payload, status_code=200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("HTTP error with secret brave-secret")

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append((url, params, headers, timeout))
        return self.response


def test_brave_search_maps_web_results_without_leaking_token() -> None:
    http = FakeHttpClient(
        FakeResponse(
            {"web": {"results": [{"title": "Decision gardens", "url": "https://example.com/d", "description": "Reversible claims."}]}}
        )
    )
    provider = BraveSearchProvider(
        credentials=BraveSearchCredentials(api_key=SecretStr("brave-secret")),
        http_client=http,
        runtime=LiveSearchRuntime(),
    )

    response = provider.search(
        SearchQuery(text="Reversible team decisions", purpose=SearchPurpose.PRIOR_ART, limit=1)
    )

    assert http.calls[0][0] == "https://api.search.brave.com/res/v1/web/search"
    assert http.calls[0][1]["q"] == "Reversible team decisions"
    assert http.calls[0][2]["X-Subscription-Token"] == "brave-secret"
    assert response.results[0].snippet == "Reversible claims."
    assert "brave-secret" not in response.trace.request_json


def test_brave_search_provider_errors_are_sanitized() -> None:
    provider = BraveSearchProvider(
        credentials=BraveSearchCredentials(api_key=SecretStr("brave-secret")),
        http_client=FakeHttpClient(FakeResponse({}, status_code=401)),
        runtime=LiveSearchRuntime(),
    )

    try:
        provider.search(SearchQuery(text="x", purpose=SearchPurpose.EVIDENCE, limit=1))
    except Exception as error:
        assert "brave-secret" not in str(error)
        assert "[REDACTED]" in str(error)
    else:
        raise AssertionError("expected provider error")
```

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_brave_search.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task3-red
```

- [ ] **Step 3: Implement Brave adapter**

Use injected `http_client.get()`, endpoint
`https://api.search.brave.com/res/v1/web/search`, `X-Subscription-Token`, params
`q`, `count`, and `search_lang="en"`. Convert `payload["web"]["results"]` into
validated `SearchResult` values and sanitize errors with `SearchProviderError`.

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_brave_search.py tests/test_live_search_config.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task3-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/muse/brave_search.py tests/test_brave_search.py
git commit -m "feat: add Brave search adapter"
```

## Task 4: OpenAI Web Search Adapter

**Files:**
- Create: `src/muse/openai_web_search.py`
- Create: `tests/test_openai_web_search.py`

- [ ] **Step 1: Write failing OpenAI web-search tests**

```python
# tests/test_openai_web_search.py
from muse.live_search_config import OpenAIWebSearchConfig, LiveSearchRuntime
from muse.openai_web_search import OpenAIWebSearchProvider
from muse.search import SearchPurpose, SearchQuery


class FakeResponses:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Decision gardens source.",
                            "annotations": [
                                {"type": "url_citation", "title": "Decision gardens", "url": "https://example.com/d"}
                            ],
                        }
                    ]
                }
            ]
        }


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_openai_web_search_uses_explicit_model_and_maps_citations() -> None:
    client = FakeOpenAIClient()
    provider = OpenAIWebSearchProvider(
        client=client,
        config=OpenAIWebSearchConfig(model="gpt-test-search"),
        runtime=LiveSearchRuntime(),
    )

    response = provider.search(
        SearchQuery(text="Reversible team decisions", purpose=SearchPurpose.EVIDENCE, limit=1)
    )

    call = client.responses.calls[0]
    assert call["model"] == "gpt-test-search"
    assert {"type": "web_search_preview"} in call["tools"]
    assert response.provider_name == "openai-web-search"
    assert response.results[0].url == "https://example.com/d"
    assert "OPENAI_API_KEY" not in response.trace.request_json
```

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_web_search.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task4-red
```

- [ ] **Step 3: Implement OpenAI web-search adapter**

Call:

```python
self.client.responses.create(
    model=self.config.model,
    input=query.text,
    tools=[{"type": "web_search_preview"}],
)
```

Extract `url_citation` annotations from dict-like or object-like responses. Build
`SearchResult` from title/url/text, skip citations without URLs, and use sanitized
`SearchProviderError` for client failures.

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_web_search.py tests/test_live_search_config.py -v -p no:cacheprovider --basetemp=.pytest-tmp-task4-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/muse/openai_web_search.py tests/test_openai_web_search.py
git commit -m "feat: add OpenAI web search adapter"
```

## Task 5: Live Smoke Tests, Docs, and Final No-Network Checks

**Files:**
- Create: `tests/test_live_search.py`
- Modify: `README.md`
- Modify: `tests/test_final_review.py`

- [ ] **Step 1: Write live-gated and final-review tests**

```python
# tests/test_live_search.py
import os

import pytest
from openai import OpenAI

from muse.brave_search import BraveSearchProvider
from muse.exa_search import ExaSearchProvider
from muse.live_search_config import (
    BraveSearchCredentials,
    ExaSearchCredentials,
    LiveSearchRuntime,
    OpenAIWebSearchConfig,
)
from muse.openai_web_search import OpenAIWebSearchProvider
from muse.search import SearchPurpose, SearchQuery

pytestmark = pytest.mark.live_search


def _approved() -> bool:
    return os.getenv("MUSE_LIVE_SEARCH_APPROVED") == "1"


def test_live_exa_search_smoke() -> None:
    if not _approved() or not os.getenv("EXA_API_KEY"):
        pytest.skip("live Exa search is not configured and approved")
    provider = ExaSearchProvider(credentials=ExaSearchCredentials.from_environment())
    response = provider.search(SearchQuery(text="reversible decisions", purpose=SearchPurpose.NOVELTY, limit=1))
    assert len(response.results) <= 1


def test_live_brave_search_smoke() -> None:
    if not _approved() or not os.getenv("BRAVE_SEARCH_API_KEY"):
        pytest.skip("live Brave search is not configured and approved")
    provider = BraveSearchProvider(credentials=BraveSearchCredentials.from_environment())
    response = provider.search(SearchQuery(text="reversible decisions", purpose=SearchPurpose.PRIOR_ART, limit=1))
    assert len(response.results) <= 1


def test_live_openai_web_search_smoke() -> None:
    required = ("OPENAI_API_KEY", "OPENAI_WEB_SEARCH_MODEL")
    if not _approved() or any(not os.getenv(name) for name in required):
        pytest.skip("live OpenAI web search is not configured and approved")
    provider = OpenAIWebSearchProvider(
        client=OpenAI(),
        config=OpenAIWebSearchConfig.from_environment(),
        runtime=LiveSearchRuntime(timeout_seconds=10.0),
    )
    response = provider.search(SearchQuery(text="reversible decisions", purpose=SearchPurpose.EVIDENCE, limit=1))
    assert len(response.results) <= 1
```

Add to `tests/test_final_review.py`:

```python
def test_normal_test_markers_exclude_live_search_by_default() -> None:
    from pathlib import Path

    assert "live_search" in Path("pyproject.toml").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run RED if docs/marker missing**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_live_search.py tests/test_final_review.py::test_normal_test_markers_exclude_live_search_by_default -v -p no:cacheprovider --basetemp=.pytest-tmp-task5-red
```

Expected before marker/docs wiring: live tests collect and skip; final review may fail if marker is absent.

- [ ] **Step 3: Update README**

Add a `Live search adapter smoke tests` section documenting:

```markdown
## Live search adapter smoke tests

Normal test runs do not call Exa, Brave, or OpenAI web search. Live search adapter
smoke tests are opt-in:

```powershell
$env:MUSE_LIVE_SEARCH_APPROVED = "1"
$env:EXA_API_KEY = "<exa-api-key>"
$env:BRAVE_SEARCH_API_KEY = "<brave-search-api-key>"
$env:OPENAI_API_KEY = "<openai-api-key>"
$env:OPENAI_WEB_SEARCH_MODEL = "<explicit-web-search-capable-model>"
python -m pytest -m live_search
```

The default `compare` command remains no-network and uses deterministic search
fixtures.
```

- [ ] **Step 4: Run full verification and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not live_openai and not live_search" -q -p no:cacheprovider --basetemp=.pytest-tmp-2bb-final
.\.venv\Scripts\python.exe -m ruff check .
git diff --check
git add tests/test_live_search.py tests/test_final_review.py README.md
git commit -m "test: add live search smoke coverage"
```

## Final Verification

Run before PR:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not live_openai and not live_search" -q --cov=muse --cov-report=term-missing -p no:cacheprovider --basetemp=.pytest-tmp-2bb-final
.\.venv\Scripts\python.exe -m ruff check .
git diff --check origin/main...HEAD
```

Expected: all offline tests pass, live OpenAI and live search tests deselected, Ruff
passes, and diff whitespace check is clean.
