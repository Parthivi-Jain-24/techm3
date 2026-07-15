"""Phase 3 tests: masking utilities and keyed pseudonymization."""

from __future__ import annotations

from app.privacy.masking import mask_identifier, mask_name, pseudonymize, redact

KEY = "unit-test-key"


# --- identifier masking (15, 17, 18, 19) --------------------------------- #
def test_identifier_masking_hides_full_value() -> None:
    masked = mask_identifier("CLI-123456")
    assert masked.endswith("56")
    assert "CLI-1234" not in masked
    assert masked.count("*") == len("CLI-123456") - 2


def test_identifier_masking_short_and_empty() -> None:
    assert mask_identifier("7") == "*"
    assert mask_identifier("") == ""
    assert mask_identifier(None) == ""


def test_identifier_masking_unicode_safe() -> None:
    masked = mask_identifier("café12")  # 6 codepoints
    assert masked == "****12"


# --- name masking (16, 17, 18, 19) --------------------------------------- #
def test_person_name_masking_hides_full_name() -> None:
    masked = mask_name("John Smith", is_person=True)
    assert masked == "J*** S****"
    assert "John" not in masked and "Smith" not in masked


def test_org_name_masking_keeps_first_token_only() -> None:
    masked = mask_name("Acme Global Holdings", is_person=False)
    assert masked == "Acme G***** H*******"


def test_name_masking_unicode_and_empty() -> None:
    assert mask_name("José García") == "J*** G*****"
    assert mask_name("") == ""
    assert mask_name(None) == ""


def test_redact() -> None:
    assert redact("anything") == "[REDACTED]"
    assert redact("") == ""


# --- pseudonymization (21, 22, 23, 24) ----------------------------------- #
def test_pseudonym_is_deterministic_same_key() -> None:
    assert pseudonymize("123456", KEY) == pseudonymize("123456", KEY)


def test_pseudonym_differs_by_input() -> None:
    assert pseudonymize("123456", KEY) != pseudonymize("123457", KEY)


def test_pseudonym_differs_by_key() -> None:
    assert pseudonymize("123456", "key-a") != pseudonymize("123456", "key-b")


def test_pseudonym_does_not_contain_raw_identifier_or_key() -> None:
    out = pseudonymize("123456", KEY)
    assert "123456" not in out
    assert KEY not in out
    assert out.startswith("anon_")


def test_pseudonym_empty_input() -> None:
    assert pseudonymize("", KEY) == ""
