"""Phase 6 tests: encrypted artifact store — path safety, atomicity, round trip."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.encryption.artifact_store import EncryptedArtifactStore, resolve_artifact_path
from app.encryption.errors import EncryptedArtifactPathError
from tests._encryption_helpers import TEST_KEY_ID, make_service

MARKER = "SYNTHETIC_TEST_CUSTOMER_987654"


@pytest.fixture
def store(tmp_path: Path) -> EncryptedArtifactStore:
    return EncryptedArtifactStore(make_service(), approved_dir=tmp_path)


# --- write inside approved dir / path safety (35-38) ------------------------ #
def test_valid_artifact_written_inside_approved_dir(store, tmp_path) -> None:  # 35
    path = store.write_json("out.enc.json", {"a": 1}, key_id=TEST_KEY_ID, artifact_type="t")
    assert path.parent == tmp_path.resolve()
    assert path.is_file()


def test_path_traversal_rejected(tmp_path) -> None:  # 36
    with pytest.raises(EncryptedArtifactPathError):
        resolve_artifact_path("../escape.enc.json", tmp_path)


def test_write_outside_approved_dir_rejected(store) -> None:  # 37
    with pytest.raises(EncryptedArtifactPathError):
        store.write_json("../../evil.enc.json", {"a": 1}, key_id=TEST_KEY_ID, artifact_type="t")


def test_read_outside_approved_dir_rejected(store) -> None:  # 38
    with pytest.raises(EncryptedArtifactPathError):
        store.read_json("../../evil.enc.json")


# --- source dataset safety / no plaintext (39, 40, 43) ---------------------- #
def test_source_raw_dataset_not_modified(tmp_path) -> None:  # 39
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    source = raw_dir / "clients.csv"
    source.write_text("client_id,client_name\n1,Original\n", encoding="utf-8")
    original_bytes = source.read_bytes()

    enc_dir = tmp_path / "encrypted"
    enc_dir.mkdir()
    store = EncryptedArtifactStore(make_service(), approved_dir=enc_dir)
    store.write_json("out.enc.json", {"x": 1}, key_id=TEST_KEY_ID, artifact_type="t")

    assert source.read_bytes() == original_bytes  # untouched


def test_stored_artifact_contains_no_plaintext(store) -> None:  # 40
    path = store.write_json(
        "out.enc.json", {"client_name": MARKER}, key_id=TEST_KEY_ID, artifact_type="t"
    )
    assert MARKER.encode() not in path.read_bytes()


def test_no_plaintext_temp_files_created(tmp_path) -> None:  # 43
    store = EncryptedArtifactStore(make_service(), approved_dir=tmp_path)
    path = store.write_json(
        "out.enc.json", {"client_name": MARKER}, key_id=TEST_KEY_ID, artifact_type="t"
    )
    # Only the final encrypted artifact remains in its directory; no leftover
    # .tmp files, and no plaintext file was ever written anywhere in it.
    names = os.listdir(path.parent)
    assert names == ["out.enc.json"]
    for name in names:
        assert MARKER.encode() not in (path.parent / name).read_bytes()


# --- decrypt round trip (41) -------------------------------------------------- #
def test_stored_artifact_decrypts_through_service(store) -> None:  # 41
    payload = {"client_id": "1", "client_name": MARKER}
    store.write_json("out.enc.json", payload, key_id=TEST_KEY_ID, artifact_type="t")
    assert store.read_json("out.enc.json") == payload


# --- atomic writes (42) ------------------------------------------------------- #
def test_no_partial_file_left_after_simulated_write_failure(tmp_path, monkeypatch) -> None:  # 42
    store = EncryptedArtifactStore(make_service(), approved_dir=tmp_path)

    import os as os_mod

    real_replace = os_mod.replace

    def failing_replace(*args, **kwargs):
        raise OSError("simulated failure during atomic replace")

    monkeypatch.setattr(os_mod, "replace", failing_replace)
    with pytest.raises(OSError):
        store.write_json("out.enc.json", {"a": 1}, key_id=TEST_KEY_ID, artifact_type="t")
    monkeypatch.setattr(os_mod, "replace", real_replace)

    # No final artifact and no leftover temp file.
    assert list(tmp_path.iterdir()) == []
