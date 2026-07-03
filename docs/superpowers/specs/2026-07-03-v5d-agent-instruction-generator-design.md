# V5-D Agent Instruction Generator Design

## Goal

After a user connects the Muse MCP server to an agent host, the agent still
needs clear project instructions for when to call `muse_plan` and how to use the
result. V5-D adds a read-only generator for those instructions.

## Decision

Add `muse-agent-instructions`, a CLI that prints copy-pasteable instruction
blocks for:

- `agents-md`: a project `AGENTS.md` section.
- `cursor-rules`: a Cursor rules section.
- `claude-project`: Claude-style project instructions.
- `generic`: a host-neutral prompt block.

The generated text must stay aligned with Muse's middleware posture:

- call `muse_plan` for creative planning, failed verification recovery,
  architecture alternatives, and workflow design;
- pass observed repo facts through `repo_signals`;
- do not ask Muse to crawl the repo;
- do not treat finalists as applied code;
- always run repository-owned verification;
- use `quick`, then escalate to `standard` or `deep` only when justified;
- keep public usage live-only and avoid deterministic provider instructions.

## Non-Goals

- No automatic edits to user projects.
- No hosted API.
- No deterministic public mode.
- No replacement for the MCP server or agent host configuration.

## Public Behavior

- `muse-agent-instructions --target agents-md` prints an `AGENTS.md`-ready block.
- `muse-agent-instructions --target cursor-rules` prints Cursor-friendly rules.
- `muse-agent-instructions --target generic --format json` returns JSON with
  `target`, `recommended_file`, and `content`.
- README and MCP host docs reference the generator after `muse-mcp-config`.
