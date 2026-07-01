# Agent Loop Proof Design

## Goal

Prove that a coding-agent-style workflow can call the `creative_plan` MCP tool, feed it repo signals, consume the operational contract, make one bounded code change, and verify that change in a separate sample repository.

## Current Problem

The MCP server and config packs prove that the tool can be exposed to agent hosts. They do not yet prove the end-to-end workflow the product is meant to support: an agent working in an arbitrary repo asks for planning help, receives JSON it can route into a decision, applies a small action, and reruns the narrowest verification command.

Manual smoke commands are useful, but they still leave a gap between "tool returns JSON" and "an agent loop can use that JSON while coding."

## Selected Design

Add a deterministic proof harness that creates a tiny external Python sample repo in a temp directory, observes a failing pytest command, calls the in-process FastMCP `creative_plan` tool with repo signals from that sample repo, applies one constrained repair, and reruns the same verification command.

The proof returns a structured result rather than only printing text. It includes the sample repo path, initial and final verification results, the MCP result summary, the repo signals sent to MCP, the selected finalist operational fields, and whether the proof passed.

The harness should call `build_mcp_server().call_tool("creative_plan", ...)` so tests exercise the MCP boundary rather than a direct Python shortcut.

## Boundaries

- No live OpenAI calls, Exa calls, Brave calls, or network access.
- No agent host automation or global MCP config writes.
- No replacement CLI product surface; any command is only a local proof runner.
- No hardcoded user repository assumptions. The sample repo is created under a caller-provided or temporary directory.
- No generic "analyze logs and retry" acceptance. The proof must show repo signals, a bounded action, and a repeated verification command.

## Files

- `src/creativity_layer/agent_loop_proof.py`: sample repo creator, verification runner, MCP caller, bounded repair, and structured proof result.
- `tests/test_agent_loop_proof.py`: tests the failing sample, MCP call path, bounded repair, and proof output.
- `docs/integrations/agent-loop-proof.md`: explains how to run and interpret the proof.
- `README.md`: links the MCP integration section to the proof doc.
- `pyproject.toml`: optionally registers `creativity-layer-agent-proof` as a proof-only console script.

## Validation

Tests should verify that the sample repo starts failing, the proof calls the FastMCP tool, the MCP output includes deterministic context tags, the repair touches only the intended sample file, and the final pytest command passes.

Final branch verification should include the full pytest suite, coverage gate, Ruff, and `git diff --check`.

## Spec Self-Review

- The scope is a proof harness, not middleware hosting or agent config installation.
- The design remains repo-agnostic because the sample repo is external and generated.
- The MCP boundary is explicit and testable.
- The proof is deterministic and cheap enough for normal development.
