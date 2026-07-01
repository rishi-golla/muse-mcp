# Agent Dogfood Playbook

This playbook is for using creativity-layer while coding normally in another repository. The integration surface is the MCP tool `creative_plan`; CLI commands are only smoke tests.

## Effort Presets

- `quick`: default for normal coding loops. Cheap, one finalist, no generations.
- `standard`: use after the first verification failure or when repo context is ambiguous.
- `deep`: use before high-impact edits, architecture choices, or repeated failure loops.

Explicit values such as `budget_usd`, `seed_count`, `finalist_count`, and `max_generations` override the preset for that call.

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
