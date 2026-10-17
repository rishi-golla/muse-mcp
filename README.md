<p align="center">
  <strong>Muse</strong>
</p>

<p align="center">
  Creative planning infrastructure for AI coding agents.
</p>

## Agent-first Quickstart

### Paste this into your coding agent

```text
Read this README and set up Muse for this project. Install the package, verify
the live OpenAI configuration, generate the MCP configuration and agent
instructions, restart the host, then use Muse when the task needs exploration or
non-obvious planning. Never commit secrets.
```

### Manual PowerShell setup

Install Muse in the Python environment used by the agent host:

```powershell
python -m pip install -e ".[dev]"
```

Set live OpenAI configuration in your shell or agent-host environment. Keep real
values outside the repository:

```powershell
$env:OPENAI_API_KEY = "replace_me"
$env:OPENAI_ECONOMY_MODEL = "gpt-5.4-mini"
$env:OPENAI_STRONG_MODEL = "gpt-5.4"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
```

Muse includes packaged default pricing for the documented example models. Set
`OPENAI_PRICING_FILE` only for different models or a local pricing override.
Verify the configuration without making provider calls:

```powershell
muse-mcp-doctor --json
```

Generate the Codex MCP configuration instead of hand-copying it:

```powershell
muse-mcp-config --host codex
```

Generate project instructions so the agent knows when and how to call Muse:

```powershell
muse-agent-instructions --target agents-md
```

Initialize the project with overwrite protection:

```powershell
muse-project-init `
  --project C:\path\to\your\repo `
  --host generic-json `
  --instruction-target agents-md `
  --json
```

Use `--dry-run` to preview generated files. Use `--force` only when replacing
existing MCP configuration or agent instruction files is intentional. The command
writes placeholders, not real secrets, and makes no provider calls.

Restart the MCP-capable agent host. Ask the agent to observe the repository and
call `muse_plan` for its first live task when exploration or non-obvious planning
is needed. Muse runs behind the agent; it does not replace the agent's normal
editing, testing, or verification workflow.

## What Muse Adds

`muse_plan` returns creative planning finalists with operational fields such as
`inputs_required`, `agent_workflow`, `decision_policy`, `integration_points`,
`verification_strategy`, and `failure_modes`. These are planning options for an
agent to evaluate and turn into one bounded next action, not applied work.

Muse is repo-agnostic. The calling agent supplies the relevant repository facts,
such as changed files, test commands, CI logs, languages, and frameworks; Muse
does not crawl arbitrary repositories.

## Use Muse Through Your Agent

MCP is the intended integration surface. Use `mode: "normal"` for routine
planning and failed-test recovery. Use `mode: "extensive"` after repeated failed
verification, ambiguous repository context, or before high-impact edits.

Repository observation, implementation decisions, safety checks, and
verification remain the calling agent's responsibility. Treat returned finalists
as advice, select a bounded action, and run the narrowest relevant repository
check.

## Agent Loop

Use `muse_plan` for a new task. Follow the returned bounded next action, run
repository-owned verification, and return evidence through the session tools.
Muse never replaces the calling agent's observation, authorization, editing,
or verification responsibilities.

### Optional web research with Parallel Search MCP

When planning depends on current library documentation or migration guidance, the
calling agent can research public sources with
[Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp) before
calling Muse. It provides free web search and page fetching without a Parallel
account or API key; anonymous search uses Fast mode and has usage limits. Muse
still requires the live OpenAI configuration from the quickstart.

For Codex, first generate Muse's configuration with `muse-mcp-config --host codex`.
Keep that configuration and add this separate entry to the same
`~/.codex/config.toml` or trusted project's `.codex/config.toml`:

```toml
[mcp_servers.parallel-search]
url = "https://search.parallel.ai/mcp"
```

Restart the host and confirm that Muse's `muse_plan` and Parallel's `web_search`
and `web_fetch` tools are available. The remote server uses Streamable HTTP;
[Codex MCP configuration](https://developers.openai.com/codex/mcp) describes the
host settings. No Parallel authorization header is needed for anonymous use.

Try this task with the calling agent:

```text
Plan a migration from asyncio.wait_for to asyncio.timeout in this project.
Inspect the repository's Python version, timeout handling, and tests first.
Use Parallel's web_search to find current Python documentation on timeout
semantics, then web_fetch to read the relevant official pages. Summarize the
relevant findings with their source URLs. Include that summary in the goal sent
to muse_plan, pass observed repository facts in repo_signals, and use
mode="normal" and search_mode="off" for this call. Evaluate Muse's finalists,
choose one bounded action, and run the repository's relevant tests.
```

The host agent chooses and passes the research; Muse does not automatically read
other servers' tool results. Put the selected public findings and URLs in `goal`,
not extra fields in `repo_signals`. Explicit `search_mode="off"` avoids a second
search through Muse's internal providers for this workflow. Adding the companion
server does not change Muse's search defaults or saved provider choices.

Send only public research queries to Parallel, and review fetched text as
untrusted evidence. Keep secrets and private repository content out of queries.
The goal and selected findings are also sent to Muse's configured live provider;
follow the [Security policy](SECURITY.md) when choosing what to share.

## Expected Output

The MCP tool returns JSON-safe finalists and advisory routing data. When live
configuration is missing or invalid, it returns `stopped_reason:
"configuration_error"` with a structured error and no finalists instead of
making provider calls.

Quality warnings and the quality action policy are planning signals. An agent can
add repository signals, choose another finalist, or request `mode: "extensive"`,
then still verify the work in the repository.

## Privacy and Live Configuration

Public MCP usage is live-only. When `provider_mode` is omitted, Muse uses the
agent-host default and falls back to `live_openai`. Configure real values only in
the local shell or agent-host environment; never commit API keys, local `.env`
files, private traces, or raw provider responses containing credentials.

Use [.env.example](.env.example) for safe environment-variable names and
[openai-pricing.example.json](openai-pricing.example.json) for the local pricing
override schema. Review the [Security policy](SECURITY.md) before enabling live
providers or search providers.

## Quality Evidence

Muse is a research prototype. Unit tests validate contracts and accounting, but
unit tests do not establish creative quality. Comparative claims need a direct
strong-model baseline, blinded pairwise judging, repeated runs, per-task
uncertainty, and complete cost, latency, and failure accounting.

## Quality Benchmark Library

`muse.quality_benchmark.run_quality_benchmark` supports repeated, blinded
comparisons against a direct strong-model baseline. A quality claim requires
per-task outcomes, uncertainty, cost, latency, and failure accounting.

## Roadmap

Muse is pre-1.0 open-source middleware for AI coding agents. The public product
path is live MCP planning; ongoing work strengthens the planning contracts,
agent guidance, quality evidence, and integrations without taking repository
observation or verification away from the calling agent.

## Contributing

Read the [Contributing guide](CONTRIBUTING.md) for development setup, testing,
quality evidence, and MCP-facing change expectations. Keep contributions
repo-agnostic, small, reviewable, and free of real secrets.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
```

Internal maintainer references: deterministic fixture tests, `muse compare`,
calibration review packets, and MCP smoke commands support protocol, regression,
or research work. They are not public onboarding commands. Maintainers can use
`muse-dogfood-quality` for live quality-gate evidence; it is distinct from the
agent-facing MCP workflow. The no-spend `muse-external-dogfood` command creates
a marked sample repository before a real project is initialized. Search-related
MCP smoke checks can use `--search-mode`, `--search-provider`, and
`--search-strict`; they remain maintainer tooling.

### Live branch evidence

For `provider_mode: "live_openai"`, `seed_count` requests an ordered schedule
of independent live model trajectories rather than one shared batched seed
response. The response records requested strategy directives and independently
completed seed branches in `config.branch_generation`.

The count covers only evidenced completed branches from the metered seed trace.
Evidence requires an ordered prefix of the strategy schedule, a complete
canonical branch directive with its exact instruction, non-empty structurally
valid nested request and response traces, and calls and token usage exactly
reconcile with the charged seeding spend record. A deterministic fixture result
does not prove a provider call. Its metadata can report modeled spend, while
`independent_call_count` remains zero without evidenced live branch calls.

## License

Muse is released under the [MIT License](LICENSE).
