from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


@dataclass(slots=True, kw_only=True)
class SanctionedEntity:
    """One normalized entry from a sanctions/PEP list.

    A slotted dataclass rather than a BaseModel on purpose. This is internal
    reference data — it is never serialized by the API and never validated from
    untrusted input, so pydantic buys nothing here and costs a great deal. At
    ~1,617 bytes per instance the full OpenSanctions list (~1.28M screenable
    entities) needed ~2.1 GB of models and would not fit alongside the rest of
    the stack; slots plus interning bring it to ~624 bytes measured on real data
    (~0.8 GB), which does. That is what makes full-coverage screening possible.

    Keyword-only so field order stays free to change and every call site reads
    explicitly. Everything crossing the API boundary (EvidenceRecord,
    AdverseMediaFinding) stays a validated BaseModel.
    """

    entity_id: str
    name: str
    source_list: str
    aliases: list[str] = dataclass_field(default_factory=list)
    dob: str | None = None
    nationality: str | None = None
    entity_type: str | None = None
    company: str | None = None
    topics: list[str] = dataclass_field(default_factory=list)
    source_url: str | None = None
    context: str | None = None


class MatchComponentScores(BaseModel):
    name: float = 0.0
    alias: float = 0.0
    dob: float = 0.0
    nationality: float = 0.0
    company: float = 0.0
    context: float = 0.0


class EvidenceRecord(BaseModel):
    evidence_id: str
    entity_id: str
    matched_against: str
    match_score: float
    component_scores: MatchComponentScores
    classification: str
    source: str
    retrieved_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    claim: str
    supported: bool
    confidence: float


class AdverseMediaFinding(BaseModel):
    evidence_id: str
    entity_id: str
    source_url: str
    extracted_claims: list[Claim] = Field(default_factory=list)
    injection_attempt_detected: bool = False
    injection_details: str | None = None
    retrieved_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class OwnershipEdge(BaseModel):
    owner_id: str
    owned_id: str
    percentage: float | None = None


class EntityRecord(BaseModel):
    entity_id: str
    name: str
    context: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)