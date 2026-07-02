# MCP Server Design

## Goal

Expose muse to AI coding agents as an MCP tool they can call during normal planning and verification work, without making the CLI or a repo-specific script the primary integration surface.

## Approach Options

1. MCP server directly around `CreativeEngine`.
   This is fast, but it couples transport details to engine setup and would make a future HTTP or in-process middleware adapter repeat the same orchestration code.

2. Transport-neutral runner plus MCP adapter.
   This adds one small internal layer, but it gives agents a stable request and response contract while keeping MCP, HTTP, and direct library calls as replaceable transports.

3. Full middleware daemon with persistence and background jobs.
   This may be useful later, but it is too broad for the current slice because the engine contract still needs more real-world validation.

## Selected Design

Build option 2. The feature adds a `CreativeMiddlewareRunner` that accepts a goal, generic repo signals, context-provider settings, and a bounded run config. The runner returns JSON-safe planning output with finalists, operational contracts, context tags, generated candidate count, spend, stopped reason, and errors.

The MCP server is a thin adapter over that runner. It exposes one tool, `muse_plan`, over stdio. Agents pass current repo/task signals into the tool instead of asking muse to crawl arbitrary repositories. This keeps trust boundaries clear and avoids hardcoding repo shape, agent identity, or task type.

## Components

- `muse.middleware`
  Owns request and response models, default deterministic provider construction, context-provider invocation, run-config construction, and JSON-safe serialization.

- `muse.mcp_server`
  Owns MCP registration and stdio startup. It delegates all behavior to `CreativeMiddlewareRunner`.

- `pyproject.toml`
  Adds the MCP SDK dependency and a `muse-mcp` console script.

- `README.md`
  Documents MCP as the agent-facing integration path and keeps CLI examples framed as harnesses.

## Data Flow

1. Agent observes the current coding task and repository state.
2. Agent calls `muse_plan` with `goal`, optional `repo_signals`, and cheap bounded run settings.
3. MCP adapter validates the request and calls `CreativeMiddlewareRunner`.
4. Runner builds `TaskContext`, enriches it with `ContextBundle` via `DeterministicContextProvider`, runs `CreativeEngine`, and serializes the result.
5. Agent receives finalists with operational fields it can convert into its own plan, verification policy, or retry decision.

## Non-Goals

- No repository crawling inside the MCP server.
- No hardcoded TypeScript, GraphQL, portfolio, or retry-specific logic.
- No background daemon, durable memory, auth, or HTTP API in this slice.
- No automatic Brave/Exa research wiring in the MCP tool. Search adapters remain available for later context-provider slices.

## Error Handling

Invalid MCP input should fail validation before engine execution. Provider errors should be returned in the structured result exactly as engine errors, not hidden by the MCP adapter. The deterministic default must not require OpenAI keys, pricing files, Exa, Brave, or network access.

## Testing

Tests should cover the runner directly and the MCP tool function without launching a long-lived stdio process. They must verify that repo signals affect workflow output, the response is JSON-safe, defaults are cheap, and the MCP adapter delegates to the same runner path as direct middleware use.

## Spec Self-Review

- No placeholders remain.
- Scope is one adapter plus one reusable runner, not the whole future middleware platform.
- The design preserves the user requirement that muse integrate into agent workflows without becoming a CLI replacement.
