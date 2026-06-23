from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from creativity_layer.models import (
    EvaluationScores,
    FramedTask,
    IdeaGenome,
    ProviderIdentity,
    RunConfig,
)
from creativity_layer.providers import MeteredResponse, OperationQuote
from creativity_layer.transforms import TransformationRequest


def _validation_data(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    return value


def provider_identity(provider: object) -> ProviderIdentity:
    return ProviderIdentity.model_validate(
        {
            "name": getattr(provider, "name", type(provider).__name__),
            "version": getattr(provider, "version", "unknown"),
        }
    )


def validate_framed_task(value: object) -> FramedTask:
    return FramedTask.model_validate(_validation_data(value))


def validate_quote(value: object) -> OperationQuote:
    return OperationQuote.model_validate(_validation_data(value))


def validate_metered_envelope(value: object) -> MeteredResponse[Any]:
    return MeteredResponse[Any].model_validate(_validation_data(value))


def validate_seed_payload(
    response: MeteredResponse[Any],
    *,
    config: RunConfig,
) -> tuple[IdeaGenome, ...]:
    typed = MeteredResponse[tuple[IdeaGenome, ...]].model_validate(
        response.model_dump(mode="python")
    )
    candidates = typed.value
    if len(candidates) != config.seed_count:
        raise ValueError("seed cardinality does not match requested seed_count")
    ids = [candidate.id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("seed candidate IDs must be unique")
    for candidate in candidates:
        if candidate.generation != 0:
            raise ValueError("seed generation must be zero")
        if candidate.parent_ids:
            raise ValueError("seed candidates must not have parents")
        if candidate.transformations:
            raise ValueError("seed candidates must not have transformations")
    return candidates


def validate_transform_payload(
    response: MeteredResponse[Any],
    *,
    request: TransformationRequest,
    parents: tuple[IdeaGenome, ...],
    candidate_ids: set[UUID],
) -> IdeaGenome:
    typed = MeteredResponse[IdeaGenome].model_validate(
        response.model_dump(mode="python")
    )
    candidate = typed.value
    expected_parent_ids = tuple(parent.id for parent in parents)
    if candidate.generation != max(parent.generation for parent in parents) + 1:
        raise ValueError("transform generation does not follow its parents")
    if candidate.parent_ids != expected_parent_ids or candidate.parent_ids != request.parent_ids:
        raise ValueError("transform parent IDs do not match the request")
    if not candidate.transformations:
        raise ValueError("transform output must record its operator")
    if candidate.transformations[-1] != request.operator.value:
        raise ValueError("transform output records the wrong operator")
    if candidate.id in candidate_ids:
        raise ValueError("transform output ID must be new")
    return candidate


def validate_evaluation_payload(
    response: MeteredResponse[Any],
) -> EvaluationScores:
    typed = MeteredResponse[EvaluationScores].model_validate(
        response.model_dump(mode="python")
    )
    return typed.value
