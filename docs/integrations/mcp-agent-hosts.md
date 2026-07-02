# MCP Agent Host Integration

This guide wires muse into coding agents as an MCP tool. The goal is
for the agent to call `muse_plan` during normal planning, debugging, and
verification work. The CLI remains a local harness; `muse-mcp` is
the agent-facing server.

## Install Once Per Python Environment

From this repository:

```powershell
python -m pip install -e ".[dev]"
```

For open-source quickstart setup, configure live OpenAI first. Public Muse is
live-only because the MCP output should reflect the behavior agents will use in
real coding workflows.

Then verify the MCP tool without starting an agent host:

```powershell
muse-mcp-smoke "Design a retry strategy for AI coding agents" `
  --repo-language Python `
  --effort quick `
  --budget-usd 0.20
```

The smoke command invokes the FastMCP server in-process and prints the
structured payload returned by `muse_plan`. If live config is missing, it
returns a structured `configuration_error`; with valid OpenAI config, it runs
the actual live planning path.

For live runs, copy `.env.example` into your local shell or agent-host
environment and use `openai-pricing.example.json` as the safe pricing schema
example. Do not commit local files with real secrets.

For when to call the tool inside a normal coding loop, see
`docs/integrations/agent-dogfood-playbook.md`.

## Config Packs

- Codex: `docs/integrations/config-packs/codex/config.toml`
- Claude Code style project config: `docs/integrations/config-packs/claude-code/.mcp.json`
- Generic JSON MCP client config: `docs/integrations/config-packs/generic-mcp/mcp.json`

## Codex

Codex supports MCP servers in `~/.codex/config.toml` or a project-scoped
`.codex/config.toml`, using `[mcp_servers.<server-name>]` tables with keys such
as `command`, `args`, `env`, `enabled_tools`, `startup_timeout_sec`, and
`tool_timeout_sec`.

Copy the Codex pack into the config file you want to use:

```toml
[mcp_servers.muse]
command = "muse-mcp"
args = []
enabled = true
enabled_tools = ["muse_plan"]
startup_timeout_sec = 10
tool_timeout_sec = 120
```

Use project-scoped config when you want the tool available only for one repo.
Use user config when you want it available across repos.

Sources: OpenAI Codex MCP docs and configuration reference:
https://developers.openai.com/codex/mcp and
https://developers.openai.com/codex/config-reference

## Claude Code Style Project Config

Claude Code stores project-scoped MCP servers in `.mcp.json`. Use:

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

The checked-in pack includes live OpenAI env placeholders. Keep real secret
values in local-only config or shell environment, not in committed repo files.

Sources: Anthropic Claude Code MCP and settings docs:
https://docs.anthropic.com/en/docs/claude-code/mcp and
https://docs.anthropic.com/en/docs/claude-code/settings

## Generic JSON MCP Clients

Many editor MCP clients accept an `mcpServers` JSON shape with `command` and
`args`. Start with:

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

For Cursor-style clients, use the client UI or project/global MCP JSON location
supported by that client version, then paste the generic pack. This repo does
not install or mutate editor config automatically.

## Tool Payload

Agents should pass repo signals they already observed. The server should not
crawl arbitrary repositories. The agent-facing default is live-first, so omit
`provider_mode` for normal live planning once live environment variables are
configured:

```json
{
  "goal": "Design a better retry strategy for AI coding agents after failed tests",
  "effort": "quick",
  "repo_signals": {
    "changed_files": ["src/agent/runner.py"],
    "test_commands": ["python -m pytest tests/test_runner.py"],
    "ci_logs": ["pytest failed after retry loop change"],
    "detected_languages": ["Python"],
    "detected_frameworks": ["pytest"]
  }
}
```

Use `effort: "standard"` after an initial verification failure or ambiguous repo
context. Use `effort: "deep"` only for deliberate planning before high-impact
edits or repeated failure loops. Explicit `budget_usd`, `seed_count`,
`finalist_count`, and `max_generations` values override the preset.

## Provider Posture

MCP and `muse-mcp-smoke` are live-first by default. If
`provider_mode` is omitted, `muse_plan` resolves it from
`MUSE_PROVIDER_MODE`, falling back to `live_openai`.

Set these runtime defaults in the agent host environment when you want a stable
default without repeating fields in every tool call:

```powershell
$env:MUSE_PROVIDER_MODE = "live_openai"
$env:MUSE_EFFORT = "quick"
$env:MUSE_PRIVACY = "research"
$env:MUSE_BUDGET_USD = "0.25"
$env:MUSE_SEARCH_MODE = "off"
$env:MUSE_SEARCH_PROVIDER = "auto"
$env:MUSE_SEARCH_STRICT = "false"
```

The deterministic provider is an internal maintainer fixture for no-network CI
and protocol regression tests. Public MCP and smoke calls reject it unless the
maintainer sets `MUSE_ENABLE_TEST_PROVIDER=1`.

## Opt-in Search Context

The default is `off` for search context. `effort: "standard"` and
`effort: "deep"` do not automatically call search providers. Agents can request
opt-in search with `search_mode`. Use `search_provider` to select `auto`,
`exa`, or `brave`; use `search_strict` only when the agent should fail closed if
requested search cannot run:

```json
{
  "goal": "Design a debugging workflow for flaky CI",
  "provider_mode": "live_openai",
  "effort": "standard",
  "search_mode": "light",
  "search_provider": "auto",
  "search_strict": false,
  "budget_usd": 0.25
}
```

Use `search_mode: "deep"` only when broader bounded context is worth the extra
latency and possible provider spend. For smoke tests:

```powershell
muse-mcp-smoke "Design a retry strategy for AI coding agents" `
  --search-mode off `
  --search-provider auto `
  --repo-language Python
```

For environment-level defaults:

```powershell
$env:MUSE_SEARCH_MODE = "light"
$env:MUSE_SEARCH_PROVIDER = "auto"
$env:MUSE_SEARCH_STRICT = "false"
$env:MUSE_LIVE_SEARCH_APPROVED = "1"
```

`MUSE_LIVE_SEARCH_APPROVED=1` is required before live search
providers may be used. If approval or provider configuration is missing,
`muse_plan` returns `search_context` metadata explaining the skipped reason
and still runs planning when possible. Strict search changes that behavior: if
`search_strict` or `MUSE_SEARCH_STRICT=true` is set and requested
search is unavailable, `muse_plan` returns `configuration_error` with no
finalists. The MCP server still does not crawl repos; agents must pass observed
repo facts through `repo_signals`.

## Live OpenAI

Live mode can be selected explicitly per tool call, or used implicitly by
omitting `provider_mode`:

```json
{
  "goal": "Design a debugging workflow for flaky CI",
  "provider_mode": "live_openai",
  "privacy": "private",
  "effort": "quick",
  "budget_usd": 0.25
}
```

Set these environment variables in the agent host environment:

Set `OPENAI_API_KEY`, `OPENAI_ECONOMY_MODEL`, `OPENAI_STRONG_MODEL`,
`OPENAI_EMBEDDING_MODEL`, and `OPENAI_PRICING_FILE` in the shell or local
agent-host environment before starting the MCP server. Do not commit real
values to the repository.

If config is missing or invalid, `muse_plan` returns
`stopped_reason: "configuration_error"` with a structured error and no finalists.

## Agent Prompt Hook

Use this instruction in an agent system prompt or project instruction file:

```text
When a coding task needs creative planning, retry strategy design, test-failure
recovery, workflow alternatives, or repo-agnostic middleware design, call the
muse MCP tool `muse_plan`. Pass the current task goal and repo
signals you already observed, such as changed files, test commands, CI logs,
dependency hints, languages, and frameworks. Treat returned finalists as planning
options; do not execute them blindly. Pick one bounded next action and verify it
with the narrowest relevant check.
```

## Troubleshooting

- `configuration_error`: check env variables, model names, and pricing file path.
- Tool does not appear: rerun `muse-mcp-smoke`, then restart the agent host.
- Live calls spend money: lower `budget_usd`, `seed_count`, or `max_generations`.
- Weak context: pass richer `repo_signals`; the MCP server intentionally does not crawl the repo.
