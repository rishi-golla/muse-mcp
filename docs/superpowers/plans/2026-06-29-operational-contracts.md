# V3-A Operational Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured operational contracts and stricter workflow-fit scoring so creativity-layer outputs are consumable by future agent middleware.

**Architecture:** Extend the domain idea model with backward-compatible contract fields, require those fields in live OpenAI idea schemas, and extend evaluation scores with operational dimensions. Keep provider boundaries intact: generation produces contracts, evaluation scores them, and population selection ranks them.

**Tech Stack:** Python 3.12, Pydantic 2, OpenAI structured-output schemas, pytest, Ruff.

---

## File Map

```text
src/creativity_layer/models.py             Add contract fields and score dimensions
src/creativity_layer/openai_schemas.py     Require/convert contract fields for live ideas and evaluations
src/creativity_layer/openai_provider.py    Strengthen generation/evaluation instructions
src/creativity_layer/deterministic.py      Populate contract fields in fixture ideas and deterministic scores
src/creativity_layer/population.py         Rank by operational dimensions
tests/test_models.py                       Backward compatibility and validation coverage
tests/test_openai_schemas.py               Required live schema fields and conversion coverage
tests/test_openai_provider.py              Prompt pressure coverage
tests/test_deterministic.py                Fixture contract coverage
tests/test_population.py                   Selection pressure coverage
tests/test_final_review.py                 Bad-example regression coverage
```

## Shared Rules

- Domain `IdeaGenome` stays backward-compatible with old traces.
- Live `OpenAIIdea` requires every operational contract field.
- Do not add middleware, web search, or a new CLI command in this slice.
- Do not weaken 0..1 score validation.
- Keep tests deterministic; no live provider calls in normal tests.

## Task 1: Domain Model Contract

**Files:**
- Modify: `src/creativity_layer/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write failing model tests**

Add tests to `tests/test_models.py`:

```python
def test_idea_genome_defaults_operational_contract_for_legacy_traces() -> None:
    idea = IdeaGenome(
        generation=0,
        title="Retry loop",
        core_mechanism="Use failure evidence before retrying.",
        problem_framing="Retries are too blind.",
        task_value="Agents recover with less wasted work.",
    )

    assert idea.inputs_required == ()
    assert idea.outputs_produced == ()
    assert idea.agent_workflow == ()
    assert idea.decision_policy == ""
    assert idea.integration_points == ()
    assert idea.verification_strategy == ""
    assert idea.failure_modes == ()


def test_evaluation_scores_include_operational_dimensions() -> None:
    scores = EvaluationScores(
        originality=0.7,
        usefulness=0.8,
        coherence=0.9,
        feasibility=0.6,
        user_fit=0.75,
        operational_specificity=0.85,
        workflow_fit=0.95,
    )

    assert scores.operational_specificity == 0.85
    assert scores.workflow_fit == 0.95
```

- [ ] **Step 2: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_models.py::test_idea_genome_defaults_operational_contract_for_legacy_traces tests/test_models.py::test_evaluation_scores_include_operational_dimensions -v -p no:cacheprovider --basetemp=.pytest-tmp-task1-red
```

Expected: FAIL because fields do not exist.

- [ ] **Step 3: Implement model fields**

In `src/creativity_layer/models.py`, update:

```python
class EvaluationScores(FrozenModel):
    originality: Score
    usefulness: Score
    coherence: Score
    feasibility: Score
    user_fit: Score
    operational_specificity: Score = 0.0
    workflow_fit: Score = 0.0
```

Add to `IdeaGenome` after `distinguishing_features`:

```python
    inputs_required: tuple[str, ...] = ()
    outputs_produced: tuple[str, ...] = ()
    agent_workflow: tuple[str, ...] = ()
    decision_policy: str = ""
    integration_points: tuple[str, ...] = ()
    verification_strategy: str = ""
    failure_modes: tuple[str, ...] = ()
```

- [ ] **Step 4: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_models.py -q -p no:cacheprovider --basetemp=.pytest-tmp-task1-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/models.py tests/test_models.py
git commit -m "feat: add operational contract fields"
```

## Task 2: Live Schema and Prompt Pressure

**Files:**
- Modify: `src/creativity_layer/openai_schemas.py`
- Modify: `src/creativity_layer/openai_provider.py`
- Modify: `tests/test_openai_schemas.py`
- Modify: `tests/test_openai_provider.py`

- [ ] **Step 1: Write failing schema test**

Add to `tests/test_openai_schemas.py`:

```python
def test_openai_idea_requires_operational_contract_fields() -> None:
    payload = _idea_payload()
    payload.pop("inputs_required", None)

    with pytest.raises(ValidationError):
        OpenAIIdea.model_validate(payload)


def test_openai_idea_operational_contract_converts_to_domain() -> None:
    candidate = _idea(
        inputs_required=["failed test output", "changed files"],
        outputs_produced=["failure classification", "next action"],
        agent_workflow=["collect evidence", "choose action", "verify"],
        decision_policy="Stop after two identical failed attempts.",
        integration_points=["post-test-failure hook"],
        verification_strategy="Run targeted test before full suite.",
        failure_modes=["ambiguous logs"],
    ).to_seed()

    assert candidate.inputs_required == ("failed test output", "changed files")
    assert candidate.outputs_produced == ("failure classification", "next action")
    assert candidate.agent_workflow == ("collect evidence", "choose action", "verify")
    assert candidate.decision_policy == "Stop after two identical failed attempts."
    assert candidate.integration_points == ("post-test-failure hook",)
    assert candidate.verification_strategy == "Run targeted test before full suite."
    assert candidate.failure_modes == ("ambiguous logs",)
```

Update `_idea_payload()` in the same test file to include all new fields for existing tests.

- [ ] **Step 2: Write failing prompt test**

Add to `tests/test_openai_provider.py`:

```python
def test_openai_generation_prompts_require_operational_contracts() -> None:
    seed_instruction = DEVELOPER_INSTRUCTIONS["seed"]
    transform_instruction = DEVELOPER_INSTRUCTIONS["transform"]
    evaluate_instruction = DEVELOPER_INSTRUCTIONS["evaluate"]

    assert "inputs_required" in seed_instruction
    assert "agent_workflow" in seed_instruction
    assert "GraphQL" in evaluate_instruction
    assert "operational_specificity" in evaluate_instruction
    assert "workflow_fit" in evaluate_instruction
    assert "agent_workflow" in transform_instruction
```

Import `DEVELOPER_INSTRUCTIONS` from `creativity_layer.openai_provider`.

- [ ] **Step 3: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_schemas.py::test_openai_idea_requires_operational_contract_fields tests/test_openai_schemas.py::test_openai_idea_operational_contract_converts_to_domain tests/test_openai_provider.py::test_openai_generation_prompts_require_operational_contracts -v -p no:cacheprovider --basetemp=.pytest-tmp-task2-red
```

Expected: FAIL because schema and prompts do not include operational contract fields.

- [ ] **Step 4: Implement schema and prompts**

In `OpenAIIdea`, add list/string fields and include them in validators and `_domain_fields()`.

Update `DEVELOPER_INSTRUCTIONS` to explicitly require contract fields in seed/transform output and require the evaluator to penalize generic ideas, arbitrary GraphQL choices, and weak workflow fit.

In `OpenAIEvaluation`, add:

```python
    operational_specificity: float = Field(description="0.0 to 1.0 score, not 0 to 10.")
    workflow_fit: float = Field(description="0.0 to 1.0 score, not 0 to 10.")
```

- [ ] **Step 5: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_openai_schemas.py tests/test_openai_provider.py -q -p no:cacheprovider --basetemp=.pytest-tmp-task2-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/openai_schemas.py src/creativity_layer/openai_provider.py tests/test_openai_schemas.py tests/test_openai_provider.py
git commit -m "feat: require operational live outputs"
```

## Task 3: Deterministic Provider and Population Ranking

**Files:**
- Modify: `src/creativity_layer/deterministic.py`
- Modify: `src/creativity_layer/population.py`
- Modify: `tests/test_deterministic.py`
- Modify: `tests/test_population.py`

- [ ] **Step 1: Write failing deterministic test**

Add to `tests/test_deterministic.py`:

```python
def test_deterministic_seed_populates_operational_contract() -> None:
    provider = DeterministicCreativeProvider()
    framed = provider.frame(TaskContext(goal="Improve agent retries")).value

    candidate = provider.seed(framed, RunConfig(seed_count=2, finalist_count=1)).value[0]

    assert candidate.inputs_required
    assert candidate.outputs_produced
    assert candidate.agent_workflow
    assert candidate.decision_policy
    assert candidate.integration_points
    assert candidate.verification_strategy
    assert candidate.failure_modes
```

- [ ] **Step 2: Write failing population test**

Add to `tests/test_population.py`:

```python
def test_population_prefers_operational_workflow_fit_over_shallow_originality() -> None:
    shallow = scored_candidate(
        "Shallow",
        originality=0.95,
        usefulness=0.85,
        coherence=0.9,
        operational_specificity=0.2,
        workflow_fit=0.2,
    )
    operational = scored_candidate(
        "Operational",
        originality=0.86,
        usefulness=0.86,
        coherence=0.9,
        operational_specificity=0.95,
        workflow_fit=0.95,
    )

    selected = PopulationManager().select(
        (shallow, operational),
        finalist_count=1,
    )

    assert selected == (operational,)
```

Update the local `scored_candidate` helper to accept optional `operational_specificity` and `workflow_fit`.

- [ ] **Step 3: Run RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_deterministic.py::test_deterministic_seed_populates_operational_contract tests/test_population.py::test_population_prefers_operational_workflow_fit_over_shallow_originality -v -p no:cacheprovider --basetemp=.pytest-tmp-task3-red
```

Expected: FAIL because deterministic contracts are empty and ranking ignores operational dimensions.

- [ ] **Step 4: Implement deterministic contracts and ranking**

Populate deterministic seed and transform candidates with simple non-empty contract fields.

Update deterministic evaluation to set:

```python
operational_specificity=score(5, 0.50),
workflow_fit=score(6, 0.50),
```

Update population ranking to include these dimensions in `_dominates()` and `_balanced_rank()`.

- [ ] **Step 5: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_deterministic.py tests/test_population.py -q -p no:cacheprovider --basetemp=.pytest-tmp-task3-green
.\.venv\Scripts\python.exe -m ruff check .
git add src/creativity_layer/deterministic.py src/creativity_layer/population.py tests/test_deterministic.py tests/test_population.py
git commit -m "feat: rank operational ideas"
```

## Task 4: Bad-Example Final Regressions

**Files:**
- Modify: `tests/test_final_review.py`

- [ ] **Step 1: Add final review regression tests**

Add tests that lock the V3-A expectations:

```python
def test_retry_strategy_contract_rejects_shallow_log_analysis() -> None:
    source = DEVELOPER_INSTRUCTIONS["evaluate"]

    assert "analyze logs and retry smarter" in source
    assert "penalize" in source.lower()
    assert "decision_policy" in source
    assert "verification_strategy" in source


def test_arbitrary_repo_middleware_penalizes_graphql_by_default() -> None:
    source = DEVELOPER_INSTRUCTIONS["evaluate"]

    assert "GraphQL" in source
    assert "unless requested" in source
    assert "arbitrary repos" in source


def test_typescript_monorepo_contract_mentions_repo_specific_signals() -> None:
    source = DEVELOPER_INSTRUCTIONS["seed"] + DEVELOPER_INSTRUCTIONS["evaluate"]

    for expected in ("package graph", "affected packages", "test shards", "tsc"):
        assert expected in source
```

Import `DEVELOPER_INSTRUCTIONS` from `creativity_layer.openai_provider`.

- [ ] **Step 2: Run GREEN and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_final_review.py -q -p no:cacheprovider --basetemp=.pytest-tmp-task4-green
.\.venv\Scripts\python.exe -m ruff check .
git add tests/test_final_review.py
git commit -m "test: lock operational rubric regressions"
```

## Task 5: Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add README note**

Under the live mode section, add:

```markdown
Live idea artifacts include an operational contract (`inputs_required`,
`outputs_produced`, `agent_workflow`, `decision_policy`, `integration_points`,
`verification_strategy`, and `failure_modes`) so downstream agents can consume
ideas as planning artifacts instead of prose-only briefs.
```

- [ ] **Step 2: Run final checks**

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=creativity_layer --cov-report=term-missing -p no:cacheprovider --basetemp=.pytest-tmp-v3a-final
.\.venv\Scripts\python.exe -m ruff check .
git diff --check origin/main...HEAD
```

- [ ] **Step 3: Commit docs**

```powershell
git add README.md
git commit -m "docs: document operational idea contracts"
```
