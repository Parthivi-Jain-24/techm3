"""Shared fake-Vault test helpers for Phase 8 (not a test module).

Mimics the small slice of the real ``hvac.Client`` shape our
``VaultSecretProvider`` actually calls
(``client.secrets.kv.v2.read_secret_version(path=..., mount_point=...)``), so
tests never require a real Vault server or network access.
"""

from __future__ import annotations

import base64
import os


def random_key_b64(n_bytes: int = 32) -> str:
    return base64.b64encode(os.urandom(n_bytes)).decode("ascii")


class FakeKV2:
    def __init__(self, data: dict[str, str] | None = None, exc: Exception | None = None) -> None:
        self._data = data or {}
        self._exc = exc
        self.calls: list[tuple[str, str]] = []

    def read_secret_version(self, path: str, mount_point: str, **kwargs) -> dict:
        self.calls.append((path, mount_point))
        if self._exc is not None:
            raise self._exc
        return {"data": {"data": dict(self._data), "metadata": {"version": 1}}}


class FakeKV:
    def __init__(self, kv2: FakeKV2) -> None:
        self.v2 = kv2


class FakeSecrets:
    def __init__(self, kv2: FakeKV2) -> None:
        self.kv = FakeKV(kv2)


class FakeVaultClient:
    """Drop-in stand-in for ``hvac.Client`` covering only what we use."""

    def __init__(self, data: dict[str, str] | None = None, exc: Exception | None = None) -> None:
        self.kv2 = FakeKV2(data, exc)
        self.secrets = FakeSecrets(self.kv2)


def make_vault_provider(data: dict[str, str] | None = None, exc: Exception | None = None, **kwargs):
    from app.secrets.vault_provider import VaultSecretProvider

    client = FakeVaultClient(data=data, exc=exc)
    params = dict(addr="http://127.0.0.1:8200", token="fake-test-token", client=client)
    params.update(kwargs)
    return VaultSecretProvider(**params), client
