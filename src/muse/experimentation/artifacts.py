from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Collection
from pathlib import Path
from threading import Lock
from typing import Protocol, runtime_checkable
from uuid import uuid4

from pydantic import Field, ValidationError, field_validator

from muse.models import FrozenModel

MAX_ARTIFACT_BYTES = 10 * 1024 * 1024
SUPPORTED_SENSITIVITIES = frozenset({"public", "private", "restricted"})

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_MEDIA_TYPE_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*\Z"
)
_STORE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


class EvidenceIntegrityError(RuntimeError):
    """Raised when an artifact reference or stored object fails integrity checks."""


class ArtifactRef(FrozenModel):
    """Immutable metadata identifying one content-addressed artifact."""

    sha256: str = Field(strict=True)
    byte_length: int = Field(strict=True, ge=0)
    media_type: str = Field(strict=True)
    sensitivity: str = Field(strict=True)
    store_id: str = Field(strict=True)

    @field_validator("sha256")
    @classmethod
    def require_lowercase_sha256(cls, value: str) -> str:
        if _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("artifact SHA-256 must be a lowercase 64-character hex digest")
        return value

    @field_validator("media_type")
    @classmethod
    def require_valid_media_type(cls, value: str) -> str:
        return _validate_media_type(value)

    @field_validator("sensitivity")
    @classmethod
    def require_supported_sensitivity(cls, value: str) -> str:
        return _validate_sensitivity(value)

    @field_validator("store_id")
    @classmethod
    def require_safe_store_id(cls, value: str) -> str:
        return _validate_store_id(value)


@runtime_checkable
class ArtifactStore(Protocol):
    def put(
        self,
        content: bytes,
        *,
        media_type: str,
        sensitivity: str,
    ) -> ArtifactRef: ...

    def get(self, ref: ArtifactRef) -> bytes: ...


class LocalArtifactStore:
    """Local immutable object storage addressed only by SHA-256.

    Media types are validated as lowercase parameter-free MIME tokens. The
    default policy remains domain-general because this store never executes or
    interprets content. Callers that need a narrower policy can supply an
    ``allowed_media_types`` collection, which is copied into an immutable set.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        store_id: str,
        max_artifact_bytes: int = MAX_ARTIFACT_BYTES,
        allowed_media_types: Collection[str] | None = None,
    ) -> None:
        self._root = _resolved_path(Path(root))
        self._store_id = _validate_store_id(store_id)
        if (
            isinstance(max_artifact_bytes, bool)
            or not isinstance(max_artifact_bytes, int)
            or max_artifact_bytes <= 0
        ):
            raise ValueError("maximum artifact bytes must be a positive integer")
        self._max_artifact_bytes = max_artifact_bytes
        self._write_lock = Lock()
        self._allowed_media_types = (
            None
            if allowed_media_types is None
            else frozenset(_validate_media_type(value) for value in allowed_media_types)
        )

    def put(
        self,
        content: bytes,
        *,
        media_type: str,
        sensitivity: str,
    ) -> ArtifactRef:
        if type(content) is not bytes:
            raise TypeError("artifact content must be bytes")
        validated_media_type = self._require_allowed_media_type(media_type)
        validated_sensitivity = _validate_sensitivity(sensitivity)
        if len(content) > self._max_artifact_bytes:
            raise ValueError(
                f"artifact exceeds maximum size of {self._max_artifact_bytes} bytes"
            )

        digest = hashlib.sha256(content).hexdigest()
        ref = ArtifactRef(
            sha256=digest,
            byte_length=len(content),
            media_type=validated_media_type,
            sensitivity=validated_sensitivity,
            store_id=self._store_id,
        )
        with self._write_lock:
            self._store_content(content, ref)
        return ref

    def _store_content(self, content: bytes, ref: ArtifactRef) -> None:
        digest = ref.sha256
        target = self._path_for_digest(digest)
        if target.exists() or target.is_symlink():
            self._verify_object(target, ref, existing=True)
            return

        self._prepare_parent(target)
        temporary = target.parent / f".{digest}.{uuid4().hex}.tmp"
        self._require_contained(temporary)
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())

            if target.exists() or target.is_symlink():
                self._verify_object(target, ref, existing=True)
                return
            try:
                temporary.replace(target)
            except PermissionError:
                if not target.exists() and not target.is_symlink():
                    raise
                self._verify_object(target, ref, existing=True)
                return
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, ref: ArtifactRef) -> bytes:
        validated = self._validate_ref_for_store(ref)
        target = self._path_for_digest(validated.sha256)
        if not target.exists() and not target.is_symlink():
            raise FileNotFoundError(f"artifact not found: {validated.sha256}")
        return self._verify_object(target, validated, existing=False)

    def _validate_ref_for_store(self, ref: ArtifactRef) -> ArtifactRef:
        try:
            if not isinstance(ref, ArtifactRef):
                raise TypeError("artifact reference has the wrong type")
            validated = ArtifactRef.model_validate(ref.model_dump(mode="python"))
        except (AttributeError, TypeError, ValidationError, ValueError) as error:
            raise EvidenceIntegrityError("artifact reference is invalid") from error
        if validated.store_id != self._store_id:
            raise EvidenceIntegrityError("artifact store identifier does not match")
        try:
            self._require_allowed_media_type(validated.media_type)
        except ValueError as error:
            raise EvidenceIntegrityError("artifact reference violates media policy") from error
        return validated

    def _require_allowed_media_type(self, value: str) -> str:
        validated = _validate_media_type(value)
        if (
            self._allowed_media_types is not None
            and validated not in self._allowed_media_types
        ):
            raise ValueError(f"unsupported media type: {validated}")
        return validated

    def _path_for_digest(self, digest: str) -> Path:
        if _SHA256_PATTERN.fullmatch(digest) is None:
            raise EvidenceIntegrityError("artifact reference contains an invalid SHA-256")
        target = self._root / digest[:2] / digest[2:]
        self._require_contained(target)
        return target

    def _prepare_parent(self, target: Path) -> None:
        self._require_contained(target)
        self._root.mkdir(parents=True, exist_ok=True)
        self._require_contained(self._root)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._require_contained(target.parent)
        self._require_contained(target)

    def _require_contained(self, path: Path) -> None:
        resolved = _resolved_path(path)
        if not resolved.is_relative_to(self._root):
            raise EvidenceIntegrityError("artifact path escapes the artifact root")

    def _verify_object(
        self,
        target: Path,
        ref: ArtifactRef,
        *,
        existing: bool,
    ) -> bytes:
        self._require_contained(target)
        prefix = "existing artifact" if existing else "artifact"
        if target.is_symlink() or not target.is_file():
            raise EvidenceIntegrityError(f"{prefix} is not a regular file")
        try:
            content = target.read_bytes()
        except FileNotFoundError:
            raise FileNotFoundError(f"artifact not found: {ref.sha256}") from None
        except OSError as error:
            raise EvidenceIntegrityError(f"{prefix} cannot be read") from error
        if len(content) != ref.byte_length:
            raise EvidenceIntegrityError(f"{prefix} byte length does not match its reference")
        if hashlib.sha256(content).hexdigest() != ref.sha256:
            raise EvidenceIntegrityError(f"{prefix} SHA-256 does not match its reference")
        return content


def _validate_media_type(value: str) -> str:
    if not isinstance(value, str) or _MEDIA_TYPE_PATTERN.fullmatch(value) is None:
        raise ValueError("media type must be a lowercase parameter-free type/subtype token")
    return value


def _validate_sensitivity(value: str) -> str:
    if not isinstance(value, str) or value not in SUPPORTED_SENSITIVITIES:
        supported = ", ".join(sorted(SUPPORTED_SENSITIVITIES))
        raise ValueError(f"artifact sensitivity must be one of: {supported}")
    return value


def _validate_store_id(value: str) -> str:
    if not isinstance(value, str) or _STORE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("store identifier must use lowercase letters, digits, '.', '_', or '-'")
    return value


def _resolved_path(path: Path) -> Path:
    resolved = str(path.resolve(strict=False))
    if os.name == "nt" and resolved.startswith("\\\\?\\"):
        resolved = (
            f"\\\\{resolved[8:]}"
            if resolved.startswith("\\\\?\\UNC\\")
            else resolved[4:]
        )
    return Path(resolved)
