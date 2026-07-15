"""Prompt-injection detection for untrusted article text.

An article is DATA. Nothing inside it is an instruction. This module is the
first of two defences: it normalises evasion tricks out of the text and matches
instruction-override semantics. The second defence lives in the extraction
contract — claims are lifted verbatim from the source, so an injected command
cannot become a claim.

Detection is deliberately structural rather than a fixed phrase list: a literal
substring list only catches the exact wording it was written for, which makes a
rehearsed demo pass while "disregard previous instructions" walks straight
through.
"""

from __future__ import annotations

import re
import unicodedata

# Zero-width characters used to break up trigger words.
_ZERO_WIDTH = dict.fromkeys(
    map(ord, "​‌‍⁠﻿­"), None
)

# Cyrillic/Greek characters that render identically to Latin ones. Applied only
# to a detection-time copy of the text, never to stored evidence, so folding
# these cannot corrupt genuine non-Latin content.
_HOMOGLYPHS = str.maketrans(
    {
        "а": "a", "в": "b", "с": "c", "е": "e", "н": "h", "і": "i", "ј": "j",
        "к": "k", "м": "m", "о": "o", "р": "p", "ѕ": "s", "т": "t", "у": "y",
        "х": "x", "ѵ": "v",
        "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p",
        "τ": "t", "υ": "u", "χ": "x",
    }
)

_OVERRIDE_VERB = r"(?:ignore|disregard|forget|discard|omit|skip|drop|bypass)"
_TARGET_NOUN = r"(?:instruction|prompt|direction|guidance|rule|polic|context|message)"
_SCOPE = r"(?:previous|prior|earlier|above|preceding|all|any|the)"

# (compiled pattern, human-readable category)
INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(rf"\b{_OVERRIDE_VERB}\b[^.!?]{{0,40}}\b{_SCOPE}\b[^.!?]{{0,40}}\b{_TARGET_NOUN}"),
        "instruction override",
    ),
    (
        re.compile(rf"\bdo not\b[^.!?]{{0,20}}\b(?:follow|obey|apply|use)\b[^.!?]{{0,30}}\b{_TARGET_NOUN}"),
        "instruction override",
    ),
    (
        re.compile(r"\b(?:you are now|you're now|from now on|new task|new instructions?)\b"),
        "role reassignment",
    ),
    (
        re.compile(r"(?:^|\n|#|\*)\s*(?:system|assistant|developer)\s*(?::|message)"),
        "role-marker spoof",
    ),
    (
        re.compile(r"\bact as\s+(?:a|an|the)?\s*(?:compliance|admin|reviewer|auditor|analyst|system|assistant|officer)\b"),
        "role impersonation",
    ),
    (
        re.compile(r"\b(?:override|bypass|suppress|clear|disable|remove)\b[^.!?]{0,30}\b(?:compliance|flag|risk|sanction|control|check|alert)"),
        "control override",
    ),
    (
        re.compile(r"\b(?:mark|set|report|classify|treat|rate|score)\b[^.!?]{0,30}\b(?:as\s+)?(?:clean|low[\s-]?risk|no[\s-]?risk|not\s+sanctioned)\b"),
        "verdict injection",
    ),
    (
        # Quotes/brackets sit between key and separator in JSON payloads:
        # {"risk_score": 0, "sanctions_match": false}
        re.compile(
            r"\b(?:risk[_\s-]?score|sanctions?[_\s-]?match|match[_\s-]?score|confidence)"
            r"[\"']?\s*(?:[=:]|\bis\b)\s*[\"']?\s*(?:0(?:\.0+)?|false|none|null)\b"
        ),
        "field injection",
    ),
    (
        re.compile(r"\bapprove\b[^.!?]{0,30}\b(?:all|pending|the)\b[^.!?]{0,20}\btransactions?\b"),
        "action injection",
    ),
]


def normalize_for_detection(text: str) -> str:
    """Strip the evasion tricks that hide a trigger phrase from a substring match.

    Folds compatibility forms and homoglyphs, drops zero-width joiners, rejoins
    s p a c e d - o u t words, and collapses whitespace. The result is used only
    for detection; the original text is what gets stored and analysed.
    """
    folded = unicodedata.normalize("NFKC", text)
    folded = folded.translate(_ZERO_WIDTH)
    folded = folded.lower()
    folded = folded.translate(_HOMOGLYPHS)
    # Rejoin runs of single letters separated by spaces: "i g n o r e" -> "ignore".
    folded = re.sub(
        r"\b(?:[a-z]\s+){2,}[a-z]\b",
        lambda match: match.group(0).replace(" ", ""),
        folded,
    )
    folded = re.sub(r"[^\S\n]+", " ", folded)
    return folded


# Collapsing "i g n o r e   p r e v i o u s" joins the words too, so the
# spaced-out variant is matched against a fully de-punctuated, de-spaced copy.
_DESPACED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            rf"{_OVERRIDE_VERB}(?:all|any)?{_SCOPE}?(?:{_TARGET_NOUN})"
        ),
        "instruction override",
    ),
    (re.compile(r"youarenow|newtask|newinstruction"), "role reassignment"),
]


def _despace(normalized: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalized)


def detect_injection(text: str) -> tuple[bool, list[str]]:
    """Return (detected, categories) for an untrusted article.

    Categories are deduplicated and ordered for stable reporting.
    """
    if not text:
        return False, []

    normalized = normalize_for_detection(text)
    categories: list[str] = []

    for pattern, category in INJECTION_PATTERNS:
        if pattern.search(normalized) and category not in categories:
            categories.append(category)

    despaced = _despace(normalized)
    for pattern, category in _DESPACED_PATTERNS:
        if pattern.search(despaced) and category not in categories:
            categories.append(category)

    return bool(categories), categories
