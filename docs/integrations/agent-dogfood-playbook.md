# Agent Dogfood Playbook

This playbook is for using creativity-layer while coding normally in another repository. The integration surface is the MCP tool `creative_plan`; CLI commands are only smoke tests.

## Effort Presets

- `quick`: default for normal coding loops. Cheap, one finalist, no generations.
- `standard`: use after the first verification failure or when repo context is ambiguous.
- `deep`: use before high-impact edits, architecture choices, or repeated failure loops.

Explicit values such as `budget_usd`, `seed_count`, `finalist_count`, and `max_generations` override the preset for that call.

## Provider Posture

Normal dogfood runs should use the live-first MCP posture. If `provider_mode` is
omitted, the tool uses `CREATIVITY_LAYER_PROVIDER_MODE` and falls back to
`live_openai`. Use runtime defaults when your agent host should apply the same
settings to every call:

```powershell
$env:CREATIVITY_LAYER_PROVIDER_MODE = "live_openai"
$env:CREATIVITY_LAYER_EFFORT = "quick"
$env:CREATIVITY_LAYER_PRIVACY = "research"
$env:CREATIVITY_LAYER_BUDGET_USD = "0.25"
$env:CREATIVITY_LAYER_SEARCH_MODE = "off"
$env:CREATIVITY_LAYER_SEARCH_PROVIDER = "auto"
$env:CREATIVITY_LAYER_SEARCH_STRICT = "false"
```

The deterministic test provider is only for no-network CI, smoke tests, and
protocol checks. Use `--provider-mode deterministic` or
`CREATIVITY_LAYER_PROVIDER_MODE=deterministic` when you need that mode, but do
not judge creative quality from it.

## Opt-in Search Context

Search context is off by default. Use `search_mode: "light"` when a task would
benefit from bounded outside context, and `search_mode: "deep"` only before
important planning decisions where the extra latency and possible provider cost
are justified. Use `search_provider` to choose `auto`, `deterministic`, `exa`,
or `brave`. Use strict search only when the agent should fail closed instead of
continuing without search context. This is opt-in search, not repo crawling.

```powershell
$env:CREATIVITY_LAYER_SEARCH_MODE = "off"
$env:CREATIVITY_LAYER_SEARCH_PROVIDER = "auto"
$env:CREATIVITY_LAYER_SEARCH_STRICT = "false"
$env:CREATIVITY_LAYER_LIVE_SEARCH_APPROVED = "1"
```

`CREATIVITY_LAYER_LIVE_SEARCH_APPROVED=1` is required before live search
providers may be used. Without approval, the tool reports the skipped reason in
`search_context` and continues with the repo signals the agent supplied. If
`search_strict` or `CREATIVITY_LAYER_SEARCH_STRICT=true` is set, missing search
returns `configuration_error` and no finalists.

## V3-L quality runs

V3-L is the last V3 validation slice before V4 productization. It gives the team
a repeatable dogfood harness for the actual MCP path. Run it when changing
prompts, evaluator pressure, search policy, or agent guidance.

```powershell
creativity-layer-dogfood-quality `
  --provider-mode deterministic `
  --case agent-retry-python `
  --variant search-off `
  --json
```

Use `--variant search-light` and `--variant search-deep` to compare search
behavior against `search-off`. Add `--fail-on-gates` when a CI or release check
should fail if any run has quality gates:

```powershell
creativity-layer-dogfood-quality `
  --provider-mode live_openai `
  --variant search-off `
  --variant search-light `
  --variant search-deep `
  --fail-on-gates `
  --json
```

Deterministic output can intentionally fail quality gates. Treat that as a
protocol-quality check, not a creative-quality failure of the live engine.

## V4-B live prompt pressure

V4-B connects the live OpenAI provider prompts to the dogfood quality gates. The
live seed, transform, and evaluation instructions now name failures such as
`generic_title`, `generic_mechanism`, `missing_required_terms`, and
`missing_operational_field` before output is returned.

This is live prompt pressure, not proof that a run is high quality. Keep using
`creativity-layer-dogfood-quality` with live OpenAI when making product-quality
claims, and compare `search-off`, `search-light`, and `search-deep` when search
context is part of the decision.

## V4-C quality warning fields

V4-C surfaces advisory warning fields in every normal `creative_plan` response.
Use top-level `quality_warnings` and `quality_summary` to decide whether an
agent should ask for a stronger effort level, add more repo signals, or choose a
different finalist. Each finalist also includes `quality_warnings` so agents can
avoid generic options without running the separate dogfood CLI.

Warnings are not hard failures. They flag review pressure such as generic titles
or missing operational fields; the coding agent still owns the final judgment and
repository verification.

## V4-D quality action policy

V4-D adds `quality_action_policy` to `creative_plan` output and mirrors it inside
`agent_guidance`. The policy includes `status`, `escalate_effort_to`,
`recommended_actions`, and `warning_actions`.

Use it as routing guidance. If `status` is `needs_retry`, the agent should add
repo signals or request the recommended effort level before relying on the
finalist. If `escalate_effort_to` is set, the host may call `creative_plan`
again with that effort, but creativity-layer does not automatically spend that
budget.

## before-edit

Call `creative_plan` before editing when the task has multiple plausible approaches, unclear boundaries, or needs a repo-agnostic workflow idea.

```json
{
  "goal": "Design a bounded fix plan for the failing retry tests",
  "effort": "quick",
  "repo_signals": {
    "changed_files": ["src/agent/retry.py"],
    "test_commands": ["python -m pytest tests/test_retry.py"],
    "detected_languages": ["Python"],
    "detected_frameworks": ["pytest"]
  }
}
```

Use the returned `agent_guidance.recommended_agent_loop` as the route:

1. Observe repo state.
2. Pass current `repo_signals`.
3. Pick one bounded action from a finalist.
4. Run the narrowest relevant verification.
5. Stop or escalate based on verification.

## after-failure

Call `creative_plan` after a failed test when the next action is not obvious. Include the exact failing command and a sanitized CI or terminal log excerpt.

```json
{
  "goal": "Recover from failed tests after changing retry backoff behavior",
  "effort": "standard",
  "repo_signals": {
    "changed_files": ["src/agent/retry.py"],
    "test_commands": ["python -m pytest tests/test_retry.py -q"],
    "ci_logs": ["test_backoff_caps_at_30 failed: expected 30, got 64"],
    "detected_languages": ["Python"],
    "detected_frameworks": ["pytest"]
  }
}
```

Use `deep` only after repeated failures, broad architectural uncertainty, or when a wrong fix would be expensive to unwind.

## after-fix

Call `creative_plan` after a fix only when you need a verification strategy, follow-up risk review, or a safer next slice.

```json
{
  "goal": "Choose the next verification step after retry tests passed",
  "effort": "quick",
  "repo_signals": {
    "changed_files": ["src/agent/retry.py", "tests/test_retry.py"],
    "test_commands": ["python -m pytest tests/test_retry.py -q"],
    "ci_logs": ["2 passed"],
    "detected_languages": ["Python"],
    "detected_frameworks": ["pytest"]
  }
}
```

Treat finalists as planning options, not applied work. The agent still owns edits, safety checks, and repository verification.

## What To Pass As Repo Signals

Prefer concise facts the agent already observed:

- `file_paths`: relevant files or package manifests.
- `changed_files`: files already touched or likely to be touched.
- `test_commands`: exact commands available for verification.
- `ci_logs`: short sanitized failure excerpts.
- `dependency_hints`: package graph or ownership facts.
- `detected_languages`: languages in scope.
- `detected_frameworks`: test frameworks, build tools, UI frameworks, or CI tools.

Do not ask creativity-layer to crawl the repo. It should receive context from the agent workflow.
