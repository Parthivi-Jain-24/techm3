"""Privacy & data-governance layer (Phase 3).

Privacy-aware ENGINEERING controls — classification, masking, minimization,
safe representations, and record-level data quality — designed to support
privacy and governance requirements. This is not, and does not claim to be, a
legal-compliance certification.

Nothing here mutates the canonical NormalizedKYCEntity; every transformation
returns a derived, JSON-safe representation.
"""

from app.privacy.classification import DataClass, classify
from app.privacy.contexts import ProcessingContext
from app.privacy.errors import PrivacyError, UnknownProcessingContextError
from app.privacy.masking import mask_identifier, mask_name, pseudonymize, redact
from app.privacy.minimization import (
    minimize_kyc_entity,
    to_agent_safe_dict,
    to_log_safe_dict,
)
from app.privacy.quality import assess_record_quality

__all__ = [
    "ProcessingContext",
    "classify",
    "DataClass",
    "mask_identifier",
    "mask_name",
    "redact",
    "pseudonymize",
    "minimize_kyc_entity",
    "to_log_safe_dict",
    "to_agent_safe_dict",
    "assess_record_quality",
    "PrivacyError",
    "UnknownProcessingContextError",
]
