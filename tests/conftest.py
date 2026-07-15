"""Shared test configuration.

The suite pins two ambient things so results do not depend on the machine:

  * Sanctions load from the synthetic fixtures, so the playbook §9 regression
    cases stay deterministic and fast. Real-list behaviour lives in
    test_real_data.py, skipped when the downloads are absent.
  * The LLM agent is switched off. Ollama is the default provider and needs no
    key, so on a machine where it happens to be running the suite would silently
    start calling a real 7B model — slow, non-deterministic, and a test of the
    model rather than of our code. Tests that exercise the LLM path inject a fake
    backend explicitly; the live check is scripts/verify_llm.py.
"""

from __future__ import annotations

import os

import pytest

from projecttechm.services import reset_registry


@pytest.fixture(scope="session", autouse=True)
def _pin_ambient_state() -> None:
    os.environ["PROJECTTECHM_SANCTIONS_MODE"] = "sample"
    os.environ.setdefault("PROJECTTECHM_LLM_PROVIDER", "none")
    reset_registry()
