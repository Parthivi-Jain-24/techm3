"""Phase 6 tests: versioned encrypted-envelope validation."""

from __future__ import annotations

import base64
import os

import pydantic
import pytest

from app.encryption.errors import (
    MalformedEncryptedEnvelopeError,
    UnsupportedAlgorithmError,
    UnsupportedEnvelopeVersionError,
)
from app.encryption.models import ALGORITHM, ENVELOPE_VERSION, EncryptedEnvelope

VALID_KWARGS = dict(
    version=ENVELOPE_VERSION,
    algorithm=ALGORITHM,
    key_id="k1",
    artifact_type="t",
    nonce=base64.b64encode(os.urandom(12)).decode(),
    ciphertext=base64.b64encode(b"ciphertext-bytes-here").decode(),
)


def _envelope(**overrides) -> EncryptedEnvelope:
    return EncryptedEnvelope(**{**VALID_KWARGS, **overrides})


# --- explicit fields (20-24) ------------------------------------------------ #
def test_envelope_has_explicit_version() -> None:  # 20
    assert _envelope().version == 1


def test_envelope_has_explicit_algorithm() -> None:  # 21
    assert _envelope().algorithm == "AES-256-GCM"


def test_envelope_has_nonsecret_key_id() -> None:  # 22
    assert _envelope(key_id="kyc-data-key-v1").key_id == "kyc-data-key-v1"


def test_envelope_contains_no_encryption_key() -> None:  # 23
    fields = set(EncryptedEnvelope.model_fields)
    assert not any("key_material" in f or f == "key" for f in fields)
    assert "key_id" in fields  # reference only


def test_envelope_contains_no_plaintext_field() -> None:  # 24
    fields = set(EncryptedEnvelope.model_fields)
    assert "plaintext" not in fields


# --- strict validation (25-29) ---------------------------------------------- #
def test_unsupported_version_rejected() -> None:  # 25
    with pytest.raises(UnsupportedEnvelopeVersionError):
        _envelope(version=2)


def test_unsupported_algorithm_rejected() -> None:  # 26
    with pytest.raises(UnsupportedAlgorithmError):
        _envelope(algorithm="AES-128-GCM")
    with pytest.raises(UnsupportedAlgorithmError):
        _envelope(algorithm="none")


def test_malformed_base64_nonce_rejected() -> None:  # 27
    with pytest.raises(MalformedEncryptedEnvelopeError):
        _envelope(nonce="not-valid-base64!!!")


def test_malformed_base64_ciphertext_rejected() -> None:  # 28
    with pytest.raises(MalformedEncryptedEnvelopeError):
        _envelope(ciphertext="not-valid-base64!!!")


def test_missing_required_fields_rejected() -> None:  # 29
    with pytest.raises(pydantic.ValidationError):
        EncryptedEnvelope(version=1, algorithm=ALGORITHM)  # missing key_id/nonce/etc


def test_wrong_nonce_length_rejected() -> None:
    with pytest.raises(MalformedEncryptedEnvelopeError):
        _envelope(nonce=base64.b64encode(os.urandom(16)).decode())


def test_extra_fields_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        _envelope(unexpected_field="x")


def test_envelope_round_trips_through_json() -> None:
    env = _envelope()
    restored = EncryptedEnvelope.model_validate_json(env.model_dump_json())
    assert restored == env
