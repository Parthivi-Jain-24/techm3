"""Deterministic, Unicode-safe masking utilities.

All functions are pure and never mutate their inputs. They degrade gracefully
on short, empty, or None values and never expose a full sensitive value.
"""

from __future__ import annotations

_MASK_CHAR = "*"
_REDACTED = "[REDACTED]"


def mask_identifier(value: str | None, keep: int = 2) -> str:
    """Mask an identifier, revealing only the last ``keep`` characters.

    Examples: ``"123456" -> "****56"``, ``"7" -> "*"``, ``"" -> ""``. For very
    short values nothing is revealed. Prefer :func:`pseudonymize` for log-safe
    identifiers whose value space is small/guessable.
    """
    text = "" if value is None else str(value)
    chars = list(text)  # list() is codepoint-safe for masking length
    n = len(chars)
    if n == 0:
        return ""
    if n <= keep:
        return _MASK_CHAR * n
    return _MASK_CHAR * (n - keep) + "".join(chars[-keep:])


def mask_name(value: str | None, is_person: bool = True) -> str:
    """Mask a name while keeping enough for a human to recognize a record.

    Person: each whitespace token is reduced to its first character
    (``"John Smith" -> "J*** S****"``). Organization: the first token is kept
    (legal names are often less private) and later tokens are initialled
    (``"Acme Global Holdings" -> "Acme G**** H*******"``). Empty -> "".
    """
    text = "" if value is None else str(value)
    tokens = text.split()
    if not tokens:
        return ""

    def initial(token: str) -> str:
        chars = list(token)
        if len(chars) <= 1:
            return "".join(chars)
        return chars[0] + _MASK_CHAR * (len(chars) - 1)

    if is_person:
        return " ".join(initial(t) for t in tokens)
    # Organization: keep the first token, initial the remainder.
    return " ".join([tokens[0], *[initial(t) for t in tokens[1:]]])


def redact(value: str | None) -> str:
    """Replace any non-empty value with a fixed placeholder; empty -> ""."""
    text = "" if value is None else str(value)
    return _REDACTED if text else ""
