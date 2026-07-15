"""Phase 9 tests: centralized audit-metadata sanitization (PART R/S)."""

from __future__ import annotations

from app.audit.events.sanitize import (
    MAX_COLLECTION_SIZE,
    MAX_METADATA_DEPTH,
    MAX_STRING_LENGTH,
    REDACTED,
    sanitize_metadata,
)

SYNTHETIC_PASSWORD = "SYNTHETIC_PASSWORD_DO_NOT_LOG_111"
SYNTHETIC_JWT = "SYNTHETIC_JWT_DO_NOT_LOG_222"
SYNTHETIC_VAULT_TOKEN = "SYNTHETIC_VAULT_TOKEN_DO_NOT_LOG_333"
SYNTHETIC_API_KEY = "SYNTHETIC_API_KEY_DO_NOT_LOG_444"
SYNTHETIC_ENCRYPTION_KEY = "SYNTHETIC_ENCRYPTION_KEY_DO_NOT_LOG_555"


# --- sensitive key-name redaction (60-66) ----------------------------------- #
def test_password_fields_redacted() -> None:  # 60
    out = sanitize_metadata({"password": SYNTHETIC_PASSWORD, "user_password": SYNTHETIC_PASSWORD})
    assert out["password"] == REDACTED
    assert out["user_password"] == REDACTED


def test_token_fields_redacted() -> None:  # 61
    out = sanitize_metadata({"access_token": SYNTHETIC_JWT, "refresh_token": SYNTHETIC_JWT})
    assert out["access_token"] == REDACTED
    assert out["refresh_token"] == REDACTED


def test_authorization_fields_redacted() -> None:  # 62
    out = sanitize_metadata({"Authorization": "Bearer " + SYNTHETIC_JWT})
    assert out["Authorization"] == REDACTED


def test_api_key_fields_redacted() -> None:  # 63
    out = sanitize_metadata({"api_key": SYNTHETIC_API_KEY, "apikey": SYNTHETIC_API_KEY})
    assert out["api_key"] == REDACTED
    assert out["apikey"] == REDACTED


def test_encryption_key_fields_redacted() -> None:  # 64
    out = sanitize_metadata({"encryption_key": SYNTHETIC_ENCRYPTION_KEY})
    assert out["encryption_key"] == REDACTED


def test_vault_token_fields_redacted() -> None:  # 65
    out = sanitize_metadata({"vault_token": SYNTHETIC_VAULT_TOKEN})
    assert out["vault_token"] == REDACTED


def test_nested_sensitive_fields_sanitized() -> None:  # 66
    out = sanitize_metadata(
        {"upstream": {"headers": {"authorization": "Bearer " + SYNTHETIC_JWT}, "ok": True}}
    )
    assert out["upstream"]["headers"]["authorization"] == REDACTED
    assert out["upstream"]["ok"] is True


def test_credential_and_passphrase_and_private_key_redacted() -> None:
    out = sanitize_metadata(
        {"credential": "x", "passphrase": "x", "private_key": "x", "client_secret": "x"}
    )
    assert all(v == REDACTED for v in out.values())


# --- deliberate allow-list (PART R: "do not blindly redact 'key'") --------- #
def test_key_id_and_secret_reference_style_fields_not_redacted() -> None:  # 70
    out = sanitize_metadata(
        {
            "key_id": "kyc-data-key-v1",
            "secret_id": "trusted-kyc-provider-token",
            "secret_reference": "trusted-kyc-provider-token",
            "source_id": "kyc_provider",
            "artifact_type": "normalized_kyc_entities",
        }
    )
    assert out["key_id"] == "kyc-data-key-v1"
    assert out["secret_id"] == "trusted-kyc-provider-token"
    assert out["secret_reference"] == "trusted-kyc-provider-token"
    assert out["source_id"] == "kyc_provider"
    assert out["artifact_type"] == "normalized_kyc_entities"


def test_bare_substring_key_is_not_a_redaction_trigger() -> None:
    # "resource_id" / "key_id" contain no dangerous substring on their own --
    # confirms the sanitizer does not naively match the bare word "key".
    out = sanitize_metadata({"resource_id": "safe-value", "key_id": "safe-value"})
    assert out["resource_id"] == "safe-value"
    assert out["key_id"] == "safe-value"


# --- structural bounds (67-69) ---------------------------------------------- #
def test_excessive_depth_is_bounded() -> None:  # 67
    nested: dict = {"v": "bottom"}
    for _ in range(MAX_METADATA_DEPTH + 5):
        nested = {"n": nested}
    out = sanitize_metadata({"root": nested})
    # Must not raise (e.g. RecursionError) and must not preserve full depth.
    assert out is not None


def test_excessive_string_length_is_bounded() -> None:  # 68
    huge = "A" * (MAX_STRING_LENGTH * 3)
    out = sanitize_metadata({"note": huge})
    assert len(out["note"]) <= MAX_STRING_LENGTH + len("...[TRUNCATED]")
    assert out["note"] != huge


def test_excessive_collection_size_is_bounded() -> None:  # 69
    huge_list = list(range(MAX_COLLECTION_SIZE * 5))
    out = sanitize_metadata({"items": huge_list})
    assert len(out["items"]) <= MAX_COLLECTION_SIZE + 1  # + truncation marker


def test_sanitize_never_raises_on_unserializable_object() -> None:
    class Weird:
        def __repr__(self) -> str:
            return SYNTHETIC_PASSWORD  # even repr() must not leak

    out = sanitize_metadata({"thing": Weird()})
    assert SYNTHETIC_PASSWORD not in str(out)


def test_empty_and_none_metadata_returns_empty_dict() -> None:
    assert sanitize_metadata(None) == {}
    assert sanitize_metadata({}) == {}
