"""Record-level data-quality models (governance layer).

Distinct from Phase 2's file-level ``DataQualityReport`` (ingestion/reports.py):
this assesses ONE already-normalized canonical entity.

IMPORTANT: ``data_quality_score`` measures how complete/valid/consistent the
DATA is. It is NOT customer AML risk and NOT entity match confidence. A
high-quality record can describe a high-risk customer; a low-quality record may
simply lack information.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import utcnow


class QualitySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class QualityIssueCode(str, Enum):
    MISSING_VALUE = "missing_value"
    INVALID_VALUE = "invalid_value"
    INCONSISTENT_VALUE = "inconsistent_value"
    DUPLICATE_IDENTIFIER = "duplicate_identifier"
    NORMALIZATION_WARNING = "normalization_warning"


class QualityIssue(BaseModel):
    """A single data-quality finding. Carries no raw sensitive values."""

    model_config = ConfigDict(extra="forbid")

    field: str
    issue_code: QualityIssueCode
    severity: QualitySeverity
    message: str = Field(..., description="Short, PII-safe description.")


class RecordQualityAssessment(BaseModel):
    """Deterministic, explainable quality assessment for one KYC entity."""

    model_config = ConfigDict(extra="forbid")

    client_ref: str = Field(..., description="Masked client_id (no raw identifier).")
    data_quality_score: float = Field(
        ..., ge=0, le=100,
        description="Deterministic 0-100 data-quality score. NOT risk, NOT match confidence.",
    )
    completeness_ratio: float = Field(
        ..., ge=0, le=1, description="Fraction of assessed fields populated."
    )
    issues: list[QualityIssue] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=utcnow)
