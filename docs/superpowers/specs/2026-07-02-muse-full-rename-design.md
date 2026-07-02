# Muse Full Rename Design

## Goal

Make Muse the only public project, package, CLI, and MCP identity throughout the
active codebase, tests, docs, CLI entry points, and MCP host examples.

## Scope

This is a breaking rename. The canonical Python package becomes `muse`, the
canonical distribution name becomes `muse`, and the canonical commands become
`muse`, `muse-mcp`, `muse-mcp-smoke`, `muse-agent-proof`, and
`muse-dogfood-quality`.

The MCP planning tool name also becomes `muse_plan` so host configs read as
Muse end to end.

Historical design and plan documents under `docs/superpowers` should also be
rewritten so repository search no longer surfaces the old name. The local
checkout directory and GitHub repository URL may still contain the old name
until the repository itself is renamed outside this code change.

## Non-Goals

- No compatibility aliases for the old package or commands.
- No behavior changes to the engine, middleware, providers, search, or quality
  policy.
- No repository remote rename in this branch.

## Verification

Tests must prove:

- `import muse` works.
- `muse` CLI parser reports `usage: muse`.
- `muse-mcp-smoke` works through the installed console script.
- FastMCP exposes `muse_plan`.
- Repository search no longer finds pre-rename product, package, or MCP tool
  identifiers in tracked active files after the rename.
