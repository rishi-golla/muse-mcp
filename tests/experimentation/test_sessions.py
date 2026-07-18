from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from muse.experimentation.sessions import (
    AuthorizationGrant,
    AuthorizationPolicy,
    CreativeSession,
    Objective,
    PrivacyPolicy,
    SessionBudgets,
    SessionStatus,
    SideEffectClass,
)


def _valid_session(**overrides: object) -> CreativeSession:
    values: dict[str, object] = {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "goal": "Design a safer coordination mechanism",
        "objectives": (
            Objective(name="usefulness", direction="maximize", priority=1),
        ),
        "hard_constraints": ("No external writes without authorization",),
        "privacy": PrivacyPolicy(mode="private", retention_days=30),
        "authorization": AuthorizationPolicy(
            automatic_side_effects=(SideEffectClass.READ_ONLY_LOCAL,),
        ),
        "budgets": SessionBudgets(
            max_cost_usd=1.0,
            max_provider_calls=50,
            max_latency_ms=120_000,
            max_human_minutes=10,
        ),
        "schema_version": 1,
        "policy_version": "evidence-v1",
    }
    values.update(overrides)
    return CreativeSession.model_validate(values)


def test_creative_session_requires_versioned_domain_general_policy() -> None:
    session = _valid_session()

    assert session.status is SessionStatus.ACTIVE
    assert session.sequence == 0


@pytest.mark.parametrize("goal", ["", "   "])
def test_creative_session_rejects_blank_goal(goal: str) -> None:
    with pytest.raises(ValidationError, match="blank"):
        _valid_session(goal=goal)


def test_creative_session_rejects_duplicate_objective_names() -> None:
    objectives = (
        Objective(name="usefulness", direction="maximize", priority=1),
        Objective(name="Usefulness", direction="minimize", priority=2),
    )

    with pytest.raises(ValidationError, match="objective names"):
        _valid_session(objectives=objectives)


def test_creative_session_rejects_canonically_equivalent_objective_names() -> None:
    objectives = (
        Objective(name="Caf\u00e9", direction="maximize", priority=1),
        Objective(name="Cafe\u0301", direction="minimize", priority=2),
    )

    with pytest.raises(ValidationError, match="objective names"):
        _valid_session(objectives=objectives)


def test_creative_session_rejects_duplicate_objective_priorities() -> None:
    objectives = (
        Objective(name="usefulness", direction="maximize", priority=1),
        Objective(name="risk", direction="minimize", priority=1),
    )

    with pytest.raises(ValidationError, match="objective priorities"):
        _valid_session(objectives=objectives)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_cost_usd", -0.01),
        ("max_provider_calls", -1),
        ("max_latency_ms", -1),
        ("max_human_minutes", -1),
    ],
)
def test_session_budgets_are_non_negative(field: str, value: float | int) -> None:
    values: dict[str, float | int] = {
        "max_cost_usd": 0.0,
        "max_provider_calls": 0,
        "max_latency_ms": 0,
        "max_human_minutes": 0,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        SessionBudgets.model_validate(values)


@pytest.mark.parametrize(
    "side_effect",
    [
        SideEffectClass.EXTERNAL_WRITE,
        SideEffectClass.FINANCIAL,
        SideEffectClass.PARTICIPANT_INVOLVING,
        SideEffectClass.IRREVERSIBLE,
    ],
)
def test_authorization_policy_rejects_forbidden_automatic_side_effects(
    side_effect: SideEffectClass,
) -> None:
    with pytest.raises(ValidationError, match="automatic authorization"):
        AuthorizationPolicy(automatic_side_effects=(side_effect,))


def test_authorization_policy_defaults_to_no_automatic_side_effects() -> None:
    assert AuthorizationPolicy().automatic_side_effects == ()


def test_authorization_grant_rejects_naive_expiration() -> None:
    with pytest.raises(ValidationError):
        AuthorizationGrant(
            session_id=UUID("00000000-0000-0000-0000-000000000001"),
            experiment_id=UUID("00000000-0000-0000-0000-000000000002"),
            side_effect=SideEffectClass.READ_ONLY_EXTERNAL,
            allowed_actions=("Inspect external evidence",),
            expires_at=datetime(2026, 7, 17, 12, 0),
            issuer="operator",
            integrity_hash="sha256:grant",
        )


def test_authorization_grant_accepts_timezone_aware_expiration() -> None:
    expires_at = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)

    grant = AuthorizationGrant(
        session_id=UUID("00000000-0000-0000-0000-000000000001"),
        experiment_id=UUID("00000000-0000-0000-0000-000000000002"),
        side_effect=SideEffectClass.READ_ONLY_EXTERNAL,
        allowed_actions=("Inspect external evidence",),
        expires_at=expires_at,
        issuer="operator",
        integrity_hash="sha256:grant",
    )

    assert grant.expires_at == expires_at


def test_session_statuses_are_exhaustive() -> None:
    assert {status.value for status in SessionStatus} == {
        "active",
        "awaiting_evidence",
        "awaiting_human",
        "concluded",
        "stopped",
        "failed",
    }


@pytest.mark.parametrize(
    "constraints",
    [
        ("",),
        ("   ",),
        ("No external writes", "no external writes"),
    ],
)
def test_creative_session_rejects_blank_or_duplicate_constraints(
    constraints: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError):
        _valid_session(hard_constraints=constraints)


def test_creative_session_rejects_canonically_equivalent_constraints() -> None:
    with pytest.raises(ValidationError, match="hard constraints"):
        _valid_session(hard_constraints=("Caf\u00e9", "Cafe\u0301"))


def test_session_contracts_are_frozen_and_reject_extra_fields() -> None:
    session = _valid_session()

    with pytest.raises(ValidationError, match="frozen"):
        session.goal = "Mutated goal"

    with pytest.raises(ValidationError, match="Extra inputs"):
        CreativeSession.model_validate(
            {
                **session.model_dump(),
                "repository_path": "software-only-field",
            }
        )


def test_experimentation_package_exports_only_stable_contract_names() -> None:
    from muse import experimentation

    assert experimentation.__all__ == (
        "AuthorizationDenied",
        "AuthorizationGrant",
        "AuthorizationPolicy",
        "CreativeSession",
        "Objective",
        "ObjectiveDirection",
        "PrivacyPolicy",
        "SessionBudgets",
        "SessionProjection",
        "SessionStatus",
        "SideEffectClass",
    )
