# Evaluation Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make live evaluation recover from invalid 0-10 score outputs and preserve generated candidates when some evaluations fail.

**Architecture:** Keep the existing engine/provider split. The OpenAI provider repairs structured parse `ValidationError`s, while the engine treats evaluation failures as candidate-level failures and returns partial results with unevaluated candidates. The CLI summary becomes inspectable without changing trace storage.

**Tech Stack:** Python 3.12, Pydantic 2, OpenAI SDK fake client tests, pytest, Ruff.

---

## File Map

```text
src/creativity_layer/openai_schemas.py       Add explicit score field descriptions
src/creativity_layer/openai_provider.py      Repair parse ValidationError and improve repair prompt
src/creativity_layer/engine.py               Preserve unevaluated candidates and prefer scored finalists
src/creativity_layer/cli.py                  Add generated/unevaluated summary fields
tests/test_openai_provider.py                Provider repair regression for 0-10 scores
tests/test_engine.py                         Partial evaluation failure regressions
tests/test_cli.py                            Summary regressions for unevaluated candidates
tests/test_final_review.py                   Final regression for live evaluation robustness
```

## Shared Rules

- Do not silently normalize 0-10 scores to 0-1.
- Do not call live providers in normal tests.
- Do not weaken `EvaluationScores` or `OpenAIEvaluation`; the 0-1 contract stays strict.
- Preserve generated candidates with `scores=None` when evaluation fails.
- Prefer scored candidates as finalists. Use unevaluated candidates as finalists only when no scored candidates exist.
- Error messages must be secret-safe and must not include prompts, API keys, raw requests, or raw responses.

## Task 1: OpenAI Evaluation Repair

**Files:**
- Modify: `src/creativity_layer/openai_schemas.py`
- Modify: `src/creativity_layer/openai_provider.py`
- Modify: `tests/test_openai_provider.py`

- [ ] **Step 1: Write failing provider repair test**

Add this test to `tests/test_openai_provider.py` near existing repair tests:

```python
def invalid_openai_evaluation_error() -> ValidationError:
    with pytest.raises(ValidationError) as error:
        OpenAIEvaluation(
            originality=9.7,
            usefulness=8.4,
            coherence=9.2,
            feasibility=7.6,
            user_fit=9.1,
        )
    return error.value


def test_evaluation_parse_validation_error_triggers_repair() -> None:
    frame = FramedTask(
        context=TaskContext(goal="Design an interactive portfolio."),
        assumptions=("3D should support the content",),
        obvious_solution="Use a normal animated portfolio.",
    )
    candidate = sample_openai_idea(title="Living Atlas Portfolio").to_seed()
    client = FakeOpenAIClient(
        parsed_sequence=[
            invalid_openai_evaluation_error(),
            OpenAIEvaluation(
                originality=0.97,
                usefulness=0.84,
                coherence=0.92,
                feasibility=0.76,
                user_fit=0.91,
            ),
        ],
        usage=FakeUsage(input_tokens=100, output_tokens=25),
    )
    provider = build_provider(client, repair_attempts=1)

    response = provider.evaluate(candidate, frame)

    assert response.value.originality == 0.97
    assert response.calls == 2
    assert client.call_count == 2
    assert "0.0 and 1.0" in str(client.last_request["input"])
```

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_provider.py::test_evaluation_parse_validation_error_triggers_repair -v -p no:cacheprovider --basetemp=.pytest-tmp-task1-red
```

Expected: FAIL because `_execute_parse()` `ValidationError`s are treated as immediate provider failures instead of repairable structured-output failures.

- [ ] **Step 3: Add score descriptions**

In `src/creativity_layer/openai_schemas.py`, change `OpenAIEvaluation` fields to:

```python
class OpenAIEvaluation(OpenAIOutputModel):
    originality: float = Field(description="0.0 to 1.0 score, not 0 to 10.")
    usefulness: float = Field(description="0.0 to 1.0 score, not 0 to 10.")
    coherence: float = Field(description="0.0 to 1.0 score, not 0 to 10.")
    feasibility: float = Field(description="0.0 to 1.0 score, not 0 to 10.")
    user_fit: float = Field(description="0.0 to 1.0 score, not 0 to 10.")
```

Also import `Field` from `pydantic`.

- [ ] **Step 4: Repair parse `ValidationError`s**

In `src/creativity_layer/openai_provider.py`, update `_call_structured()` so `ValidationError` raised by `_execute_parse()` is handled like parsed-domain validation failures:

```python
            try:
                response = self._execute_parse(
                    model=model,
                    request_input=request_input,
                    schema=schema,
                )
            except ValidationError as error:
                last_error = error
                if attempt >= self._config.repair_attempts:
                    raise RuntimeError(
                        _safe_error_message(operation=operation, error=error)
                    ) from error
                request_input = _repair_request_input(
                    operation=operation,
                    domain_payload=domain_payload,
                    error=error,
                )
                continue
            except Exception as error:
                raise RuntimeError(
                    _safe_error_message(operation=operation, error=error)
                ) from error
```

Change `_repair_request_input()` signature to accept `error: ValueError | ValidationError`, and make the developer repair instruction explicit:

```python
"Repair attempt: the previous response could not be parsed into the required schema. "
"Return valid structured output only. Evaluation scores must be finite floats between "
"0.0 and 1.0, not percentages or 0-10 scores."
```

- [ ] **Step 5: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_provider.py -q -p no:cacheprovider --basetemp=.pytest-tmp-task1-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/openai_schemas.py src/creativity_layer/openai_provider.py tests/test_openai_provider.py
git commit -m "fix: repair invalid OpenAI evaluation scale"
```

## Task 2: Preserve Unevaluated Candidates

**Files:**
- Modify: `src/creativity_layer/engine.py`
- Modify: `tests/test_engine.py`

- [ ] **Step 1: Replace seed-batch hiding regression**

In `tests/test_engine.py`, replace `test_engine_hides_seed_batch_when_later_evaluation_fails` with:

```python
def test_engine_preserves_seed_candidates_when_later_evaluation_fails() -> None:
    provider = AdversarialProvider(raise_evaluation_at=2)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert len(result.all_candidates) == 2
    assert sum(candidate.scores is None for candidate in result.all_candidates) == 1
    assert len(result.finalists) == 1
    assert result.finalists[0].scores is not None
    assert [record.stage for record in result.spend_records] == [
        "framing",
        "seeding",
        "evaluation",
    ]
    assert result.errors[-1].stage == "evaluation"
    assert result.errors[-1].category == "provider_error"
    assert result.errors[-1].message == "provider operation failed"
    assert result.stopped_reason == "provider_error"
```

Add a second regression:

```python
def test_engine_returns_unevaluated_seed_candidates_when_all_evaluations_fail() -> None:
    provider = AdversarialProvider(raise_evaluation_at=1)

    result = build_engine(provider).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert len(result.all_candidates) == 2
    assert all(candidate.scores is None for candidate in result.all_candidates)
    assert len(result.finalists) == 1
    assert result.finalists[0].scores is None
    assert result.stopped_reason == "provider_error"
```

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_engine.py::test_engine_preserves_seed_candidates_when_later_evaluation_fails tests/test_engine.py::test_engine_returns_unevaluated_seed_candidates_when_all_evaluations_fail -v -p no:cacheprovider --basetemp=.pytest-tmp-task2-red
```

Expected: FAIL because the engine currently returns an empty candidate list on seed evaluation failure.

- [ ] **Step 3: Preserve partial seed evaluation results**

In `_seed_and_evaluate()`, change the evaluation loop to collect attributed candidates even when evaluation fails:

```python
            evaluated: list[IdeaGenome] = []
            had_evaluation_failure = False
            for candidate in seeds:
                attributed = _validated_candidate(
                    candidate,
                    branch_cost=seed_cost,
                    branch_latency=seed_latency,
                )
                result = self._evaluate(
                    attributed,
                    framed_task,
                    evaluation_quote,
                    reservation,
                    budget,
                    errors,
                    providers,
                )
                if result is None:
                    had_evaluation_failure = True
                    evaluated.append(attributed)
                    continue
                evaluated.append(result)
            return evaluated, "provider_error" if had_evaluation_failure else None
```

- [ ] **Step 4: Prefer scored finalists**

In `_result()`, select scored candidates first and use all candidates only when no scored candidates exist:

```python
        finalist_pool = tuple(candidate for candidate in candidates if candidate.scores is not None)
        if not finalist_pool:
            finalist_pool = candidates
        finalists = (
            self._population.select(
                finalist_pool,
                finalist_count=min(config.finalist_count, len(finalist_pool)),
            )
            if finalist_pool
            else ()
        )
```

- [ ] **Step 5: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_engine.py -q -p no:cacheprovider --basetemp=.pytest-tmp-task2-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/engine.py tests/test_engine.py
git commit -m "fix: preserve unevaluated candidates"
```

## Task 3: Safe Evaluation Diagnostics

**Files:**
- Modify: `src/creativity_layer/engine.py`
- Modify: `tests/test_engine.py`
- Modify: `tests/test_final_review.py`

- [ ] **Step 1: Write failing diagnostics regression**

Add to `tests/test_engine.py`:

```python
class InvalidEvaluationScaleProvider(DeterministicCreativeProvider):
    def evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
    ) -> MeteredResponse[EvaluationScores]:
        raise RuntimeError(
            "openai evaluate failed: score must be finite and between 0 and 1"
        )


def test_engine_records_safe_evaluation_scale_diagnostic() -> None:
    result = build_engine(InvalidEvaluationScaleProvider()).run(
        TaskContext(goal="Invent a new decision process."),
        RunConfig(
            max_cost_usd=1,
            max_calls=10,
            max_generations=0,
            seed_count=2,
            finalist_count=1,
            framing_reserve_usd=0,
            finalization_reserve_usd=0,
        ),
    )

    assert result.errors[-1].category == "validation_error"
    assert result.errors[-1].message == "provider returned evaluation scores outside 0..1"
    assert "Invent a new decision process" not in result.errors[-1].message
```

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_engine.py::test_engine_records_safe_evaluation_scale_diagnostic -v -p no:cacheprovider --basetemp=.pytest-tmp-task3-red
```

Expected: FAIL because the engine records a generic provider error.

- [ ] **Step 3: Add diagnostic classifier**

In `src/creativity_layer/engine.py`, add:

```python
def _evaluation_error_details(error: Exception) -> tuple[str, str]:
    message = str(error).lower()
    if "score must be finite and between 0 and 1" in message:
        return "validation_error", "provider returned evaluation scores outside 0..1"
    return "provider_error", "provider operation failed"
```

Use it in `_evaluate()` exception handling:

```python
        except Exception as error:
            category, message = _evaluation_error_details(error)
            _error(
                errors,
                stage="evaluation",
                provider=providers.evaluator.name,
                category=category,
                message=message,
                cost_incurred=False,
            )
            return None
```

- [ ] **Step 4: Add final regression**

Add to `tests/test_final_review.py`:

```python
def test_evaluation_scale_errors_are_safe_and_actionable() -> None:
    source = inspect.getsource(engine_module._evaluation_error_details)

    assert "provider returned evaluation scores outside 0..1" in source
    assert "score must be finite and between 0 and 1" in source
    assert "api_key" not in source.lower()
    assert "request_json" not in source
```

Import `creativity_layer.engine as engine_module` if missing.

- [ ] **Step 5: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_engine.py::test_engine_records_safe_evaluation_scale_diagnostic tests/test_final_review.py::test_evaluation_scale_errors_are_safe_and_actionable -q -p no:cacheprovider --basetemp=.pytest-tmp-task3-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/engine.py tests/test_engine.py tests/test_final_review.py
git commit -m "fix: classify evaluation scale failures"
```

## Task 4: CLI Partial Result Summary

**Files:**
- Modify: `src/creativity_layer/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI summary test**

Update `tests/test_cli.py` helper `make_result()` to accept `all_candidates: tuple[IdeaGenome, ...] | None = None` and pass `all_candidates if all_candidates is not None else finalists`.

Add:

```python
def test_cli_summarizes_unevaluated_generated_candidates(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    scored = make_candidate(title="Scored", scored=True)
    unevaluated = make_candidate(title="Unevaluated", scored=False)
    use_engine_result(
        monkeypatch,
        make_result(
            stopped_reason="provider_error",
            finalists=(scored,),
            all_candidates=(scored, unevaluated),
        ),
    )

    exit_code = run_cli(["Goal", "--trace-dir", str(tmp_path)])

    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert summary["generated_count"] == 2
    assert summary["unevaluated_count"] == 1
    assert summary["unevaluated_candidates"] == [{"title": "Unevaluated"}]
```

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli.py::test_cli_summarizes_unevaluated_generated_candidates -v -p no:cacheprovider --basetemp=.pytest-tmp-task4-red
```

Expected: FAIL because the summary does not include generated/unevaluated fields.

- [ ] **Step 3: Add summary fields**

In `_save_and_print_summary()`, compute:

```python
    unevaluated_candidates = tuple(
        candidate for candidate in result.all_candidates if candidate.scores is None
    )
```

Add to summary JSON:

```python
                "generated_count": len(result.all_candidates),
                "unevaluated_count": len(unevaluated_candidates),
                "unevaluated_candidates": [
                    {"title": summary_value(candidate.title)}
                    for candidate in unevaluated_candidates
                ],
```

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_cli.py -q -p no:cacheprovider --basetemp=.pytest-tmp-task4-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/cli.py tests/test_cli.py
git commit -m "feat: summarize unevaluated candidates"
```

## Task 5: Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add README note**

In `README.md`, under live mode, add:

```markdown
Live summaries include `generated_count` and `unevaluated_count` so production-like
smoke tests can distinguish generation failures from evaluation failures.
```

- [ ] **Step 2: Run final checks**

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=creativity_layer --cov-report=term-missing -p no:cacheprovider --basetemp=.pytest-tmp-2da-final
.\.venv\Scripts\python.exe -m ruff check .
git diff --check origin/main...HEAD
```

Expected: all tests pass, Ruff passes, diff check exits 0.

- [ ] **Step 3: Commit docs**

```powershell
git add README.md
git commit -m "docs: document partial live summaries"
```
