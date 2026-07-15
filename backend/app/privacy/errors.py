"""Errors for the privacy / data-governance layer.

Privacy decisions fail CLOSED: when a context or field is not recognized, the
layer refuses to expose data rather than defaulting to exposure.
"""

from __future__ import annotations


class PrivacyError(Exception):
    """Base class for privacy-layer errors."""


class UnknownProcessingContextError(PrivacyError):
    """A minimization was requested for an unrecognized processing context.

    Raised instead of silently returning the full record (fail-closed).
    """
