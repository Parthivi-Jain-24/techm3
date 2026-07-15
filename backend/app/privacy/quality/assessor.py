"""Deterministic, explainable record-level data-quality assessment.

Only justified, deterministic checks are performed. We deliberately do NOT
invent business rules that conflate data quality with AML risk (e.g. we never
assume a PEP must be sanctioned, or that an FATF-country customer is sanctioned)
— those are risk concepts owned by a different workstream.
"""

from __future__ import annotations

from app.privacy.masking.masker import mask_identifier
from app.privacy.quality.models import (
    QualityIssue,
    QualityIssueCode,
    QualitySeverity,
    RecordQualityAssessment,
)
from app.schemas.kyc import NormalizedKYCEntity

# Fields whose population reflects informational completeness. Required fields
# are guaranteed by the contract; aliases legitimately may be empty (which lowers
# completeness but is NOT itself an issue — the record simply lacks information).
_COMPLETENESS_FIELDS: tuple[str, ...] = (
    "client_name",
    "country",
    "sector",
    "sector_risk",
    "aliases",
)

# Deterministic, documented score penalties by severity.
_PENALTY = {QualitySeverity.LOW: 3, QualitySeverity.MEDIUM: 10, QualitySeverity.HIGH: 25}


def _populated(entity: NormalizedKYCEntity, field: str) -> bool:
    value = getattr(entity, field)
    if isinstance(value, (list, str)):
        return len(value) > 0
    return value is not None


def assess_record_quality(
    entity: NormalizedKYCEntity, known_duplicate: bool = False
) -> RecordQualityAssessment:
    """Assess one canonical entity. ``known_duplicate`` comes from ingestion
    (uniqueness is determined there, not re-derived here)."""
    issues: list[QualityIssue] = []

    # VALIDITY: country should look like a 2-letter code after normalization.
    country = entity.country.strip()
    if not (len(country) == 2 and country.isalpha()):
        issues.append(QualityIssue(
            field="country",
            issue_code=QualityIssueCode.NORMALIZATION_WARNING,
            severity=QualitySeverity.LOW,
            message="country is not a 2-letter code",
        ))

    # CONSISTENCY: record timestamps must be ordered (deterministic, no risk logic).
    if entity.updated_at < entity.created_at:
        issues.append(QualityIssue(
            field="updated_at",
            issue_code=QualityIssueCode.INCONSISTENT_VALUE,
            severity=QualitySeverity.MEDIUM,
            message="updated_at is earlier than created_at",
        ))

    # UNIQUENESS: reflect the ingestion pipeline's duplicate finding.
    if known_duplicate:
        issues.append(QualityIssue(
            field="client_id",
            issue_code=QualityIssueCode.DUPLICATE_IDENTIFIER,
            severity=QualitySeverity.HIGH,
            message="client_id was flagged as a duplicate by ingestion",
        ))

    # COMPLETENESS (informational; does not by itself penalize the score).
    populated = sum(1 for f in _COMPLETENESS_FIELDS if _populated(entity, f))
    completeness_ratio = populated / len(_COMPLETENESS_FIELDS)

    score = max(0, 100 - sum(_PENALTY[i.severity] for i in issues))

    return RecordQualityAssessment(
        client_ref=mask_identifier(entity.client_id),
        data_quality_score=float(score),
        completeness_ratio=completeness_ratio,
        issues=issues,
    )


def aggregate_quality(entities: list[NormalizedKYCEntity]) -> dict[str, object]:
    """PII-safe aggregate for a batch (for real-data verification)."""
    assessments = [assess_record_quality(e) for e in entities]
    n = len(assessments)
    issue_counts: dict[str, int] = {}
    for a in assessments:
        for issue in a.issues:
            issue_counts[issue.issue_code.value] = issue_counts.get(issue.issue_code.value, 0) + 1
    avg_score = round(sum(a.data_quality_score for a in assessments) / n, 2) if n else 0.0
    avg_completeness = round(sum(a.completeness_ratio for a in assessments) / n, 4) if n else 0.0
    return {
        "total_entities": n,
        "avg_data_quality_score": avg_score,
        "avg_completeness_ratio": avg_completeness,
        "records_with_issues": sum(1 for a in assessments if a.issues),
        "issue_counts": issue_counts,
    }
