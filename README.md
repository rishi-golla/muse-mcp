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

For host setup and agent-loop guidance, see the [MCP host guide](docs/integrations/mcp-agent-hosts.md)
and [Agent dogfood playbook](docs/integrations/agent-dogfood-playbook.md).

## Expected Output

The MCP tool returns JSON-safe finalists and advisory routing data. When live
configuration is missing or invalid, it returns `stopped_reason:
"configuration_error"` with a structured error and no finalists instead of
making provider calls.

Quality warnings and the quality action policy are planning signals. An agent can
add repository signals, choose another finalist, or request `mode: "extensive"`,
then still verify the work in the repository.

For a deterministic local proof that an agent loop can consume MCP output and
apply a bounded repair, see [Agent loop proof](docs/integrations/agent-loop-proof.md).

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

The quality benchmark is a library-first maintainer workflow, not a public CLI.
Read the [Benchmarking guide](docs/quality/benchmarking.md) before producing or
interpreting a quality claim.

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
does not prove a provider call; its metadata does not report provider calls or
spend.

## License

Muse is released under the [MIT License](LICENSE).
