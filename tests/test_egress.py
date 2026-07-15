"""Tests for third-party LLM egress control.

The property under test: an adverse-media agent sends public article text to a
model and nothing else. Free LLM tiers are explicit that they are not for
confidential data, so this must be enforced rather than assumed.

The interesting cases are the two edges — names must survive (they are the
subject of the analysis and already public), internal identifiers must not
(they could only come from our own systems).
"""

from __future__ import annotations

import pytest

from projecttechm.egress import (
    ALLOW,
    BLOCK,
    DEFAULT_POLICY,
    REDACT,
    EgressBlocked,
    current_policy,
    enforce,
    redact,
    scan,
)

ARTICLE = (
    "Financial regulators have opened an investigation into ABC Holdings Ltd. "
    "The company's director, Mohammed Al Rashid, denies any wrongdoing. "
    "Wire transfers totalling USD 4.7 million were routed through Cyprus."
)


class TestPolicyDefault:
    def test_default_is_block(self) -> None:
        """A compliance system fails closed, not open."""
        assert DEFAULT_POLICY == BLOCK

    def test_unset_env_gives_block(self, monkeypatch) -> None:
        monkeypatch.delenv("PROJECTTECHM_LLM_EGRESS", raising=False)
        assert current_policy() == BLOCK

    def test_unknown_policy_falls_back_to_block(self, monkeypatch) -> None:
        """A typo must not silently open the gate."""
        monkeypatch.setenv("PROJECTTECHM_LLM_EGRESS", "yolo")
        assert current_policy() == BLOCK

    def test_policy_is_configurable(self, monkeypatch) -> None:
        monkeypatch.setenv("PROJECTTECHM_LLM_EGRESS", "redact")
        assert current_policy() == REDACT


class TestPublicArticlesPassThrough:
    def test_ordinary_article_is_clean(self) -> None:
        report = enforce(ARTICLE)
        assert report.clean
        assert report.text == ARTICLE

    def test_personal_names_are_never_redacted(self) -> None:
        """Redacting names would defeat the agent — they ARE the analysis."""
        report = enforce(ARTICLE, policy=REDACT)
        assert "Mohammed Al Rashid" in report.text
        assert "ABC Holdings" in report.text

    def test_money_amounts_survive(self) -> None:
        assert "USD 4.7 million" in enforce(ARTICLE, policy=REDACT).text

    def test_dates_are_not_mistaken_for_identifiers(self) -> None:
        report = enforce("The probe covers 12 March 2026 to 30 June 2026.")
        assert report.clean


class TestIdentifiersAreCaught:
    @pytest.mark.parametrize(
        "kind,text",
        [
            ("internal_id", "Review customer CLIENT-2041 immediately."),
            ("internal_id", "See CUST-8832 for details."),
            ("internal_id", "Evidence EVD-203 refers."),
            ("email", "Contact rahul.sharma@examplebank.com about this."),
            ("card_number", "Card 4532015112830366 was used."),
            ("iban", "Funds sent to GB29NWBK60161331926819."),
            ("ssn", "SSN 123-45-6789 on file."),
            ("phone", "Reachable on +1 555-123-4567."),
        ],
    )
    def test_identifier_is_detected(self, kind: str, text: str) -> None:
        found = {k for k, _ in scan(text)}
        assert kind in found, f"{kind} not detected in {text!r}"

    def test_block_policy_raises(self) -> None:
        with pytest.raises(EgressBlocked):
            enforce("Customer CLIENT-2041 flagged.")

    def test_block_message_names_what_was_found(self) -> None:
        with pytest.raises(EgressBlocked, match="internal_id"):
            enforce("Customer CLIENT-2041 flagged.")

    def test_block_message_offers_the_alternatives(self) -> None:
        """An error a developer can act on, not just a refusal."""
        with pytest.raises(EgressBlocked) as exc:
            enforce("Customer CLIENT-2041 flagged.")
        assert "redact" in str(exc.value)
        assert "ollama" in str(exc.value)


class TestRedactPolicy:
    def test_identifier_is_replaced(self) -> None:
        report = enforce("Customer CLIENT-2041 flagged.", policy=REDACT)
        assert "CLIENT-2041" not in report.text
        assert "[REDACTED:internal_id]" in report.text
        assert report.redacted is True

    def test_findings_are_still_reported(self) -> None:
        """Redaction is not silence — the caller learns what was stripped."""
        report = enforce("Email rahul@bank.com now.", policy=REDACT)
        assert "email" in report.kinds

    def test_surrounding_text_survives(self) -> None:
        report = enforce("Customer CLIENT-2041 is under investigation.", policy=REDACT)
        assert "under investigation" in report.text

    def test_redact_reports_multiple_kinds(self) -> None:
        text = "CLIENT-1 at a@b.com on +1 555-123-4567"
        assert set(enforce(text, policy=REDACT).kinds) >= {"internal_id", "email", "phone"}

    def test_redact_function_is_idempotent(self) -> None:
        once, _ = redact("Customer CLIENT-2041.")
        twice, _ = redact(once)
        assert once == twice


class TestAllowPolicy:
    def test_allow_transmits_unchanged(self) -> None:
        text = "Customer CLIENT-2041 flagged."
        report = enforce(text, policy=ALLOW)
        assert report.text == text
        assert not report.clean  # still reported, just not acted on


class TestLocalBackendExemption:
    def test_local_is_exempt(self) -> None:
        """Nothing leaves the host, so there is no third party to withhold from."""
        text = "Customer CLIENT-2041, card 4532015112830366."
        report = enforce(text, local=True)
        assert report.text == text
        assert report.clean

    def test_local_exemption_beats_block_policy(self) -> None:
        enforce("CLIENT-2041", policy=BLOCK, local=True)  # must not raise


class TestBackendIntegration:
    def test_remote_backend_enforces_on_every_call(self) -> None:
        """The check lives at the boundary, so no provider can skip it."""
        from projecttechm.llm_providers import Backend

        class Remote(Backend):
            name, model, local = "remote", "m", False

            def _complete_json(self, system, user, schema, required_keys, max_tokens):
                return {"claims": []}

        with pytest.raises(EgressBlocked):
            Remote().complete_json("s", "CLIENT-2041 review", {}, ("claims",), 10)

    def test_local_backend_skips_the_check(self) -> None:
        from projecttechm.llm_providers import Backend

        class Local(Backend):
            name, model, local = "local", "m", True

            def _complete_json(self, system, user, schema, required_keys, max_tokens):
                return {"seen": user}

        result = Local().complete_json("s", "CLIENT-2041 review", {}, (), 10)
        assert result["seen"] == "CLIENT-2041 review"

    def test_ollama_backend_is_marked_local(self, monkeypatch) -> None:
        from projecttechm.llm_providers import build_backend

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PROJECTTECHM_LLM_BASE_URL", raising=False)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "ollama")
        assert build_backend().local is True

    def test_hosted_backend_is_not_local(self, monkeypatch) -> None:
        from projecttechm.llm_providers import build_backend

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # conftest pins a localhost base_url; a hosted-provider test must not inherit it.
        monkeypatch.delenv("PROJECTTECHM_LLM_BASE_URL", raising=False)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "nvidia")
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        assert build_backend().local is False
