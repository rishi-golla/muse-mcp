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
