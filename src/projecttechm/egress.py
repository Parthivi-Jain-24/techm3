"""Egress control for text leaving the process for a third-party LLM.

Why this exists: free LLM tiers are explicit that they are not for confidential
data — NVIDIA's own guidance for build.nvidia.com is not to upload personal or
confidential information, and reporting on the free tier disagrees about whether
inputs are retained or used for training. For a KYC system that is not a risk you
manage with a code comment.

The adverse-media agent is *designed* to send only public news article text —
customer records, the sanctions index, transactions, and entity IDs never reach a
model. But `POST /adverse-media/analyze` accepts arbitrary text, so that property
holds by convention. This module makes it hold by enforcement: every outbound
string is scanned before it leaves, and the policy decides.

What is deliberately NOT redacted: personal names. An adverse-media agent whose
input has had "Mohammed Al Rashid" masked out cannot do its job — names are the
subject of the analysis, and they are already public in the article. The line
drawn here is *structured identifiers that could only come from our own systems
or a customer record*: internal IDs, account numbers, national IDs, contact
details, card numbers.

Policies (PROJECTTECHM_LLM_EGRESS):
    block   - refuse to send; raise. The default: a compliance system should
              fail closed, not leak and log about it afterwards.
    redact  - replace identifiers with [REDACTED:<kind>] and send.
    allow   - send unchanged. Only sane for a local backend.

A local backend (Ollama, vLLM on localhost) is exempt: nothing leaves the host,
so there is no third party to protect the data from.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

BLOCK, REDACT, ALLOW = "block", "redact", "allow"
POLICIES = (BLOCK, REDACT, ALLOW)
DEFAULT_POLICY = BLOCK


class EgressBlocked(RuntimeError):
    """Outbound text contained identifiers the policy refuses to transmit."""


# (kind, pattern). Ordered: more specific patterns first so a card number is not
# first matched as a generic account number.
PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Our own internal identifiers. These can only come from our database — an
    # article never contains them, so their presence means a caller passed a
    # customer record where an article belongs.
    ("internal_id", re.compile(r"\b(?:CLIENT|CUST|CUSTOMER|ACCT|EVD|AUD)-\d+\b", re.I)),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")),
    # 13-19 digits, optionally spaced/hyphened in groups of 4.
    ("card_number", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("aadhaar", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")),
    ("passport", re.compile(r"\b[Pp]assport\s+(?:no\.?\s*)?[A-Z0-9]{6,9}\b")),
    ("phone", re.compile(r"(?:\+\d{1,3}[ -]?)?\(?\d{3}\)?[ -]\d{3}[ -]\d{4}\b")),
    ("swift", re.compile(r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b(?=\s*(?:SWIFT|BIC))")),
]


@dataclass
class EgressReport:
    """What the scanner found, and what would leave."""

    text: str
    findings: list[tuple[str, str]] = field(default_factory=list)
    redacted: bool = False

    @property
    def clean(self) -> bool:
        return not self.findings

    @property
    def kinds(self) -> list[str]:
        seen: list[str] = []
        for kind, _ in self.findings:
            if kind not in seen:
                seen.append(kind)
        return seen


def scan(text: str) -> list[tuple[str, str]]:
    """Return (kind, matched_text) for every identifier found."""
    findings: list[tuple[str, str]] = []
    for kind, pattern in PII_PATTERNS:
        for match in pattern.finditer(text):
            findings.append((kind, match.group(0)))
    return findings


def redact(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace identifiers with typed placeholders."""
    findings = scan(text)
    redacted = text
    for kind, pattern in PII_PATTERNS:
        redacted = pattern.sub(f"[REDACTED:{kind}]", redacted)
    return redacted, findings


def current_policy() -> str:
    raw = (os.environ.get("PROJECTTECHM_LLM_EGRESS") or DEFAULT_POLICY).strip().lower()
    return raw if raw in POLICIES else DEFAULT_POLICY


def enforce(text: str, policy: str | None = None, local: bool = False) -> EgressReport:
    """Apply the egress policy to one outbound string.

    `local=True` exempts the call: a model running on this host is not a third
    party, so there is nothing to withhold from it.
    """
    if local:
        return EgressReport(text=text)

    policy = policy or current_policy()
    findings = scan(text)

    if not findings or policy == ALLOW:
        return EgressReport(text=text, findings=findings)

    if policy == REDACT:
        cleaned, _ = redact(text)
        return EgressReport(text=cleaned, findings=findings, redacted=True)

    kinds = sorted({k for k, _ in findings})
    raise EgressBlocked(
        f"refusing to send text containing {kinds} to a third-party model. "
        "The adverse-media agent expects public article text only. "
        "Set PROJECTTECHM_LLM_EGRESS=redact to mask and send, or use a local "
        "backend (PROJECTTECHM_LLM_PROVIDER=ollama) where nothing leaves the host."
    )
