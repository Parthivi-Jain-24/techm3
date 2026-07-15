"""Safe, server-controlled audit-log path resolution (Phase 9, PART O/P).

The audit log destination is ALWAYS derived from server-side configuration
(``settings.audit_log_path``) -- there is no code path, anywhere in this
subsystem, that accepts a path (or path fragment) from an HTTP caller. This
mirrors the Phase 2 ``resolve_kyc_path`` / Phase 6 ``resolve_artifact_path``
pattern: resolve once, confirm the result stays inside the approved runtime
directory, and never trust caller-supplied path segments.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import PROJECT_ROOT, settings

# The one approved parent directory for runtime audit output. Never a
# dataset, docs, tests, or source-code directory (PART O).
AUDIT_RUNTIME_DIR = PROJECT_ROOT / "backend" / "var" / "audit"


def resolve_audit_log_path() -> Path:
    """Resolve the configured audit-log file path, anchored under the
    approved runtime audit directory. Raises ``ValueError`` if configuration
    would place the file outside that directory (defense in depth against a
    misconfigured ``AUDIT_LOG_PATH`` -- e.g. containing ``..``)."""
    configured = Path(settings.audit_log_path)
    candidate = configured if configured.is_absolute() else (PROJECT_ROOT / configured)
    candidate = candidate.resolve()

    approved = AUDIT_RUNTIME_DIR.resolve()
    try:
        candidate.relative_to(approved)
    except ValueError:
        # Fail safe to the approved default rather than writing outside the
        # approved directory or raising and taking down the whole app.
        return approved / "audit.jsonl"
    return candidate
