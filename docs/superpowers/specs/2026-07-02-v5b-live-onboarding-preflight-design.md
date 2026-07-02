# V5-B Live Onboarding Preflight Design

## Goal

Reduce public Muse onboarding friction after V5-A made the MCP path live-only.
Users should not have to hand-create a pricing file before their first smoke
test, and agents should have a cheap local way to diagnose missing live config
without making provider calls.

## Decision

Add a live preflight layer that:

- uses a packaged default OpenAI pricing example when `OPENAI_PRICING_FILE` is
  omitted;
- still honors `OPENAI_PRICING_FILE` when callers need their own pricing table;
- validates `OPENAI_API_KEY`, selected model ids, pricing coverage, and search
  approval/key hints without exposing secrets;
- powers a `muse-mcp-doctor` command for editor/agent host setup checks;
- is reused by middleware so MCP live calls and doctor checks agree.

## Non-Goals

- No hosted API.
- No network validation call.
- No deterministic public mode.
- No automatic editing of user editor config.

## Public Behavior

- `muse-mcp-doctor --json` returns a JSON-safe report and exits `0` only when
  required live OpenAI config is valid.
- Missing pricing file env is not an error; bundled example pricing is used.
- Missing API key or model env vars are actionable errors.
- Invalid override pricing files remain errors.
