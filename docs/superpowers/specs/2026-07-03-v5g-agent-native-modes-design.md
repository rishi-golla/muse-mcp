# V5-G Agent-Native Modes Design

## Goal

Make Muse feel like backend planning middleware instead of a CLI workflow. A
human should give the agent only a broad goal; the agent should gather repo
facts and call `muse_plan` with a simple mode.

## User-facing behavior

Normal user flow:

1. User runs `muse-project-init` once in a repo.
2. User asks Codex, Cursor, or another MCP host for a creative/planning task.
3. The agent observes repo state and calls Muse MCP in the backend.
4. Muse uses live OpenAI and returns planning output.
5. The agent applies the useful planning output to its normal workflow.

Users should not manually type repo-language flags, seed counts, finalist
counts, generation counts, or budget values.

## Agent-facing modes

Expose two public modes:

- `normal`: default for most planning and creative-thinking calls. Internally
  maps to the existing standard run shape: 4 seeds, 2 finalists, 1 generation,
  bounded internal spend.
- `extensive`: for high-impact planning, ambiguous architecture choices, or
  repeated failed verification. Internally maps to the existing deep run shape:
  6 seeds, 3 finalists, 2 generations, higher bounded internal spend.

The engine can keep its lower-level configuration internally for tests and
future provider controls, but the MCP tool should guide agents toward `mode`,
not `budget_usd`, `seed_count`, `finalist_count`, or `max_generations`.

## MCP contract

`muse_plan` accepts:

- `goal`
- `repo_signals`
- `mode`
- `provider_mode` for internal/dev compatibility only
- `privacy`
- search policy fields
- context-size fields

It should not expose budget/seed/finalist/generation arguments in the public
tool signature.

## Instructions and docs

Generated agent instructions should tell the host agent to:

- call Muse automatically for creative planning, failed verification recovery,
  architecture alternatives, and workflow design;
- gather repo facts itself and pass them in `repo_signals`;
- use `mode: "normal"` by default;
- escalate to `mode: "extensive"` when verification keeps failing, context is
  ambiguous, or the task is high-impact;
- never ask the human to provide seed counts, budget, repo language flags, or
  other low-level run parameters.

Public docs should make `muse-project-init` the recommended test path. Smoke
commands can remain internal/dev tooling, but they should not be the main
onboarding flow.

## Acceptance criteria

- `CreativePlanRequest(goal=...)` defaults to `mode = normal` and resolves to
  the 4-seed standard run shape.
- `mode = extensive` resolves to the 6-seed deep run shape.
- MCP `muse_plan` supports `mode` and no longer exposes public budget/seed
  arguments.
- Agent guidance and suggested retry calls use `mode`, not effort.
- Generated instructions mention automatic Muse calls, repo-signal collection,
  `normal`, and `extensive`.
- README and MCP host docs emphasize `muse-project-init` and agent-native use
  instead of smoke-test commands.
