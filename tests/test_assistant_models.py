"""Tests for assistant answer/eval contracts."""

from contig.assistant.models import Answer, Citation, EvalReport


def test_answer_round_trips():
    answer = Answer(
        intent="verdict",
        answer="PASS",
        citations=[Citation(label="run_record", path="run_record.json", sha256="abc")],
        actions=["contig show r1 --explain"],
    )
    again = Answer.model_validate_json(answer.model_dump_json())
    assert again.intent == "verdict"
    assert again.citations[0].label == "run_record"


def test_eval_report_threshold():
    report = EvalReport(total=10, passed=9, accuracy=0.9)
    assert report.exit_ok(0.9)
    assert not report.exit_ok(0.95)
