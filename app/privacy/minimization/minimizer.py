"""Context-aware minimization + masking of a NormalizedKYCEntity.

Produces a NEW JSON-safe dict for a given processing context. The original
canonical entity is never mutated. Unknown contexts fail closed (raise);
unlisted fields are omitted.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from app.privacy.classification.classifier import classify
from app.privacy.classification.models import MaskStrategy
from app.privacy.contexts import ProcessingContext
from app.privacy.errors import UnknownProcessingContextError
from app.privacy.masking.masker import mask_identifier, mask_name, redact
from app.privacy.masking.pseudonymize import pseudonymize
from app.privacy.minimization.policies import CONTEXT_POLICIES, Treatment
from app.schemas.kyc import NormalizedKYCEntity


def _json_safe(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _is_person(entity: NormalizedKYCEntity) -> bool:
    return entity.client_type.strip().lower() == "individual"


def _apply_mask(field: str, value: object, entity: NormalizedKYCEntity,
                pseudonymize_key: str | None) -> object:
    """Obscure a single field's value using its classified mask strategy."""
    strategy = classify(field).default_mask
    is_person = _is_person(entity)

    if strategy is MaskStrategy.PSEUDONYMIZE:
        return pseudonymize(str(value), key=pseudonymize_key)
    if strategy is MaskStrategy.MASK_IDENTIFIER:
        return mask_identifier(str(value))
    if strategy is MaskStrategy.MASK_NAME:
        if isinstance(value, list):  # aliases
            return [mask_name(str(v), is_person=is_person) for v in value]
        return mask_name(str(value), is_person=is_person)
    if strategy is MaskStrategy.REDACT:
        if isinstance(value, list):
            return [redact(str(v)) for v in value]
        return redact(str(value))
    # MaskStrategy.NONE: no dedicated masker -> redact rather than expose raw.
    return redact(str(value)) if not isinstance(value, list) else [redact(str(v)) for v in value]


def minimize_kyc_entity(
    entity: NormalizedKYCEntity,
    context: ProcessingContext,
    pseudonymize_key: str | None = None,
) -> dict[str, object]:
    """Return a JSON-safe, context-appropriate representation of ``entity``.

    Fail-closed: an unrecognized ``context`` raises rather than exposing data.
    Fields not permitted for the context are omitted (minimization); permitted
    sensitive fields may be masked. The canonical ``entity`` is not mutated.
    """
    policy = CONTEXT_POLICIES.get(context)
    if policy is None:
        raise UnknownProcessingContextError(
            f"unknown processing context: {context!r} (refusing to expose data)"
        )

    source = entity.model_dump()  # a copy; does not mutate the entity
    out: dict[str, object] = {}
    for field, raw_value in source.items():
        treatment = policy.get(field, Treatment.OMIT)  # fail-closed default
        if treatment is Treatment.OMIT:
            continue
        if treatment is Treatment.MASK:
            out[field] = _json_safe(
                _apply_mask(field, raw_value, entity, pseudonymize_key)
            )
        else:  # RAW
            out[field] = _json_safe(raw_value)
    return out


def to_log_safe_dict(
    entity: NormalizedKYCEntity, pseudonymize_key: str | None = None
) -> dict[str, object]:
    """Log-safe representation: minimal operational fields, pseudonymized id."""
    return minimize_kyc_entity(entity, ProcessingContext.LOGGING, pseudonymize_key)


def to_agent_safe_dict(
    entity: NormalizedKYCEntity,
    context: ProcessingContext = ProcessingContext.AGENT_CONTEXT,
    pseudonymize_key: str | None = None,
) -> dict[str, object]:
    """Agent-safe representation.

    Defaults to the aggressively-minimized AGENT_CONTEXT — the full canonical
    record is never exposed to an agent by default. Future agent access must be
    authenticated, authorized, validated, bounded, and audited (Phase 4+), and
    agents must never receive unrestricted database access.
    """
    return minimize_kyc_entity(entity, context, pseudonymize_key)
