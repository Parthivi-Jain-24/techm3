"""Safe outbound HTTP client for API ingestion.

Guarantees on every request: explicit timeouts, redirects OFF (unless a trusted
source opts in), TLS verification NEVER disabled, SSRF destination validation
before connecting, Content-Length + streamed byte-cap enforcement, Content-Type
validation, safe JSON parsing, and bounded retries for transient failures only.

Secret safety: auth values come from the SecretProvider, are placed only in
request headers (never the URL/query), and are NEVER logged. This module does no
request/response body logging at all.
"""

from __future__ import annotations

import asyncio
import json

import httpx

from app.audit.integrations import audit_secret_access
from app.core.config import settings
from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError
from app.ingestion.api.models import ApiAuthType, TrustedApiSourceConfig
from app.ingestion.api.security import Resolver, _default_resolver, validate_destination
from app.secrets.provider import SecretProvider

# JSON content types accepted for a successful KYC payload.
_ALLOWED_JSON_TYPES = ("application/json",)


class ApiConnector:
    """Performs a single safe outbound fetch for a trusted source."""

    def __init__(
        self,
        secret_provider: SecretProvider,
        *,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = _default_resolver,
    ) -> None:
        self._secrets = secret_provider
        self._transport = transport  # httpx MockTransport in tests; None in prod
        self._resolver = resolver

    # ---- auth header construction (never logged, never in URL) ----------- #
    def _auth_headers(self, source: TrustedApiSourceConfig) -> dict[str, str]:
        if source.auth_type is ApiAuthType.NONE:
            return {}
        logical_name = source.auth_secret_name or ""
        try:
            secret = self._secrets.get_secret(logical_name)
        except Exception:
            audit_secret_access(self._secrets, logical_name, success=False)
            raise
        if not secret:
            audit_secret_access(self._secrets, logical_name, success=False)
            raise ApiIngestionError(
                ApiErrorCode.AUTHENTICATION_CONFIGURATION_ERROR,
                "authentication secret is not configured",
            )
        audit_secret_access(self._secrets, logical_name, success=True)
        if source.auth_type is ApiAuthType.BEARER_TOKEN:
            return {"Authorization": f"Bearer {secret}"}
        # API_KEY_HEADER
        return {source.auth_header_name: secret}  # type: ignore[dict-item]

    def _max_bytes(self, source: TrustedApiSourceConfig) -> int:
        mb = source.max_response_size_mb or settings.max_api_response_size_mb
        return int(mb * 1024 * 1024)

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=settings.api_connect_timeout_seconds,
            read=settings.api_read_timeout_seconds,
            write=settings.api_write_timeout_seconds,
            pool=settings.api_pool_timeout_seconds,
        )

    async def fetch(self, source: TrustedApiSourceConfig) -> object:
        """Fetch + validate + parse JSON from a trusted source; return payload."""
        url = source.url
        validate_destination(
            url, allow_insecure=source.allow_insecure, resolve=self._resolver
        )
        headers = {"Accept": "application/json", **self._auth_headers(source)}
        max_bytes = self._max_bytes(source)

        attempts = settings.api_max_retries + 1
        last_error: ApiIngestionError | None = None
        for attempt in range(attempts):
            try:
                return await self._attempt(source, url, headers, max_bytes)
            except ApiIngestionError as exc:
                last_error = exc
                if exc.retryable and attempt < attempts - 1:
                    await asyncio.sleep(settings.api_retry_backoff_seconds * (2 ** attempt))
                    continue
                raise
        assert last_error is not None  # pragma: no cover
        raise last_error

    async def _attempt(
        self, source: TrustedApiSourceConfig, url: str, headers: dict[str, str], max_bytes: int
    ) -> object:
        client_kwargs = dict(
            timeout=self._timeout(),
            follow_redirects=source.follow_redirects,  # False by default
            # NOTE: verify is left at httpx default (True). Never set verify=False.
        )
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                async with client.stream(
                    source.http_method.value, url, headers=headers
                ) as response:
                    self._check_status(response.status_code)
                    self._check_content_length(response, max_bytes)
                    self._check_content_type(response)
                    body = await self._read_bounded(response, max_bytes)
        except httpx.TimeoutException:
            raise ApiIngestionError(
                ApiErrorCode.UPSTREAM_TIMEOUT, "upstream request timed out", retryable=True
            )
        except httpx.TransportError:
            raise ApiIngestionError(
                ApiErrorCode.UPSTREAM_UNAVAILABLE, "upstream is unavailable", retryable=True
            )
        return self._parse_json(body)

    # ---- response validation -------------------------------------------- #
    @staticmethod
    def _check_status(status: int) -> None:
        if 200 <= status < 300:
            return
        if status == 429:
            raise ApiIngestionError(
                ApiErrorCode.UPSTREAM_RATE_LIMITED, "upstream rate limited", retryable=True
            )
        if 500 <= status < 600:
            raise ApiIngestionError(
                ApiErrorCode.UPSTREAM_UNAVAILABLE, "upstream server error", retryable=True
            )
        # 4xx (incl. 401/403/404) — client/config problem; never retry, never
        # echo the upstream body.
        raise ApiIngestionError(
            ApiErrorCode.UPSTREAM_CLIENT_ERROR,
            f"upstream returned status {status}",
            retryable=False,
        )

    def _check_content_length(self, response: httpx.Response, max_bytes: int) -> None:
        cl = response.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > max_bytes:
                    raise ApiIngestionError(
                        ApiErrorCode.RESPONSE_TOO_LARGE, "response too large"
                    )
            except ValueError:
                pass  # untrustworthy header; the streamed cap still applies

    def _check_content_type(self, response: httpx.Response) -> None:
        ctype = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if ctype not in _ALLOWED_JSON_TYPES:
            raise ApiIngestionError(
                ApiErrorCode.INVALID_CONTENT_TYPE,
                f"unexpected content type: {ctype or 'unknown'}",
            )

    @staticmethod
    async def _read_bounded(response: httpx.Response, max_bytes: int) -> bytes:
        chunks = bytearray()
        async for chunk in response.aiter_bytes():
            chunks.extend(chunk)
            if len(chunks) > max_bytes:  # enforce ACTUAL bytes, not just header
                raise ApiIngestionError(
                    ApiErrorCode.RESPONSE_TOO_LARGE, "response too large"
                )
        return bytes(chunks)

    @staticmethod
    def _parse_json(body: bytes) -> object:
        if not body.strip():
            raise ApiIngestionError(ApiErrorCode.MALFORMED_JSON, "empty response body")
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            raise ApiIngestionError(ApiErrorCode.MALFORMED_JSON, "response was not valid JSON")
