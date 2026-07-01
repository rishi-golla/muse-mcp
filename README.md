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

## Calibration review packets

```powershell
python -m creativity_layer.cli review-packet --trace <trace.json> --output-dir .review-packets --shuffle-seed 17
```

Review packets are anonymized and randomized artifacts for human review. Rating
ingestion, agreement metrics, and calibration fitting are later 2C slices.

## Live OpenAI mode

Set:

```powershell
$env:OPENAI_API_KEY = "<OPENAI_API_KEY>"
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

Live mode performs no web search in Slice 2A. Live summaries include
`generated_count` and `unevaluated_count` so production-like smoke tests can
distinguish generation failures from evaluation failures.

Live idea artifacts include an operational contract (`inputs_required`,
`outputs_produced`, `agent_workflow`, `decision_policy`, `integration_points`,
`verification_strategy`, and `failure_modes`) so downstream agents can consume
ideas as planning artifacts instead of prose-only briefs.

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

## Context grounding harness

Core callers should pass typed `ContextBundle` data directly into `TaskContext`.
The CLI `--context-file` flag is only a local harness for exercising that same
middleware-shaped path:

```powershell
creativity-layer live "Design a debugging workflow for flaky CI" `
  --context-file .\context.json `
  --budget-usd 0.25 `
  --privacy private
```

Context files use this shape:

```json
{
  "snippets": [
    {
      "source": "repo/ci-snapshot",
      "title": "CI signals",
      "content": "package graph, affected packages, test shards, tsc, Jest, Vitest, Playwright, CI logs",
      "metadata": {"kind": "monorepo"}
    }
  ],
  "tags": ["typescript", "monorepo"]
}
```

## Agent MCP integration

The preferred workflow integration surface is MCP, not the CLI. Install the
package into the Python environment your agent host can run, then point the
agent at the stdio server:

For host-specific config packs and setup notes, see
`docs/integrations/mcp-agent-hosts.md`.
For a deterministic local proof that an agent loop can consume the MCP output
and apply a bounded repair, see `docs/integrations/agent-loop-proof.md`.
For when to call the tool during normal coding in another repo, see
`docs/integrations/agent-dogfood-playbook.md`.

```json
{
  "mcpServers": {
    "creativity-layer": {
      "command": "creativity-layer-mcp",
      "args": []
    }
  }
}
```

The server exposes `creative_plan`. Agents should pass repo facts they already
observed instead of asking creativity-layer to crawl the repository:

```json
{
  "goal": "Design a better retry strategy for AI coding agents after failed tests",
  "effort": "quick",
  "repo_signals": {
    "file_paths": ["pnpm-workspace.yaml", "apps/web/package.json"],
    "changed_files": ["packages/ui/src/Button.tsx"],
    "test_commands": ["pnpm test --filter apps/web -- --shard=2/4"],
    "ci_logs": ["Vitest shard 2 failed after Playwright smoke tests"],
    "dependency_hints": ["apps/web depends on packages/ui"],
    "detected_languages": ["TypeScript"],
    "detected_frameworks": ["Vitest", "Playwright"]
  }
}
```

The MCP tool returns JSON-safe finalists with operational fields such as
`inputs_required`, `agent_workflow`, `decision_policy`,
`integration_points`, `verification_strategy`, and `failure_modes`. The
current MCP server uses the deterministic local provider by default, so it does
not require OpenAI, Exa, Brave, pricing files, or network access.

To smoke-test the actual MCP tool registration without an agent host:

```powershell
creativity-layer-mcp-smoke "Design a retry strategy for AI coding agents" `
  --repo-language Python `
  --seed-count 2 `
  --finalist-count 1 `
  --generations 0 `
  --budget-usd 0.20
```

For live OpenAI MCP calls, keep the same MCP server command and pass
`"provider_mode": "live_openai"` in the tool payload. The live path uses the
same environment variables as CLI live mode:

```powershell
$env:OPENAI_API_KEY = "<OPENAI_API_KEY>"
$env:OPENAI_ECONOMY_MODEL = "<cheap-model-id>"
$env:OPENAI_STRONG_MODEL = "<stronger-model-id>"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
$env:OPENAI_PRICING_FILE = "C:\path\to\openai-pricing.json"
```

Example live MCP payload:

```json
{
  "goal": "Design a better retry strategy for AI coding agents after failed tests",
  "provider_mode": "live_openai",
  "privacy": "private",
  "budget_usd": 0.25,
  "seed_count": 4,
  "finalist_count": 2,
  "max_generations": 1,
  "repo_signals": {
    "changed_files": ["src/agent/runner.py"],
    "test_commands": ["python -m pytest tests/test_runner.py"],
    "ci_logs": ["pytest failed after retry loop change"],
    "detected_languages": ["Python"],
    "detected_frameworks": ["pytest"]
  }
}
```

If live configuration is missing or invalid, the MCP tool returns
`stopped_reason: "configuration_error"` with a structured error and no finalists
instead of charging provider calls.

The engine does not read this file. The CLI parses it into `ContextBundle`, then
calls the same provider-neutral API a future middleware layer will call.

`--repo-signals-file` exercises the V3-C context provider harness. The engine still
does not crawl the repository or read this file directly; the CLI parses generic repo
facts into `RepoSignals`, then uses `DeterministicContextProvider` to build a
`ContextBundle`:

```powershell
creativity-layer "Design a debugging workflow for flaky CI" `
  --repo-signals-file .\repo-signals.json `
  --trace-dir .traces
```

Example:

```json
{
  "file_paths": ["pnpm-workspace.yaml", "apps/web/package.json"],
  "changed_files": ["packages/ui/src/Button.tsx"],
  "package_manifests": ["apps/web/package.json", "packages/ui/package.json"],
  "test_commands": ["pnpm test --filter apps/web -- --shard=2/4"],
  "ci_logs": ["Vitest shard 2 failed after Playwright smoke tests"],
  "dependency_hints": ["apps/web depends on packages/ui"],
  "detected_languages": ["TypeScript"],
  "detected_frameworks": ["Vitest", "Playwright"]
}
```
