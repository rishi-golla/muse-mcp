# V4-D Quality Action Policy Design

## Purpose

V4-C exposed quality warnings in normal MCP responses. V4-D makes those warnings
actionable for agent hosts. The goal is to tell an AI coding agent what to do
when output is generic, under-specified, or disconnected from supplied repo
signals.

## Scope

This slice adds advisory action guidance only. It does not reject finalists,
change ranking, spend live tokens, or force an automatic retry. Agent hosts keep
control of whether to escalate effort, pass more repo signals, run search, or
choose a different finalist.

## Design

Add a pure `quality_action_policy` helper in
`src/muse/quality_warnings.py`. The helper accepts the current
warning names and effort level, then returns a JSON-safe policy object:

- `status`: `clear`, `review`, or `needs_retry`.
- `escalate_effort_to`: `standard`, `deep`, or `null`.
- `recommended_actions`: ordered agent actions.
- `warning_actions`: per-warning remediation hints.

Middleware serialization will include this object as top-level
`quality_action_policy` and inside `agent_guidance`. Configuration-error
responses return a clear empty policy.

## Policy Rules

No warnings means `clear`. Missing operational fields or missing required terms
mean `needs_retry`, because the current output is likely not usable enough for
agent planning. Generic titles or mechanisms mean `review`, because a finalist
may still contain useful operational content but should not be accepted blindly.

Quick runs with warning pressure should recommend `standard`; standard runs with
warnings should recommend `deep`; deep runs should not recommend further effort
escalation.

## Testing

Tests cover the pure helper, middleware response shape, MCP structured output,
configuration-error shape, and documentation describing the action policy.
