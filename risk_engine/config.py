from dataclasses import dataclass, field


@dataclass(frozen=True)
class RiskWeights:
    kyc_profile: int = 25
    sanctions: int = 30
    transactions: int = 25
    adverse_media: int = 15
    jurisdiction: int = 5


@dataclass(frozen=True)
class RiskThresholds:
    medium: int = 31
    high: int = 61
    critical: int = 81
    investigation: int = 61
    sar: int = 81
    minimum_sar_confidence: float = 0.70
    high_confidence_sanctions_floor: int = 85
    medium_confidence_sanctions_floor: int = 65


@dataclass(frozen=True)
class RiskEngineConfig:
    model_version: str = "risk-engine-v2.0"
    weights: RiskWeights = field(default_factory=RiskWeights)
    thresholds: RiskThresholds = field(default_factory=RiskThresholds)