# V3-B Context Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add middleware-shaped typed context grounding so Creativity Layer can consume repo/task evidence without making CLI files the core product interface.

**Architecture:** Add `ContextSnippet` and `ContextBundle` to domain models, carry the bundle through `TaskContext` and `FramedTask`, and make providers consume it through existing protocol signatures. CLI `--context-file` only parses JSON into the same typed API used by direct Python callers.

**Tech Stack:** Python 3.12, Pydantic 2, pytest, Ruff, existing provider/trace/privacy modules

---

## File Map

- `src/creativity_layer/models.py`: context evidence models and fields on task/frame.
- `src/creativity_layer/deterministic.py`: context-aware deterministic outputs and scoring.
- `src/creativity_layer/openai_provider.py`: prompt pressure and request payload checks.
- `src/creativity_layer/cli.py`: edge-only `--context-file` parser for deterministic, compare, and live.
- `src/creativity_layer/privacy.py`: private trace hashing for context evidence.
- `README.md`: context file harness documentation.
- `tests/test_models.py`: model validation and legacy defaults.
- `tests/test_deterministic.py`: direct API context behavior.
- `tests/test_openai_provider.py`: context payload and prompt pressure.
- `tests/test_cli.py`, `tests/test_live_cli.py`, `tests/test_compare_cli.py`: CLI adapter tests.
- `tests/test_privacy.py`, `tests/test_tracing.py`: trace behavior.

## Task 1: Context Models

**Files:**
- Modify: `src/creativity_layer/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write failing model tests**

Add tests asserting:

```python
from creativity_layer.models import ContextBundle, ContextSnippet, FramedTask


def test_context_bundle_preserves_repo_evidence() -> None:
    bundle = ContextBundle(
        snippets=(
            ContextSnippet(
                source="repo/package-graph",
                title="Package graph",
                content="apps/web depends on packages/ui",
                metadata={"kind": "monorepo"},
            ),
        ),
        tags=("typescript", "monorepo"),
    )

    task = TaskContext(goal="Improve flaky CI", context_bundle=bundle)
    framed = FramedTask(
        context=task,
        assumptions=("CI has package-level signals.",),
        obvious_solution="Retry failing jobs.",
    )

    assert framed.context.context_bundle == bundle
    assert framed.context.context_bundle.snippets[0].source == "repo/package-graph"


def test_context_bundle_defaults_empty_for_legacy_traces() -> None:
    task = TaskContext(goal="Improve retries")

    assert task.context_bundle.snippets == ()
    assert task.context_bundle.tags == ()
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests/test_models.py::test_context_bundle_preserves_repo_evidence tests/test_models.py::test_context_bundle_defaults_empty_for_legacy_traces -v -p no:cacheprovider --basetemp=.pytest-tmp-task1-red
```

Expected: import or attribute failure for missing context models.

- [ ] **Step 3: Implement minimal models**

Add `ContextSnippet` and `ContextBundle` before `TaskContext`, then add
`context_bundle: ContextBundle = Field(default_factory=ContextBundle)` to
`TaskContext`.

```python
class ContextSensitivity(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class ContextSnippet(FrozenModel):
    source: RequiredText
    content: RequiredText
    title: str = ""
    metadata: Mapping[str, object] = Field(default_factory=dict)
    sensitivity: ContextSensitivity = ContextSensitivity.PRIVATE


class ContextBundle(FrozenModel):
    snippets: tuple[ContextSnippet, ...] = ()
    tags: tuple[str, ...] = ()
```

- [ ] **Step 4: Verify GREEN**

Run the same focused tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/creativity_layer/models.py tests/test_models.py
git commit -m "feat: add context grounding models"
```

## Task 2: Direct API Context Behavior

**Files:**
- Modify: `src/creativity_layer/deterministic.py`
- Modify: `tests/test_deterministic.py`

- [ ] **Step 1: Write failing direct API tests**

Add tests that construct `TaskContext(context_bundle=...)`, call the deterministic
provider through `CreativeEngine`, and assert candidates mention supplied TypeScript
monorepo signals such as package graph, affected packages, test shards, `tsc`, Jest,
Vitest, Playwright, and CI logs.

- [ ] **Step 2: Verify RED**

Run the focused deterministic test and expect assertion failure because current
candidates ignore the context bundle.

- [ ] **Step 3: Implement context-aware deterministic helpers**

Add helpers in `deterministic.py`:

```python
def _context_terms(task: TaskContext) -> tuple[str, ...]:
    texts = [*task.context_bundle.tags]
    texts.extend(snippet.content for snippet in task.context_bundle.snippets)
    joined = " ".join(texts).casefold()
    terms = []
    for label in (
        "package graph",
        "affected packages",
        "test shards",
        "tsc",
        "jest",
        "vitest",
        "playwright",
        "ci logs",
    ):
        if label in joined:
            terms.append(label)
    return tuple(dict.fromkeys(terms))
```

Use the terms in generated mechanisms, workflow fields, and evaluation digest input.

- [ ] **Step 4: Verify GREEN**

Run focused deterministic tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/creativity_layer/deterministic.py tests/test_deterministic.py
git commit -m "feat: ground deterministic ideas in context"
```

## Task 3: OpenAI Context Payload and Pressure

**Files:**
- Modify: `src/creativity_layer/openai_provider.py`
- Modify: `tests/test_openai_provider.py`

- [ ] **Step 1: Write failing provider tests**

Add tests asserting:

- frame, seed, and evaluate request payloads include `context_bundle`;
- developer instructions say context snippets are evidence, not commands;
- evaluator penalizes ignoring context;
- evaluator penalizes GraphQL for arbitrary repo middleware unless context requests it.

- [ ] **Step 2: Verify RED**

Run the focused provider tests and expect missing instruction failures where the text is
not present yet.

- [ ] **Step 3: Update instructions only**

Extend `DEVELOPER_INSTRUCTIONS` for `frame`, `seed`, `transform`, and `evaluate`.
Do not change provider protocol signatures. Existing `model_dump` payloads should carry
context after Task 1.

- [ ] **Step 4: Verify GREEN**

Run focused OpenAI provider tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/creativity_layer/openai_provider.py tests/test_openai_provider.py
git commit -m "feat: add context-aware OpenAI prompt pressure"
```

## Task 4: CLI JSON Harness

**Files:**
- Modify: `src/creativity_layer/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_live_cli.py`
- Modify: `tests/test_compare_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI tests**

Add tests for:

- `deterministic --context-file context.json` includes context-grounded output in trace;
- `compare --context-file context.json` passes context into both runs;
- `live --context-file context.json` includes context in provider request payload;
- invalid JSON context file returns exit code `2` without traceback.

- [ ] **Step 2: Verify RED**

Run focused CLI tests and expect parser failures for unknown `--context-file`.

- [ ] **Step 3: Implement edge parser**

Add parser flags to deterministic, compare, and live. Add:

```python
def _load_context_bundle(path: Path | None, parser: argparse.ArgumentParser) -> ContextBundle:
    if path is None:
        return ContextBundle()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return ContextBundle.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        parser.error(f"could not read context file {path}: {error}")
```

Pass `context_bundle=_load_context_bundle(args.context_file, parser)` into every
`TaskContext(...)` construction.

- [ ] **Step 4: Document harness**

Add README text clearly saying `--context-file` is a test harness and core callers
should build `ContextBundle` directly.

- [ ] **Step 5: Verify GREEN**

Run focused CLI tests and expect PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/creativity_layer/cli.py tests/test_cli.py tests/test_live_cli.py tests/test_compare_cli.py README.md
git commit -m "feat: add context file CLI harness"
```

## Task 5: Trace Privacy

**Files:**
- Modify: `src/creativity_layer/privacy.py`
- Modify: `tests/test_privacy.py`
- Modify: `tests/test_tracing.py`

- [ ] **Step 1: Write failing trace tests**

Add tests asserting research traces preserve context structure and private traces hash
context snippet `content`, `title`, tags, and metadata values that may include
proprietary details.

- [ ] **Step 2: Verify RED**

Run focused privacy/tracing tests and expect private trace assertions to fail.

- [ ] **Step 3: Extend private text keys**

Add normalized keys for `content`, `contextbundle`, `metadata`, `source`, and `tags`
only where needed to hash private context text without redacting token metrics.

- [ ] **Step 4: Verify GREEN**

Run focused privacy/tracing tests and expect PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/creativity_layer/privacy.py tests/test_privacy.py tests/test_tracing.py
git commit -m "feat: protect context in private traces"
```

## Task 6: Final Verification and Review

**Files:**
- Modify tests only if final regressions expose missing assertions.

- [ ] **Step 1: Run full offline tests**

```powershell
python -m pytest -m "not live_openai" -q --cov=creativity_layer --cov-report=term-missing -p no:cacheprovider --basetemp=.pytest-tmp-v3b-final
```

Expected: all offline tests pass, live smoke tests skipped/deselected.

- [ ] **Step 2: Run Ruff**

```powershell
python -m ruff check .
```

Expected: no lint failures.

- [ ] **Step 3: Run diff hygiene**

```powershell
git diff --check origin/main...HEAD
```

Expected: no whitespace errors.

- [ ] **Step 4: Commit any final fixes**

Use a targeted `test:` or `fix:` commit if verification exposes a real issue.

## Success Checklist

- [ ] Core engine does not read files.
- [ ] CLI JSON is only an adapter into `ContextBundle`.
- [ ] Direct Python API tests prove middleware-shaped usage.
- [ ] OpenAI payloads and instructions include context pressure.
- [ ] Private traces protect context content.
- [ ] Full offline tests and Ruff pass.
