"""Phase 6 tests: encrypted export integration with existing KYC ingestion."""

from __future__ import annotations

from pathlib import Path

from app.encryption.artifact_store import EncryptedArtifactStore
from app.ingestion.pipelines.kyc_ingestion_pipeline import (
    export_encrypted_kyc_artifact,
    ingest_kyc_file,
)
from app.schemas.kyc import NormalizedKYCEntity
from tests._encryption_helpers import TEST_KEY_ID, make_service

SYNTHETIC_NAME = "SYNTHETIC_TEST_CUSTOMER_987654"


def _write_synthetic_csv(directory: Path) -> None:
    header = (
        "client_id,client_name,client_type,sector,sector_risk,country,"
        "pep_flag,sanctions_flag,fatf_country_flag\n"
    )
    row = f'1,"{SYNTHETIC_NAME}",Individual,Tech,High,in,0,0,0\n'
    (directory / "synthetic.csv").write_text(header + row, encoding="utf-8")


def test_synthetic_entity_serialized_and_encrypted(tmp_path: Path) -> None:  # 44
    entity = NormalizedKYCEntity(
        client_id="1", client_name=SYNTHETIC_NAME, client_type="Individual",
        country="IN", sector="Tech", sector_risk="high",
    )
    svc = make_service()
    envelope = svc.encrypt_json(
        [entity.model_dump(mode="json")], key_id=TEST_KEY_ID, artifact_type="normalized_kyc_entities"
    )
    assert envelope.ciphertext


def test_encrypted_kyc_artifact_full_pipeline_no_plaintext_name(tmp_path: Path) -> None:  # 45, 47, 48
    _write_synthetic_csv(tmp_path)
    result = ingest_kyc_file("synthetic.csv", approved_dir=tmp_path)  # reuses Phase 2
    assert len(result.entities) == 1
    assert isinstance(result.entities[0], NormalizedKYCEntity)  # existing canonical schema

    enc_dir = tmp_path / "encrypted"
    enc_dir.mkdir()
    store = EncryptedArtifactStore(make_service(), approved_dir=enc_dir)
    path = export_encrypted_kyc_artifact(
        result, "clients.enc.json", key_id=TEST_KEY_ID, store=store
    )
    stored_bytes = path.read_bytes()
    assert SYNTHETIC_NAME.encode() not in stored_bytes  # 45: no plaintext name


def test_encrypted_kyc_artifact_decrypts_to_expected_structure(tmp_path: Path) -> None:  # 46
    _write_synthetic_csv(tmp_path)
    result = ingest_kyc_file("synthetic.csv", approved_dir=tmp_path)

    enc_dir = tmp_path / "encrypted"
    enc_dir.mkdir()
    store = EncryptedArtifactStore(make_service(), approved_dir=enc_dir)
    export_encrypted_kyc_artifact(result, "clients.enc.json", key_id=TEST_KEY_ID, store=store)

    decrypted = store.read_json("clients.enc.json")
    assert isinstance(decrypted, list) and len(decrypted) == 1
    assert decrypted[0]["client_id"] == "1"
    assert decrypted[0]["client_name"] == SYNTHETIC_NAME
    assert decrypted[0]["sector_risk"] == "high"
