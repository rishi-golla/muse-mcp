# V4-F Agent Handoff Design

## Problem

V4-C through V4-E expose useful host signals, but a normal coding agent still
has to interpret several fields together: `quality_action_policy`,
`suggested_next_call`, `finalists`, `errors`, and `stopped_reason`. That is
extra host glue and makes integrations inconsistent.

## Design

Add a compact top-level `agent_handoff` object to every `creative_plan`
response. Mirror the same object in `agent_guidance.agent_handoff`.

The handoff is advisory and does not execute provider calls, apply code, or skip
repository verification. It answers four host questions:

- Is this response usable for the next agent step?
- Should the host use the current finalist or retry `creative_plan`?
- Which finalist should the host inspect first?
- Which action should the host take next?

Normal responses should derive the handoff from existing fields:

- `status`: `ready`, `review`, `retry_recommended`, or `blocked`.
- `recommended_action`: `apply_current_finalist`, `review_current_finalist`,
  `retry_creative_plan`, or `fix_configuration`.
- `use_current_finalist`: `true` only when a current finalist is safe to use as
  advisory planning input.
- `selected_finalist_id`: first finalist id when present, otherwise `null`.
- `suggested_next_call_available`: whether V4-E produced a follow-up call.
- `verification_required`: always `true`.

Configuration errors should return a blocked handoff with
`recommended_action: fix_configuration` and no selected finalist.

## Scope

Modify:

- `src/creativity_layer/middleware.py`
- `tests/test_middleware.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_config_packs.py`
- `docs/integrations/agent-dogfood-playbook.md`

Do not add automatic retries, HTTP APIs, repo crawling, or provider-specific
host behavior.
