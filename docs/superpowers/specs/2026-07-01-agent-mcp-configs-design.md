# Agent MCP Config Packs Design

## Goal

Make creativity-layer easy to wire into real AI coding-agent hosts by shipping copyable MCP config packs, a focused integration guide, and tests that keep the examples syntactically valid.

## Current Problem

The MCP server exists and can be smoke-tested, but users still have to translate the command into each host's config shape. That increases the chance of broken setup, missing environment variables, or accidentally treating the CLI as the primary interface.

## Selected Design

Add repo-owned config templates for common MCP host shapes:

- Codex `config.toml` fragment using `[mcp_servers.creativity-layer]`.
- Project-scoped MCP JSON using `.mcp.json` shape for Claude Code style hosts.
- Generic `mcp.json` for JSON-based editor clients such as Cursor-style MCP clients.

Add a short integration guide explaining where each template belongs, how to install the package, how to run deterministic smoke tests, and how to opt into live OpenAI without committing secrets. The guide should cite the official docs used for the host-specific claims and be careful where a client-specific path is only a generic JSON-compatible template.

## Boundaries

- No new engine, provider, or MCP server behavior.
- No secrets, real API keys, or user-specific absolute paths.
- No automatic file copying into a user's global config.
- No paid live OpenAI calls in normal tests.
- No Brave/Exa research wiring in this slice.

## Files

- `docs/integrations/mcp-agent-hosts.md`: integration guide.
- `docs/integrations/config-packs/codex/config.toml`: Codex config fragment.
- `docs/integrations/config-packs/claude-code/.mcp.json`: Claude Code style project config.
- `docs/integrations/config-packs/generic-mcp/mcp.json`: generic JSON MCP client config.
- `tests/test_mcp_config_packs.py`: parses templates and checks command/tool/env conventions.
- `README.md`: links to the guide.

## Validation

Tests parse every JSON/TOML template, assert `creativity-layer-mcp` is the command, assert deterministic config does not require secrets, assert live env placeholders are present only as placeholder strings, and assert the guide links to the config packs.

## Spec Self-Review

- The scope is integration docs and templates only.
- The templates remain domain-general and agent-facing.
- Host-specific statements are constrained to docs verified during this slice.
