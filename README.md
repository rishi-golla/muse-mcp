# Muse

A research prototype for testing whether evolutionary creative search produces ideas
that humans judge as simultaneously more original and useful than strong prompting.

Muse is open-source middleware for AI coding agents. The preferred
integration surface is MCP: agents call `muse_plan` during planning,
debugging, and verification instead of replacing their normal coding workflow.

## Open-source quickstart

Install from a fresh clone:

```powershell
python -m pip install -e ".[dev]"
```

Set live OpenAI configuration in your shell or agent-host environment:

```powershell
$env:OPENAI_API_KEY = "replace_me"
$env:OPENAI_ECONOMY_MODEL = "gpt-5.4-mini"
$env:OPENAI_STRONG_MODEL = "gpt-5.4"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
```

Muse includes packaged default pricing for the example models above. Set
`OPENAI_PRICING_FILE` only when you choose different models or want to override
the bundled pricing table.

Check local MCP live configuration without making provider calls:

```powershell
muse-mcp-doctor --json
```

Generate the host config snippet you need. For Codex:

```powershell
muse-mcp-config --host codex
```

For Claude Code or Cursor-style JSON MCP clients:

```powershell
muse-mcp-config --host claude-code --include-env
```

Generate project instructions so the connected agent knows when to call Muse:

```powershell
muse-agent-instructions --target agents-md
```

For Cursor rules:

```powershell
muse-agent-instructions --target cursor-rules
```

Before touching a real repo, create a throwaway external dogfood repo with the
same MCP config and project instructions:

```powershell
muse-external-dogfood `
  --workspace ..\muse-external-dogfood-sample `
  --host generic-json `
  --instruction-target agents-md `
  --json
```

This does not spend provider budget. It writes a marked sample repo, reports
`ready_for_manual_agent_test`, and tells you whether `muse-mcp-doctor --json`
still needs live OpenAI environment variables.

When the sample looks right, initialize the actual project repo:

```powershell
muse-project-init `
  --project C:\path\to\your\repo `
  --host generic-json `
  --instruction-target agents-md `
  --json
```

Use `--dry-run` first to preview files, and `--force` only when you intend to
replace existing `.mcp.json`, `.codex/config.toml`, `AGENTS.md`, or Cursor rule
targets. The command writes no real secrets and makes no provider calls.

Restart the MCP-capable agent host, then ask the agent for a creative planning
task in that project. The agent should observe repo facts and call `muse_plan`
in the backend with `mode: "normal"` or `mode: "extensive"`.

For local setup, copy `.env.example` to a local environment file or shell setup
and set real provider values outside the repo. `openai-pricing.example.json`
shows the packaged default pricing schema for overrides.

Historical note: the first implementation milestone used deterministic fixtures
to validate orchestration, data contracts, budget accounting, selection
behavior, and trace reproducibility before paid model and search providers were
introduced. Public MCP usage now starts with live OpenAI.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

### Quality benchmarking

The V6-A quality benchmark is a library-first maintainer workflow for comparing
Muse with a direct strong-model baseline. It uses blinded pairwise judgments and
repeated runs, while preserving cost, latency, and failure accounting. Unit tests
do not establish creative quality; follow the [benchmarking guide](docs/quality/benchmarking.md)
for the evidence required for a quality claim. This is not a public CLI.

## Internal fixture research-spine demo

```powershell
muse "Invent a calmer way for distributed teams to make decisions" `
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

This maintainer fixture uses local providers; it makes no external model or search
calls. Its CLI sets both framing and finalization reserves to zero because
framing is unmetered and finalization is not implemented in this milestone.
`RunConfig` retains nonzero library defaults as future-provider policy; those
reserves intentionally reduce exploration capacity when enabled. A nonzero
library framing reserve remains unspent in this milestone because framing is
unmetered, deliberately stranding that capacity for future metered framing.

## Compare mode

```powershell
muse compare "Invent a calmer way for distributed teams to make decisions" `
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
python -m muse.cli review-packet --trace <trace.json> --output-dir .review-packets --shuffle-seed 17
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
```

Run:

```powershell
muse live "Invent a low-cost coordination mechanism" `
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
$env:MUSE_LIVE_SEARCH_APPROVED = "1"
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
muse live "Design a debugging workflow for flaky CI" `
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
For a throwaway external repo that proves the onboarding files before touching a
real codebase, run `muse-external-dogfood`.
To write the same files into a real project with overwrite protection, run
`muse-project-init`.
For a deterministic local proof that an agent loop can consume the MCP output
and apply a bounded repair, see `docs/integrations/agent-loop-proof.md`.
For when to call the tool during normal coding in another repo, see
`docs/integrations/agent-dogfood-playbook.md`.

```json
{
  "mcpServers": {
    "muse": {
      "command": "muse-mcp",
      "args": []
    }
  }
}
```

The server exposes `muse_plan`. Agents should pass repo facts they already
observed instead of asking muse to crawl the repository:

```json
{
  "goal": "Design a better retry strategy for AI coding agents after failed tests",
  "mode": "normal",
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
agent-facing posture is live-first: if `provider_mode` is omitted, MCP calls use
`live_openai` and return a structured `configuration_error` when required live
environment variables are missing.

V4-C adds advisory quality fields to that same response. Top-level
`quality_warnings` lists warning names seen across finalists, `quality_summary`
counts those warnings, and each finalist includes its own `quality_warnings`.
Treat these as planning signals, not hard rejection: an agent should prefer a
specific, operational finalist when warnings such as `generic_title`,
`generic_mechanism`, or `missing_operational_field` appear, then still run
repository-owned verification.

V4-D adds `quality_action_policy`, also mirrored inside `agent_guidance`. The
policy turns warning names into `status`, `escalate_effort_to`,
`recommended_actions`, and per-warning remediation hints. It recommends actions
such as adding repo signals or moving from `mode: "normal"` to
`mode: "extensive"`, but it does not automatically perform another provider
call.

Set runtime defaults in the agent host environment when you want every omitted
tool field to use the same posture:

```powershell
$env:MUSE_PROVIDER_MODE = "live_openai"
$env:MUSE_MODE = "normal"
$env:MUSE_PRIVACY = "research"
$env:MUSE_SEARCH_MODE = "off"
$env:MUSE_SEARCH_PROVIDER = "auto"
$env:MUSE_SEARCH_STRICT = "false"
```

The deterministic provider is an internal maintainer fixture for no-network CI,
protocol checks, and transport regression tests. Public MCP usage is live-only;
internal tests that need the fixture must set `MUSE_ENABLE_TEST_PROVIDER=1`.

### V3-L dogfood quality suite

V3-L is the last V3 validation slice before V4 productization. It adds a
repeatable MCP quality harness, not a new product surface. Use it to compare
`search-off`, `search-light`, and `search-deep` runs across built-in dogfood
cases and to catch weak output before it reaches an agent workflow.

Cheap live quality run:

```powershell
muse-dogfood-quality `
  --provider-mode live_openai `
  --case agent-retry-python `
  --variant search-off `
  --json
```

CI-style quality gate:

```powershell
muse-dogfood-quality `
  --provider-mode live_openai `
  --case agent-retry-python `
  --variant search-off `
  --fail-on-gates `
  --json
```

Quality gates are calibrated for live output. Compare `search-off`,
`search-light`, and `search-deep` before changing prompts or evaluator
pressure.

For live OpenAI MCP calls, keep the same MCP server command and either omit
`provider_mode` or pass `"provider_mode": "live_openai"` in the tool payload.
The live path uses the same environment variables as CLI live mode:

```powershell
$env:OPENAI_API_KEY = "<OPENAI_API_KEY>"
$env:OPENAI_ECONOMY_MODEL = "<cheap-model-id>"
$env:OPENAI_STRONG_MODEL = "<stronger-model-id>"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
```

`OPENAI_PRICING_FILE` is optional when the selected models are covered by the
packaged default pricing. Set it to a local JSON file when using different
models or pricing.

Example live MCP payload:

```json
{
  "goal": "Design a better retry strategy for AI coding agents after failed tests",
  "privacy": "private",
  "mode": "normal",
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

### Live branch evidence

For `provider_mode: "live_openai"`, `seed_count` requests an ordered schedule of independent
live model trajectories rather than one shared batched seed response. The response records
the ordered creative strategies and the number of independently completed seed branches in
`config.branch_generation`:

```json
{
  "seed_count": 4,
  "branch_generation": {
    "strategies": [
      "constraint_inversion",
      "failure_first",
      "cross_domain_transfer",
      "systems_effects"
    ],
    "independent_call_count": 4
  }
}
```

`strategies` lists the ordered requested strategy directives. `independent_call_count`
counts only evidenced completed branches from the run's metered seed trace, so it can be
lower than `seed_count` after a branch failure and is zero when seeding never starts.
Evidence is accepted only when the requested branches are an ordered prefix of the exact
strategy schedule, each nested request contains the complete canonical branch directive
including its exact instruction, every branch has non-empty structurally valid nested request
and response traces, and their calls and token usage exactly reconcile with the charged
seeding spend record. Placeholders, reordered or forged branches, duplicates, and
inconsistent accounting produce a zero count.

The deterministic provider remains a no-network test fixture. Its metadata
uses `independent_call_count: 0`, so a fixture result does not prove a provider
call or provider spend.

### Opt-in search context

MCP search context is explicit. The default is `off`, so `quick`, `standard`,
and `deep` internal effort levels do not trigger search by themselves. Set
`"search_mode": "light"` for bounded context or `"search_mode": "deep"` for a
broader bounded pass. `search_provider` selects `auto`, `exa`, or `brave`;
`auto` chooses a configured live search provider when one is
available. Set `search_strict: true` only when the agent should fail closed if
requested search cannot run:

```json
{
  "goal": "Design a better retry strategy for AI coding agents after failed tests",
  "mode": "extensive",
  "search_mode": "light",
  "search_provider": "auto",
  "search_strict": false,
  "repo_signals": {
    "test_commands": ["python -m pytest tests/test_runner.py"],
    "detected_languages": ["Python"],
    "detected_frameworks": ["pytest"]
  }
}
```

For environment-level defaults, use:

```powershell
$env:MUSE_SEARCH_MODE = "light"
$env:MUSE_SEARCH_PROVIDER = "auto"
$env:MUSE_SEARCH_STRICT = "false"
$env:MUSE_LIVE_SEARCH_APPROVED = "1"
```

`MUSE_LIVE_SEARCH_APPROVED=1` is required before live search
providers may be used. Without approval or provider configuration, the result
still returns finalists when possible and includes `search_context` metadata
with the skipped reason. Strict search changes that behavior: if
`search_strict` or `MUSE_SEARCH_STRICT=true` is set and requested
search is unavailable, the MCP result returns `configuration_error` and no
finalists. This is opt-in search; muse still does not crawl
repositories, and agents should pass observed repo signals.

The smoke command exposes the same policy controls:

```powershell
muse-mcp-smoke "Design a retry strategy for AI coding agents" `
  --provider-mode live_openai `
  --search-mode light `
  --search-provider auto `
  --search-strict `
  --repo-language Python
```

The engine does not read this file. The CLI parses it into `ContextBundle`, then
calls the same provider-neutral API a future middleware layer will call.

`--repo-signals-file` exercises the V3-C context provider harness. The engine still
does not crawl the repository or read this file directly; the CLI parses generic repo
facts into `RepoSignals`, then uses `DeterministicContextProvider` to build a
`ContextBundle`:

```powershell
muse "Design a debugging workflow for flaky CI" `
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
