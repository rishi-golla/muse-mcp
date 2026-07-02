from __future__ import annotations

from creativity_layer.quality_warnings import (
    finalist_quality_warnings,
    summarize_quality_warnings,
)


def test_finalist_quality_warnings_flags_generic_title_mechanism_and_empty_contract() -> None:
    finalist = {
        "title": "Decision garden",
        "core_mechanism": (
            "People allocate reversible confidence rather than binary votes."
        ),
        "inputs_required": [],
        "outputs_produced": ["next action"],
        "agent_workflow": ["collect evidence"],
        "decision_policy": "choose bounded action",
        "integration_points": ["planning step"],
        "verification_strategy": "run tests",
        "failure_modes": ["ambiguous evidence"],
    }

    warnings = finalist_quality_warnings(finalist)

    assert warnings == (
        "generic_title",
        "generic_mechanism",
        "missing_operational_field",
    )


def test_finalist_quality_warnings_flags_missing_required_terms() -> None:
    finalist = {
        "title": "Shard replay",
        "core_mechanism": "Replay the failing shard and compare verification output.",
        "inputs_required": ["test command"],
        "outputs_produced": ["report"],
        "agent_workflow": ["run failing shard"],
        "decision_policy": "stop after repeated failure",
        "integration_points": ["agent planning step"],
        "verification_strategy": "run the shard",
        "failure_modes": ["environment mismatch"],
    }

    assert finalist_quality_warnings(
        finalist,
        required_terms=("pytest", "retry"),
    ) == ("missing_required_terms",)


def test_summarize_quality_warnings_counts_unique_finalists() -> None:
    summary = summarize_quality_warnings(
        [
            ("generic_title", "generic_mechanism"),
            ("generic_title",),
            (),
        ]
    )

    assert summary == {
        "warning_count": 3,
        "finalist_warning_count": 2,
        "warnings": {"generic_mechanism": 1, "generic_title": 2},
    }
