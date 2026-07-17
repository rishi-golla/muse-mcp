from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from muse.experimentation.artifacts import (
    MAX_ARTIFACT_BYTES,
    ArtifactRef,
    ArtifactStore,
    EvidenceIntegrityError,
    LocalArtifactStore,
)


def _path_for(root: Path, ref: ArtifactRef) -> Path:
    return root / ref.sha256[:2] / ref.sha256[2:]


def _put(store: LocalArtifactStore, content: bytes = b"domain-general evidence") -> ArtifactRef:
    return store.put(
        content,
        media_type="application/octet-stream",
        sensitivity="private",
    )


def test_artifact_ref_is_frozen_and_requires_strict_lowercase_sha256() -> None:
    ref = ArtifactRef(
        sha256="a" * 64,
        byte_length=3,
        media_type="text/plain",
        sensitivity="public",
        store_id="evidence-v1",
    )

    with pytest.raises(ValidationError, match="frozen"):
        ref.sha256 = "b" * 64

    for invalid_digest in ("A" * 64, "g" * 64, "a" * 63, "../artifact"):
        with pytest.raises(ValidationError, match="SHA-256"):
            ArtifactRef(
                sha256=invalid_digest,
                byte_length=3,
                media_type="text/plain",
                sensitivity="public",
                store_id="evidence-v1",
            )


def test_local_store_implements_artifact_store_protocol(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts", store_id="evidence-v1")

    assert isinstance(store, ArtifactStore)


def test_put_records_metadata_and_round_trips_bytes(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1")
    content = b"measured observation\n"

    ref = store.put(content, media_type="text/plain", sensitivity="restricted")

    assert ref == ArtifactRef(
        sha256=hashlib.sha256(content).hexdigest(),
        byte_length=len(content),
        media_type="text/plain",
        sensitivity="restricted",
        store_id="evidence-v1",
    )
    assert store.get(ref) == content


def test_identical_content_is_deduplicated_by_hash(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1")

    first = _put(store)
    second = _put(store)

    assert second == first
    assert [path.relative_to(root) for path in root.rglob("*") if path.is_file()] == [
        Path(first.sha256[:2]) / first.sha256[2:]
    ]


def test_existing_object_is_validated_before_deduplication(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1")
    ref = _put(store)
    _path_for(root, ref).write_bytes(b"corrupted")

    with pytest.raises(EvidenceIntegrityError, match="existing artifact"):
        _put(store)


def test_get_rejects_hash_and_length_corruption(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1")
    ref = _put(store)
    path = _path_for(root, ref)

    path.write_bytes(b"DOMAIN-general evidence")
    assert path.stat().st_size == ref.byte_length
    with pytest.raises(EvidenceIntegrityError, match="SHA-256"):
        store.get(ref)

    path.write_bytes(b"short")
    with pytest.raises(EvidenceIntegrityError, match="byte length"):
        store.get(ref)


def test_get_rejects_refs_for_another_store(tmp_path: Path) -> None:
    first = LocalArtifactStore(tmp_path / "first", store_id="first-store")
    second = LocalArtifactStore(tmp_path / "second", store_id="second-store")
    ref = _put(first)

    with pytest.raises(EvidenceIntegrityError, match="store identifier"):
        second.get(ref)


def test_get_missing_artifact_raises_file_not_found(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts", store_id="evidence-v1")
    ref = ArtifactRef(
        sha256="0" * 64,
        byte_length=0,
        media_type="application/octet-stream",
        sensitivity="private",
        store_id="evidence-v1",
    )

    with pytest.raises(FileNotFoundError, match=ref.sha256):
        store.get(ref)


def test_put_rejects_oversized_content_before_writing(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1", max_artifact_bytes=4)

    with pytest.raises(ValueError, match="maximum"):
        _put(store, b"12345")

    assert MAX_ARTIFACT_BYTES == 10 * 1024 * 1024
    assert not root.exists()


@pytest.mark.parametrize(
    "media_type",
    [
        "",
        "TEXT/PLAIN",
        "text/plain; charset=utf-8",
        "../text/plain",
        "text",
    ],
)
def test_put_rejects_malformed_media_types_without_writing(
    tmp_path: Path,
    media_type: str,
) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1")

    with pytest.raises(ValueError, match="media type"):
        store.put(b"evidence", media_type=media_type, sensitivity="private")

    assert not root.exists()


@pytest.mark.parametrize(
    "media_type",
    [
        "image/webp",
        "application/zip",
        "application/vnd.example.measurement+json",
        "model/vnd.example.mesh",
    ],
)
def test_default_media_policy_stays_domain_general(
    tmp_path: Path,
    media_type: str,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts", store_id="evidence-v1")

    ref = store.put(b"evidence", media_type=media_type, sensitivity="private")

    assert ref.media_type == media_type


def test_configured_media_policy_rejects_an_unsupported_valid_type(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    allowed = {"text/plain"}
    store = LocalArtifactStore(
        root,
        store_id="evidence-v1",
        allowed_media_types=allowed,
    )
    allowed.add("application/json")

    with pytest.raises(ValueError, match="unsupported media type"):
        store.put(
            b"{}",
            media_type="application/json",
            sensitivity="private",
        )

    assert not root.exists()


@pytest.mark.parametrize("sensitivity", ["secret", "PRIVATE", "", "../private"])
def test_put_rejects_unsupported_sensitivity_without_writing(
    tmp_path: Path,
    sensitivity: str,
) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1")

    with pytest.raises(ValueError, match="sensitivity"):
        store.put(b"evidence", media_type="text/plain", sensitivity=sensitivity)

    assert not root.exists()


def test_put_uses_same_directory_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1")
    original_replace = Path.replace
    replacements: list[tuple[Path, Path, bytes]] = []

    def tracked_replace(source: Path, target: Path) -> Path:
        replacements.append((source, target, source.read_bytes()))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", tracked_replace)

    ref = _put(store)

    assert len(replacements) == 1
    source, target, staged_content = replacements[0]
    assert source.parent == target.parent
    assert target == _path_for(root, ref)
    assert staged_content == b"domain-general evidence"
    assert not source.exists()


def test_put_cleans_temporary_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1")

    def fail_replace(source: Path, target: Path) -> Path:
        raise OSError("simulated atomic replacement failure")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replacement failure"):
        _put(store)

    assert not [path for path in root.rglob("*") if path.is_file()]


def test_concurrent_identical_puts_leave_one_valid_object(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="evidence-v1")

    with ThreadPoolExecutor(max_workers=8) as executor:
        refs = tuple(executor.map(lambda _: _put(store), range(24)))

    assert len(set(refs)) == 1
    ref = refs[0]
    assert store.get(ref) == b"domain-general evidence"
    assert [path for path in root.rglob("*") if path.is_file()] == [_path_for(root, ref)]


def test_storage_names_are_only_lowercase_hash_components(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root, store_id="private-customer-name")
    ref = store.put(b"sensitive title", media_type="text/plain", sensitivity="private")
    relative = _path_for(root, ref).relative_to(root)

    assert re.fullmatch(r"[0-9a-f]{2}", relative.parts[0])
    assert re.fullmatch(r"[0-9a-f]{62}", relative.parts[1])
    assert "private" not in str(relative)
    assert "customer" not in str(relative)
    assert "sensitive" not in str(relative)


def test_get_rejects_a_tampered_traversal_ref_before_path_access(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    outside.write_bytes(b"do not read")
    store = LocalArtifactStore(root, store_id="evidence-v1")
    ref = ArtifactRef(
        sha256="a" * 64,
        byte_length=11,
        media_type="text/plain",
        sensitivity="private",
        store_id="evidence-v1",
    )
    object.__setattr__(ref, "sha256", f"..{os.sep}outside")

    with pytest.raises(EvidenceIntegrityError, match="reference"):
        store.get(ref)

    assert outside.read_bytes() == b"do not read"


def test_put_rejects_directory_link_escape_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    digest = hashlib.sha256(b"domain-general evidence").hexdigest()
    linked_prefix = root / digest[:2]
    try:
        linked_prefix.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory links unavailable: {error}")
    store = LocalArtifactStore(root, store_id="evidence-v1")

    with pytest.raises(EvidenceIntegrityError, match="artifact root"):
        _put(store)

    assert list(outside.iterdir()) == []


def test_get_rejects_symlinked_object_escape_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    store = LocalArtifactStore(root, store_id="evidence-v1")
    ref = _put(store)
    target = _path_for(root, ref)
    target.unlink()
    outside.write_bytes(b"domain-general evidence")
    try:
        target.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"file links unavailable: {error}")

    with pytest.raises(EvidenceIntegrityError, match="artifact root"):
        store.get(ref)
