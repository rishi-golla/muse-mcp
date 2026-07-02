# V3-L Quality Dogfood Suite Design

## Goal

V3-L adds a repeatable dogfood quality suite for the real MCP planning path. The purpose is not to add another user-facing planning surface; it is to prove whether the MCP middleware output is good enough for agent consumption before moving to V4 productization.

## Recommended Approach

Use a repo-owned prompt suite that calls the in-process FastMCP `muse_plan` tool with realistic coding-agent tasks and observed `repo_signals`. The suite should run cheap deterministic checks in CI and optionally support live OpenAI runs when the caller provides live configuration.

This is better than adding a separate API or building a broad benchmark runner now. It keeps the product direction aligned with MCP middleware, gives us regression data for search modes, and avoids pretending deterministic fixture output is product-quality.

## Scope

The suite will include:

- Built-in prompt cases for AI-agent retry strategy, TypeScript monorepo flaky CI, arbitrary repo planning middleware, and interactive portfolio planning.
- Search variants for `off`, `light`, and `deep`, with configurable `search_provider` and `search_strict`.
- MCP-path execution through `build_mcp_server().call_tool("muse_plan", ...)`.
- Structured report fields for cost, latency, generated/finalist counts, search metadata, errors, and quality gates.
- Quality gates for generic output, missing operational contract fields, missing repo-signal terms, unavailable requested search, and configuration/provider errors.
- A smoke CLI for local dogfood runs, with `--json`, `--provider-mode`, `--effort`, `--budget-usd`, `--search-provider`, `--search-strict`, `--fail-on-gates`, and case/variant filters.

## Non-Goals

- No human scoring UI.
- No stored evaluation database.
- No automatic repo crawling.
- No mandatory live provider spend in tests.
- No change to the `muse_plan` MCP contract.

## Architecture

Create a focused `dogfood_quality` module. It owns case definitions, variant definitions, MCP invocation, metric extraction, and gate evaluation. The module returns JSON-safe dictionaries so both tests and the CLI can consume the same contract.

The CLI should remain a harness, not the product surface. Agent hosts still use MCP. The CLI exists to run a repeatable suite from a terminal and to make future V4 release checks easier.

## Quality Gates

The gate layer should be intentionally conservative. It should flag weak output rather than hiding it:

- `missing_finalist`: no finalist was produced.
- `generic_title`: finalist title matches known deterministic/generic fixtures such as `Decision garden`.
- `generic_mechanism`: finalist mechanism uses generic governance phrasing unrelated to the task.
- `missing_operational_field`: required middleware fields are empty.
- `missing_required_terms`: output did not mention enough case-specific repo/task terms.
- `search_expected_but_unused`: `light` or `deep` search was requested but `search_context.used` is false.
- `provider_error`: the MCP result contains errors or stopped for configuration/provider reasons.

Default CLI runs should exit successfully and report gates. `--fail-on-gates` should exit non-zero for CI quality enforcement.

## Testing

Tests should prove:

- Built-in cases are valid and contain required terms.
- The suite invokes the FastMCP tool path and returns JSON-safe report data.
- Deterministic output is flagged as generic where appropriate, instead of being silently accepted.
- Search variants preserve search metadata and can flag unused requested search.
- CLI output is parseable JSON and `--fail-on-gates` exits non-zero when gates fail.

## Documentation

README and dogfood docs should explain that V3-L is the final V3 validation slice and that deterministic results are useful for protocol checks, not quality approval. Live runs are optional and controlled by existing live OpenAI environment variables.
