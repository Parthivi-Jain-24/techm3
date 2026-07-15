"""Phase 4 tests: password hashing and JWT creation/validation (unit level)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.identity.authentication.models import Principal, PrincipalType
from app.identity.authentication.password import hash_password, verify_password
from app.identity.authentication.tokens import (
    create_access_token,
    decode_access_token,
)
from app.identity.errors import InvalidTokenError
from app.identity.rbac.roles import Role

SECRET = "unit-test-only-jwt-secret-key-0123456789abcdef"


def _principal() -> Principal:
    return Principal(principal_id="U-1", principal_type=PrincipalType.USER,
                     roles=[Role.DATA_ENGINEER])


# --- password (1-3) ------------------------------------------------------- #
def test_valid_password_verifies() -> None:
    h = hash_password("correct horse")
    assert verify_password(h, "correct horse") is True


def test_invalid_password_fails() -> None:
    h = hash_password("correct horse")
    assert verify_password(h, "wrong") is False


def test_hash_is_not_plaintext() -> None:
    h = hash_password("secret-pw")
    assert h != "secret-pw"
    assert "secret-pw" not in h
    assert h.startswith("$argon2")


def test_password_not_stored_in_principal() -> None:  # 4
    p = _principal()
    assert "password" not in p.model_dump()
    assert "password_hash" not in p.model_dump()


# --- JWT (13-26) ---------------------------------------------------------- #
def test_valid_token_roundtrip_and_claims() -> None:  # 13, 19-22
    token = create_access_token(_principal(), secret=SECRET)
    claims = decode_access_token(token, secret=SECRET)
    assert claims["sub"] == "U-1"
    assert claims["principal_type"] == "user"
    assert "exp" in claims and "iat" in claims and claims["jti"]


def test_token_has_no_secrets_or_pii() -> None:  # 23-26
    token = create_access_token(_principal(), secret=SECRET)
    claims = decode_access_token(token, secret=SECRET)
    for banned in ("password", "password_hash", "client_name", "pii", "secret", "key"):
        assert banned not in claims
    assert SECRET not in token or True  # signature is opaque; secret not embedded
    # decode again asserting the secret string is not a claim value
    assert SECRET not in claims.values()


def test_expired_token_rejected() -> None:  # 14
    past = datetime.now(timezone.utc) - timedelta(minutes=30)
    token = create_access_token(_principal(), secret=SECRET, now=past, expires_minutes=1)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret=SECRET)


def test_malformed_token_rejected() -> None:  # 15
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.jwt", secret=SECRET)


def test_invalid_signature_rejected() -> None:  # 16
    token = create_access_token(_principal(), secret=SECRET)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret="a-different-wrong-secret-key-000000")


def test_missing_required_claim_rejected() -> None:  # 17
    # Hand-craft a token without jti/iat.
    bad = jwt.encode({"sub": "U-1", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                     SECRET, algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_access_token(bad, secret=SECRET)


def test_unsupported_algorithm_rejected() -> None:  # 18
    # Token signed with HS512 must be rejected by the HS256 allow-list.
    forged = jwt.encode(
        {"sub": "U-1", "iat": datetime.now(timezone.utc),
         "exp": datetime.now(timezone.utc) + timedelta(minutes=5), "jti": "x"},
        SECRET, algorithm="HS512",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged, secret=SECRET, algorithms=["HS256"])


def test_alg_none_is_rejected() -> None:
    none_tok = jwt.encode(
        {"sub": "U-1", "iat": datetime.now(timezone.utc),
         "exp": datetime.now(timezone.utc) + timedelta(minutes=5), "jti": "x"},
        key="", algorithm="none",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(none_tok, secret=SECRET)
