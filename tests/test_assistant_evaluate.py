"""Tests for the frozen ask-your-run eval set."""

from pathlib import Path

import pytest

from contig.assistant.context import load_context
from contig.assistant.evaluate import evaluate_cases, load_eval_cases
from contig.assistant.models import EvalCase

FIX = Path(__file__).parent / "fixtures" / "reporting"
ASSIST = Path(__file__).parent / "fixtures" / "assistant"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"
READINESS = FIX / "readiness.json"
CASES = ASSIST / "eval.jsonl"


def _context():
    return load_context(RUNS, "r1", variants_path=VARIANTS, readiness_path=READINESS)


def test_fixture_cases_all_pass():
    cases = load_eval_cases(CASES)
    report = evaluate_cases(_context(), cases)
    assert report.total == 9
    assert report.passed == 9
    assert report.accuracy == 1.0
    assert report.misses == []


def test_a_wrong_case_is_a_miss():
    report = evaluate_cases(
        _context(),
        [EvalCase(question="what is the verdict?", expected_intent="unknown")],
    )
    assert report.passed == 0
    assert report.misses[0]["actual_intent"] == "verdict"


def test_empty_cases_file_is_refused(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n")
    with pytest.raises(ValueError):
        load_eval_cases(path)


def test_missing_cases_file_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_eval_cases(tmp_path / "missing.jsonl")
