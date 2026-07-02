# MCP Live Usability Design

## Goal

Make the MCP integration usable in a real coding-agent workflow by letting agents opt into live OpenAI runs safely and cheaply, while keeping deterministic mode as the default no-credentials path.

## Approach Options

1. Replace the MCP default with live OpenAI.
   This would make production testing feel real immediately, but it would break local agent startup when credentials, model IDs, or pricing files are absent.

2. Add explicit provider selection to the middleware and MCP tool.
   Agents can call `muse_plan` with `provider_mode: "deterministic"` or `provider_mode: "live_openai"`. This preserves the existing fast path and makes live usage explicit.

3. Build a larger daemon with persisted configuration.
   This may be useful later, but it introduces storage and lifecycle concerns before the MCP contract is fully proven.

## Selected Design

Use option 2. Add a provider mode field to the transport-neutral middleware request. The default remains deterministic. `live_openai` builds the existing `OpenAICreativeProvider` from environment variables, validates model pricing before provider calls, and uses the same cheap defaults already exposed through the MCP tool.

MCP should return structured, JSON-safe configuration errors instead of surfacing raw exceptions to the agent host. That lets an agent know whether it needs `OPENAI_API_KEY`, model IDs, or a pricing file before retrying.

## Components

- `muse.middleware`
  Adds provider mode validation, live OpenAI provider construction, pricing-file loading, and structured configuration-error output.

- `muse.mcp_server`
  Adds `provider_mode` and `privacy` tool parameters and delegates to the middleware.

- `muse.mcp_smoke`
  Adds a lightweight local smoke command that invokes the FastMCP server in-process. It verifies actual MCP tool registration and invocation without needing an agent host or a long-lived stdio session.

- `README.md`
  Documents deterministic MCP, live OpenAI MCP, cheap defaults, required environment variables, and the smoke command.

## Data Flow

1. Agent calls `muse_plan` with repo signals and optional `provider_mode`.
2. Middleware validates the request.
3. If mode is deterministic, the current local provider path runs.
4. If mode is live OpenAI, middleware loads credentials, model config, pricing, retry policy, and circuit breaker from environment.
5. Configuration failures return a structured response with `stopped_reason: "configuration_error"` and no finalists.
6. Provider failures still return engine-level errors in the normal run result.

## Non-Goals

- No automatic Brave or Exa research in MCP.
- No persisted server config.
- No HTTP server.
- No hidden credential discovery outside documented environment variables.
- No live network calls in normal tests.

## Testing

Tests should prove deterministic defaults stay unchanged, live mode reports missing environment as structured JSON, live provider construction uses the existing OpenAI provider path with fake injected dependencies, MCP exposes provider mode parameters, and the smoke harness calls the FastMCP server in-process.

## Spec Self-Review

- The design is transport-neutral and does not make MCP logic own provider orchestration.
- Live OpenAI is opt-in, so deterministic agent startup remains reliable.
- The scope is small enough for one implementation branch and does not pull search adapters into this slice.
