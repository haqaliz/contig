"""Failure corpus storage + detector eval (moat #2).

The corpus is accumulated, labeled failure data persisted as JSONL (one
FailureCase per line, so it appends cheaply and diffs cleanly in git). The eval
replays the rule-based detector over the corpus and scores it per class, which
is how we measure (and then improve) detection as real runs accrue.
"""

from __future__ import annotations

import hashlib
import re
from os import PathLike
from pathlib import Path

from contig.detect import Detector, diagnose_failure
from contig.models import (
    ClassScore,
    DetectorEvalReport,
    DetectorMismatch,
    EvalSnapshot,
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


def evaluate_detector(
    cases: list[FailureCase], detector: Detector | None = None
) -> DetectorEvalReport:
    """Replay a detector over the corpus and score it per class.

    `detector` is any callable matching the Detector type; it defaults to the
    rules detector (`diagnose_failure`) so existing callers are unchanged. This
    is how `eval-detector --detector <name>` scores ANY registered detector.

    Accuracy is the headline; `mismatches` names every case the detector got
    wrong (so gaps are actionable); `per_class` precision/recall shows where the
    detector is weak, which is what drives the next rule.
    """
    detector = detector or diagnose_failure
    correct = 0
    mismatches: list[DetectorMismatch] = []
    # Per-class tallies for precision/recall: support (true), predicted, hits.
    support: dict[str, int] = {}
    predicted_count: dict[str, int] = {}
    hits: dict[str, int] = {}

    for case in cases:
        predicted = detector(case.events, case.log_text).failure_class
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


def promote_pending_case(
    case_id: str,
    *,
    pending_path: str | PathLike[str],
    golden_path: str | PathLike[str] | None = None,
    corrected_class: FailureClass | None = None,
) -> FailureCase:
    """Promote a human-reviewed pending case into the golden corpus (moat #2).

    The reviewer confirms the detector's provisional label or corrects it; the
    case then moves from the pending file into the golden corpus, where the eval
    counts it. This is the step that makes the corpus (and the detector) compound
    from real runs. A case is promoted at most once (deduped by case_id).
    """
    golden = Path(golden_path) if golden_path is not None else default_corpus_path()
    pending = list(load_corpus(pending_path))

    case = next((c for c in pending if c.case_id == case_id), None)
    if case is None:
        raise ValueError(f"no pending case with id {case_id!r}")

    golden_cases = load_corpus(golden) if Path(golden).exists() else []
    if any(c.case_id == case_id for c in golden_cases):
        raise ValueError(f"case {case_id!r} is already in the golden corpus")

    # Mark it human-confirmed and apply any label correction.
    source = case.source
    confirmed_source = (
        "confirmed:" + source[len("pending:") :]
        if source.startswith("pending:")
        else "confirmed"
    )
    promoted = case.model_copy(
        update={
            "expected_class": corrected_class or case.expected_class,
            "source": confirmed_source,
        }
    )

    append_case(promoted, golden)
    save_corpus([c for c in pending if c.case_id != case_id], pending_path)
    return promoted


# --- failure clustering (PRD contract B) ---------------------------------------
# Group cases by failure class plus a normalized log signature, so the same
# systemic failure mode collapses into one cluster even across different runs
# (different absolute paths, task hashes, line numbers, timestamps).

# Patterns we strip so a signature is invariant to the per-run noise that would
# otherwise scatter one systemic mode across many "unique" logs. Order matters:
# timestamps and hex hashes are stripped before bare numbers so their digits are
# not half-consumed by the number rule first.
_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}(?:\.\d+)?z?", re.IGNORECASE
)
# An absolute path (leading slash, then non-space path chars). Replaced wholesale
# so /work/ab/cd and /data/genome/GRCh38.fa do not split a cluster.
_PATH_RE = re.compile(r"/[^\s]+")
# A long-ish hex run (a task hash / digest); 6+ hex chars so ordinary words and
# small numbers are left for the number rule.
_HEX_RE = re.compile(r"\b[0-9a-f]{6,}\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+")

# Words that mark a salient line (an error / the failure itself). Keeping only
# these lines focuses the signature on the failure mode, not the surrounding
# chatter that varies run to run.
_SALIENT_TOKENS = (
    "error",
    "fail",
    "killed",
    "not found",
    "exit",
    "out of memory",
    "cannot",
    "unable",
    "no such",
    "missing",
    "denied",
    "fault",
    "exception",
    "traceback",
)


def normalize_signature(log_text: str) -> str:
    """A normalized fingerprint of a log: invariant to per-run noise.

    Lowercase, strip absolute paths, hex hashes, timestamps, and bare numbers,
    keep only the salient (error-like) lines (falling back to all lines when none
    match), then hash the result. Two logs that describe the same systemic
    failure mode produce the same signature even when their paths, hashes, line
    numbers, and timestamps differ.
    """
    text = log_text.lower()
    text = _TIMESTAMP_RE.sub("<ts>", text)
    text = _PATH_RE.sub("<path>", text)
    text = _HEX_RE.sub("<hash>", text)
    text = _NUMBER_RE.sub("<n>", text)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    salient = [line for line in lines if any(tok in line for tok in _SALIENT_TOKENS)]
    kept = salient or lines
    canonical = "\n".join(kept)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def cluster_failures(cases: list[FailureCase]) -> list[dict]:
    """Group corpus cases by failure class plus a normalized log signature.

    Returns clusters `[{failure_class, signature, count, case_ids}]` ordered
    worst-first (largest count). Cases sharing a (failure_class, signature) are
    one cluster, so a recurring systemic mode is one row no matter how many runs
    it appeared in (PRD contract B).
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for case in cases:
        signature = normalize_signature(case.log_text)
        key = (case.expected_class, signature)
        groups.setdefault(key, []).append(case.case_id)

    clusters = [
        {
            "failure_class": failure_class,
            "signature": signature,
            "count": len(case_ids),
            "case_ids": case_ids,
        }
        for (failure_class, signature), case_ids in groups.items()
    ]
    # Worst-first by count; ties broken by class then signature for determinism.
    clusters.sort(key=lambda c: (-c["count"], c["failure_class"], c["signature"]))
    return clusters


# --- corpus coverage (PRD contract C) ------------------------------------------
# Per-class support, a thin-coverage flag (fewer than three cases), a by-source
# breakdown, and a confirmed-cases-over-time series from the eval history.

_THIN_THRESHOLD = 3


def _source_kind(source: str) -> str:
    """The provenance kind of a case: the prefix before ':' (e.g. run, confirmed).

    A source like "run:r1" or "confirmed:r2" reduces to its kind ("run",
    "confirmed"); a bare "synthetic" with no colon is its own kind.
    """
    return source.split(":", 1)[0] if ":" in source else source


def coverage_report(
    cases: list[FailureCase], *, history: list[EvalSnapshot] | None = None
) -> dict:
    """Summarize how well the corpus covers each failure class (PRD contract C).

    Returns `{total, per_class, thin, by_source, confirmed_over_time}`: per_class
    is the support per failure class, thin lists the classes with fewer than
    three cases (the gaps to fill next), by_source breaks the corpus down by
    provenance kind, and confirmed_over_time is the corpus-size trend drawn from
    the eval history (empty when no history is supplied).
    """
    per_class: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for case in cases:
        per_class[case.expected_class] = per_class.get(case.expected_class, 0) + 1
        kind = _source_kind(case.source)
        by_source[kind] = by_source.get(kind, 0) + 1

    thin = sorted(cls for cls, count in per_class.items() if count < _THIN_THRESHOLD)
    confirmed_over_time = [
        {"timestamp": snap.timestamp, "corpus_size": snap.corpus_size}
        for snap in (history or [])
    ]
    return {
        "total": len(cases),
        "per_class": per_class,
        "thin": thin,
        "by_source": by_source,
        "confirmed_over_time": confirmed_over_time,
    }
