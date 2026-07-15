"""Shared helpers for Phase 6 encryption tests (not a test module)."""

from __future__ import annotations

import base64
import os

from app.encryption.service import EncryptionService
from app.secrets.provider import EnvironmentSecretProvider

TEST_KEY_ID = "test-encryption-key"


def random_key_b64(n_bytes: int = 32) -> str:
    return base64.b64encode(os.urandom(n_bytes)).decode("ascii")


def make_service(key_id: str = TEST_KEY_ID, key_b64: str | None = None) -> EncryptionService:
    key_b64 = key_b64 if key_b64 is not None else random_key_b64()
    provider = EnvironmentSecretProvider({key_id: key_b64})
    return EncryptionService(provider)
