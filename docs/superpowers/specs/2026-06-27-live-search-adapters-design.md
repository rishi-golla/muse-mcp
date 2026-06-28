# Live Search Adapters Design

## 1. Purpose

Slice 2B-B connects the merged no-network search and novelty spine to live search
providers without changing the core orchestration contract. The goal is to make Exa,
Brave, and OpenAI web search available as provider-neutral `SearchProvider`
implementations while keeping normal tests deterministic and no-network.

This slice tests a narrower claim than full live search integration:

> The Creativity Layer can call live search providers through the existing search
> contract, normalize their results into safe internal models, meter usage
> conservatively, and verify the adapters through mocked tests plus opt-in live smoke
> tests.

2B-B does not change novelty scoring weights, automatically route search in the
pipeline, run calibration, or claim that live prior-art coverage is exhaustive.

## 2. Scope

### Included

- Exa search adapter for analogy and novelty-oriented semantic search.
- Brave Search adapter for prior-art and evidence-oriented broad web search.
- OpenAI web-search adapter as fallback and comparison provider.
- Search credential loading from explicit environment variables.
- Provider-neutral response conversion into `SearchResult`, `MeteredSearchUsage`, and
  `SearchProviderResponse`.
- Secret-safe `OperationTrace` payloads with provider, purpose, normalized query,
  result count, source IDs, latency, and estimated cost metadata.
- Mocked unit tests for all adapters.
- Environment-gated live smoke tests for Exa, Brave, and OpenAI web search.
- README documentation for live search setup and no-network defaults.

### Excluded

- Automatic provider routing in `SearchAwareEngine`.
- Live search calls from normal test runs or default `compare`.
- Paid search execution unless a live smoke test is explicitly enabled.
- Search-result clustering, embedding-backed novelty, calibration, or reviewer
  packets.
- Persistent or hosted cache infrastructure.
- Claims that Brave, Exa, or OpenAI web search provide complete prior-art coverage.

## 3. Provider Roles

2B-B maps providers to their strongest initial roles without hard-coding orchestration
policy:

- `ExaSearchProvider`: semantic analogy and novelty discovery.
- `BraveSearchProvider`: broad literal prior-art and evidence search.
- `OpenAIWebSearchProvider`: fallback search and comparison baseline.

Programmatic callers may still pass any provider wherever a `SearchProvider` is
accepted. Purpose-specific routing belongs in a later slice.

## 4. Configuration

Add `src/creativity_layer/live_search_config.py` for live-search credentials and
provider-specific runtime settings. Keep search credentials separate from
`live_config.py` so model credentials and search credentials can evolve independently.

Environment variables:

- `EXA_API_KEY`
- `BRAVE_SEARCH_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_WEB_SEARCH_MODEL`

OpenAI web search must use an explicit model identifier from configuration. Do not use
implicit "latest" aliases in tests or docs.

Credential models must use secret fields where possible and must never serialize secret
values. Missing credentials should fail at construction for live providers and skip
live tests through pytest markers.

## 5. Adapter Contracts

All adapters implement the existing contract:

```python
class SearchProvider(Protocol):
    name: str
    version: str

    def quote_search(self, query: SearchQuery) -> OperationQuote: ...

    def search(self, query: SearchQuery) -> SearchProviderResponse: ...
```

Adapters must accept only `SearchQuery` and return only internal Pydantic models.
Provider-specific response objects and HTTP response objects must not leave adapter
modules.

### SearchResult Mapping

Each provider result maps to:

- `source_id`: stable provider-prefixed deterministic ID.
- `title`: provider title or a bounded fallback.
- `url`: canonical provider URL field.
- `provider`: adapter name.
- `rank`: 1-based rank in the normalized response.
- `snippet`: bounded provider snippet, summary, text, or highlight.
- `bounded_excerpt`: bounded audit excerpt suitable for private trace hashing.
- `retrieved_at`: timezone-aware timestamp from adapter execution time.
- `provider_metadata`: JSON-safe metadata only, excluding secrets and raw response
  payloads.

Adapters must skip malformed results that cannot satisfy `SearchResult` validation
unless every result is malformed. If every result is malformed, return an empty result
set with trace metadata rather than leaking provider objects.

### Usage and Cost

`MeteredSearchUsage` currently records result count and cost. 2B-B should extend it
only if needed for provider-independent facts such as:

- `search_count`
- `estimated_cost_usd`

The slice may keep cost as `0.0` for mocked tests and live smoke tests when provider
pricing is not configured, but traces must make estimated-vs-reported behavior clear.
Do not pretend a provider-reported bill exists when it does not.

## 6. Provider Behavior

### Exa

Use Exa for semantic source discovery for `SearchPurpose.ANALOGY` and
`SearchPurpose.NOVELTY`. The adapter should request bounded contents or highlights
when available and prefer highlights or summaries for snippets. It should limit
results to `SearchQuery.limit` and pass a provider-supported query string based on
`SearchQuery.text`.

Exa adapter tests should mock the SDK/client boundary and verify:

- request shape uses normalized query semantics without mutating user text;
- returned highlights or summaries become bounded snippets;
- source IDs are deterministic;
- malformed results are skipped;
- credentials do not appear in traces or exceptions.

### Brave

Use Brave Web Search for literal prior-art and evidence search. The adapter should call
the web search endpoint through an injectable HTTP client, pass the API key only in
headers, and normalize web results into `SearchResult`.

Brave adapter tests should mock HTTP responses and verify:

- request query and result count mapping;
- `title`, `url`, and `description` normalization;
- HTTP errors become structured provider errors or empty provider responses according
  to the existing project error pattern;
- API keys are never present in traces, metadata, or raised messages.

### OpenAI Web Search

Use the OpenAI Responses API web-search tool as a fallback provider. The adapter should
be explicit about model ID and search tool use. It should extract URL citations or
structured search results where available and fall back to bounded response text only
when a URL-bearing source is present.

OpenAI web-search tests should mock the Responses client boundary and verify:

- explicit configured model ID is used;
- web-search tool is included;
- citations/results map to `SearchResult`;
- no raw OpenAI response object enters core models;
- API keys and request headers are excluded from traces.

## 7. Error Handling

Adapters should fail closed and preserve search safety:

- Missing credentials fail during provider construction.
- Quoting is conservative and must not authorize unexpected live calls.
- Provider/network failures raise `SearchProviderError` with a sanitized message.
  2B-B does not add tolerant fallback mode; fallback is a later router concern.
- Malformed provider payloads do not leak raw payloads into exceptions.
- Timeouts use configured client behavior; no adapter should hang indefinitely.
- Trace metadata records provider name, purpose, normalized query, result count, and
  failure category without secrets.

The slice should favor explicit adapter errors over silent fallback. A later router can
decide when to try fallback providers.

## 8. Privacy and Security

Search provider responses are untrusted input. Adapters must:

- bound snippets and excerpts before constructing `SearchResult`;
- reject or strip provider metadata that is not JSON-safe;
- exclude credentials, authorization headers, cookies, raw request objects, and raw
  response objects from models and traces;
- preserve enough source provenance for audit and private trace hashing;
- never pass raw source snippets into creative prompts.

The existing private trace behavior for `snippet`, `excerpt`, and `bounded_excerpt`
must continue to apply to all live provider results.

## 9. Testing

Normal test runs stay no-network:

```powershell
python -m pytest -m "not live_search and not live_openai"
```

Add a `live_search` pytest marker for opt-in provider smoke tests. Live tests should
skip unless the required provider-specific environment variables are present.

Required mocked tests:

- credentials and secret serialization;
- Exa request/response mapping;
- Brave request/response mapping;
- OpenAI web-search request/response mapping;
- trace secret safety;
- malformed result handling;
- quote/search usage metadata.

Required live smoke tests:

- Exa returns at most one result for a harmless query when `EXA_API_KEY` is set and
  live search tests are explicitly enabled.
- Brave returns at most one result for a harmless query when `BRAVE_SEARCH_API_KEY` is
  set and live search tests are explicitly enabled.
- OpenAI web search returns at most one source-bearing result when `OPENAI_API_KEY` and
  `OPENAI_WEB_SEARCH_MODEL` are set and live search tests are explicitly enabled.

Live tests must use tiny limits, conservative timeouts, and clear markers so they never
run by accident in normal CI.

## 10. Provider Documentation Sources

Implementation should follow the provider documentation current at plan time:

- Exa Search API and Python SDK documentation for `search` and returned contents.
- Brave Search API documentation for the Web Search endpoint and
  `X-Subscription-Token` authentication.
- OpenAI Responses API web-search tool documentation for tool configuration,
  response shape, and citations.

## 11. CLI and Docs

2B-B should not make default `compare` live. README should document:

- required environment variables;
- no-network default behavior;
- how to run provider-specific live smoke tests;
- that live search is an adapter slice, not calibrated originality.

If a CLI flag is added, it should be an explicit smoke-test or provider-check command,
not a change to default `compare` behavior.

## 12. Success Criteria

2B-B is complete when:

- Exa, Brave, and OpenAI web-search adapters implement `SearchProvider`.
- Mocked tests prove request mapping, response normalization, trace safety, and error
  behavior.
- Normal tests make no network calls.
- Live smoke tests are skipped by default and run only with explicit credentials and
  markers.
- Credentials and secret-like values cannot enter traces, exceptions, or
  `SearchResult.provider_metadata`.
- README documents setup and no-network defaults.
- The adapter boundary is ready for a later router/integration slice.
