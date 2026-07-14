# V5-F Project Bootstrap Design

## Goal

Make Muse onboarding feel like a normal MCP setup flow: a user can run one
local command inside any repository and get the project files needed for an
agent host to call Muse.

## Context

V5-C generates host config snippets, V5-D generates agent instructions, and
V5-E proves those artifacts in a throwaway external repo. Users still have to
copy the files into their real projects by hand. This slice adds a safe project
initializer that writes those files directly to a chosen repository.

## Non-goals

- Do not run live model calls.
- Do not store real secrets.
- Do not mutate editor-global config.
- Do not crawl or inspect the target repo beyond checking file existence.
- Do not reintroduce public deterministic mode.

## Command

Add `muse-project-init`.

Default behavior:

- Target path defaults to the current directory.
- Host defaults to `generic-json`.
- Agent instructions default to `agents-md`.
- The command writes missing files and refuses to overwrite existing files.
- `--dry-run` previews planned files without writing.
- `--force` overwrites existing generated targets.
- `--strict-live` returns non-zero if live OpenAI preflight is not ready.

Supported generated files:

- `generic-json` and `claude-code`: `.mcp.json`
- `codex`: `.codex/config.toml`
- `agents-md`: `AGENTS.md`
- `cursor-rules`: `.cursor/rules/muse.mdc`
- `claude-project` and `generic`: `MUSE_INSTRUCTIONS.md`

## Output contract

The API returns a JSON-safe report with:

- `project_path`
- `host`
- `instruction_target`
- `dry_run`
- `planned_files`
- `written_files`
- `skipped_existing_files`
- `doctor_status`
- `ready_for_manual_agent_test`
- `next_steps`

## Safety rules

- Existing target files block writes unless `--force` is passed.
- Generated config may include env placeholders via `--include-env`, but never
  real values.
- No provider calls are made. Live readiness comes from local preflight checks.

## Acceptance criteria

- The API writes `.mcp.json` and `AGENTS.md` into a temp project.
- Dry-run mode reports planned files and writes nothing.
- Existing files are protected unless `--force` is used.
- Codex and Cursor target paths are supported.
- The CLI prints JSON and exposes `--strict-live`.
- README and MCP host docs mention `muse-project-init`.
