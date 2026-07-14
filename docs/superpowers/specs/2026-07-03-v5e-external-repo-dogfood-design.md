# V5-E External Repo Dogfood Design

## Goal

Make Muse easy to validate in a separate repository before a user wires it into
their real coding workflow. This slice adds a read-only dogfood command that
creates a throwaway external repo, installs Muse MCP onboarding artifacts into
that repo, and reports whether the live OpenAI environment is ready.

## Non-goals

- Do not add another provider mode.
- Do not spend live provider budget by default.
- Do not crawl or modify the user's real repository.
- Do not turn Muse into a replacement CLI for coding agents.

## User flow

1. User installs Muse.
2. User runs `muse-external-dogfood --workspace <path>`.
3. Muse creates a marked sample repo outside the Muse checkout.
4. Muse writes MCP host config and agent instructions into that sample repo.
5. Muse runs the same live preflight checks used by `muse-mcp-doctor`.
6. Muse prints a JSON-safe report with next steps for trying the MCP from an
   agent host.

## Design

The command defaults to a no-spend proof. It verifies that Muse can produce the
files a real repo needs, but it does not call `muse_plan` unless a future slice
explicitly adds a live smoke option.

Generated artifacts:

- `.muse-external-dogfood` marker
- `pyproject.toml`
- `src/retry_policy.py`
- `tests/test_retry_policy.py`
- MCP host config, usually `.mcp.json`
- agent instruction document, usually `AGENTS.md`

The dogfood workspace is protected by a marker file. Existing directories are
only replaced when they already contain the marker, preventing accidental
destructive behavior in a real project directory.

## Output contract

The report includes:

- `workspace`
- `host`
- `instruction_target`
- `created_files`
- `host_config_path`
- `instructions_path`
- `doctor_status`
- `pricing_source`
- `mcp_smoke_status`
- `ready_for_manual_agent_test`
- `next_steps`

## Acceptance criteria

- A pure Python API creates a marked external repo and returns a JSON-safe
  report.
- The CLI prints JSON and exits successfully for artifact generation even when
  OpenAI secrets are missing.
- `--strict-live` exits non-zero when the live preflight is not ready.
- The command is exposed as `muse-external-dogfood`.
- Public dogfood output does not mention deterministic provider mode.
- README and agent host docs describe how to use the command before wiring Muse
  into a real repository.
