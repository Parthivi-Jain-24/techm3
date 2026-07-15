"""Trusted API source registry.

Resolves a caller-supplied ``source_id`` to server-controlled
``TrustedApiSourceConfig``. Callers can ONLY pick an id — never a URL, auth,
mapping, TLS, or redirect setting. Unknown/disabled sources are rejected.
"""

from __future__ import annotations

import json

from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError
from app.ingestion.api.models import TrustedApiSourceConfig


class ApiSourceRegistry:
    def __init__(self, sources: list[TrustedApiSourceConfig] | None = None) -> None:
        self._by_id: dict[str, TrustedApiSourceConfig] = {
            s.source_id: s for s in (sources or [])
        }

    def resolve(self, source_id: str) -> TrustedApiSourceConfig:
        source = self._by_id.get(source_id)
        if source is None:
            raise ApiIngestionError(ApiErrorCode.UNKNOWN_SOURCE, "unknown source")
        if not source.enabled:
            raise ApiIngestionError(ApiErrorCode.SOURCE_DISABLED, "source is disabled")
        return source

    def source_ids(self) -> list[str]:
        return list(self._by_id)


def build_registry_from_config(raw_json: str) -> ApiSourceRegistry:
    """Build a registry from a JSON array string (``settings.api_sources_json``).

    Malformed entries are skipped; empty/blank yields an empty registry.
    """
    sources: list[TrustedApiSourceConfig] = []
    raw_json = (raw_json or "").strip()
    if raw_json:
        try:
            items = json.loads(raw_json)
        except json.JSONDecodeError:
            items = []
        for item in items if isinstance(items, list) else []:
            try:
                sources.append(TrustedApiSourceConfig(**item))
            except Exception:  # noqa: BLE001 - skip invalid source entries safely
                continue
    return ApiSourceRegistry(sources)
