"""Tests for the pluggable LLM backends.

The interesting surface is `OpenAICompatBackend`. Anthropic guarantees
schema-valid JSON; an open model behind an OpenAI-compatible endpoint does not —
it wraps JSON in markdown fences, adds a preamble, or drops a required key. These
tests pin the defensive parsing that makes the two-pass agent usable on a free
provider.
"""

from __future__ import annotations

import pytest

from projecttechm.llm_providers import (
    DEFAULT_PRESET,
    PRESETS,
    LLMError,
    OpenAICompatBackend,
    _strip_fences,
    build_backend,
    describe,
    is_configured,
    parse_json_response,
)

KEYS = ("claims",)


# ---------------------------------------------------------------------------
# Parsing what open models actually return
# ---------------------------------------------------------------------------

class TestStripFences:
    def test_plain_json_passes_through(self) -> None:
        assert _strip_fences('{"a": 1}') == '{"a": 1}'

    def test_markdown_fence_is_stripped(self) -> None:
        assert _strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_bare_fence_is_stripped(self) -> None:
        assert _strip_fences('```\n{"a": 1}\n```') == '{"a": 1}'

    def test_preamble_is_discarded(self) -> None:
        assert _strip_fences('Here is the JSON:\n{"a": 1}') == '{"a": 1}'

    def test_trailing_commentary_is_discarded(self) -> None:
        assert _strip_fences('{"a": 1}\n\nLet me know if you need more!') == '{"a": 1}'

    def test_nested_braces_survive(self) -> None:
        assert _strip_fences('{"a": {"b": 2}}') == '{"a": {"b": 2}}'


class TestParseJsonResponse:
    def test_valid_object_parses(self) -> None:
        assert parse_json_response('{"claims": []}', KEYS) == {"claims": []}

    def test_fenced_object_parses(self) -> None:
        assert parse_json_response('```json\n{"claims": []}\n```', KEYS) == {"claims": []}

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(LLMError, match="not valid JSON"):
            parse_json_response("this is not json at all", KEYS)

    def test_json_array_is_rejected(self) -> None:
        """A bare array is valid JSON but not the contract."""
        with pytest.raises(LLMError, match="expected a JSON object"):
            parse_json_response("[1, 2, 3]", KEYS)

    def test_missing_required_key_raises(self) -> None:
        with pytest.raises(LLMError, match="missing required keys"):
            parse_json_response('{"entities": []}', KEYS)


# ---------------------------------------------------------------------------
# OpenAI-compatible backend
# ---------------------------------------------------------------------------

class FakeChatCompletions:
    def __init__(self, replies: list) -> None:
        self._replies = list(replies)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        message = type("M", (), {"content": reply})()
        choice = type("C", (), {"message": message})()
        return type("R", (), {"choices": [choice]})()


def _backend(replies: list) -> tuple[OpenAICompatBackend, FakeChatCompletions]:
    backend = OpenAICompatBackend.__new__(OpenAICompatBackend)
    fake = FakeChatCompletions(replies)
    backend._client = type("Cli", (), {"chat": type("Ch", (), {"completions": fake})()})()
    backend.model = "test-model"
    backend.base_url = "http://test/v1"
    backend.preset = "test"
    return backend, fake


SCHEMA = {"type": "object", "properties": {"claims": {"type": "array"}}}


class TestOpenAICompatBackend:
    def test_clean_json_response(self) -> None:
        backend, _ = _backend(['{"claims": []}'])
        assert backend.complete_json("sys", "user", SCHEMA, KEYS, 100) == {"claims": []}

    def test_fenced_response_recovers(self) -> None:
        """The single most common open-model failure — must not cost a retry."""
        backend, fake = _backend(['```json\n{"claims": []}\n```'])
        assert backend.complete_json("sys", "user", SCHEMA, KEYS, 100) == {"claims": []}
        assert len(fake.calls) == 1

    def test_schema_is_injected_into_the_prompt(self) -> None:
        """Open models have no schema enforcement, so it goes in the system prompt."""
        backend, fake = _backend(['{"claims": []}'])
        backend.complete_json("BASE PROMPT", "user", SCHEMA, KEYS, 100)

        system = fake.calls[0]["messages"][0]["content"]
        assert "BASE PROMPT" in system
        assert "JSON Schema" in system
        assert '"claims"' in system

    def test_bad_json_triggers_one_retry(self) -> None:
        backend, fake = _backend(["I cannot help with that", '{"claims": []}'])
        assert backend.complete_json("sys", "user", SCHEMA, KEYS, 100) == {"claims": []}
        assert len(fake.calls) == 2

    def test_retry_feeds_the_error_back(self) -> None:
        backend, fake = _backend(["garbage", '{"claims": []}'])
        backend.complete_json("sys", "user", SCHEMA, KEYS, 100)

        retry_user = fake.calls[1]["messages"][-1]["content"]
        assert "could not be used" in retry_user
        assert "ONLY the JSON object" in retry_user

    def test_two_failures_raise_rather_than_return_garbage(self) -> None:
        """A guard that returns junk is worse than one that fails loudly."""
        backend, _ = _backend(["nope", "still nope"])
        with pytest.raises(LLMError, match="did not return usable JSON after a retry"):
            backend.complete_json("sys", "user", SCHEMA, KEYS, 100)

    def test_empty_response_raises(self) -> None:
        backend, _ = _backend([None, None])
        with pytest.raises(LLMError):
            backend.complete_json("sys", "user", SCHEMA, KEYS, 100)

    def test_response_format_unsupported_falls_back(self) -> None:
        """Some endpoints 400 on response_format; the call must still go through."""
        backend, fake = _backend([TypeError("unexpected kwarg response_format"),
                                  '{"claims": []}'])
        assert backend.complete_json("sys", "user", SCHEMA, KEYS, 100) == {"claims": []}
        assert "response_format" in fake.calls[0]
        assert "response_format" not in fake.calls[1]

    def test_temperature_is_low_for_determinism(self) -> None:
        backend, fake = _backend(['{"claims": []}'])
        backend.complete_json("sys", "user", SCHEMA, KEYS, 100)
        assert fake.calls[0]["temperature"] <= 0.2


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestPresets:
    def test_default_preset_exists(self) -> None:
        assert DEFAULT_PRESET in PRESETS

    def test_every_preset_has_the_required_fields(self) -> None:
        for name, preset in PRESETS.items():
            for field in ("base_url", "model", "key_env", "note"):
                assert field in preset, f"{name} missing {field}"

    def test_ollama_preset_is_local(self) -> None:
        assert "localhost" in PRESETS["ollama"]["base_url"]


class TestResolution:
    def test_anthropic_key_selects_anthropic(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("PROJECTTECHM_LLM_PROVIDER", raising=False)
        assert describe()["provider"] == "anthropic"

    def test_explicit_provider_wins_over_anthropic_key(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "groq")
        assert describe()["preset"] == "groq"

    def test_defaults_to_free_preset_without_any_key(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PROJECTTECHM_LLM_PROVIDER", raising=False)
        described = describe()
        assert described["provider"] == "openai_compat"
        assert described["preset"] == DEFAULT_PRESET

    def test_model_override_is_honoured(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("PROJECTTECHM_LLM_BASE_URL", raising=False)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "nvidia")
        monkeypatch.setenv("PROJECTTECHM_LLM_MODEL", "custom/model-x")
        assert describe()["model"] == "custom/model-x"

    def test_missing_key_is_an_actionable_error(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        monkeypatch.delenv("PROJECTTECHM_LLM_API_KEY", raising=False)
        monkeypatch.delenv("PROJECTTECHM_LLM_BASE_URL", raising=False)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "nvidia")

        with pytest.raises(LLMError, match="NVIDIA_API_KEY"):
            build_backend()

    def test_unknown_preset_is_rejected(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "not-a-provider")
        with pytest.raises(LLMError, match="unknown preset"):
            build_backend()

    def test_hosted_provider_without_a_key_is_not_configured(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        monkeypatch.delenv("PROJECTTECHM_LLM_API_KEY", raising=False)
        monkeypatch.delenv("PROJECTTECHM_LLM_BASE_URL", raising=False)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "nvidia")
        assert is_configured() is False

    def test_local_provider_is_probed_not_assumed(self, monkeypatch) -> None:
        """Ollama needs no key, so config alone cannot prove it will serve.

        Without a probe, /health would claim the agent is available for a server
        that was never started, and every article would quietly fall back.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "ollama")
        # Point at a port nothing is listening on.
        monkeypatch.setenv("PROJECTTECHM_LLM_BASE_URL", "http://localhost:1/v1")
        assert is_configured() is False

    def test_local_server_without_the_model_is_not_configured(self, monkeypatch) -> None:
        """`ollama serve` answers on a fresh install with zero models pulled."""
        from projecttechm import llm_providers

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("PROJECTTECHM_LLM_MODEL", "a-model-nobody-pulled")
        monkeypatch.setattr(
            llm_providers,
            "_local_server_reachable",
            lambda base_url, model: model == "qwen2.5:7b",
        )
        assert is_configured() is False

    def test_ollama_needs_no_key(self, monkeypatch) -> None:
        """Local inference has no credential to supply."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("PROJECTTECHM_LLM_API_KEY", raising=False)
        monkeypatch.delenv("PROJECTTECHM_LLM_BASE_URL", raising=False)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "ollama")

        backend = build_backend()  # must not raise
        assert backend.name == "openai_compat"
        assert "localhost" in backend.base_url


class TestDisableSwitch:
    """`PROJECTTECHM_LLM_PROVIDER=none` turns the agent off deliberately.

    Distinct from a misconfigured backend: no probe, no network call, no
    fallback-after-failure. The test suite relies on this to stay deterministic
    on a machine that happens to have Ollama running.
    """

    @pytest.mark.parametrize("value", ["none", "off", "disabled", "false", "NONE"])
    def test_disable_values(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", value)
        assert is_configured() is False

    def test_disabled_beats_a_present_key(self, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "none")
        assert is_configured() is False

    def test_describe_reports_disabled(self, monkeypatch) -> None:
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "none")
        assert describe()["provider"] == "disabled"

    def test_build_raises_when_disabled(self, monkeypatch) -> None:
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "none")
        with pytest.raises(LLMError, match="disabled"):
            build_backend()

    def test_disabled_makes_no_network_call(self, monkeypatch) -> None:
        """A probe against a disabled agent is wasted latency on every /health."""
        from projecttechm import llm_providers

        def _fail(*a, **k):
            raise AssertionError("probed while disabled")

        monkeypatch.setattr(llm_providers, "_local_server_reachable", _fail)
        monkeypatch.setenv("PROJECTTECHM_LLM_PROVIDER", "none")
        assert is_configured() is False
