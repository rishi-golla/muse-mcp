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
muse-mcp-doctor --json
```

The doctor command performs local live OpenAI preflight checks without making
provider calls. It reports missing env vars, selected model ids, and pricing
coverage using redacted output.

Generate the host config you need instead of hand-copying the static examples:

```powershell
muse-mcp-config --host codex
```

For Claude Code or Cursor-style JSON MCP clients:

```powershell
muse-mcp-config --host claude-code --include-env
```

Generate project instructions so the connected agent knows when to call Muse
and how to use `muse_plan` output:

```powershell
muse-agent-instructions --target agents-md
```

For Cursor rules:

```powershell
muse-agent-instructions --target cursor-rules
```

Before editing a real repository, generate a marked throwaway repo with the same
MCP config and agent instructions:

```powershell
muse-external-dogfood `
  --workspace ..\muse-external-dogfood-sample `
  --host generic-json `
  --instruction-target agents-md `
  --json
```

`muse-external-dogfood` is a no-spend onboarding proof. It creates a small
sample project, writes `.mcp.json` or `.codex/config.toml`, writes the selected
agent instruction file, runs local live preflight checks, and reports
`ready_for_manual_agent_test`. Use `--strict-live` when CI or release checks
should fail until `muse-mcp-doctor --json` is clean.

After the external proof looks right, initialize a real project repo with the
same generated files:

```powershell
muse-project-init `
  --project C:\path\to\your\repo `
  --host generic-json `
  --instruction-target agents-md `
  --json
```

Use `--dry-run` to preview the files before writing. By default
`muse-project-init` refuses to overwrite existing target files; pass `--force`
only when replacing `.mcp.json`, `.codex/config.toml`, `AGENTS.md`, or
`.cursor/rules/muse.mdc` is intentional. The command writes placeholders, not
real secrets, and performs only local live preflight checks.

For live runs, copy `.env.example` into your local shell or agent-host
environment. Muse includes packaged default pricing for the documented example
models; use `openai-pricing.example.json` as the safe schema example only when
you want a local override. Do not commit local files with real secrets.

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

Use `mode: "normal"` for routine planning. Use `mode: "extensive"` after
repeated failed verification, ambiguous repo context, or deliberate planning
before high-impact edits. The agent should not ask the human for seed counts,
budget values, framework flags, or generation counts.

## Provider Posture

MCP is live-first by default. If `provider_mode` is omitted, `muse_plan`
resolves it from `MUSE_PROVIDER_MODE`, falling back to `live_openai`.

Set these runtime defaults in the agent host environment when you want a stable
default without repeating fields in every tool call:

```powershell
$env:MUSE_PROVIDER_MODE = "live_openai"
$env:MUSE_MODE = "normal"
$env:MUSE_PRIVACY = "research"
$env:MUSE_SEARCH_MODE = "off"
$env:MUSE_SEARCH_PROVIDER = "auto"
$env:MUSE_SEARCH_STRICT = "false"
```

The deterministic provider is an internal maintainer fixture for no-network CI
and protocol regression tests. Public MCP calls reject it unless the maintainer
sets `MUSE_ENABLE_TEST_PROVIDER=1`.

## Opt-in Search Context

The default is `off` for search context. `mode: "normal"` and
`mode: "extensive"` do not automatically call search providers. Agents can
request opt-in search with `search_mode`. Use `search_provider` to select `auto`,
`exa`, or `brave`; use `search_strict` only when the agent should fail closed if
requested search cannot run:

```json
{
  "goal": "Design a debugging workflow for flaky CI",
  "mode": "extensive",
  "search_mode": "light",
  "search_provider": "auto",
  "search_strict": false
}
```

Use `search_mode: "deep"` only when broader bounded context is worth the extra
latency and possible provider spend.

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
  "privacy": "private",
  "mode": "normal"
}
```

Set these environment variables in the agent host environment:

Set `OPENAI_API_KEY`, `OPENAI_ECONOMY_MODEL`, `OPENAI_STRONG_MODEL`,
and `OPENAI_EMBEDDING_MODEL` in the shell or local agent-host environment before
starting the MCP server. `OPENAI_PRICING_FILE` is optional when the selected
models are covered by packaged default pricing; set it for local pricing
overrides. Do not commit real values to the repository.

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
options; do not execute them blindly. Use mode: "normal" by default and
mode: "extensive" only for high-impact or repeated-failure planning. Do not ask
the human for seed counts, budgets, repo-language flags, framework flags, or
generation counts. Pick one bounded next action and verify it with the narrowest
relevant check.
```

## Troubleshooting

- `configuration_error`: check env variables, model names, and pricing file path.
- Tool does not appear: rerun `muse-project-init --dry-run`, then restart the agent host.
- Live calls spend money: use `mode: "normal"` unless the task truly needs extensive planning.
- Weak context: pass richer `repo_signals`; the MCP server intentionally does not crawl the repo.
