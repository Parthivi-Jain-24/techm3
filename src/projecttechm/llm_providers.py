"""Pluggable LLM backends for the adverse-media agent.

The playbook's §4 requirement is the *two-pass shape* — extract, then guard —
not a particular vendor. This module isolates the vendor so the agent logic
stays one implementation.

Two backends:

  anthropic       — `output_config.format` guarantees schema-valid JSON.
  openai_compat   — anything speaking OpenAI's /v1/chat/completions: NVIDIA NIM,
                    Groq, OpenRouter, Together, Ollama, LM Studio, vLLM.

The second is where the engineering is. Anthropic's structured outputs are a
hard guarantee; an open model asked for JSON returns JSON *usually* — wrapped in
markdown fences, prefixed with "Here is the JSON:", or subtly off-schema. So the
compat backend asks for JSON, then assumes nothing: it strips fences, extracts
the outermost object, validates required keys, and retries once with the parse
error fed back. A guard pass that silently returns garbage is worse than one
that fails loudly, so exhausted retries raise.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .egress import enforce

# Free-tier presets. base_url + a model known to follow JSON instructions well
# enough for a two-pass extract/guard loop.
PRESETS: dict[str, dict[str, str]] = {
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "meta/llama-3.3-70b-instruct",
        "key_env": "NVIDIA_API_KEY",
        "note": "build.nvidia.com free credits",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "key_env": "GROQ_API_KEY",
        "note": "console.groq.com free tier",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "key_env": "OPENROUTER_API_KEY",
        "note": "openrouter.ai — :free models",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        # Qwen2.5 7B follows JSON/instruction formats notably better than
        # similarly-sized Llama variants, which matters most here: the compat
        # backend has to parse whatever comes back, and a model that reliably
        # emits a bare object costs fewer retries. Q4 lands ~4.7 GB, inside a
        # 6 GB card.
        "model": "qwen2.5:7b",
        "key_env": "OLLAMA_API_KEY",  # unused; Ollama ignores auth
        "note": "fully local — no key, no network, data never leaves the machine",
    },
}

# Local by default. The agent's input is public article text, but the free hosted
# tiers are explicit that they are not for confidential data, and a KYC system
# should not depend on a reviewer trusting that distinction. Local inference
# removes the question: there is no third-party processor, no egress, and the
# demo survives bad conference wifi. Switch with PROJECTTECHM_LLM_PROVIDER.
DEFAULT_PRESET = "ollama"


class LLMError(RuntimeError):
    """A backend could not produce a usable response."""


def _strip_fences(text: str) -> str:
    """Pull JSON out of whatever wrapping an open model put around it.

    Instruction-tuned models routinely answer with ```json ... ``` or a
    "Here is the JSON:" preamble even when told not to. Anthropic's structured
    outputs make this impossible; everywhere else it is the common case.
    """
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    # Fall back to the outermost {...} span.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


def parse_json_response(text: str, required_keys: tuple[str, ...]) -> dict[str, Any]:
    """Parse a model's text into a dict, or raise with a message worth retrying on."""
    candidate = _strip_fences(text)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError(f"response was not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise LLMError(f"expected a JSON object, got {type(data).__name__}")

    missing = [k for k in required_keys if k not in data]
    if missing:
        raise LLMError(f"response missing required keys: {missing}")
    return data


class Backend:
    """Interface: one JSON-returning call.

    Subclasses implement `_complete_json`. `complete_json` is final and applies
    the egress policy first, so a new backend cannot forget to — the check lives
    at the boundary every provider must cross, not in each provider.
    """

    name = "base"
    model = ""
    #: True when inference happens on this host, so no third party sees the text.
    local = False

    def complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        required_keys: tuple[str, ...],
        max_tokens: int,
    ) -> dict[str, Any]:
        report = enforce(user, local=self.local)
        self.last_egress = report
        return self._complete_json(
            system, report.text, schema, required_keys, max_tokens
        )

    def _complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        required_keys: tuple[str, ...],
        max_tokens: int,
    ) -> dict[str, Any]:
        raise NotImplementedError


class AnthropicBackend(Backend):
    """Claude via the Anthropic SDK. Schema is guaranteed, not requested."""

    name = "anthropic"
    local = False

    def __init__(self, model: str = "claude-opus-4-8") -> None:
        import anthropic  # noqa: PLC0415 - optional dependency

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self.model = model

    def _complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        required_keys: tuple[str, ...],
        max_tokens: int,
    ) -> dict[str, Any]:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            raise LLMError("model declined the request")
        if response.stop_reason == "max_tokens":
            raise LLMError("response truncated; raise max_tokens")
        for block in response.content:
            if block.type == "text":
                return parse_json_response(block.text, required_keys)
        raise LLMError("no text block in response")


class OpenAICompatBackend(Backend):
    """Any OpenAI-compatible endpoint: NVIDIA NIM, Groq, OpenRouter, Ollama…

    Schema is *requested*, never guaranteed, so every response is parsed
    defensively and one retry is spent feeding the parse error back. Empirically
    that recovers most fence/preamble failures on a 70B open model.
    """

    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        preset: str | None = None,
    ) -> None:
        from openai import OpenAI  # noqa: PLC0415 - optional dependency

        # Ollama and local servers ignore auth but the client requires a value.
        self._client = OpenAI(base_url=base_url, api_key=api_key or "not-needed")
        self.model = model
        self.base_url = base_url
        self.preset = preset
        # Inference on this host is not a third-party disclosure.
        self.local = (
            "localhost" in base_url or "127.0.0.1" in base_url or "://0.0.0.0" in base_url
        )

    def _call(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            # Low but non-zero: the guard should be near-deterministic, and some
            # endpoints reject an exact 0.
            "temperature": 0.1,
        }
        try:
            response = self._client.chat.completions.create(
                **kwargs, response_format={"type": "json_object"}
            )
        except Exception:  # noqa: BLE001 - endpoint may not know response_format
            response = self._client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content
        if not content:
            raise LLMError("empty response from model")
        return content

    def _complete_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        required_keys: tuple[str, ...],
        max_tokens: int,
    ) -> dict[str, Any]:
        # Open models have no schema enforcement, so the schema goes in the prompt.
        system_with_schema = (
            f"{system}\n\n"
            "Reply with a single JSON object and nothing else. No markdown fences, "
            "no explanation before or after. It must match this JSON Schema exactly:\n"
            f"{json.dumps(schema, indent=2)}"
        )
        messages = [
            {"role": "system", "content": system_with_schema},
            {"role": "user", "content": user},
        ]

        try:
            return parse_json_response(self._call(messages, max_tokens), required_keys)
        except LLMError as first_error:
            # One retry, with the failure quoted back. Cheaper than failing the run.
            messages.append({"role": "assistant", "content": "(invalid response)"})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That response could not be used: {first_error}\n"
                        "Reply again with ONLY the JSON object matching the schema."
                    ),
                }
            )
            try:
                return parse_json_response(self._call(messages, max_tokens), required_keys)
            except LLMError as retry_error:
                raise LLMError(
                    f"{self.model} did not return usable JSON after a retry "
                    f"(first: {first_error}; retry: {retry_error})"
                ) from retry_error


def _resolve_preset(name: str) -> dict[str, str]:
    preset = PRESETS.get(name)
    if preset is None:
        raise LLMError(f"unknown preset {name!r}; known: {sorted(PRESETS)}")
    return preset


#: Values that switch the LLM agent off entirely, so the adverse-media agent
#: uses its heuristic extractor. Distinct from a misconfigured backend: this is
#: a deliberate choice, and no probe or network call is attempted.
DISABLED_VALUES = frozenset({"none", "off", "disabled", "false", "heuristic"})


def is_disabled() -> bool:
    return (
        os.environ.get("PROJECTTECHM_LLM_PROVIDER") or ""
    ).strip().lower() in DISABLED_VALUES


def describe() -> dict[str, Any]:
    """What the current environment would build, without building it."""
    provider = (os.environ.get("PROJECTTECHM_LLM_PROVIDER") or "").strip().lower()

    if provider in DISABLED_VALUES:
        return {"provider": "disabled", "note": "LLM off; heuristic extractor in use"}

    if provider == "anthropic" or (
        not provider and os.environ.get("ANTHROPIC_API_KEY")
    ):
        return {"provider": "anthropic", "model": os.environ.get(
            "PROJECTTECHM_LLM_MODEL", "claude-opus-4-8"
        )}

    preset_name = provider or DEFAULT_PRESET
    if preset_name in PRESETS:
        preset = PRESETS[preset_name]
        return {
            "provider": "openai_compat",
            "preset": preset_name,
            "base_url": os.environ.get("PROJECTTECHM_LLM_BASE_URL", preset["base_url"]),
            "model": os.environ.get("PROJECTTECHM_LLM_MODEL", preset["model"]),
            "key_env": preset["key_env"],
            "note": preset["note"],
        }
    return {"provider": preset_name}


def _api_key_for(preset_name: str, preset: dict[str, str]) -> str | None:
    return (
        os.environ.get("PROJECTTECHM_LLM_API_KEY")
        or os.environ.get(preset["key_env"])
        or None
    )


#: How long to wait when probing a local server. It is on this host; if it does
#: not answer in a second it is not running.
LOCAL_PROBE_TIMEOUT = 1.0


def _local_server_reachable(base_url: str, model: str) -> bool:
    """Is a local server listening *and* does it have this model?

    A hosted provider proves itself with a key; a local one has no credential to
    check, so `is_configured()` would return True for a server that was never
    started — and /health would claim the agent is available while every article
    quietly fell back.

    Reachability alone is not enough either: `ollama serve` answers on a fresh
    install with zero models pulled. Both conditions have to hold, so check the
    model is actually listed.
    """
    import httpx  # noqa: PLC0415 - already a FastAPI dependency

    try:
        response = httpx.get(base_url.rstrip("/") + "/models", timeout=LOCAL_PROBE_TIMEOUT)
        available = {m.get("id", "") for m in response.json().get("data", [])}
    except Exception:  # noqa: BLE001 - any failure means "not usable"
        return False
    # Ollama reports "qwen2.5:7b"; some servers append a ":latest" tag.
    return any(m == model or m.startswith(f"{model}:") for m in available)


def is_configured() -> bool:
    """Whether a backend could actually serve a request right now."""
    if is_disabled():
        return False
    try:
        backend = build_backend()
    except Exception:  # noqa: BLE001 - probing, not running
        return False
    if getattr(backend, "local", False):
        return _local_server_reachable(backend.base_url, backend.model)
    return True


def build_backend() -> Backend:
    """Construct the backend the environment asks for.

    Resolution order:
      PROJECTTECHM_LLM_PROVIDER, else anthropic if ANTHROPIC_API_KEY is set,
      else the default free preset.
    """
    provider = (os.environ.get("PROJECTTECHM_LLM_PROVIDER") or "").strip().lower()

    if provider in DISABLED_VALUES:
        raise LLMError("LLM is disabled (PROJECTTECHM_LLM_PROVIDER=none)")

    if provider == "anthropic" or (not provider and os.environ.get("ANTHROPIC_API_KEY")):
        return AnthropicBackend(
            model=os.environ.get("PROJECTTECHM_LLM_MODEL", "claude-opus-4-8")
        )

    preset_name = provider or DEFAULT_PRESET
    preset = _resolve_preset(preset_name)
    base_url = os.environ.get("PROJECTTECHM_LLM_BASE_URL", preset["base_url"])
    model = os.environ.get("PROJECTTECHM_LLM_MODEL", preset["model"])
    api_key = _api_key_for(preset_name, preset)

    # Local servers need no key; hosted ones do.
    if api_key is None and preset_name != "ollama" and "localhost" not in base_url:
        raise LLMError(
            f"no API key for preset {preset_name!r}: set {preset['key_env']} "
            f"or PROJECTTECHM_LLM_API_KEY ({preset['note']})"
        )

    return OpenAICompatBackend(
        base_url=base_url, model=model, api_key=api_key, preset=preset_name
    )
