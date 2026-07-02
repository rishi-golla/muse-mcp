# Agent Dogfood Ergonomics Design

## Goal

Make the MCP integration practical for real coding-agent dogfooding by adding cheap effort presets, explicit agent guidance in MCP results, and a short playbook for using muse during normal coding in a separate repository.

## Current Problem

The MCP server works, and the agent-loop proof validates the controlled path. The default MCP request is still awkward for daily agent use:

- The default request explores more than a cheap dogfood call needs.
- Agents must infer how to consume finalists from documentation instead of a top-level guidance contract.
- The smoke runner does not expose a simple "quick vs deep" shape.
- The docs explain setup but not when an agent should call the tool inside a coding loop.

## Selected Design

Add a provider-neutral `effort` preset to `CreativePlanRequest` with three values:

- `quick`: cheap default for normal coding loops, using 2 seeds, 1 finalist, 0 generations, and a low budget.
- `standard`: current-ish exploratory default, using 4 seeds, 2 finalists, 1 generation, and the existing moderate budget.
- `deep`: deliberate escalation, using more seeds/finalists/generations and a larger bounded budget.

If callers explicitly provide `budget_usd`, `seed_count`, `finalist_count`, or `max_generations`, those values win over the preset. This keeps existing callers stable while making omitted MCP arguments cheap.

Add a top-level `agent_guidance` object to middleware/MCP results. It should tell agents the result is advisory planning middleware, list a recommended agent loop, require verification before edits are trusted, and include when to escalate from quick to deeper effort.

Update the MCP smoke runner with `--effort`, and add a dogfood playbook that explains before-edit, after-failure, and after-fix call points.

## Boundaries

- No hosted service or custom HTTP API.
- No automatic repository crawling.
- No agent-host mutation or config writes.
- No live OpenAI calls in normal tests.
- No Brave/Exa research integration in this slice.

## Files

- `src/muse/middleware.py`: effort presets, resolved defaults, `agent_guidance` serialization.
- `src/muse/mcp_server.py`: expose `effort` in the MCP tool signature and description.
- `src/muse/mcp_smoke.py`: add `--effort`.
- `tests/test_middleware.py`: effort defaults, override behavior, guidance contract.
- `tests/test_mcp_server.py`: MCP signature behavior and guidance presence.
- `tests/test_mcp_smoke.py`: smoke runner passes effort.
- `docs/integrations/agent-dogfood-playbook.md`: dogfood usage guide.
- `README.md` and `docs/integrations/mcp-agent-hosts.md`: link the playbook and mention effort presets.

## Validation

Tests must prove that quick is the default, standard/deep resolve expected budgets and generation counts, explicit caller values override presets, MCP results include `agent_guidance`, the smoke runner forwards `--effort`, and docs link to the playbook.

## Spec Self-Review

- The scope stays within MCP/middleware ergonomics.
- Defaults become cheaper without removing deeper operation.
- The change remains repo-agnostic because repo facts still enter through `repo_signals`.
- The result contract is additive except for cheaper omitted defaults.
