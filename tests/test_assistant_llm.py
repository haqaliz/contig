"""Tests for the optional LLM paraphrase layer (no network)."""

import pytest

from contig.assistant.llm import HttpModelClient, paraphrase
from contig.assistant.models import Answer, Citation


class FakeClient:
    def __init__(self, text="Rephrased answer."):
        self.text = text
        self.prompt = ""

    def complete(self, prompt: str) -> str:
        self.prompt = prompt
        return self.text


def test_paraphrase_keeps_citations_and_actions():
    answer = Answer(
        intent="verdict",
        answer="Verdict: PASS.",
        citations=[Citation(label="run_record", path="run_record.json", sha256="abc")],
        actions=["contig show r1 --explain"],
    )
    client = FakeClient("This run passed verification (PASS).")
    result = paraphrase(answer, client, "what is the verdict?")
    assert result.answer == "This run passed verification (PASS)."
    assert result.citations == answer.citations
    assert result.actions == answer.actions
    assert "Grounded answer" in client.prompt
    assert "run_record.json" in client.prompt


def test_changed_refusal_falls_back_to_the_grounded_answer():
    answer = Answer(intent="unknown", answer="I won't guess; the question is outside this bundle.")
    result = paraphrase(answer, FakeClient("The weather is sunny today."), "what is the weather?")
    assert result == answer


def test_dropped_verdict_falls_back_to_the_grounded_answer():
    answer = Answer(intent="verdict", answer="Verdict: WARN — completed with caveats.")
    result = paraphrase(answer, FakeClient("The run completed with caveats."), "q")
    assert result == answer


def test_heavily_truncated_paraphrase_falls_back_to_the_grounded_answer():
    answer = Answer(
        intent="verdict",
        answer="Verdict: WARN — completed with caveats and a detailed explanation.",
    )
    result = paraphrase(answer, FakeClient("WARN."), "q")
    assert result == answer


def test_empty_model_output_falls_back_to_the_grounded_answer():
    answer = Answer(intent="verdict", answer="Verdict: PASS.")
    result = paraphrase(answer, FakeClient(""), "q")
    assert result == answer


def test_missing_llm_env_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("CONTIG_LLM_URL", raising=False)
    monkeypatch.delenv("CONTIG_LLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="no LLM configured"):
        HttpModelClient.from_env()
