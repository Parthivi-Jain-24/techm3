"""THE central, deterministic role -> permission mapping.

This is the single source of truth for authorization. Route handlers must never
hard-code role-name checks; they require *permissions*, which are resolved from
this mapping. Least privilege is applied deliberately (see docstring assertions
in tests and docs/authentication-and-rbac.md).
"""

from __future__ import annotations

from app.identity.authorization.permissions import Permission
from app.identity.rbac.roles import Role

P = Permission

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    # Security/config admin — explicitly NOT a blanket grant and NOT customer
    # KYC data access. A security admin is not automatically a compliance analyst.
    Role.ADMIN: frozenset({P.SECURITY_ADMIN, P.AUDIT_READ, P.PII_CLASSIFICATION_READ}),

    # Compliance analyst — authorized KYC access including the elevated sensitive
    # view; NOT ingestion, NOT security administration.
    Role.COMPLIANCE_ANALYST: frozenset({
        P.KYC_READ, P.KYC_VIEW_SENSITIVE, P.PII_CLASSIFICATION_READ, P.DATA_QUALITY_READ,
    }),

    # Compliance reviewer — authorized (non-sensitive) KYC read for review.
    Role.COMPLIANCE_REVIEWER: frozenset({P.KYC_READ, P.PII_CLASSIFICATION_READ}),

    # Data engineer — ingestion + data-quality + limited (non-sensitive) KYC read.
    Role.DATA_ENGINEER: frozenset({P.KYC_INGEST, P.DATA_QUALITY_READ, P.KYC_READ}),

    # Auditor — read-only audit/security visibility. NOT ingestion, NOT KYC content.
    Role.AUDITOR: frozenset({P.AUDIT_READ, P.PII_CLASSIFICATION_READ}),

    # Service account — grants NOTHING by itself. A machine identity gains
    # capabilities only by ALSO holding a narrow functional role (least privilege),
    # and never inherits ADMIN implicitly.
    Role.SERVICE_ACCOUNT: frozenset(),
}
