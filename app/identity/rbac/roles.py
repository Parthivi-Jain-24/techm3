"""Explicit roles for the Secure Data / Identity / Governance workstream.

Roles are coarse job functions. They grant permissions ONLY via the central
mapping in ``mappings.py`` — never by name checks in route handlers.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    # Security / configuration administration. NOT "bypass every check": ADMIN
    # holds security-admin permissions, not blanket access to customer KYC data.
    ADMIN = "admin"
    # Reads authorized KYC information for compliance analysis (incl. sensitive).
    COMPLIANCE_ANALYST = "compliance_analyst"
    # Performs authorized review actions (future integrated review workflow).
    COMPLIANCE_REVIEWER = "compliance_reviewer"
    # Approved ingestion operations + data-quality inspection.
    DATA_ENGINEER = "data_engineer"
    # Read-only audit / security visibility.
    AUDITOR = "auditor"
    # Machine-to-machine identity. Grants NOTHING on its own (see mappings).
    SERVICE_ACCOUNT = "service_account"
