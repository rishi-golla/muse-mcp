# V5-C Host Config Generator Design

## Goal

Make Muse easier to connect to agent hosts after V5-A and V5-B. A user should
be able to ask Muse for the right MCP config snippet instead of reading several
static config-pack files and manually adapting them.

## Decision

Add a read-only `muse-mcp-config` command that prints copy-pasteable MCP config
for supported host shapes:

- `codex`: TOML snippet for Codex config.
- `claude-code`: JSON `.mcp.json` shape used by Claude-style project configs.
- `generic-json`: generic MCP client JSON shape.

The command does not edit files. It can include optional live OpenAI env
placeholders when `--include-env` is passed, and it can output a compact
installation note with `--format text`. Defaults stay provider-mode-free so the
runtime remains live-only through V5-A defaults.

## Non-Goals

- No automatic editor mutation.
- No hosted API.
- No deterministic public mode.
- No credential storage.

## Public Behavior

- `muse-mcp-config --host codex` prints TOML.
- `muse-mcp-config --host claude-code --include-env` prints JSON with redacted
  placeholder env values.
- `muse-mcp-config --host generic-json` prints JSON without env by default.
- The generated snippets include `muse-mcp` and `muse_plan`.
- Docs point users from doctor -> config generator -> smoke.
