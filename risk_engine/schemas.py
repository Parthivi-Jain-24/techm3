from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskTrend(str, Enum):
    STABLE = "STABLE"
    RISING = "RISING"
    FALLING = "FALLING"


@dataclass(frozen=True)
class SubFactor:
    name: str
    max_points: float
    confidence: float
    contribution: float
    reason: str
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "max_points": round(self.max_points, 2),
            "confidence": round(self.confidence, 4),
            "contribution": round(self.contribution, 2),
            "reason": self.reason,
            "evidence_ids": self.evidence_ids,
        }


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    score: float
    max_score: int
    sub_factors: list[SubFactor] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    confidence_inputs: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 2),
            "max_score": self.max_score,
            "reasons": self.reasons,
            "evidence_ids": self.evidence_ids,
            "sub_factors": [sub_factor.to_dict() for sub_factor in self.sub_factors],
        }


@dataclass(frozen=True)
class TimelineEvent:
    customer_id: str
    previous_score: int
    new_score: int
    change: int
    reason: str
    evidence_ids: list[str]
    confidence: float
    model_version: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "previous_score": self.previous_score,
            "new_score": self.new_score,
            "change": self.change,
            "reason": self.reason,
            "evidence_ids": self.evidence_ids,
            "confidence": round(self.confidence, 4),
            "model_version": self.model_version,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class RiskAssessment:
    customer_id: str
    risk_score: int
    base_score: int
    risk_level: RiskLevel
    confidence_score: float
    risk_delta: int
    risk_trend: RiskTrend
    velocity: dict[str, Any]
    escalation_floor: int | None
    applied_overrides: list[str]
    trigger_investigation: bool
    sar_recommended: bool
    breakdown: dict[str, float]
    component_details: list[ScoreComponent]
    evidence_ids: list[str]
    top_reasons: list[str]
    timeline_event: TimelineEvent
    model_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "risk_score": self.risk_score,
            "base_score": self.base_score,
            "risk_level": self.risk_level.value,
            "confidence_score": round(self.confidence_score, 4),
            "risk_delta": self.risk_delta,
            "risk_trend": self.risk_trend.value,
            "velocity": self.velocity,
            "escalation_floor": self.escalation_floor,
            "applied_overrides": self.applied_overrides,
            "trigger_investigation": self.trigger_investigation,
            "sar_recommended": self.sar_recommended,
            "breakdown": {key: round(value, 2) for key, value in self.breakdown.items()},
            "component_details": [component.to_dict() for component in self.component_details],
            "evidence_ids": self.evidence_ids,
            "top_reasons": self.top_reasons,
            "timeline_event": self.timeline_event.to_dict(),
            "model_version": self.model_version,
        }