"""Controlled taxonomies for the audit subsystem (Phase 9).

Small, closed enums so ``event_type``, ``outcome``, ``severity``, and
``actor_type`` can never drift into arbitrary, uncontrolled strings scattered
across the codebase. ``action`` and ``resource_type`` are validated string
formats (see ``models.py``) with a curated constant list in ``actions.py`` /
``resources.py`` -- new domains add a constant, not a new enum member.
"""

from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    HTTP_REQUEST = "HTTP_REQUEST"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    INGESTION = "INGESTION"
    DATA_VALIDATION = "DATA_VALIDATION"
    PII_PROCESSING = "PII_PROCESSING"
    ENCRYPTION = "ENCRYPTION"
    SECRET_ACCESS = "SECRET_ACCESS"
    SECURITY_CONFIGURATION = "SECURITY_CONFIGURATION"


class Outcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DENIED = "DENIED"
    ERROR = "ERROR"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ActorType(str, Enum):
    ANONYMOUS = "ANONYMOUS"
    USER = "USER"
    SERVICE = "SERVICE"
    SYSTEM = "SYSTEM"
