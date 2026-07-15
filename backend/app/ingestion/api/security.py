"""SSRF-aware outbound destination validation.

Applied to every configured source URL BEFORE any network access. Reduces (does
NOT eliminate) SSRF risk — see the DNS-rebinding note in docs/api-ingestion.md;
production must add network egress controls / allowlists.

The ``allow_insecure`` flag (test-only, on server-controlled source config)
relaxes scheme + IP checks so mock-transport tests can use http://testserver;
production sources keep it False and remain fully validated.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

from app.ingestion.api.errors import ApiErrorCode, ApiIngestionError

# Hostnames that must never be contacted by a non-test source.
_BLOCKED_HOSTNAMES = frozenset({"localhost", "ip6-localhost", "metadata", "metadata.google.internal"})

Resolver = Callable[[str], list[str]]


def _default_resolver(hostname: str) -> list[str]:
    """Resolve a hostname to its IP strings via the system resolver."""
    infos = socket.getaddrinfo(hostname, None)
    return [info[4][0] for info in infos]


def _reject(message: str) -> ApiIngestionError:
    # Never include credentials/userinfo in the message.
    return ApiIngestionError(ApiErrorCode.UNSAFE_DESTINATION, message, retryable=False)


def _ip_is_disallowed(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable -> unsafe
    return (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local      # includes 169.254.0.0/16 (cloud metadata) and fe80::/10
        or addr.is_multicast
        or addr.is_unspecified
        or addr.is_reserved
    )


def validate_destination(
    url: str,
    *,
    allow_insecure: bool = False,
    resolve: Resolver = _default_resolver,
) -> None:
    """Validate an outbound URL, raising ``ApiIngestionError`` if unsafe."""
    try:
        parts = urlsplit(url)
    except ValueError:
        raise _reject("malformed destination URL")

    scheme = parts.scheme.lower()
    if not scheme or not parts.netloc:
        raise _reject("malformed destination URL")

    # HTTPS required for real sources; http only via explicit test-only flag.
    if scheme != "https":
        if not (allow_insecure and scheme == "http"):
            raise _reject("destination must use https")

    # No credentials in the URL.
    if parts.username or parts.password or "@" in parts.netloc:
        raise _reject("destination URL must not contain userinfo")

    # No fragments on a data-retrieval URL.
    if parts.fragment:
        raise _reject("destination URL must not contain a fragment")

    hostname = parts.hostname
    if not hostname:
        raise _reject("destination URL has no hostname")

    if allow_insecure:
        return  # test transport: structural checks only

    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise _reject("destination hostname is not permitted")

    # If the host is a literal IP, classify it directly (no DNS needed).
    try:
        ipaddress.ip_address(hostname.strip("[]"))
        literal_ip = True
    except ValueError:
        literal_ip = False

    candidates = [hostname.strip("[]")] if literal_ip else _resolve_safe(hostname, resolve)
    for ip in candidates:
        if _ip_is_disallowed(ip):
            raise _reject("destination resolves to a disallowed address")


def _resolve_safe(hostname: str, resolve: Resolver) -> list[str]:
    try:
        ips = resolve(hostname)
    except OSError:
        raise _reject("destination hostname could not be resolved")
    if not ips:
        raise _reject("destination hostname could not be resolved")
    return ips
