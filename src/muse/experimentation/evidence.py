from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID, uuid4

from pydantic import Field, field_serializer, field_validator, model_validator

from muse.experimentation.candidates import (
    CandidatePrediction,
    CandidateSelectionState,
    ClaimSupportState,
    _deduplicate_text,
    _deduplicate_uuids,
)
from muse.experimentation.sessions import SideEffectClass
from muse.models import FrozenModel, RequiredText, _reject_trace_secrets


class EvidenceCapability(StrEnum):
    EXECUTABLE = "executable"
    OBSERVATIONAL = "observational"
    HUMAN = "human"
    EXTERNAL = "external"


class ExperimentStatus(StrEnum):
    PROPOSED = "proposed"
    AUTHORIZED = "authorized"
    RUNNING = "running"
    COMPLETED = "completed"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


class EvidenceValidationStatus(StrEnum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"


class DecisionRuleKind(StrEnum):
    LOWER_IS_BETTER = "lower_is_better"
    HIGHER_IS_BETTER = "higher_is_better"
    THRESHOLD = "threshold"
    BOOLEAN = "boolean"


class MeasurementSpec(FrozenModel):
    name: RequiredText
    unit: RequiredText


class DecisionRuleSpec(FrozenModel):
    kind: DecisionRuleKind
    measurement: RequiredText
    inconclusive_margin: float = Field(strict=True, ge=0.0)
    threshold: float | None = Field(default=None, strict=True)
    expected_boolean: bool | None = Field(default=None, strict=True)

    @field_validator("threshold", mode="before")
    @classmethod
    def require_strict_float_threshold(cls, value: object) -> float | None:
        if value is not None and type(value) is not float:
            raise ValueError("decision rule threshold must be a strict float")
        return value

    @model_validator(mode="after")
    def require_kind_specific_parameters(self) -> DecisionRuleSpec:
        if self.kind is DecisionRuleKind.THRESHOLD:
            if self.threshold is None or self.expected_boolean is not None:
                raise ValueError(
                    "threshold decision rule requires only a finite strict threshold"
                )
        elif self.kind is DecisionRuleKind.BOOLEAN:
            if self.expected_boolean is None or self.threshold is not None:
                raise ValueError(
                    "boolean decision rule requires only a strict expected boolean"
                )
        elif self.threshold is not None or self.expected_boolean is not None:
            raise ValueError(
                "lower/higher decision rules cannot carry threshold or boolean parameters"
            )
        return self


class ExperimentSpec(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    target_uncertainty_ids: tuple[UUID, ...] = Field(min_length=1)
    candidate_ids: tuple[UUID, ...] = Field(min_length=2)
    hypothesis: RequiredText
    predictions: tuple[CandidatePrediction, ...] = Field(min_length=2)
    capability: EvidenceCapability
    procedure: tuple[RequiredText, ...] = Field(min_length=1)
    measurements: tuple[MeasurementSpec, ...] = Field(min_length=1)
    decision_rule: DecisionRuleSpec
    stopping_conditions: tuple[RequiredText, ...] = Field(min_length=1)
    authorization_requirements: tuple[SideEffectClass, ...] = ()
    adapter_id: RequiredText
    adapter_contract_version: int = Field(strict=True, ge=1)
    status: ExperimentStatus = ExperimentStatus.PROPOSED

    @field_validator("target_uncertainty_ids", "candidate_ids")
    @classmethod
    def deduplicate_identity_members(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _deduplicate_uuids(values)

    @field_validator("procedure", "stopping_conditions")
    @classmethod
    def deduplicate_text_members(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _deduplicate_text(values)

    @field_validator("authorization_requirements")
    @classmethod
    def deduplicate_authorization_requirements(
        cls, values: tuple[SideEffectClass, ...]
    ) -> tuple[SideEffectClass, ...]:
        return tuple(dict.fromkeys(values))

    @field_validator("predictions")
    @classmethod
    def deduplicate_predictions(
        cls, values: tuple[CandidatePrediction, ...]
    ) -> tuple[CandidatePrediction, ...]:
        seen: set[UUID] = set()
        unique: list[CandidatePrediction] = []
        for prediction in values:
            if prediction.candidate_id not in seen:
                seen.add(prediction.candidate_id)
                unique.append(prediction)
        return tuple(unique)

    @field_validator("measurements")
    @classmethod
    def deduplicate_measurements(
        cls, values: tuple[MeasurementSpec, ...]
    ) -> tuple[MeasurementSpec, ...]:
        seen: set[str] = set()
        unique: list[MeasurementSpec] = []
        for measurement in values:
            key = _identity_key(measurement.name)
            if key not in seen:
                seen.add(key)
                unique.append(measurement)
        return tuple(unique)

    @model_validator(mode="after")
    def require_complete_preregistration(self) -> ExperimentSpec:
        if len(self.candidate_ids) < 2 or len(self.predictions) < 2:
            raise ValueError("experiment must compare at least two distinct competing candidates")
        prediction_ids = {prediction.candidate_id for prediction in self.predictions}
        if prediction_ids != set(self.candidate_ids):
            raise ValueError("predictions must cover every competing candidate exactly once")
        prediction_expectations = {
            _identity_key(prediction.expected) for prediction in self.predictions
        }
        if len(prediction_expectations) < 2:
            raise ValueError(
                "experiment predictions require at least two distinct competing expectations"
            )
        measurement_names = {
            _identity_key(measurement.name) for measurement in self.measurements
        }
        if _identity_key(self.decision_rule.measurement) not in measurement_names:
            raise ValueError("decision rule must reference a registered measurement")
        return self


class EvidenceRequest(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    experiment_id: UUID
    candidate_id: UUID
    capability: EvidenceCapability
    adapter_id: RequiredText
    adapter_contract_version: int = Field(strict=True, ge=1)
    authorization_grant_ids: tuple[UUID, ...] = ()

    @field_validator("authorization_grant_ids")
    @classmethod
    def deduplicate_grant_ids(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _deduplicate_uuids(values)


class Measurement(FrozenModel):
    name: RequiredText
    value: int | float
    unit: RequiredText

    @field_validator("value", mode="before")
    @classmethod
    def require_finite_numeric_value(cls, value: object) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("measurement value must be a number, not a boolean")
        if not math.isfinite(value):
            raise ValueError("measurement value must be finite")
        return value


class EvidenceEnvelope(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    request: EvidenceRequest
    experiment_id: UUID
    candidate_id: UUID
    raw_observation: object | None = None
    artifact_hash: RequiredText | None = None
    measurements: tuple[Measurement, ...] = ()
    validation_status: EvidenceValidationStatus = EvidenceValidationStatus.PENDING
    corrects_evidence_id: UUID | None = None
    correction_sequence: int = Field(default=0, strict=True, ge=0)

    @field_validator("raw_observation", mode="before")
    @classmethod
    def sanitize_raw_observation(cls, value: object) -> object:
        if value is None:
            return None
        _reject_interpretation(value)
        try:
            _reject_trace_secrets(value)
        except ValueError as error:
            raise ValueError("raw evidence contains secret-bearing data") from error
        try:
            canonical = json.dumps(
                value,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as error:
            raise ValueError("raw observation must be JSON-safe") from error
        return _freeze_json(json.loads(canonical))

    @field_validator("measurements")
    @classmethod
    def deduplicate_measurements(
        cls, values: tuple[Measurement, ...]
    ) -> tuple[Measurement, ...]:
        seen: set[str] = set()
        unique: list[Measurement] = []
        for measurement in values:
            key = _identity_key(measurement.name)
            if key not in seen:
                seen.add(key)
                unique.append(measurement)
        return tuple(unique)

    @model_validator(mode="after")
    def validate_envelope_links(self) -> EvidenceEnvelope:
        if (self.raw_observation is None) == (self.artifact_hash is None):
            raise ValueError("evidence must contain either a raw observation or an artifact hash")
        if self.request.experiment_id != self.experiment_id:
            raise ValueError("request experiment ID must match the evidence experiment ID")
        if self.request.candidate_id != self.candidate_id:
            raise ValueError("request candidate ID must match the evidence candidate ID")
        if self.corrects_evidence_id == self.id:
            raise ValueError("evidence cannot be its own correction target")
        if self.correction_sequence == 0 and self.corrects_evidence_id is not None:
            raise ValueError("an initial envelope cannot name a correction target")
        if self.correction_sequence > 0 and self.corrects_evidence_id is None:
            raise ValueError("a correction must name the evidence it corrects")
        return self

    @field_serializer("raw_observation")
    def serialize_raw_observation(self, value: object) -> object:
        return _thaw_json(value)


class BeliefUpdate(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    evidence_id: UUID
    claim_id: UUID
    prior_state: ClaimSupportState
    updated_state: ClaimSupportState
    interpretation: RequiredText


class SelectionDecision(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    experiment_id: UUID
    considered_candidate_ids: tuple[UUID, ...] = Field(min_length=2)
    selected_candidate_id: UUID | None = None
    resulting_state: CandidateSelectionState | None = None
    supporting_evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    rationale: RequiredText
    inconclusive: bool = Field(default=False, strict=True)

    @field_validator("considered_candidate_ids", "supporting_evidence_ids")
    @classmethod
    def deduplicate_identity_members(cls, values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return _deduplicate_uuids(values)

    @model_validator(mode="after")
    def require_selection_or_inconclusive_result(self) -> SelectionDecision:
        if len(self.considered_candidate_ids) < 2:
            raise ValueError(
                "selection decision requires at least two distinct considered candidates"
            )
        if self.inconclusive:
            if self.selected_candidate_id is not None or self.resulting_state is not None:
                raise ValueError(
                    "an inconclusive decision cannot select a candidate or assign a resulting state"
                )
            return self
        if self.selected_candidate_id is None:
            raise ValueError("selection decision must select a candidate or be inconclusive")
        if (
            self.selected_candidate_id is not None
            and self.selected_candidate_id not in self.considered_candidate_ids
        ):
            raise ValueError("selected candidate must be one of the considered candidates")
        if self.resulting_state is not CandidateSelectionState.SELECTED:
            raise ValueError("a conclusive selection must have selected as its resulting state")
        return self


def _identity_key(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def _reject_interpretation(value: object) -> None:
    if isinstance(value, dict):
        keys = tuple(str(key) for key in value)
        has_source_key = any(_key_has_source(key) for key in keys)
        has_interpretive_key = any(_key_has_interpretive_term(key) for key in keys)
        if has_source_key and has_interpretive_key:
            raise ValueError("provider or model interpretation is not raw evidence")
        for key, item in value.items():
            if _key_has_source(str(key)) and _key_has_interpretive_term(str(key)):
                raise ValueError("provider or model interpretation is not raw evidence")
            _reject_interpretation(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_interpretation(item)


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _key_tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(re.findall(r"[a-z0-9]+", normalized))


def _key_has_source(value: str) -> bool:
    tokens = _key_tokens(value)
    compact = "".join(tokens)
    if any(token in _INTERPRETATION_SOURCES for token in tokens):
        return True
    if any(source in compact for source in _LONG_INTERPRETATION_SOURCES):
        return True
    return any(
        compact in {f"ai{term}", f"{term}ai"} for term in _INTERPRETATION_TERMS
    )


def _key_has_interpretive_term(value: str) -> bool:
    compact = "".join(_key_tokens(value))
    return any(term in compact for term in _INTERPRETATION_TERMS)


_INTERPRETATION_SOURCES = frozenset({"provider", "model", "llm", "ai"})
_LONG_INTERPRETATION_SOURCES = frozenset({"provider", "model", "llm"})
_INTERPRETATION_TERMS = frozenset(
    {"analysis", "inference", "rationale", "conclusion", "interpretation"}
)
