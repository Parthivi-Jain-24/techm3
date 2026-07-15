"""Phase 6 tests: logging safety + Phase 3 privacy controls remain intact."""

from __future__ import annotations

import logging

from app.privacy import ProcessingContext, minimize_kyc_entity, to_log_safe_dict
from app.schemas.kyc import NormalizedKYCEntity
from tests._encryption_helpers import TEST_KEY_ID, make_service, random_key_b64

SYNTHETIC_NAME = "SYNTHETIC_TEST_CUSTOMER_987654"
PLAINTEXT = f'{{"client_name": "{SYNTHETIC_NAME}"}}'.encode()


def test_encryption_key_not_logged(caplog) -> None:  # 49, 52
    key_b64 = random_key_b64()
    svc = make_service(key_b64=key_b64)
    with caplog.at_level(logging.DEBUG):
        envelope = svc.encrypt_bytes(PLAINTEXT, key_id=TEST_KEY_ID, artifact_type="t")
        svc.decrypt_bytes(envelope)
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert key_b64 not in blob  # exact key material never appears in logs


def test_plaintext_not_logged(caplog) -> None:  # 50
    svc = make_service()
    with caplog.at_level(logging.DEBUG):
        svc.encrypt_bytes(PLAINTEXT, key_id=TEST_KEY_ID, artifact_type="t")
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert SYNTHETIC_NAME not in blob


def test_decrypted_content_not_logged(caplog) -> None:  # 51
    svc = make_service()
    envelope = svc.encrypt_bytes(PLAINTEXT, key_id=TEST_KEY_ID, artifact_type="t")
    with caplog.at_level(logging.DEBUG):
        svc.decrypt_bytes(envelope)
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert SYNTHETIC_NAME not in blob


# --- privacy integration (53-55) ------------------------------------------- #
def test_phase3_masking_minimization_still_works() -> None:  # 53
    entity = NormalizedKYCEntity(
        client_id="1", client_name=SYNTHETIC_NAME, client_type="Individual",
        country="IN", sector="Tech", sector_risk="high",
    )
    safe = to_log_safe_dict(entity, pseudonymize_key="k")
    assert "client_name" not in safe


def test_encryption_does_not_replace_minimization() -> None:  # 54
    # Encrypting/decrypting an entity's JSON does not imply the decrypted
    # dict is automatically consumer-safe — minimization must still be applied.
    svc = make_service()
    entity = NormalizedKYCEntity(
        client_id="1", client_name=SYNTHETIC_NAME, client_type="Individual",
        country="IN", sector="Tech", sector_risk="high",
    )
    envelope = svc.encrypt_json(entity.model_dump(mode="json"), key_id=TEST_KEY_ID, artifact_type="t")
    decrypted = svc.decrypt_json(envelope)
    assert decrypted["client_name"] == SYNTHETIC_NAME  # decryption alone: full data

    # The safe path is: decrypt -> re-validate -> minimize before exposure.
    restored_entity = NormalizedKYCEntity(**decrypted)
    safe_view = minimize_kyc_entity(restored_entity, ProcessingContext.LOGGING, pseudonymize_key="k")
    assert "client_name" not in safe_view  # minimization still enforced post-decrypt


def test_decrypted_content_passes_through_privacy_controls() -> None:  # 55
    svc = make_service()
    entity = NormalizedKYCEntity(
        client_id="1", client_name=SYNTHETIC_NAME, client_type="Individual",
        country="IN", sector="Tech", sector_risk="high",
    )
    envelope = svc.encrypt_json(entity.model_dump(mode="json"), key_id=TEST_KEY_ID, artifact_type="t")
    restored = NormalizedKYCEntity(**svc.decrypt_json(envelope))
    external = minimize_kyc_entity(restored, ProcessingContext.EXTERNAL_RESPONSE, pseudonymize_key="k")
    assert SYNTHETIC_NAME not in str(external)
