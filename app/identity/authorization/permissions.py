"""Explicit, typed permissions. Authorization is permission-based, never
role-name based. Scoped to the Secure Data / Identity / Governance workstream.
"""

from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    KYC_READ = "kyc_read"                    # read minimized/authorized KYC data
    KYC_INGEST = "kyc_ingest"                # run ingestion operations
    KYC_VIEW_SENSITIVE = "kyc_view_sensitive"  # elevated: view sensitive KYC fields
    DATA_QUALITY_READ = "data_quality_read"  # read data-quality information
    PII_CLASSIFICATION_READ = "pii_classification_read"  # view classification policy
    AUDIT_READ = "audit_read"                # read authorized audit/security info
    SECURITY_ADMIN = "security_admin"        # security / configuration administration
