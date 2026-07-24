"""Tests for the OPTIONAL, env-gated LLM claim-extraction assist (aspect
`llm-assist` of reproduce-paper-claims).

Mirrors the `test_detect_llm.py` discipline exactly: the LLM assist is a pure
no-op unless a provider AND its key are configured; every test injects a FAKE
completion seam (monkeypatch of the module-local `_llm_complete`) so no test
makes a network call or touches a real API key. The real seam is shape-asserted
only (Phase 4) with a fake SDK module -- never executed against a provider.
"""

from __future__ import annotations

import json

import contig.verification.claim_extraction as claim_extraction
from contig.verification.claim_extraction import (
    ExtractedClaim,
    extract_with_llm,
)


def _fake_completion(payload: object):
    """A fake seam returning a fixed model reply (str passthrough / JSON dump)."""

    def _complete(provider: str, prompt: str) -> str:
        return payload if isinstance(payload, str) else json.dumps(payload)

    return _complete


def _canned_claims() -> list[dict]:
    return [
        {"metric": "AUC", "value": 0.91, "unit": None, "source_text": "AUC of 0.91"},
        {
            "metric": "accuracy",
            "value": 87.0,
            "unit": "%",
            "source_text": "accuracy of 87%",
        },
    ]


# --- Phase 1: the env-gated seam ----------------------------------------------


def test_unconfigured_env_returns_empty_and_never_calls_seam(monkeypatch) -> None:
    monkeypatch.delenv("CONTIG_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    calls: list[tuple[str, str]] = []

    def _spy(provider: str, prompt: str) -> str:
        calls.append((provider, prompt))
        return "[]"

    monkeypatch.setattr(claim_extraction, "_llm_complete", _spy)

    assert extract_with_llm("AUC of 0.91 was achieved.") == []
    assert calls == []


def test_configured_env_calls_seam_once_with_provider_and_prompt(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    calls: list[tuple[str, str]] = []

    def _spy(provider: str, prompt: str) -> str:
        calls.append((provider, prompt))
        return json.dumps(_canned_claims())

    monkeypatch.setattr(claim_extraction, "_llm_complete", _spy)

    claims = extract_with_llm("AUC of 0.91; accuracy of 87%.")
    assert len(calls) == 1
    provider, prompt = calls[0]
    assert provider == "claude"
    assert "AUC of 0.91" in prompt  # the paper text is embedded in the prompt
    # the seam produced claims tagged as llm-origin
    assert all(isinstance(c, ExtractedClaim) for c in claims)
    assert all(c.origin == "llm" for c in claims)
