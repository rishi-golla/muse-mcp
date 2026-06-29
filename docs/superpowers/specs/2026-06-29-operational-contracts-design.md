# V3-A Operational Contracts Design

## Goal

Make live creativity-layer outputs useful as backend planning artifacts for AI
agents, not just high-level idea briefs. Each generated idea will carry a
structured operational contract that describes what an agent needs, what it
returns, how it acts, where it integrates, how it verifies work, and how it can
fail.

## Product Boundary

This slice does not build middleware, add web search, or add persistent memory.
It improves the artifact shape and scoring pressure so a future middleware/API
layer can consume ideas without inventing missing execution semantics.

## Operational Contract

Add these fields to `IdeaGenome`:

- `inputs_required`: concrete input artifacts the agent or backend must provide.
- `outputs_produced`: structured outputs the idea returns to downstream agents.
- `agent_workflow`: ordered action loop the agent should follow.
- `decision_policy`: rule text for choosing actions, stopping, or escalating.
- `integration_points`: where the idea plugs into an agent workflow or repo.
- `verification_strategy`: how the agent proves the chosen action worked.
- `failure_modes`: expected ways the approach can fail or mislead.

The domain model will keep backward compatibility by defaulting tuple fields to
empty tuples and string fields to an empty string. Live OpenAI schemas will make
the contract required so new live outputs cannot omit it.

## Generation Pressure

OpenAI seed and transform prompts will require operational specificity:

- avoid generic phrases such as "analyze logs and retry smarter" unless backed
  by a concrete workflow and decision policy;
- avoid arbitrary stack choices such as GraphQL, Redis, or Kubernetes unless the
  task asks for them or the candidate justifies them as optional integration
  details;
- fit the task domain explicitly, such as TypeScript monorepo package graphs,
  affected packages, `tsc`, Jest, Vitest, Playwright, and CI shards when the
  prompt asks about flaky TypeScript CI;
- remain repo-agnostic when the prompt says arbitrary repos.

## Evaluation Pressure

Extend evaluation scoring with two new dimensions:

- `operational_specificity`: whether the candidate can be executed by an agent
  without a human inventing the interface or loop.
- `workflow_fit`: whether the candidate fits the prompt's workflow and avoids
  arbitrary technology choices.

Selection will account for these dimensions so plausible but shallow ideas do
not win purely on originality/usefulness. Population ranking should prefer
candidates that balance originality, usefulness, operational specificity, and
workflow fit.

## Deterministic Provider

The deterministic provider remains a local fixture but must populate the
contract fields so traces, CLI output, and tests exercise the full shape. It
does not need to become semantically intelligent.

## Tests

Regression tests should encode the observed live failures:

- a shallow retry idea that only says "analyze logs and retry" is not
  operationally specific;
- a GraphQL middleware idea loses workflow fit for "backend middleware for agent
  task planning in arbitrary repos" when GraphQL is not requested;
- a TypeScript monorepo CI idea should mention package graph, affected packages,
  test shards, and TypeScript test/build signals in the operational contract.

## Compatibility

Existing traces without the new fields should still load into `IdeaGenome`
because domain defaults are backward-compatible. New OpenAI responses must
include the fields, and traces should serialize them like other idea fields.
