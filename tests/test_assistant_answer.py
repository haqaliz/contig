"""Tests for the deterministic grounded answer builder."""

from pathlib import Path

from contig.assistant.answer import answer_question, intent_of
from contig.assistant.context import load_context

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"
READINESS = FIX / "readiness.json"


def _context():
    return load_context(RUNS, "r1", variants_path=VARIANTS, readiness_path=READINESS)


def test_intent_router_order():
    assert intent_of("is BRCA1 ready?") == "readiness"
    assert intent_of("tell me about variants") == "variants"
    assert intent_of("why did it repair?") == "repairs"
    assert intent_of("how did QC do?") == "qc"
    assert intent_of("show provenance") == "provenance"
    assert intent_of("what methods?") == "methods"
    assert intent_of("how do I share this?") == "report"
    assert intent_of("what is the verdict?") == "verdict"
    assert intent_of("what is the weather?") == "unknown"


def test_verdict_answer_cites_the_record():
    answer = answer_question(_context(), "what is the verdict?")
    assert answer.intent == "verdict"
    assert "WARN" in answer.answer
    assert "library_size_skew" in answer.answer
    assert [citation.label for citation in answer.citations] == ["run_record"]
    assert answer.actions


def test_qc_answer_lists_checks():
    answer = answer_question(_context(), "how did QC do?")
    assert "2 checks" in answer.answer
    assert "mapping_rate" in answer.answer
    assert "library_size_skew" in answer.answer


def test_repair_answer_names_the_cause():
    answer = answer_question(_context(), "why did it repair?")
    assert "oom" in answer.answer
    assert "STAR ran out of memory" in answer.answer
    assert "repaired" in answer.answer


def test_provenance_answer_includes_signature_status():
    answer = answer_question(_context(), "show provenance")
    assert "nf-core/rnaseq" in answer.answer
    assert "unsigned" in answer.answer


def test_methods_answer_is_the_methods_paragraph():
    answer = answer_question(_context(), "what methods should I cite?")
    assert answer.intent == "methods"
    assert "nf-core/rnaseq" in answer.answer


def test_variants_answer_without_a_gene_summarizes():
    answer = answer_question(_context(), "tell me about variants")
    assert answer.intent == "variants"
    assert "3 variants" in answer.answer
    assert [citation.label for citation in answer.citations] == ["variants"]


def test_variants_answer_with_a_gene_filters():
    answer = answer_question(_context(), "tell me about BRCA1")
    assert answer.intent == "variants"
    assert "BRCA1: 1 variant(s)" in answer.answer
    assert "Pathogenic" in answer.answer


def test_readiness_answer_with_a_gene_reports_the_state():
    answer = answer_question(_context(), "is GENE3 ready?")
    assert answer.intent == "readiness"
    assert "not-interpretable" in answer.answer
    assert "0 covered bases" in answer.answer
    assert [citation.label for citation in answer.citations] == ["readiness"]


def test_report_and_help_answers():
    report = answer_question(_context(), "how do I share this?")
    assert "contig report r1" in report.answer
    help_answer = answer_question(_context(), "help")
    assert help_answer.intent == "help"
    assert "I can answer" in help_answer.answer


def test_unknown_refuses_without_a_citation():
    answer = answer_question(_context(), "what is the weather?")
    assert answer.intent == "unknown"
    assert answer.confidence == "none"
    assert answer.citations == []
    assert "won't guess" in answer.answer


def test_actions_preserve_the_runs_dir_and_run_id_order():
    answer = answer_question(_context(), "what is the verdict?")
    assert answer.actions[0].startswith("contig show r1")
    assert "--runs-dir" in answer.actions[0]
