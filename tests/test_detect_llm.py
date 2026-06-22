"""Tests for the provider-agnostic LLM detector (PRD contract A).

The LLM detector is OPTIONAL: it registers only when a provider and its key are
configured in the environment. Every test here injects a FAKE completion seam
(monkeypatch); no test makes a network call or touches a real API key.
"""

from __future__ import annotations

import json

import pytest

import contig.detect as detect
from contig.detect import (
    Detector,
    build_llm_detector,
    get_detector,
    llm_detector_available,
)
from contig.models import Diagnosis, TaskEvent


def _failed_events() -> list[TaskEvent]:
    return [TaskEvent(process="ALIGN", status="FAILED", exit=1)]


def _fake_completion(payload: dict | str):
    """A fake completion seam returning a fixed model response (no network)."""

    def _complete(provider: str, prompt: str) -> str:
        return payload if isinstance(payload, str) else json.dumps(payload)

    return _complete


# --- env gating: optional, no provider/key -> not available, no network --------


def test_llm_not_available_without_provider_env(monkeypatch) -> None:
    monkeypatch.delenv("CONTIG_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm_detector_available() is False


def test_get_detector_llm_without_env_raises_naming_the_missing_env(monkeypatch) -> None:
    monkeypatch.delenv("CONTIG_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(KeyError) as excinfo:
        get_detector("llm")
    msg = str(excinfo.value)
    assert "CONTIG_LLM_PROVIDER" in msg


def test_llm_not_registered_in_detectors_without_env(monkeypatch) -> None:
    monkeypatch.delenv("CONTIG_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert "llm" not in detect.available_detectors()


def test_claude_provider_without_key_is_not_available(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_detector_available() is False


def test_openai_provider_without_key_is_not_available(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm_detector_available() is False


def test_unknown_provider_value_is_not_available(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert llm_detector_available() is False


# --- env satisfied: available + registered + resolvable ------------------------


def test_claude_provider_with_key_is_available(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert llm_detector_available() is True


def test_openai_provider_with_key_is_available(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert llm_detector_available() is True


def test_get_detector_llm_returns_a_callable_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    detector = get_detector("llm")
    assert callable(detector)


def test_llm_listed_in_available_detectors_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert "llm" in detect.available_detectors()


# --- mapping a model response to a Diagnosis (fake seam, no network) -----------


def test_detector_parses_model_json_into_a_diagnosis(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        detect,
        "_llm_complete",
        _fake_completion(
            {
                "failure_class": "oom",
                "root_cause": "the aligner exhausted memory",
                "confidence": 0.8,
            }
        ),
    )
    detector: Detector = build_llm_detector()
    d = detector(_failed_events(), "java.lang.OutOfMemoryError: Java heap space")
    assert isinstance(d, Diagnosis)
    assert d.failure_class == "oom"
    assert "memory" in d.root_cause.lower()
    assert d.confidence == 0.8


def test_detector_clamps_out_of_range_confidence(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        detect,
        "_llm_complete",
        _fake_completion(
            {"failure_class": "bad_param", "root_cause": "bad flag", "confidence": 5.0}
        ),
    )
    d = build_llm_detector()(_failed_events(), "Unknown option: --foo")
    assert 0.0 <= d.confidence <= 1.0


def test_detector_tolerates_json_wrapped_in_prose(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    wrapped = (
        "Here is my analysis:\n"
        '{"failure_class": "time_limit", "root_cause": "wall clock exceeded", '
        '"confidence": 0.7}\n'
        "Hope that helps."
    )
    monkeypatch.setattr(detect, "_llm_complete", _fake_completion(wrapped))
    d = build_llm_detector()(_failed_events(), "CANCELLED DUE TO TIME LIMIT")
    assert d.failure_class == "time_limit"


def test_detector_falls_back_to_unknown_on_unparseable_response(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        detect, "_llm_complete", _fake_completion("not json at all, sorry")
    )
    d = build_llm_detector()(_failed_events(), "some log")
    assert d.failure_class == "unknown"


def test_detector_falls_back_to_unknown_on_invalid_failure_class(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        detect,
        "_llm_complete",
        _fake_completion(
            {"failure_class": "supernova", "root_cause": "x", "confidence": 0.5}
        ),
    )
    d = build_llm_detector()(_failed_events(), "some log")
    assert d.failure_class == "unknown"


def test_detector_falls_back_to_unknown_when_seam_raises(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def _boom(provider: str, prompt: str) -> str:
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr(detect, "_llm_complete", _boom)
    d = build_llm_detector()(_failed_events(), "some log")
    assert d.failure_class == "unknown"


def test_detector_does_not_log_the_api_key(monkeypatch, caplog) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "super-secret-key-value")
    monkeypatch.setattr(
        detect,
        "_llm_complete",
        _fake_completion(
            {"failure_class": "oom", "root_cause": "x", "confidence": 0.5}
        ),
    )
    with caplog.at_level("DEBUG"):
        build_llm_detector()(_failed_events(), "out of memory")
    assert "super-secret-key-value" not in caplog.text


# --- corpus eval works with the LLM detector unchanged -------------------------


def test_corpus_evaluate_detector_runs_with_the_llm_detector(monkeypatch) -> None:
    monkeypatch.setenv("CONTIG_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        detect,
        "_llm_complete",
        _fake_completion(
            {"failure_class": "oom", "root_cause": "out of memory", "confidence": 0.9}
        ),
    )
    from contig.corpus import evaluate_detector
    from contig.models import FailureCase

    cases = [
        FailureCase(
            case_id="c1",
            description="oom case",
            source="test",
            events=_failed_events(),
            log_text="killed: out of memory",
            expected_class="oom",
        ),
        FailureCase(
            case_id="c2",
            description="another case",
            source="test",
            events=_failed_events(),
            log_text="Unknown option: --foo",
            expected_class="bad_param",
        ),
    ]
    report = evaluate_detector(cases, build_llm_detector())
    # the fake always says oom: one hit, one miss, suite never hits the network
    assert report.total == 2
    assert report.correct == 1
