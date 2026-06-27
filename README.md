# Creativity Layer

A research prototype for testing whether evolutionary creative search produces ideas
that humans judge as simultaneously more original and useful than strong prompting.

The first implementation milestone is intentionally deterministic. It validates the
core orchestration, data contracts, budget accounting, selection behavior, and trace
reproducibility before paid model and search providers are introduced.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

## Deterministic research-spine demo

```powershell
creativity-layer "Invent a calmer way for distributed teams to make decisions" `
  --seed-count 4 `
  --finalist-count 3 `
  --generations 1 `
  --trace-dir .traces
```

The command prints a JSON summary containing the resolved absolute trace path and
writes the complete structured run trace to `.traces/<run-id>.json`. Exit status `0`
means at least one scored finalist is usable, including a valid frontier returned
after budget exhaustion. Provider failures, empty frontiers, and trace-write failures
return status `1`; invalid command input returns status `2`.

Deterministic mode uses local providers; it makes no external model or search
calls. Its CLI sets both framing and finalization reserves to zero because
framing is unmetered and finalization is not implemented in this milestone.
`RunConfig` retains nonzero library defaults as future-provider policy; those
reserves intentionally reduce exploration capacity when enabled. A nonzero
library framing reserve remains unspent in this milestone because framing is
unmetered, deliberately stranding that capacity for future metered framing.

## Compare mode

```powershell
creativity-layer compare "Invent a calmer way for distributed teams to make decisions" `
  --seed-count 4 `
  --finalist-count 2 `
  --generations 0 `
  --budget-usd 0.10 `
  --trace-dir .traces
```

Compare mode runs a deterministic baseline beside a search-aware deterministic
run and writes one trace for each. Its search path uses mocked deterministic
fixtures only; it does not call Exa, Brave, OpenAI web search, or paid OpenAI
models.

## Live OpenAI mode

Set:

```powershell
$env:OPENAI_API_KEY = "<your-api-key>"
$env:OPENAI_ECONOMY_MODEL = "<explicit model id>"
$env:OPENAI_STRONG_MODEL = "<explicit model id>"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
$env:OPENAI_PRICING_FILE = "path\to\pricing.json"
```

Run:

```powershell
creativity-layer live "Invent a low-cost coordination mechanism" `
  --budget-usd 0.10 `
  --privacy private
```

Live mode performs no web search in Slice 2A.

## Live search adapter smoke tests

Normal tests do not call Exa, Brave, or OpenAI web search. Live search adapter
smoke tests are opt-in and require explicit approval plus provider credentials:

```powershell
$env:CREATIVITY_LAYER_LIVE_SEARCH_APPROVED = "1"
$env:EXA_API_KEY = "<exa-api-key>"
$env:BRAVE_SEARCH_API_KEY = "<brave-search-api-key>"
$env:OPENAI_API_KEY = "<openai-api-key>"
$env:OPENAI_WEB_SEARCH_MODEL = "<explicit-web-search-capable-model>"
python -m pytest -m "live_search"
```

The default compare path remains no-network and deterministic.
