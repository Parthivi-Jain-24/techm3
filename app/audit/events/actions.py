"""Curated, stable machine-readable ``action`` names (Phase 9).

Every call site imports a constant from here rather than inlining a literal,
so the set of action names used in practice stays discoverable in one place.
``AuditEvent.action`` still validates the *format* (see ``models.py``) so a
typo'd or user-influenced value cannot slip through even if a call site
doesn't use these constants -- but call sites SHOULD use them.
"""

from __future__ import annotations

# --- HTTP request lifecycle ------------------------------------------------ #
REQUEST_COMPLETED = "request.completed"

# --- Authentication (Phase 4 integration) ---------------------------------- #
AUTHENTICATION_SUCCEEDED = "authentication.succeeded"
AUTHENTICATION_FAILED = "authentication.failed"

# --- Authorization / RBAC (Phase 4 integration) ---------------------------- #
AUTHORIZATION_ALLOWED = "authorization.allowed"
AUTHORIZATION_DENIED = "authorization.denied"

# --- File ingestion (Phase 2 integration) ---------------------------------- #
INGESTION_FILE_STARTED = "ingestion.file.started"
INGESTION_FILE_COMPLETED = "ingestion.file.completed"
INGESTION_FILE_FAILED = "ingestion.file.failed"

# --- API ingestion (Phase 5 integration) ------------------------------------ #
INGESTION_API_STARTED = "ingestion.api.started"
INGESTION_API_COMPLETED = "ingestion.api.completed"
INGESTION_API_FAILED = "ingestion.api.failed"

# --- Encryption (Phase 6 integration) --------------------------------------- #
ENCRYPTION_ENCRYPT_SUCCEEDED = "encryption.encrypt.succeeded"
ENCRYPTION_ENCRYPT_FAILED = "encryption.encrypt.failed"
ENCRYPTION_DECRYPT_SUCCEEDED = "encryption.decrypt.succeeded"
ENCRYPTION_DECRYPT_FAILED = "encryption.decrypt.failed"

# --- Secret access (Phase 8 integration) ------------------------------------ #
SECRET_ACCESS_SUCCEEDED = "secret.access.succeeded"
SECRET_ACCESS_FAILED = "secret.access.failed"
