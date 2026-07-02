# Search and Novelty Spine Design

## 1. Purpose

Slice 2B-A adds the provider-neutral search, inspiration, provenance, and novelty
spine for the Muse without requiring live search providers. The slice
uses deterministic or mocked search adapters first so branch isolation, source
handling, novelty math, anti-copying behavior, traces, and the `compare` CLI can be
tested without network cost or provider flakiness.

This slice tests a narrower claim than the full Milestone 2 search system:

> The engine can incorporate source-derived abstractions and prior-art evidence while
> preserving search-isolated branches, truthful provenance, and conservative novelty
> estimates.

2B-A does not claim global originality. It reports provisional originality and
source-risk estimates under bounded mocked or deterministic search evidence.

## 2. Scope

### Included

- Provider-neutral search contracts.
- Deterministic and mocked search provider implementations for tests and CLI demos.
- Search query and result models with provenance.
- Search cache with stable keys and traceable cache hits.
- Source abstraction models that exclude raw retrieved content from creative prompts.
- Inspiration branch support alongside independent branches.
- Prior-art checking for finalists using mocked search evidence.
- Layered novelty and source-similarity risk scoring.
- Anti-copying classification or rejection behavior.
- `compare` CLI using no-network providers.
- Research and private trace handling for search, sources, abstractions, and novelty.
- Unit, pipeline, trace, and CLI tests that make no live search calls.

### Excluded

- Real Exa, Brave, or OpenAI web-search adapters.
- Live search smoke tests.
- Human calibration, reviewer packets, and weight fitting.
- Claims that provisional novelty scores predict human originality judgments.
- Production persistence or hosted cache infrastructure.

## 3. Architecture

2B-A extends the current provider-neutral engine with search and novelty components
that can later receive live Exa, Brave, or OpenAI web-search adapters without changing
core orchestration.

### Components

#### Search Contracts

`search.py` defines provider-neutral types and protocols:

- `SearchPurpose`: `inspiration` or `prior_art`.
- `SearchQuery`: normalized query text, purpose, result limit, freshness bucket, and
  optional domain hints.
- `SearchResult`: source identifier, title, URL, provider, rank, snippet, bounded
  excerpt, retrieval metadata, content hash, and provider usage metadata.
- `SearchProvider`: quotes and executes searches through `OperationQuote` and
  `MeteredResponse`.

Provider-specific response objects never enter core orchestration, traces, novelty
models, or candidate genomes.

#### Search Cache

`search_cache.py` stores deterministic cache entries keyed by:

- normalized query text,
- provider,
- search purpose,
- result limit,
- freshness bucket,
- provider parameters that affect returned results.

Cache hits preserve original retrieval metadata and record the cache-hit time. Cache
freshness is evidence metadata, not proof that prior-art coverage is current.

#### Inspiration Abstraction

`inspiration.py` turns `SearchResult` records into `SourceAbstraction` records:

- source identifier,
- transferable mechanism,
- constraints,
- tensions or contradictions,
- causal relationships,
- domain context,
- confidence,
- safe paraphrased principle.

Creative prompts receive only abstractions and paraphrased principles. Raw snippets,
bounded excerpts, titles, and URLs are retained for trace and later similarity checks,
but are treated as untrusted data.

#### Novelty Engine

`novelty.py` computes provisional evidence dimensions:

- peer distance,
- obvious-baseline distance,
- source similarity risk,
- prior-art distance,
- branch isolation confidence,
- search coverage confidence,
- copying classification.

The first implementation may use deterministic lexical similarity and injected
no-network embedding providers. It must keep the scoring interface ready for
embedding-backed distance when live embeddings are deliberately enabled in a later
slice or by an explicit caller-provided test double.

#### Search-Aware Orchestration

The orchestration layer creates two branch classes:

- independent branches, which receive no search material before finalist prior-art
  checking;
- inspired branches, which receive only validated source abstractions.

At least half of generated seed branches must be independent whenever inspired search
is enabled. The trace must prove which branch class each candidate belongs to and which
source abstractions, if any, it inherited.

#### Compare CLI

`compare` runs a no-network comparison:

- deterministic baseline,
- search-aware run using mocked search providers,
- summarized finalist differences and novelty/source-risk evidence.

The command is a research workflow, not a benchmark claim. It should be deterministic
for the same inputs and mock fixtures.

## 4. Data Flow

1. Validate task and run configuration.
2. Frame the task through the existing provider contract.
3. Generate independent seeds without any search material.
4. Generate inspiration search queries from the framed task.
5. Retrieve deterministic or mocked search results through `SearchProvider`.
6. Cache results and record whether each result came from provider execution or cache.
7. Convert search results into `SourceAbstraction` records.
8. Generate inspired seeds using only abstraction text and abstraction identifiers.
9. Embed or otherwise compare candidates, peers, baseline, and abstractions.
10. Compute novelty dimensions and source-similarity risk.
11. Run prior-art search for finalists only.
12. Classify candidates as independent, inspired, synthesized, adapted, or
    likely-copying.
13. Reject candidates whose source-similarity risk exceeds the configured rejection
    threshold when rejection mode is enabled; otherwise mark them high risk.
14. Save a trace containing source provenance, abstraction inheritance, search usage,
    cache events, novelty evidence, and errors.

## 5. Branch Isolation Requirements

Independent branches must not receive:

- search queries,
- source IDs,
- source URLs,
- snippets,
- bounded excerpts,
- raw retrieved content,
- source abstractions,
- source-derived principles.

They may be checked against prior-art sources only after finalist selection. The trace
must make this auditable by recording branch class and inherited abstraction IDs on each
candidate.

Inspired branches may receive:

- validated abstraction IDs,
- paraphrased transferable principles,
- confidence and domain labels.

They must not receive raw source text or provider-specific result payloads.

## 6. Novelty and Anti-Copying Behavior

Novelty scoring is provisional and conservative. 2B-A reports evidence, not objective
originality.

### Dimensions

- `peer_distance`: how different a candidate is from generated peers.
- `baseline_distance`: how different it is from the framed obvious solution.
- `source_similarity_risk`: how close it is to source abstractions or prior-art
  results.
- `prior_art_distance`: distance from mocked prior-art evidence.
- `coverage_confidence`: confidence based on result count, provider status, cache
  freshness, and prior-art success.
- `branch_isolation_confidence`: high only when branch provenance proves no premature
  search inheritance.

### Classification

Candidates receive one source relationship:

- `independent`,
- `inspired`,
- `synthesized`,
- `adapted`,
- `likely_copying`.

Only likely-copying causes automatic rejection when rejection mode is enabled. Low
novelty alone does not reject a useful candidate.

## 7. Failure Behavior

- Inspiration search failure disables inspired branches and preserves independent
  branches.
- Prior-art failure lowers coverage confidence and must never increase originality.
- Search cache failure falls back to provider execution when allowed; otherwise search
  is marked unavailable.
- Source abstraction validation failure drops the affected source and records a
  source-level error.
- Novelty scoring failure preserves candidates and records missing novelty evidence.
- Provider quote, validation, and metering failures follow the existing budget and
  spend-accounting rules.
- No failure may silently produce high-confidence originality.

## 8. Privacy and Security

Search results are untrusted input.

Research traces may store:

- search queries,
- source URLs,
- source titles,
- bounded snippets or excerpts,
- content hashes,
- abstractions,
- novelty evidence,
- provider and cache metadata.

Private traces must:

- hash or redact snippets and excerpts,
- preserve source URLs only when privacy configuration allows them,
- preserve source IDs, hashes, provider names, cache events, and usage metadata,
- redact secret-shaped text inside search results and provider errors.

Prompt construction must treat all retrieved text as data. Source content cannot
override system, developer, or orchestration instructions.

## 9. CLI

2B-A adds:

```powershell
muse compare "task description" --budget-usd 0.10 --trace-dir .traces
```

Initial `compare` behavior:

- runs the deterministic baseline;
- runs a search-aware no-network pipeline using mocked search fixtures;
- writes traces for both conditions;
- prints finalist counts, stopped reasons, novelty/source-risk summaries, and trace
  paths;
- exits `0` when both runs complete, `1` for provider/runtime failures, and `2` for
  invalid command input or missing fixture configuration.

The command must not perform live Exa, Brave, OpenAI web-search, or paid OpenAI model
calls in 2B-A.

## 10. Testing

### Unit Tests

- Search query validation and normalization.
- Search result validation and provenance.
- Cache key stability, cache hits, cache misses, and freshness metadata.
- Source abstraction validation.
- Novelty dimension math and confidence adjustment.
- Source-similarity risk thresholds.
- Private and research trace sanitization for source text.

### Pipeline Tests

- At least 50 percent independent branches when inspired branches are enabled.
- Independent branches have no source inheritance before prior-art checks.
- Inspired branches inherit only abstraction IDs and safe principles.
- Inspiration search failure preserves independent candidates.
- Prior-art failure lowers confidence.
- High similarity triggers likely-copying classification or rejection.
- Prompt-injection text in retrieved content cannot enter creative instructions.

### CLI Tests

- `compare` runs without network credentials.
- `compare` writes separate traces for baseline and search-aware runs.
- `compare` reports novelty and source-risk summaries.
- Invalid fixture/configuration input exits `2`.

## 11. Implementation Slices After This Spec

The implementation plan should keep 2B-A small enough to review:

1. Search models and contracts.
2. Cache and deterministic mocked search provider.
3. Source abstraction and provenance models.
4. Novelty and source-risk scoring.
5. Search-aware branch allocation and trace inheritance.
6. Finalist prior-art check and anti-copying behavior.
7. `compare` CLI and documentation.
8. Final privacy, isolation, and no-network review.

Live Exa, Brave, and OpenAI web-search adapters should be a follow-up slice after the
2B-A spine is merged.

## 12. Success Criteria

2B-A is complete when:

- normal tests make no network calls;
- `compare` works without live credentials;
- search contracts are provider-neutral;
- cache keys are deterministic and traceable;
- inspired branches receive only abstractions;
- at least half of seed branches remain search-isolated;
- finalist prior-art checks can mark or reject likely-copying candidates;
- traces prove provenance and branch isolation;
- private traces do not leak raw source text or secret-shaped strings;
- novelty output is clearly labeled as provisional and evidence-limited.
