"""Privacy guardrail — redact unnecessary PII from SARDraft before
finalisation.

Applies rule-based regex redaction to every free-text field in a
``SARDraft``, replacing sensitive patterns with masked placeholders.
Each redaction rule is tagged with the GDPR article that justifies it
(looked up from ``gdpr.json`` via the data loader) and optionally an
OPP-115 sensitivity category as a secondary heuristic.

Fields that are legally required for a SAR filing (client name,
country, sector) are **retained** — the guardrail only strips data
that adds identification risk without regulatory value (full DOB,
full account numbers, raw email addresses, phone numbers, national
IDs).

This is intentionally lightweight: a deterministic regex pass, not an
ML classifier.
"""

from __future__ import annotations

import re
import logging

from pydantic import BaseModel, Field

from app.schemas.sar import SARDraft
from app.data_loaders.gdpr_loader import get_gdpr_article_by_id

logger = logging.getLogger(__name__)

# ── GDPR article cache ──────────────────────────────────────────────

_GDPR_CACHE: dict[str, str] = {}


def _gdpr_title(article_id: str) -> str:
    if article_id not in _GDPR_CACHE:
        paragraphs = get_gdpr_article_by_id(article_id)
        if paragraphs:
            _GDPR_CACHE[article_id] = paragraphs[0].get("article_title", "")
        else:
            _GDPR_CACHE[article_id] = ""
    return _GDPR_CACHE[article_id]


def _gdpr_ref(article_id: str) -> str:
    title = _gdpr_title(article_id)
    if title:
        return f"GDPR {article_id} ({title})"
    return f"GDPR {article_id}"


# ── Redaction rules ─────────────────────────────────────────────────
#
# Each rule is (pattern, replacement, gdpr_article, opp115_category,
# description).  The GDPR article is the *justification* for redacting
# — typically Article 5 (data minimisation) or Article 9 (special
# categories).
#
# OPP-115 categories are secondary heuristics from the OPP-115 privacy
# policy corpus.  They indicate the *type* of data practice the field
# relates to.  We tag them for traceability but the redaction decision
# is driven by the GDPR rule, not the OPP-115 label.

_REDACTION_RULES: list[tuple[re.Pattern, str, str, str, str]] = [
    # ── Most-specific patterns first ────────────────────────────────
    # Full dates of birth:  1990-03-15, 15/03/1990, March 15 1990, etc.
    (
        re.compile(
            r"\b(?:"
            r"\d{4}[-/]\d{2}[-/]\d{2}"           # YYYY-MM-DD or YYYY/MM/DD
            r"|\d{2}[-/]\d{2}[-/]\d{4}"           # DD-MM-YYYY or DD/MM/YYYY
            r"|(?:January|February|March|April|May|June|July|August"
            r"|September|October|November|December)"
            r"\s+\d{1,2},?\s+\d{4}"               # Month DD, YYYY
            r")\b",
            re.IGNORECASE,
        ),
        "[DOB_REDACTED]",
        "article5",
        "Data Retention",
        "Full date of birth — unnecessary for SAR narrative",
    ),
    # National ID / SSN patterns (XXX-XX-XXXX) — before phone/account
    (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[NATIONAL_ID_REDACTED]",
        "article9",
        "Data Retention",
        "National ID / SSN — special category, data minimisation applies",
    ),
    # Passport numbers (1-2 uppercase letters + 6-9 digits) — before account
    (
        re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),
        "[PASSPORT_REDACTED]",
        "article9",
        "Data Retention",
        "Passport number — not required in SAR narrative",
    ),
    # Email addresses — before phone (avoids partial matching)
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "[EMAIL_REDACTED]",
        "article5",
        "First Party Collection/Use",
        "Email address — not required in SAR narrative",
    ),
    # Phone numbers (international and domestic formats)
    (
        re.compile(
            r"\+\d{1,3}[\s.-]?"
            r"(?:\(?\d{2,4}\)?[\s.-]?)?"
            r"\d{3,4}[\s.-]?\d{3,4}\b"
        ),
        "[PHONE_REDACTED]",
        "article5",
        "First Party Collection/Use",
        "Phone number — not required in SAR narrative",
    ),
    # Full account numbers (7+ digits, not preceded by "client_id")
    (
        re.compile(r"(?<!client_id[=: ])\b\d{7,}\b"),
        "[ACCT_REDACTED]",
        "article5",
        "Third Party Sharing/Collection",
        "Full account number — redacted per data minimisation",
    ),
]

# Fields in SARDraft that are legally required and should NOT be
# redacted even if they contain patterns that match a rule.
_LEGALLY_REQUIRED_CONTEXT = {
    "recommended_action",
    "disclaimer",
}

# Fields that get redacted
_REDACTABLE_FIELDS = {
    "subject_information",
    "narrative",
}


# ── Result wrapper ──────────────────────────────────────────────────

class RedactionAction(BaseModel):
    field: str
    original_snippet: str = Field(
        ..., description="The text that was redacted (first 80 chars)"
    )
    replacement: str
    gdpr_article: str
    gdpr_justification: str
    opp115_category: str = ""
    description: str = ""


class PrivacyGuardrailResult(BaseModel):
    redaction_count: int = 0
    redactions: list[RedactionAction] = Field(default_factory=list)
    gdpr_articles_cited: list[str] = Field(
        default_factory=list,
        description="Deduplicated GDPR references added to regulatory_basis",
    )


# ── Core logic ──────────────────────────────────────────────────────

_DOB_SIGNALS = ("born", "dob", "birth", "date of birth", "d.o.b")


def _redact_text(
    text: str,
    field_name: str,
    result: PrivacyGuardrailResult,
) -> str:
    """Single-pass redaction: for each rule we scan *current* text,
    build a list of (start, end, replacement) spans, apply them
    right-to-left (so earlier offsets stay valid), then move to the
    next rule.  Context checks (e.g. DOB signals) always reference
    the text as it looks *at the time of that rule's scan*.
    """
    for pattern, replacement, gdpr_art, opp115_cat, desc in _REDACTION_RULES:
        # Collect non-overlapping spans to replace
        spans: list[tuple[int, int, str]] = []
        for match in pattern.finditer(text):
            # DOB context guard — only redact dates near birth keywords
            if replacement == "[DOB_REDACTED]":
                ctx_start = max(0, match.start() - 40)
                context = text[ctx_start:match.start()].lower()
                if not any(s in context for s in _DOB_SIGNALS):
                    continue
            spans.append((match.start(), match.end(), match.group()))

        # Apply replacements right-to-left to preserve offsets
        for start, end, matched_text in reversed(spans):
            text = text[:start] + replacement + text[end:]

            result.redaction_count += 1
            result.redactions.append(RedactionAction(
                field=field_name,
                original_snippet=matched_text[:80],
                replacement=replacement,
                gdpr_article=_gdpr_ref(gdpr_art),
                gdpr_justification=_gdpr_title(gdpr_art),
                opp115_category=opp115_cat,
                description=desc,
            ))
            logger.info(
                "Redacted %s in %s: %s → %s [%s]",
                desc, field_name, matched_text[:40], replacement, gdpr_art,
            )

    return text


def _mask_account_in_list(items: list[str]) -> list[str]:
    """Mask long digit sequences in red_flags list items."""
    acct_re = re.compile(r"\b\d{7,}\b")
    return [acct_re.sub("[ACCT_REDACTED]", item) for item in items]


# ── Public API ──────────────────────────────────────────────────────

def redact_sar(sar: SARDraft) -> tuple[SARDraft, PrivacyGuardrailResult]:
    """Apply privacy redaction to a SARDraft.

    Returns a new SARDraft with PII redacted in free-text fields, plus a
    ``PrivacyGuardrailResult`` detailing every redaction and its GDPR
    justification.  Also appends any new GDPR article references to
    ``regulatory_basis``.
    """
    result = PrivacyGuardrailResult()
    updates: dict = {}

    for field_name in _REDACTABLE_FIELDS:
        original = getattr(sar, field_name, "")
        if original:
            redacted = _redact_text(original, field_name, result)
            if redacted != original:
                updates[field_name] = redacted

    red_flags = _mask_account_in_list(list(sar.red_flags))
    if red_flags != list(sar.red_flags):
        updates["red_flags"] = red_flags

    # Collect unique GDPR article references from redactions
    cited_articles: set[str] = set()
    for r in result.redactions:
        cited_articles.add(r.gdpr_article)

    existing_basis = set(sar.regulatory_basis)
    new_refs = sorted(cited_articles - existing_basis)
    if new_refs:
        updates["regulatory_basis"] = list(sar.regulatory_basis) + new_refs
        result.gdpr_articles_cited = new_refs

    if updates:
        cleaned = sar.model_copy(update=updates)
    else:
        cleaned = sar

    return cleaned, result
