"""Phase 10 — consolidated NEGATIVE security suite (Part R).

Defensive tests that exercise attacker/error paths against the LOCAL app: bad
input, forged tokens, SSRF attempts, tampered ciphertext, unavailable Vault,
malformed correlation IDs. No exploit tooling — these assert the app REJECTS
the bad case. Many individual controls also have unit tests in their phase's
own file; this suite proves them from an adversary's entry point and in one
reviewable place for the security walkthrough.
"""

from __future__ import annotations

import asyncio
import base64
import os

import pytest

from tests._api_helpers import json_transport, make_connector, make_source

# --------------------------------------------------------------------------- #
# Ingestion — path traversal / bad file
# --------------------------------------------------------------------------- #
def test_neg_path_traversal_rejected(tmp_path):
    from app.ingestion.errors import KycPathError
    from app.ingestion.pipelines.kyc_ingestion_pipeline import ingest_kyc_file

    (tmp_path / "approved").mkdir()
    with pytest.raises(KycPathError):
        ingest_kyc_file("../../etc/passwd", approved_dir=tmp_path / "approved")


def test_neg_unsupported_extension_rejected(tmp_path):
    from app.ingestion.errors import UnsupportedFileTypeError
    from app.ingestion.pipelines.kyc_ingestion_pipeline import ingest_kyc_file

    (tmp_path / "evil.exe").write_bytes(b"MZ...")
    with pytest.raises(UnsupportedFileTypeError):
        ingest_kyc_file("evil.exe", approved_dir=tmp_path)


def test_neg_corrupt_xlsx_rejected(tmp_path):
    from app.ingestion.errors import CorruptFileError
    from app.ingestion.pipelines.kyc_ingestion_pipeline import ingest_kyc_file

    (tmp_path / "corrupt.xlsx").write_bytes(b"not-a-zip")
    with pytest.raises(CorruptFileError):
        ingest_kyc_file("corrupt.xlsx", approved_dir=tmp_path)


# --------------------------------------------------------------------------- #
# JWT — malformed / modified / expired / bad algorithm
# --------------------------------------------------------------------------- #
def test_neg_malformed_jwt_rejected(jwt_secret):
    from app.identity.authentication.tokens import decode_access_token
    from app.identity.errors import InvalidTokenError

    with pytest.raises(InvalidTokenError):
        decode_access_token("this.is.not-a-real-jwt")


def test_neg_modified_jwt_signature_rejected(jwt_secret):
    from app.identity.authentication.models import Principal, PrincipalType
    from app.identity.authentication.tokens import create_access_token, decode_access_token
    from app.identity.errors import InvalidTokenError
    from app.identity.rbac.roles import Role

    p = Principal(principal_id="U-X", principal_type=PrincipalType.USER, roles=[Role.AUDITOR])
    tok = create_access_token(p)
    forged = tok[:-3] + ("aaa" if not tok.endswith("aaa") else "bbb")
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


def test_neg_unsupported_algorithm_rejected(jwt_secret):
    from app.identity.authentication.tokens import decode_access_token
    from app.identity.errors import AuthConfigError

    with pytest.raises(AuthConfigError):
        decode_access_token("x.y.z", algorithms=["none"])


def test_neg_anonymous_denied_on_protected_endpoint(client):
    r = client.post("/api/v1/ingestion/api/kyc_provider/run")
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# SSRF — localhost / private / link-local(metadata) destinations
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "10.0.0.5", "192.168.1.10", "169.254.169.254", "[::1]"],
)
def test_neg_ssrf_blocked_destinations(host):
    from app.ingestion.api.errors import ApiIngestionError
    from app.ingestion.api.security import validate_destination

    url = f"https://{host}/kyc"
    with pytest.raises(ApiIngestionError):
        # resolver returns the literal host so no DNS is needed for literal IPs;
        # for "localhost" the hostname rule rejects before resolution.
        validate_destination(url, allow_insecure=False, resolve=lambda h: [h.strip("[]")])


def test_neg_ssrf_userinfo_rejected():
    from app.ingestion.api.errors import ApiIngestionError
    from app.ingestion.api.security import validate_destination

    with pytest.raises(ApiIngestionError):
        validate_destination("https://user:pass@example.com/kyc", allow_insecure=False,
                             resolve=lambda h: ["93.184.216.34"])


def test_neg_http_external_rejected_when_https_required():
    from app.ingestion.api.errors import ApiIngestionError
    from app.ingestion.api.security import validate_destination

    with pytest.raises(ApiIngestionError):
        validate_destination("http://example.com/kyc", allow_insecure=False,
                             resolve=lambda h: ["93.184.216.34"])


# --------------------------------------------------------------------------- #
# API ingestion — oversized response / malformed JSON
# --------------------------------------------------------------------------- #
def test_neg_oversized_api_response_rejected():
    from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError

    big = [{"customerId": str(i), "fullName": "x", "kind": "Individual", "iso": "in",
            "industry": "T", "risk": "Low", "pep": False, "sanctioned": False, "fatf": 0}
           for i in range(5)]
    # Force a tiny cap so the (small) body still exceeds it.
    source = make_source(max_response_size_mb=0.0000001)
    connector = make_connector(json_transport(big))
    with pytest.raises(ApiIngestionError) as exc:
        asyncio.run(connector.fetch(source))
    assert exc.value.code == ApiErrorCode.RESPONSE_TOO_LARGE


def test_neg_malformed_api_json_rejected():
    import httpx

    from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError

    def handler(request):
        return httpx.Response(200, content=b"{not valid json", headers={"content-type": "application/json"})

    connector = make_connector(httpx.MockTransport(handler))
    with pytest.raises(ApiIngestionError) as exc:
        asyncio.run(connector.fetch(make_source()))
    assert exc.value.code == ApiErrorCode.MALFORMED_JSON


def test_neg_non_json_content_type_rejected():
    import httpx

    from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError

    def handler(request):
        return httpx.Response(200, content=b"<html>nope</html>", headers={"content-type": "text/html"})

    connector = make_connector(httpx.MockTransport(handler))
    with pytest.raises(ApiIngestionError) as exc:
        asyncio.run(connector.fetch(make_source()))
    assert exc.value.code == ApiErrorCode.INVALID_CONTENT_TYPE


# --------------------------------------------------------------------------- #
# Encryption — invalid key / tamper / wrong key / missing secret
# --------------------------------------------------------------------------- #
def test_neg_invalid_aes_key_rejected():
    from app.encryption.errors import InvalidEncryptionKeyError
    from app.encryption.keys import decode_key

    with pytest.raises(InvalidEncryptionKeyError):
        decode_key("not-valid-base64!!!")
    with pytest.raises(InvalidEncryptionKeyError):
        decode_key(base64.b64encode(os.urandom(16)).decode())  # AES-128 size


def test_neg_wrong_key_fails_closed():
    from app.encryption.errors import DecryptionFailedError
    from app.encryption.service import EncryptionService
    from app.secrets.provider import EnvironmentSecretProvider
    from tests._encryption_helpers import random_key_b64

    k1, k2 = random_key_b64(), random_key_b64()
    enc = EncryptionService(EnvironmentSecretProvider({"k": k1}))
    env = enc.encrypt_bytes(b"top secret", key_id="k", artifact_type="t")
    # Same key_id, different material -> authentication fails, no partial plaintext.
    dec = EncryptionService(EnvironmentSecretProvider({"k": k2}))
    with pytest.raises(DecryptionFailedError):
        dec.decrypt_bytes(env)


def test_neg_missing_encryption_secret_fails_safely():
    from app.encryption.errors import EncryptionConfigurationError
    from app.encryption.service import EncryptionService
    from app.secrets.provider import EnvironmentSecretProvider

    svc = EncryptionService(EnvironmentSecretProvider({}))
    with pytest.raises(EncryptionConfigurationError):
        svc.encrypt_bytes(b"x", key_id="missing", artifact_type="t")


# --------------------------------------------------------------------------- #
# Vault — unavailable / auth failure / malformed response
# --------------------------------------------------------------------------- #
def test_neg_vault_backend_unavailable_fails_safely():
    from app.secrets.exceptions import SecretBackendUnavailableError
    from tests._vault_helpers import make_vault_provider

    provider, _ = make_vault_provider(exc=RuntimeError("connection refused"))
    with pytest.raises(SecretBackendUnavailableError):
        provider.get_secret("kyc-data-key-v1")


def test_neg_vault_auth_failure_fails_safely():
    import hvac.exceptions as hvac_exc

    from app.secrets.exceptions import SecretAuthenticationError
    from tests._vault_helpers import make_vault_provider

    provider, _ = make_vault_provider(exc=hvac_exc.Forbidden("denied"))
    with pytest.raises(SecretAuthenticationError):
        provider.get_secret("kyc-data-key-v1")


def test_neg_vault_missing_secret_returns_none():
    from tests._vault_helpers import make_vault_provider

    provider, _ = make_vault_provider(data={"some-other-key": "v"})
    assert provider.get_secret("kyc-data-key-v1") is None


# --------------------------------------------------------------------------- #
# Audit — malformed request ID replaced; secret-like metadata redacted
# --------------------------------------------------------------------------- #
def test_neg_malformed_request_id_replaced(client):
    r = client.get("/api/v1/health/live", headers={"X-Request-ID": "evil\r\nInjected: 1"})
    import uuid

    returned = r.headers["x-request-id"]
    assert uuid.UUID(returned)  # a fresh valid UUID, not the injected value
    assert "Injected" not in returned


def test_neg_secret_like_audit_metadata_redacted():
    from app.audit.events.sanitize import REDACTED, sanitize_metadata

    out = sanitize_metadata({"vault_token": "PHASE10_VAULT_TOKEN_DO_NOT_LEAK_103", "key_id": "safe"})
    assert out["vault_token"] == REDACTED
    assert out["key_id"] == "safe"  # non-secret identifier preserved
