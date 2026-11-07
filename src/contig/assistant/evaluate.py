"""Frozen eval set for the deterministic ask-your-run router."""

from __future__ import annotations

from pathlib import Path

from contig.assistant.answer import answer_question
from contig.assistant.context import Context
from contig.assistant.models import EvalCase, EvalReport


def load_eval_cases(path: str | Path) -> list[EvalCase]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"eval cases not found: {path}")
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cases.append(EvalCase.model_validate_json(line))
    if not cases:
        raise ValueError(f"no eval cases in {path}")
    return cases


def evaluate_cases(context: Context, cases: list[EvalCase]) -> EvalReport:
    misses: list[dict[str, str]] = []
    passed = 0
    for case in cases:
        answer = answer_question(context, case.question)
        source_labels = {citation.label for citation in answer.citations}
        intent_ok = answer.intent == case.expected_intent
        source_ok = not case.expected_source_kind or case.expected_source_kind in source_labels
        if intent_ok and source_ok:
            passed += 1
            continue
        misses.append({
            "question": case.question,
            "expected_intent": case.expected_intent,
            "actual_intent": answer.intent,
            "expected_source_kind": case.expected_source_kind,
            "actual_sources": ",".join(sorted(source_labels)),
        })
    total = len(cases)
    return EvalReport(
        total=total,
        passed=passed,
        accuracy=passed / total if total else 0.0,
        misses=misses,
    )
