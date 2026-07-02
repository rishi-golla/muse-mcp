from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

GENERIC_TITLES = frozenset(
    {
        "consent gradients",
        "counterfactual ledger",
        "decision garden",
        "silent delegation market",
    }
)

GENERIC_MECHANISM_PHRASES = (
    "binary votes",
    "central coordinator",
    "decision authority",
    "proposals mature through evidence thresholds",
    "reversible confidence",
)

OPERATIONAL_FIELDS = (
    "inputs_required",
    "outputs_produced",
    "agent_workflow",
    "decision_policy",
    "integration_points",
    "verification_strategy",
    "failure_modes",
)

FINALIST_TEXT_FIELDS = (
    "title",
    "core_mechanism",
    "problem_framing",
    "task_value",
    "agent_workflow",
    "decision_policy",
    "verification_strategy",
)

WARNING_ACTIONS = {
    "generic_title": "prefer a finalist with a task-specific title before editing",
    "generic_mechanism": "ask for a more concrete mechanism tied to the task",
    "missing_operational_field": "retry with instructions to fill every operational contract field",
    "missing_required_terms": (
        "supply more repo signals or choose a finalist that uses observed context"
    ),
}


def finalist_quality_warnings(
    finalist: Mapping[str, Any],
    *,
    required_terms: Sequence[str] = (),
) -> tuple[str, ...]:
    warnings: list[str] = []

    title = str(finalist.get("title", "")).strip().casefold()
    if title in GENERIC_TITLES:
        warnings.append("generic_title")

    mechanism = str(finalist.get("core_mechanism", "")).casefold()
    if any(phrase in mechanism for phrase in GENERIC_MECHANISM_PHRASES):
        warnings.append("generic_mechanism")

    if missing_operational_fields(finalist):
        warnings.append("missing_operational_field")

    if missing_required_terms(finalist, required_terms=required_terms):
        warnings.append("missing_required_terms")

    return tuple(dict.fromkeys(warnings))


def summarize_quality_warnings(
    warnings_by_finalist: Sequence[Sequence[str]],
) -> dict[str, object]:
    counter: Counter[str] = Counter()
    finalist_warning_count = 0
    for warnings in warnings_by_finalist:
        unique_warnings = tuple(dict.fromkeys(warnings))
        if unique_warnings:
            finalist_warning_count += 1
        counter.update(unique_warnings)

    return {
        "warning_count": sum(counter.values()),
        "finalist_warning_count": finalist_warning_count,
        "warnings": dict(sorted(counter.items())),
    }


def quality_action_policy(
    warnings: Sequence[str],
    *,
    effort: str,
) -> dict[str, object]:
    unique_warnings = tuple(dict.fromkeys(warnings))
    if not unique_warnings:
        return {
            "status": "clear",
            "escalate_effort_to": None,
            "recommended_actions": [],
            "warning_actions": {},
        }

    retry_warnings = {"missing_operational_field", "missing_required_terms"}
    status = (
        "needs_retry"
        if any(warning in retry_warnings for warning in unique_warnings)
        else "review"
    )
    return {
        "status": status,
        "escalate_effort_to": _next_effort(effort),
        "recommended_actions": _recommended_actions(unique_warnings),
        "warning_actions": {
            warning: WARNING_ACTIONS[warning]
            for warning in unique_warnings
            if warning in WARNING_ACTIONS
        },
    }


def missing_operational_fields(finalist: Mapping[str, Any]) -> bool:
    for field in OPERATIONAL_FIELDS:
        value = finalist.get(field)
        if value is None or value == "" or value == []:
            return True
    return False


def missing_required_terms(
    finalist: Mapping[str, Any],
    *,
    required_terms: Sequence[str],
) -> bool:
    if not required_terms:
        return False
    haystack = " ".join(
        str(finalist.get(field, "")) for field in FINALIST_TEXT_FIELDS
    ).casefold()
    matches = sum(1 for term in required_terms if term.casefold() in haystack)
    required_match_count = min(2, len(required_terms))
    return matches < required_match_count


def _next_effort(effort: str) -> str | None:
    effort = effort.strip().casefold()
    if effort == "quick":
        return "standard"
    if effort == "standard":
        return "deep"
    return None


def _recommended_actions(warnings: Sequence[str]) -> list[str]:
    actions: list[str] = []
    if "missing_required_terms" in warnings:
        actions.append("supply more repo signals")
    if "missing_operational_field" in warnings:
        actions.append("retry for complete operational contract")
    if "generic_mechanism" in warnings or "generic_title" in warnings:
        actions.append("prefer a more task-specific finalist")
    actions.append("run repository-owned verification before editing")
    return actions
