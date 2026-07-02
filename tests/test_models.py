import json
from datetime import datetime
from math import inf, nan
from uuid import UUID

import pytest
from pydantic import ValidationError

from muse.models import (
    ContextBundle,
    ContextSnippet,
    CostEstimate,
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    InspirationKind,
    OperationTrace,
    RunConfig,
    RunResult,
    SpendRecord,
    TaskContext,
    TokenUsage,
)


def test_task_context_requires_a_non_blank_goal() -> None:
    with pytest.raises(ValidationError):
        TaskContext(goal="   ")


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


def test_idea_genome_records_ancestry_and_separate_scores() -> None:
    parent = IdeaGenome(
        generation=0,
        title="Borrow time",
        core_mechanism="Trade scheduling rights instead of fixed calendar slots.",
        problem_framing="Coordination is treated as ownership of time.",
        task_value="Reduces scheduling negotiation.",
        distinguishing_features=("transferable scheduling rights",),
    )

    child = IdeaGenome(
        generation=1,
        title="Time market",
        core_mechanism="Let participants exchange priority tokens.",
        problem_framing="Coordination is a constrained allocation market.",
        task_value="Makes urgency explicit.",
        distinguishing_features=("priority tokens",),
        parent_ids=(parent.id,),
        transformations=("transfer",),
        inspiration_kind=InspirationKind.SYNTHESIZED,
        scores=EvaluationScores(
            originality=0.9,
            usefulness=0.7,
            coherence=0.8,
            feasibility=0.6,
            user_fit=0.75,
        ),
    )

    assert isinstance(child.id, UUID)
    assert child.parent_ids == (parent.id,)
    assert child.scores.originality == 0.9
    assert child.scores.usefulness == 0.7


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


def test_run_config_rejects_impossible_reservations() -> None:
    with pytest.raises(ValidationError):
        RunConfig(
            max_cost_usd=1,
            max_calls=4,
            framing_reserve_usd=0.6,
            finalization_reserve_usd=0.5,
        )


@pytest.mark.parametrize("value", [inf, -inf, nan])
@pytest.mark.parametrize(
    ("model", "field"),
    [
        (RunConfig, "max_cost_usd"),
        (SpendRecord, "cost_usd"),
    ],
)
def test_models_reject_non_finite_floats(
    model: type[RunConfig] | type[SpendRecord],
    field: str,
    value: float,
) -> None:
    values = (
        {
            "stage": "generation",
            "provider": "local",
            "latency_ms": 0,
            field: value,
        }
        if model is SpendRecord
        else {field: value}
    )

    with pytest.raises(ValidationError):
        model(**values)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (
            IdeaGenome,
            {
                "generation": True,
                "title": "Boolean generation",
                "core_mechanism": "Treat truth as an integer.",
                "problem_framing": "Boolean values are numeric in Python.",
                "task_value": "Protects domain semantics.",
            },
        ),
        (RunConfig, {"max_calls": True}),
        (
            SpendRecord,
            {
                "stage": "generation",
                "provider": "local",
                "cost_usd": True,
                "latency_ms": 0,
            },
        ),
        (
            SpendRecord,
            {
                "stage": "generation",
                "provider": "local",
                "cost_usd": 0.0,
                "latency_ms": False,
            },
        ),
    ],
)
def test_numeric_domain_fields_reject_bool(
    model: type[IdeaGenome] | type[RunConfig] | type[SpendRecord],
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model(**values)


@pytest.mark.parametrize(
    "field",
    ["title", "core_mechanism", "problem_framing", "task_value"],
)
def test_idea_genome_rejects_whitespace_only_required_text(field: str) -> None:
    values = {
        "generation": 0,
        "title": "Useful title",
        "core_mechanism": "A concrete mechanism.",
        "problem_framing": "A clear framing.",
        "task_value": "A useful outcome.",
        field: "   ",
    }

    with pytest.raises(ValidationError):
        IdeaGenome(**values)


@pytest.mark.parametrize(
    "value",
    [
        "\u200b",
        "\ufeff",
        "visible\x00text",
        "visible\u200btext",
        "visible\ue000text",
    ],
)
def test_required_text_rejects_unicode_control_or_format_content(value: str) -> None:
    with pytest.raises(ValidationError):
        IdeaGenome(
            generation=0,
            title=value,
            core_mechanism="A concrete mechanism.",
            problem_framing="A clear framing.",
            task_value="A useful outcome.",
        )


def test_required_text_preserves_normal_unicode_punctuation() -> None:
    candidate = IdeaGenome(
        generation=0,
        title="Calm—coordination: “reversible”",
        core_mechanism="Use evidence → confidence.",
        problem_framing="Coordination isn’t final.",
        task_value="Keeps decisions useful.",
    )

    assert candidate.title == "Calm—coordination: “reversible”"


def test_spend_record_requires_timezone_aware_created_at() -> None:
    with pytest.raises(ValidationError):
        SpendRecord(
            stage="generation",
            provider="local",
            cost_usd=0.1,
            latency_ms=10,
            created_at=datetime(2026, 6, 22, 12, 0),
        )


@pytest.mark.parametrize("field", ["stage", "provider"])
def test_spend_record_rejects_blank_labels(field: str) -> None:
    values = {
        "stage": "generation",
        "provider": "local",
        "cost_usd": 0.1,
        "latency_ms": 10,
        field: "   ",
    }

    with pytest.raises(ValidationError):
        SpendRecord(**values)


def test_spend_record_preserves_live_operation_metadata() -> None:
    trace = OperationTrace.from_payload(
        request={"model_role": "economy"},
        response={"status": "complete"},
    )
    usage = TokenUsage(input_tokens=10, output_tokens=20)
    record = SpendRecord(
        stage="seeding",
        provider="openai",
        model="economy-test-model",
        cost_usd=0.001,
        latency_ms=25,
        usage=usage,
        pricing_version="test",
        cost_is_estimated=True,
        request_id="req_test",
        operation_trace=trace,
    )

    assert record.usage == usage
    assert record.model == "economy-test-model"
    assert record.pricing_version == "test"
    assert record.cost_is_estimated is True
    assert record.request_id == "req_test"
    assert record.operation_trace == trace


def test_cost_estimate_uses_strict_finite_float() -> None:
    estimate = CostEstimate(
        estimated_cost_usd=0.125,
        pricing_version="test",
    )

    assert estimate.estimated_cost_usd == 0.125
    with pytest.raises(ValidationError):
        CostEstimate(estimated_cost_usd="0.125", pricing_version="test")
    with pytest.raises(ValidationError):
        CostEstimate(estimated_cost_usd=inf, pricing_version="test")


@pytest.mark.parametrize(
    "values",
    [
        {"input_tokens": -1},
        {"cached_input_tokens": -1},
        {"output_tokens": -1},
        {"reasoning_tokens": -1},
        {"input_tokens": True},
    ],
)
def test_token_usage_rejects_invalid_counts(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TokenUsage(**values)


def test_live_metadata_labels_reject_blank_text() -> None:
    with pytest.raises(ValidationError):
        CostEstimate(
            estimated_cost_usd=0.0,
            pricing_version=" ",
        )
    with pytest.raises(ValidationError):
        SpendRecord(
            stage="seeding",
            provider="openai",
            model=" ",
            cost_usd=0.0,
            latency_ms=0,
        )


@pytest.mark.parametrize("value", [0, 1, "true"])
def test_estimate_flags_reject_non_boolean_values(value: object) -> None:
    with pytest.raises(ValidationError):
        CostEstimate(
            estimated_cost_usd=0.0,
            pricing_version="test",
            is_estimated=value,  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        SpendRecord(
            stage="seeding",
            provider="openai",
            cost_usd=0.0,
            latency_ms=0,
            cost_is_estimated=value,  # type: ignore[arg-type]
        )


def test_operation_trace_canonicalizes_payloads_and_is_deeply_immutable() -> None:
    trace = OperationTrace.from_payload(
        request={"z": [2, 1], "a": {"nested": True}},
        response={"ok": True},
    )

    assert trace.request_json == '{"a":{"nested":true},"z":[2,1]}'
    assert trace.response_json == '{"ok":true}'
    assert json.loads(trace.request_json)["a"]["nested"] is True


def test_operation_trace_constructor_accepts_payload_aliases() -> None:
    trace = OperationTrace(
        request={"z": 2, "a": 1},
        response={"status": "complete"},
    )

    assert trace.request_json == '{"a":1,"z":2}'
    assert trace.response_json == '{"status":"complete"}'


def test_operation_trace_standard_serialization_uses_public_payload_shape() -> None:
    trace = OperationTrace.from_payload(
        request={"z": 2, "a": {"value": 1}},
        response={"status": "complete"},
    )

    dumped = trace.model_dump(mode="json")

    assert dumped == {
        "request": {"a": {"value": 1}, "z": 2},
        "response": {"status": "complete"},
    }
    assert json.loads(trace.model_dump_json()) == dumped
    assert OperationTrace.model_validate(dumped) == trace


@pytest.mark.parametrize(
    "payload",
    [
        {"nested": {"Authorization": "safe-looking"}},
        {"api_KEY": "safe-looking"},
        {"headers": {"x-api-key": "safe-looking"}},
        {"nested": {"oauth.access-token": "safe-looking"}},
        {"nested": {"refresh token value": "safe-looking"}},
        {"nested": {"id.token": "safe-looking"}},
        {"nested": {"client-secret-value": "safe-looking"}},
        {"nested": {"db_passwd": "safe-looking"}},
        {"nested": {"password_policy": "safe-looking"}},
        {"nested": {"session_cookie": "safe-looking"}},
        {"nested": {"cookie_preferences": "safe-looking"}},
        {"nested": {"response.set-cookie": "safe-looking"}},
        {"nested": {"bearer": "safe-looking"}},
        {"nested": {"auth_token_value": "safe-looking"}},
        {"nested": {"secret_value": "safe-looking"}},
        {"nested": {"service_credential": "safe-looking"}},
        {"nested": {"private_key": "safe-looking"}},
        {"nested": {"ＰＲＩＶＡＴＥ－ＫＥＹ": "safe-looking"}},
        {"value": "Bearer abcdefghijklmnopqrstuvwxyz"},
        {"value": "sk-abcdefghijklmnopqrstuvwxyz123456"},
    ],
)
def test_operation_trace_rejects_secret_material(payload: object) -> None:
    with pytest.raises(ValueError, match="secret"):
        OperationTrace.from_payload(request=payload, response={})


@pytest.mark.parametrize(
    "key",
    [
        "token_count",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "reasoning_tokens",
    ],
)
def test_operation_trace_allows_explicit_token_usage_metric_keys(key: str) -> None:
    trace = OperationTrace(request={key: 1}, response={})

    assert json.loads(trace.request_json)[key] == 1


def test_operation_trace_aliases_do_not_bypass_secret_checks() -> None:
    with pytest.raises(ValidationError, match="secret"):
        OperationTrace(
            request={"nested": {"x-api-key": "value"}},
            response={},
        )


def test_operation_trace_rejects_noncanonical_constructor_json() -> None:
    with pytest.raises(ValidationError):
        OperationTrace(request_json='{"b": 2, "a": 1}', response_json="{}")
    with pytest.raises(ValidationError):
        OperationTrace(request_json="{", response_json="{}")


def test_legacy_run_json_retains_pre_task_2_fingerprint() -> None:
    candidate_id = "00000000-0000-0000-0000-000000000001"
    legacy_payload = {
        "run_id": "00000000-0000-0000-0000-000000000002",
        "config": {
            "max_cost_usd": 1.0,
            "max_calls": 20,
            "max_generations": 0,
            "seed_count": 2,
            "finalist_count": 1,
            "framing_reserve_usd": 0.0,
            "finalization_reserve_usd": 0.0,
            "random_seed": 0,
        },
        "providers": {
            role: {"name": "local", "version": "1"}
            for role in ("framer", "seeder", "transformer", "evaluator")
        },
        "operator_schedule": ["invert"],
        "framed_task": {
            "context": {
                "goal": "Legacy task",
                "audience": None,
                "constraints": [],
                "preferences": [],
                "risk_tolerance": 0.5,
            },
            "assumptions": [],
            "obvious_solution": "Legacy answer",
            "evaluation_dimensions": [
                "originality",
                "usefulness",
                "coherence",
                "feasibility",
                "user_fit",
            ],
        },
        "finalists": [],
        "all_candidates": [
            {
                "id": candidate_id,
                "generation": 0,
                "title": "Legacy idea",
                "core_mechanism": "Legacy mechanism",
                "problem_framing": "Legacy framing",
                "assumptions_challenged": [],
                "task_value": "Legacy value",
                "distinguishing_features": [],
                "inspiration_principles": [],
                "source_urls": [],
                "first_order_effects": [],
                "second_order_effects": [],
                "feasibility_assumptions": [],
                "uncertainties": [],
                "weaknesses": [],
                "parent_ids": [],
                "transformations": [],
                "inspiration_kind": "independent",
                "scores": None,
                "branch_cost_usd": 0.0,
                "branch_latency_ms": 0.0,
            }
        ],
        "spend_records": [
            {
                "stage": "seed",
                "provider": "local",
                "cost_usd": 0.01,
                "latency_ms": 1,
                "created_at": "2026-06-23T12:00:00Z",
            }
        ],
        "errors": [],
        "stopped_reason": "generation_limit",
        "reproducibility_fingerprint": (
            "bc39704d67e06abc4b48dc5d793253eefc7dddd4b057e0b1809baf457e6fb240"
        ),
    }

    restored = RunResult.model_validate(legacy_payload)

    assert restored.reproducibility_fingerprint == legacy_payload[
        "reproducibility_fingerprint"
    ]


def test_nested_run_result_serialization_uses_public_trace_shape_and_round_trips() -> None:
    legacy_payload = {
        "run_id": "00000000-0000-0000-0000-000000000012",
        "config": {
            "max_cost_usd": 1.0,
            "max_calls": 20,
            "max_generations": 0,
            "seed_count": 2,
            "finalist_count": 1,
            "framing_reserve_usd": 0.0,
            "finalization_reserve_usd": 0.0,
            "random_seed": 0,
        },
        "providers": {
            role: {"name": "local", "version": "1"}
            for role in ("framer", "seeder", "transformer", "evaluator")
        },
        "operator_schedule": ["invert"],
        "framed_task": {
            "context": {
                "goal": "Trace task",
                "audience": None,
                "constraints": [],
                "preferences": [],
                "risk_tolerance": 0.5,
            },
            "assumptions": [],
            "obvious_solution": "Trace answer",
            "evaluation_dimensions": [
                "originality",
                "usefulness",
                "coherence",
                "feasibility",
                "user_fit",
            ],
        },
        "finalists": [],
        "all_candidates": [],
        "spend_records": [
            {
                "stage": "seed",
                "provider": "openai",
                "model": "model",
                "cost_usd": 0.01,
                "latency_ms": 1,
                "usage": {
                    "input_tokens": 2,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                    "reasoning_tokens": 1,
                },
                "pricing_version": "test",
                "cost_is_estimated": True,
                "request_id": "req_1",
                "operation_trace": {
                    "request": {"operation": "seed"},
                    "response": {"status": "complete"},
                },
                "created_at": "2026-06-23T12:00:00Z",
            }
        ],
        "errors": [],
        "stopped_reason": "generation_limit",
    }
    result = RunResult.model_validate(legacy_payload)

    dumped = result.model_dump(mode="json")

    assert dumped["spend_records"][0]["operation_trace"] == {
        "request": {"operation": "seed"},
        "response": {"status": "complete"},
    }
    assert RunResult.model_validate(dumped) == result
    assert RunResult.model_validate_json(result.model_dump_json()) == result
