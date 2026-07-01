# MCP Agent Host Integration

This guide wires creativity-layer into coding agents as an MCP tool. The goal is
for the agent to call `creative_plan` during normal planning, debugging, and
verification work. The CLI remains a local harness; `creativity-layer-mcp` is
the agent-facing server.

## Install Once Per Python Environment

From this repository:

```powershell
python -m pip install -e ".[dev]"
```

Then verify the MCP tool without starting an agent host:

```powershell
creativity-layer-mcp-smoke "Design a retry strategy for AI coding agents" `
  --repo-language Python `
  --seed-count 2 `
  --finalist-count 1 `
  --generations 0 `
  --budget-usd 0.20
```

The smoke command invokes the FastMCP server in-process and prints the
structured payload returned by `creative_plan`.

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
[mcp_servers.creativity-layer]
command = "creativity-layer-mcp"
args = []
enabled = true
enabled_tools = ["creative_plan"]
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
    "creativity-layer": {
      "command": "creativity-layer-mcp",
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
    "creativity-layer": {
      "command": "creativity-layer-mcp",
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
crawl arbitrary repositories:

```json
{
  "goal": "Design a better retry strategy for AI coding agents after failed tests",
  "provider_mode": "deterministic",
  "budget_usd": 0.35,
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

## Live OpenAI

Live mode is opt-in per tool call:

```json
{
  "goal": "Design a debugging workflow for flaky CI",
  "provider_mode": "live_openai",
  "privacy": "private",
  "budget_usd": 0.25,
  "seed_count": 4,
  "finalist_count": 2,
  "max_generations": 1
}
```

Set these environment variables in the agent host environment:

```powershell
$env:OPENAI_API_KEY = "<OPENAI_API_KEY>"
$env:OPENAI_ECONOMY_MODEL = "<OPENAI_ECONOMY_MODEL>"
$env:OPENAI_STRONG_MODEL = "<OPENAI_STRONG_MODEL>"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
$env:OPENAI_PRICING_FILE = "C:\path\to\openai-pricing.json"
```

If config is missing or invalid, `creative_plan` returns
`stopped_reason: "configuration_error"` with a structured error and no finalists.

## Agent Prompt Hook

Use this instruction in an agent system prompt or project instruction file:

```text
When a coding task needs creative planning, retry strategy design, test-failure
recovery, workflow alternatives, or repo-agnostic middleware design, call the
creativity-layer MCP tool `creative_plan`. Pass the current task goal and repo
signals you already observed, such as changed files, test commands, CI logs,
dependency hints, languages, and frameworks. Treat returned finalists as planning
options; do not execute them blindly. Pick one bounded next action and verify it
with the narrowest relevant check.
```

## Troubleshooting

- `configuration_error`: check env variables, model names, and pricing file path.
- Tool does not appear: rerun `creativity-layer-mcp-smoke`, then restart the agent host.
- Live calls spend money: lower `budget_usd`, `seed_count`, or `max_generations`.
- Weak context: pass richer `repo_signals`; the MCP server intentionally does not crawl the repo.
