"""Shared enums and base models used across pipeline stages."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceType(str, Enum):
    KYC_PROFILE = "kyc_profile"
    TRANSACTION = "transaction"
    SANCTIONS_LIST = "sanctions_list"
    GDPR = "gdpr"
    PEP_REGISTRY = "pep_registry"
    OPEN_SOURCE = "open_source"
    LLM_ANALYSIS = "llm_analysis"


class EvidenceItem(BaseModel):
    claim: str = Field(..., description="Factual assertion this evidence supports")
    source_type: SourceType
    source_id: str = Field(..., description="Identifier: file name, article ID, transaction ID, etc.")
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
