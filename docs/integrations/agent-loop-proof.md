# Agent Loop Proof

This proof is a deterministic local harness for validating the middleware-shaped workflow:

1. Create a tiny external Python repo with a failing pytest check.
2. Capture repo signals from that repo, including files, changed files, test command, CI-style failure text, language, and framework.
3. Call the `creative_plan` MCP tool through the in-process FastMCP server.
4. Consume the selected operational plan fields.
5. Apply one bounded repair to `retry_policy.py`.
6. Rerun the same verification command and report whether it passed.

It is not the product interface. The preferred integration surface remains MCP from an agent host. This command is only a cheap proof that the MCP output can sit inside a coding-agent loop.

## Run

```powershell
creativity-layer-agent-proof --workspace .agent-proof-tmp
```

The command prints JSON. A successful proof includes:

- `"passed": true`
- a failing `initial_verification`
- a passing `final_verification`
- `mcp_result.provider_mode` set to `deterministic`
- repo context tags such as `python` and `pytest`
- `selected_plan.agent_workflow`
- `selected_plan.verification_strategy`
- `repair.changed_files` set to `["retry_policy.py"]`

## What This Proves

The proof validates that an agent can use creativity-layer as a planning middleware instead of a replacement CLI:

- The agent owns repo observation.
- creativity-layer receives repo facts as generic signals.
- MCP returns JSON-safe operational planning fields.
- The agent chooses and applies a bounded repair.
- Verification is still performed by the agent with the repo's own test command.

## Limits

- It uses deterministic providers only.
- It does not call OpenAI, Exa, Brave, or the network.
- It does not install or mutate agent-host MCP configuration.
- It does not claim the generated idea is the final product behavior.

Use `docs/integrations/mcp-agent-hosts.md` when wiring the MCP server into a real agent host.
