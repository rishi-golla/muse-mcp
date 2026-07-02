# Live Model, Search, and Novelty Milestone Design

## 1. Purpose

Milestone 2 connects the deterministic Muse research spine to live model,
embedding, and search providers. It adds source-aware inspiration, prior-art checking,
layered originality estimation, usage-based cost accounting, and a human-calibration
pilot.

The milestone tests this claim:

> Under a $0.10 default budget, provider-neutral live creative search can produce
> traceable, source-aware ideas whose originality estimates correlate with blinded
> human judgments and whose combined originality and usefulness beats strong prompting
> often enough to justify further research.

This milestone does not claim to measure absolute originality. It estimates originality
relative to the task baseline, generated peers, retrieved inspiration, searchable prior
art, and structural comparisons.

## 2. Scope

### Included

- OpenAI Responses API adapters
- OpenAI economy, strong, and embedding model roles
- Exa semantic inspiration search
- Brave broad prior-art search
- OpenAI web-search fallback and comparison baseline
- Provider-neutral model, embedding, and search contracts
- Search-isolated and inspiration-assisted branches
- Search-result abstraction and source provenance
- Layered novelty and source-similarity scoring
- Usage-based token, search, latency, and cost accounting
- Retry, timeout, rate-limit, circuit-breaker, fallback, and caching behavior
- Research and private trace modes
- `live`, `compare`, and `calibrate` CLI workflows
- A 20-task rubric-validation batch
- Infrastructure for a later 50–100-task calibration pilot

### Excluded

- Anthropic, Gemini, or other additional model integrations
- Eight production-quality domain adapters
- Persistent creative identity or shared lineages
- Hosted services, queues, dashboards, or multi-user accounts
- The full 50–100-task human study
- Claims that originality estimates are objective or exhaustive

## 3. Architecture

Milestone 2 uses provider-neutral pipeline components with OpenAI, Exa, and Brave as
the initial adapters. Provider-specific objects never enter core orchestration,
scoring, or trace models.

### Components

#### OpenAI Model Adapter

Uses the Responses API and structured outputs for:

- Task framing
- Seed generation
- Structural transformations
- Source abstraction
- Consequence simulation
- Structural novelty comparison
- Candidate evaluation
- Final refinement

#### Embedding Adapter

Produces vector representations for:

- Candidate deduplication
- Candidate-to-candidate distance
- Candidate-to-baseline distance
- Candidate-to-source similarity
- Search-result clustering

OpenAI provides the first embedding adapter.

#### Search Router

Routes searches by purpose, coverage requirements, provider availability, and budget:

- Exa for semantic and distant-domain inspiration
- Brave for broad literal prior-art coverage
- OpenAI web search as fallback and benchmark

#### Inspiration Engine

Builds distant-domain queries, retrieves bounded source material, converts it into
transferable abstractions, and preserves provenance without sending raw source content
into creative prompts.

#### Prior-Art Engine

Builds literal and mechanism-focused searches for finalists, retrieves discoverable
existing work, and evaluates semantic and structural overlap.

#### Novelty Engine

Calculates separate novelty dimensions, source-similarity risk, coverage confidence,
and an evidence-backed originality estimate.

#### Live Operation Executor

Handles provider quotes, actual usage, tokens, search calls, retries, timeouts,
rate limits, fallbacks, circuit breakers, cache access, secret redaction, and truthful
trace accounting.

#### Calibration Harness

Creates anonymized pairwise review packets, records human choices and confidence,
measures reviewer agreement, fits provisional originality weights, and evaluates them
on held-out tasks.

## 4. Provider Contracts

The existing provider-neutral engine remains the owner of control flow and budget
decisions. Milestone 2 extends the contracts without introducing OpenAI-specific types
into core modules.

### Model roles

Configuration identifies model roles rather than hard-coded model names:

- `economy`: framing, seed generation, source abstraction, and routine evaluation
- `strong`: difficult transformations, uncertain structural comparisons, and final
  refinement
- `embedding`: semantic similarity and deduplication

Each role maps to a configurable provider and model identifier. Model names, versions,
reasoning settings, output schemas, and pricing-table versions enter traces.

### Search roles

- `inspiration`: Exa by default
- `prior_art`: Brave by default
- `fallback`: OpenAI web search by default

Search providers implement normalized query, result, content, usage, provenance, and
failure models.

### Credentials

CLI credentials load from:

- `OPENAI_API_KEY`
- `EXA_API_KEY`
- `BRAVE_SEARCH_API_KEY`

Programmatic users may supply credentials or fully constructed provider instances.
Credentials, authorization headers, and secret-like values never enter prompts, logs,
traces, exceptions, fixtures, or fingerprints.

## 5. Model Routing and Cost Control

### Budget modes

- Default product target: `$0.10`
- Comparison budget: `$0.50`
- Upper research reference: `$2.00`

These are hard authorization ceilings. Provider quote violations are recorded as
incurred overages and stop further external work.

### Allocation policy

At the default budget, the engine:

1. Reserves capacity for finalist evaluation and prior-art checks.
2. Frames the task and generates a small seed population with the economy model.
3. Deduplicates candidates using embeddings before expensive evaluation.
4. Keeps at least half of seed branches search-isolated.
5. Gives a smaller inspired branch only abstracted distant-domain principles.
6. Uses the strong model only for uncertain structural novelty, difficult
   transformations, or final refinement.
7. Runs prior-art search only for finalists.
8. Stops when recent operations no longer improve the originality-usefulness frontier
   enough to justify their expected cost.

### Accounting

Every external operation records:

- Provider and model
- Provider version where exposed
- Input, output, reasoning, and cached tokens where exposed
- Search calls and result count
- Latency
- Provider-reported usage
- Pricing-table version
- Estimated dollar cost
- Whether cost is estimated or provider-reported
- Quote and actual-usage variance

Providers do not always report final dollar charges. The engine preserves raw usage and
calculates estimated cost using versioned pricing tables so costs can be recalculated.

## 6. Branch Isolation and Inspiration

Each run creates:

- Independent seed branches that never see search material before ideation
- Inspired seed branches that receive only abstracted principles

At least 50 percent of seed branches remain search-isolated. The trace identifies branch
class and every inspiration source inherited by a candidate.

### Inspiration flow

1. Generate several conceptual search queries from the task frame.
2. Route semantic and distant-domain queries to Exa.
3. Retrieve bounded source metadata and content.
4. Treat retrieved content as untrusted data, never as instructions.
5. Extract mechanisms, constraints, tensions, emotional effects, relationships, and
   transferable principles.
6. Store URLs, provider, retrieval time, content hash, bounded audit excerpt, and
   abstraction.
7. Pass only paraphrased abstractions into creative prompts.
8. Retain raw bounded content outside creative prompts for later similarity checks.

### Search isolation test

The trace must prove that independent branches did not inherit search queries, source
content, abstractions, or source identifiers before finalist prior-art checking.

## 7. Prior-Art and Anti-Copying Flow

Prior-art checks run only on finalists.

1. Generate literal queries from candidate wording and distinguishing features.
2. Generate mechanism-focused queries from the idea genome.
3. Route broad searches to Brave.
4. Use OpenAI web search as fallback and comparison baseline.
5. Retrieve bounded source content and metadata.
6. Compare candidate and sources semantically through embeddings.
7. Compare underlying mechanisms through a structured strong-model judgment.
8. Identify closest overlaps, differences, and source coverage limitations.
9. Classify the candidate as independent, inspired, synthesized, adapted, or likely
   copying.
10. Reject or transform candidates whose source-similarity risk exceeds the configured
    copying threshold.

The system never declares that an idea is objectively or globally original.

## 8. Source Abstraction and Provenance

Creative stages do not receive raw web pages or raw search snippets. They receive
validated abstraction models containing:

- Transferable mechanism
- Constraints
- Causal relationships
- Tensions and contradictions
- Emotional or experiential effects
- Domain context
- Confidence
- Source identifiers

Traces retain:

- Source URL
- Search provider
- Retrieval timestamp
- Normalized query
- Content hash
- Bounded excerpt when needed for auditability
- Paraphrased abstractions
- Candidates and transformations that inherited each abstraction

Raw retrieved content is bounded by configuration and is not treated as trusted
instructions.

## 9. Originality and Novelty Scoring

Each candidate receives these independent dimensions:

- Peer distance
- Obvious-baseline distance
- Inspiration distance
- Prior-art distance
- Structural novelty
- Combinational novelty
- Source-similarity risk
- Search-coverage confidence
- Judge agreement

### Provisional originality formula

```text
raw originality =
  15% peer distance
+ 20% baseline distance
+ 25% prior-art distance
+ 30% structural novelty
+ 10% combinational novelty
```

The reported estimate adjusts raw originality using:

- Search-coverage confidence
- Judge agreement
- Likely-copying penalty
- Randomness or incoherence penalty

### Reported result

The result contains:

- Originality estimate from 0 to 100
- Confidence from 0 to 100
- Search coverage: low, medium, or high
- Closest known overlaps
- Structural similarities
- Structural differences
- Evidence and explanation
- Scoring version

Originality remains separate from usefulness, coherence, feasibility, and user fit.
Only likely copying causes automatic rejection. Low originality alone does not.

The provisional weights are versioned and must not be represented as empirically
validated until calibration demonstrates that they predict human judgments.

## 10. Search Caching

Search and bounded content retrieval are cached by:

- Normalized query
- Provider
- Search purpose
- Provider parameters
- Result limit
- Content-retrieval settings
- Retrieval date or configured freshness bucket

Cache entries preserve provenance and expiration policy. A cache hit records its
original retrieval time and the time it was reused.

The cache reduces cost but cannot make prior-art coverage appear fresher than it is.

## 11. Reliability and Failure Behavior

### Reliability controls

- Per-operation timeouts
- Bounded retries
- Exponential backoff with jitter
- Provider-specific rate-limit handling
- Structured-output validation
- Bounded output-repair attempts
- Circuit breaking after repeated failures
- Configurable fallback routing
- Cancellation before unaffordable operations
- Idempotency keys where supported
- Cache reads before external calls

### Failure behavior

- Search failure preserves independent branches.
- Inspiration failure disables affected inspired branches.
- Prior-art failure lowers originality confidence and coverage.
- Prior-art failure never increases originality.
- Strong-model failure may use the economy model when fallback is allowed.
- Provider and validation failures preserve all prior candidates, sources, usage, and
  trace events.
- Partial token, search, latency, and cost usage remains recorded.
- Circuit-breaker state enters the trace.

No provider failure may silently produce a high-confidence originality estimate.

## 12. Privacy and Security

### Research mode

Stores:

- Prompts
- Structured outputs
- Bounded retrieved excerpts
- Source links and hashes
- Abstractions
- Provider and model configuration
- Usage and cost
- Scores and explanations

### Private mode

Stores:

- Redacted prompt summaries
- Redacted output summaries where configured
- Source links where allowed
- Content and prompt hashes
- Abstractions
- Usage and scores

Both modes:

- Remove API keys and authorization headers
- Redact configured secret patterns
- Sanitize provider exceptions
- Treat retrieved content as untrusted input
- Prevent source text from overriding system or developer instructions
- Exclude secrets from cache keys and fingerprints

## 13. Developer Configuration and CLI

Example configuration:

```yaml
models:
  economy: openai/<configured-economy-model>
  strong: openai/<configured-strong-model>
  embedding: openai/<configured-embedding-model>

search:
  inspiration: exa
  prior_art: brave
  fallback: openai_web_search

budgets:
  default_usd: 0.10
  comparison_usd: [0.50, 2.00]

privacy:
  mode: research
```

Model names remain explicit configuration and are not embedded in core orchestration.

### CLI

```powershell
muse live "task description" --budget-usd 0.10
muse compare "task description" --budgets 0.10 0.50 2.00
muse calibrate path/to/tasks.jsonl
```

The deterministic offline command remains available for regression testing.

### Programmatic interface

SDK users may:

- Supply configuration objects
- Supply credentials directly
- Inject custom model, embedding, search, pricing, cache, or clock implementations
- Disable fallback providers
- Select privacy mode
- Set hard cost, call, token, search, and duration ceilings

## 14. Calibration Pilot

The calibration system supports 50–100 tasks across multiple creative domains, but the
first actual batch contains 20 tasks to validate the rubric before larger spending.

Each task compares:

- Strong prompting baseline
- Muse at `$0.10`
- Muse at `$0.50`
- Muse at `$2.00`

Outputs are anonymized and randomized. Each candidate pair records 3–5 independent
ratings for:

- Which idea is more original
- Which idea is more useful
- Which idea better fits the task
- Whether either resembles known work
- Reviewer confidence

The harness records reviewer agreement, disagreement, and confidence.

### Calibration analysis

1. Compare computed originality estimates with pairwise human choices.
2. Measure each novelty dimension's predictive value.
3. Fit provisional weights on a training split.
4. Evaluate ranking accuracy on held-out tasks.
5. Report correlation, ranking accuracy, confidence calibration, reviewer agreement,
   and domain-specific failures.

The original provisional weights remain available as a fixed baseline.

## 15. Testing

### Unit and contract tests

- OpenAI model adapter contracts
- OpenAI embedding adapter contracts
- Exa and Brave search adapter contracts
- OpenAI web-search fallback contracts
- Structured-output parsing and repair
- Token, search, and cost accounting
- Search routing
- Search caching and freshness
- Source abstraction
- Provenance inheritance
- Novelty math and confidence
- Copying threshold behavior
- Privacy and redaction

### Pipeline tests

- At least 50 percent search-isolated branches
- Inspiration failure
- Prior-art failure
- Search fallback
- Rate limits and retry exhaustion
- Timeouts
- Malformed outputs
- Provider quote violations
- Cache hits and misses
- Circuit breaking
- Budget cancellation
- Private trace mode
- Prompt-injection text in retrieved content

### Live smoke tests

Live tests are optional and gated by environment variables. They use strict low budgets,
small result limits, and explicit test markers so normal test runs never incur cost.

Recorded-response fixtures remove secrets and personally identifying data.

### Calibration tests

Synthetic reviewer data verifies:

- Pair randomization
- Anonymization
- Training and held-out splits
- Weight fitting
- Agreement measures
- Confidence calibration
- Report generation

## 16. Success and Continuation Criteria

Milestone 2 succeeds when:

- Live runs stay within their authorized budget unless a provider violates its quote,
  in which case the incurred overage is recorded and external work stops.
- At least half of seed branches are provably search-isolated.
- Raw retrieved content never enters creative prompts.
- Controlled copying cases are detected.
- Traces preserve configuration, sources, abstractions, usage, errors, scores, and
  provider versions.
- The 20-task rubric-validation batch shows that the originality estimate ranks human
  preferences better than chance.
- At `$0.10`, the Muse achieves at least a 55 percent pairwise win rate
  over strong prompting on simultaneous originality and usefulness, with confidence
  intervals reported.

Results near 50 percent do not justify proceeding directly to identity or production
infrastructure. The team must identify the limiting stage and revise the process first.

## 17. Deliverables

Milestone 2 is complete when the repository contains:

- OpenAI model and embedding adapters
- Exa, Brave, and OpenAI web-search adapters
- Provider-neutral search and embedding interfaces
- Search router and cache
- Inspiration and prior-art engines
- Source abstraction and provenance models
- Novelty and confidence scoring
- Extended live usage and cost accounting
- Reliability and fallback controls
- Research and private trace modes
- `live`, `compare`, and `calibrate` CLI workflows
- A 20-task calibration task set and reviewer rubric
- Automated unit, contract, pipeline, privacy, and calibration tests
- Optional environment-gated live smoke tests
- A report comparing `$0.10`, `$0.50`, `$2.00`, and strong-prompting conditions

Negative results remain valid. The milestone exists to test whether live, source-aware
creative search is worth further investment, not to preserve the product premise.

## 18. Implementation Slices

Milestone 2 is delivered through three sequential implementation plans. Each slice must
produce working, independently testable software and pass its own review before the next
slice begins.

### Slice 2A: Live OpenAI Foundation

- OpenAI Responses API model adapter
- OpenAI embedding adapter
- Extended token, usage, quote, and pricing-table accounting
- Structured-output validation and repair
- Retry, timeout, rate-limit, and circuit-breaker primitives
- Research and private trace modes
- `live` CLI command using search-isolated branches only
- Environment-gated OpenAI smoke test

This slice proves that the existing engine can run safely against a live nondeterministic
provider without adding search.

### Slice 2B: Search, Inspiration, and Novelty

- Provider-neutral search interfaces
- Exa, Brave, and OpenAI web-search adapters
- Search router and cache
- Inspiration abstraction and provenance
- Independent and inspired branch allocation
- Prior-art checking
- Layered novelty, source-risk, and confidence scoring
- Anti-copying behavior
- `compare` CLI command

This slice proves that search improves or at least meaningfully changes creative results
without contaminating independent branches or encouraging imitation.

### Slice 2C: Calibration Pilot

- Review-packet generation
- Anonymization and randomization
- Reviewer rating ingestion
- Agreement and confidence measures
- Weight fitting and held-out evaluation
- `calibrate` CLI command
- Twenty-task rubric-validation task set
- Budget comparison report for `$0.10`, `$0.50`, and `$2.00`

This slice determines whether the originality estimate predicts human judgments and
whether the live pipeline meets the continuation threshold.
