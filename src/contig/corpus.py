"""Failure corpus storage + detector eval (moat #2).

The corpus is accumulated, labeled failure data persisted as JSONL (one
FailureCase per line, so it appends cheaply and diffs cleanly in git). The eval
replays the rule-based detector over the corpus and scores it per class, which
is how we measure (and then improve) detection as real runs accrue.
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path

from contig.detect import diagnose_failure
from contig.models import (
    ClassScore,
    DetectorEvalReport,
    DetectorMismatch,
    FailureCase,
    FailureClass,
    RunRecord,
)


def default_corpus_path() -> Path:
    """Path to the seed corpus shipped with the package (the accumulated data)."""
    return Path(__file__).parent / "data" / "detector_corpus.jsonl"


def save_corpus(cases: list[FailureCase], path: str | PathLike[str]) -> None:
    """Write the corpus as JSONL (one FailureCase per line)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(case.model_dump_json() + "\n" for case in cases))


def load_corpus(path: str | PathLike[str]) -> list[FailureCase]:
    """Read a JSONL corpus back into FailureCase objects (blank lines skipped)."""
    text = Path(path).read_text()
    return [
        FailureCase.model_validate_json(line)
        for line in text.splitlines()
        if line.strip()
    ]


def evaluate_detector(cases: list[FailureCase]) -> DetectorEvalReport:
    """Replay `diagnose_failure` over the corpus and score it per class.

    Accuracy is the headline; `mismatches` names every case the detector got
    wrong (so gaps are actionable); `per_class` precision/recall shows where the
    detector is weak, which is what drives the next rule.
    """
    correct = 0
    mismatches: list[DetectorMismatch] = []
    # Per-class tallies for precision/recall: support (true), predicted, hits.
    support: dict[str, int] = {}
    predicted_count: dict[str, int] = {}
    hits: dict[str, int] = {}

    for case in cases:
        predicted = diagnose_failure(case.events, case.log_text).failure_class
        expected = case.expected_class
        support[expected] = support.get(expected, 0) + 1
        predicted_count[predicted] = predicted_count.get(predicted, 0) + 1
        if predicted == expected:
            correct += 1
            hits[expected] = hits.get(expected, 0) + 1
        else:
            mismatches.append(
                DetectorMismatch(case_id=case.case_id, expected=expected, predicted=predicted)
            )

    per_class: dict[str, ClassScore] = {}
    for cls in set(support) | set(predicted_count):
        sup = support.get(cls, 0)
        pred = predicted_count.get(cls, 0)
        hit = hits.get(cls, 0)
        per_class[cls] = ClassScore(
            support=sup,
            predicted=pred,
            correct=hit,
            precision=hit / pred if pred else 0.0,
            recall=hit / sup if sup else 0.0,
        )

    total = len(cases)
    return DetectorEvalReport(
        total=total,
        correct=correct,
        accuracy=correct / total if total else 0.0,
        mismatches=mismatches,
        per_class=per_class,
    )


def failure_case_from_run(
    record: RunRecord,
    log_text: str,
    expected_class: FailureClass,
    *,
    case_id: str | None = None,
    source: str | None = None,
) -> FailureCase:
    """Build a corpus FailureCase from a failed run.

    Keep only the failing events (what the detector keys on), bundle the
    captured log, and attach the label. This is the loop that turns a real
    failed run into labeled corpus data instead of hand-authoring cases.
    """
    failing = [event for event in record.events if event.is_failure]
    return FailureCase(
        case_id=case_id or f"run:{record.run_id}",
        description=f"captured from run {record.run_id} ({record.pipeline})",
        source=source or f"run:{record.run_id}",
        events=failing,
        log_text=log_text,
        expected_class=expected_class,
    )


def append_case(case: FailureCase, path: str | PathLike[str]) -> None:
    """Append one FailureCase as a JSONL line (creates the file/dirs if needed)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:
        fh.write(case.model_dump_json() + "\n")
