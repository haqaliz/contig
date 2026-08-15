"""Reproduce-case corpus core (C8 slice 2: capture/promote/scorer).

The corpus-analog of verify_corpus.py: a `ReproduceCase` is built from a real
`ReproduceRecord` (the gate decides when a run earns a case), held pending
until a human promotes it into the golden corpus with expected labels, and
re-derived by the scorer under the CURRENT `classify` bands.

The honesty contract mirrors verify_corpus.py exactly: a case stores INPUTS --
the claimed/observed/tolerance triples (plus repair and exit code) -- never the
stored statuses. `expected_status` pins what the human says the CURRENT bands
should derive; the scorer re-derives each claim with `classify` and counts a
match only when the re-derived status equals the expected one, so a case whose
stored input crosses a changed band must flip status (the mutation-control
pin). A claim with no locator-family in the original claims list (or none
supplied) is `family="unknown"` -- never fabricated, never a crash.

The golden corpus file does NOT ship: it is created on first promote, mirroring
the verify golden. This module is pure (no I/O beyond the JSONL sidecar
helpers), so the future `reproduce-corpus` guard command consumes one module.
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from contig.models import (
    ClaimStatus,
    FamilyScore,
    RepairOutcome,
    ReproduceCase,
    ReproduceCaseClaim,
    ReproduceCaseResult,
    ReproduceCorpusReport,
    ReproduceCorpusSnapshot,
    ReproduceRecord,
)
from contig.reproduce_guard import claim_family
from contig.verification.reproduce import Claim, classify

_CLAIM_STATUSES = set(get_args(ClaimStatus))
_REPAIR_OUTCOMES = set(get_args(RepairOutcome))


def default_reproduce_corpus_path() -> Path:
    """Path to the golden reproduce-case corpus.

    The golden corpus does NOT ship -- it is created on first promote (a
    human-confirmed case), mirroring the verify golden. `reproduce-guard`
    never falls back to it, so golden cases never leak into the regression
    guard.
    """
    return Path(__file__).parent / "data" / "reproduce_corpus.jsonl"


def default_reproduce_corpus_history_path() -> Path:
    """Committed reproduce-corpus trend (JSONL, one ReproduceCorpusSnapshot per line)."""
    return Path(__file__).parent / "data" / "reproduce_corpus_history.jsonl"


def should_capture_reproduce(record: ReproduceRecord) -> bool:
    """Whether a finished reproduce run earns a pending case (the capture gate).

    True when there is anything interesting for a human to judge: any claim
    `diverged` or `unverified` (a clean "no" or an unlocatable metric is a
    judgement, not a pass), any repair history (the run needed healing), or a
    non-zero exit code (the run failed). A clean run -- all claims
    `reproduced`/`within_tolerance`, empty repair history, exit 0 -- is never
    captured. Always-on: no flag toggles this, it is the honest-skip contract.
    """
    return (
        any(r.status in {"diverged", "unverified"} for r in record.claim_results)
        or bool(record.repair_history)
        or record.exit_code != 0
    )


def reproduce_case_from_record(
    record: ReproduceRecord, *, claims: list[Claim] | None = None
) -> ReproduceCase:
    """Build a pending ReproduceCase from a reproduce record (mirrors
    verify_corpus.py:verification_case_from_run).

    Per-claim inputs come from the record's `claim_results` (the
    claimed/observed/tolerance triple, NEVER the stored status), with the
    family taken from the matching `Claim` (by id) when supplied -- or
    `"unknown"` when the claims list is absent or the id is unmatched (never
    fabricated, never a crash). `expected_status` stays None until a human
    promotes the case; the description is a one-line honesty note naming the
    interesting signal so the reviewer can judge the case without opening the
    run.
    """
    claims_by_id = {c.id: c for c in claims} if claims else {}
    case_claims = [
        ReproduceCaseClaim(
            claim_id=r.id,
            claimed=r.claimed,
            observed=r.observed,
            tolerance=r.tolerance,
            family=claim_family(claims_by_id[r.id]) if r.id in claims_by_id else "unknown",
        )
        for r in record.claim_results
    ]

    repair = record.repair_history[-1].outcome if record.repair_history else None

    signals: list[str] = []
    interesting = [r.id for r in record.claim_results if r.status in {"diverged", "unverified"}]
    if interesting:
        signals.append("claims " + ", ".join(sorted(interesting)) + " diverged or unverified")
    if record.repair_history:
        signals.append(f"repair={repair}")
    if record.exit_code != 0:
        signals.append(f"exit={record.exit_code}")

    return ReproduceCase(
        case_id=f"{record.reproduce_id}-reproduce",
        description=(
            f"captured from reproduce run {record.reproduce_id}: "
            f"{'; '.join(signals) if signals else 'clean inputs, captured for labeling'}"
        ),
        source=f"pending:{record.reproduce_id}",
        repo=record.repo,
        run_command=record.run_command,
        claims_sha256=record.claims_sha256,
        claims=case_claims,
        repair=repair,
        exit_code=record.exit_code,
    )


def load_reproduce_cases(path: str | PathLike[str]) -> list[ReproduceCase]:
    """Read a JSONL reproduce corpus back into ReproduceCase objects.

    Blank and malformed lines are skipped (snapshot_history.py precedent), so
    a hand-edited or half-written file never crashes the consumer; mirrors
    verify_corpus.py:load_verify_cases.
    """
    text = Path(path).read_text()
    cases: list[ReproduceCase] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            cases.append(ReproduceCase.model_validate_json(line))
        except ValidationError:
            continue  # skip a malformed/half-written line; rest is valid
    return cases


def save_reproduce_cases(
    cases: list[ReproduceCase], path: str | PathLike[str]
) -> None:
    """Write the corpus as JSONL (one ReproduceCase per line)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(case.model_dump_json() + "\n" for case in cases))


def append_reproduce_case(
    case: ReproduceCase, path: str | PathLike[str]
) -> None:
    """Append one ReproduceCase as a JSONL line (creates the file/dirs if needed)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:
        fh.write(case.model_dump_json() + "\n")


def promote_reproduce_case(
    case_id: str,
    *,
    pending_path: str | PathLike[str],
    golden_path: str | PathLike[str],
    expected_claims: dict[str, str] | None = None,
    expected_repair: str | None = None,
    expected_exit_code: int | None = None,
) -> None:
    """Promote a human-reviewed pending reproduce case into the golden corpus
    (mirrors verify_corpus.py:promote_pending_verify_case).

    `expected_claims` maps claim id -> expected ClaimStatus (validated against
    the literal; an unknown claim id raises). `expected_repair`, when given,
    must be a valid RepairOutcome and pins the case's repair expectation; a
    None leaves it unset (pending cases always start unset). `expected_exit_code`,
    when given, pins the expected exit code. The case moves from the pending
    file into the golden corpus (`source` pending: -> confirmed:), where the
    scorer can re-derive it; a case is promoted at most once (deduped by id).
    """
    pending = list(load_reproduce_cases(pending_path))

    case = next((c for c in pending if c.case_id == case_id), None)
    if case is None:
        raise ValueError(f"no pending reproduce case with id {case_id!r}")

    golden = Path(golden_path)
    golden_cases = load_reproduce_cases(golden) if golden.exists() else []
    if any(c.case_id == case_id for c in golden_cases):
        raise ValueError(f"case {case_id!r} is already in the golden corpus")

    expected_claims = expected_claims or {}
    claims_by_id = {c.claim_id: c for c in case.claims}
    for claim_id, status in expected_claims.items():
        if claim_id not in claims_by_id:
            raise ValueError(f"no claim with id {claim_id!r} in case {case_id!r}")
        if status not in _CLAIM_STATUSES:
            raise ValueError(f"invalid expected status {status!r} for claim {claim_id!r}")
    if expected_repair is not None and expected_repair not in _REPAIR_OUTCOMES:
        raise ValueError(f"invalid expected repair {expected_repair!r}")

    update: dict = {
        "claims": [
            c.model_copy(update={"expected_status": expected_claims.get(c.claim_id)})
            if c.claim_id in expected_claims
            else c
            for c in case.claims
        ]
    }
    if expected_repair is not None:
        update["expected_repair"] = expected_repair
    if expected_exit_code is not None:
        update["expected_exit_code"] = expected_exit_code

    source = case.source
    confirmed_source = (
        "confirmed:" + source[len("pending:") :]
        if source.startswith("pending:")
        else "confirmed"
    )
    update["source"] = confirmed_source
    promoted = case.model_copy(update=update)

    append_reproduce_case(promoted, golden)
    save_reproduce_cases([c for c in pending if c.case_id != case_id], pending_path)


def evaluate_reproduce_case(
    case: ReproduceCase, *, classifier=None
) -> ReproduceCaseResult:
    """Re-derive one case's claim statuses under the CURRENT `classify` bands
    and score it against its expected labels (pure, no I/O).

    The re-derived status of every claim is produced with the shipped
    `classify` -- `(claimed, observed, tolerance) -> (status, delta, msg)` --
    or the injected `classifier` (the mutation-control seam: a mutated
    classifier with a looser tolerance must flip stored cases). A claim
    matches only when its `expected_status` is set and equals the re-derived
    status; unlabeled claims are never counted wrong. Case-level expectations
    (`expected_repair`, `expected_exit_code`) are extra: a mismatch appends a
    named divergence and flips the case to unmatched.
    """
    classifier = classify if classifier is None else classifier

    predicted_statuses: dict[str, str] = {}
    labeled = 0
    matching = 0
    divergence: list[str] = []

    for claim in case.claims:
        status = classifier(claim.claimed, claim.observed, claim.tolerance)[0]
        predicted_statuses[claim.claim_id] = status
        if claim.expected_status is None:
            continue
        labeled += 1
        if status == claim.expected_status:
            matching += 1
        else:
            divergence.append(
                f"{claim.claim_id}: expected {claim.expected_status}, "
                f"re-derived {status}"
            )

    matched = matching == labeled
    if case.expected_repair is not None and case.expected_repair != case.repair:
        divergence.append(
            f"repair: expected {case.expected_repair}, observed {case.repair}"
        )
        matched = False
    if (
        case.expected_exit_code is not None
        and case.expected_exit_code != case.exit_code
    ):
        divergence.append(
            f"exit_code: expected {case.expected_exit_code}, observed {case.exit_code}"
        )
        matched = False

    return ReproduceCaseResult(
        case_id=case.case_id,
        predicted_statuses=predicted_statuses,
        matched=matched,
        labeled_claims=labeled,
        matching_claims=matching,
        divergence=divergence,
    )


def evaluate_reproduce_cases(
    cases: list[ReproduceCase], *, classifier=None
) -> ReproduceCorpusReport:
    """Score the current `classify` bands over a case corpus (pure, no I/O).

    `total`/`correct`/`claim_match_rate` cover labeled claims only; unlabeled
    claims are excluded, never counted wrong (mirrors evaluate_verify). A
    labeled case is one with any expected claim status, or an expected repair
    or exit code. `per_family` rates accumulate over labeled claims via their
    stored family; `mismatches` carries the unmatched labeled cases.
    """
    labeled = [
        c
        for c in cases
        if any(cl.expected_status is not None for cl in c.claims)
        or c.expected_repair is not None
        or c.expected_exit_code is not None
    ]
    results = [
        evaluate_reproduce_case(case, classifier=classifier) for case in labeled
    ]

    total = sum(r.labeled_claims for r in results)
    correct = sum(r.matching_claims for r in results)

    per_family: dict[str, FamilyScore] = {}
    for case, result in zip(labeled, results):
        for claim in case.claims:
            if claim.expected_status is None:
                continue
            score = per_family.get(claim.family)
            if score is None:
                score = per_family[claim.family] = FamilyScore(
                    matched=0, total=0, rate=0.0
                )
            score.total += 1
            if result.predicted_statuses[claim.claim_id] == claim.expected_status:
                score.matched += 1
    for score in per_family.values():
        score.rate = score.matched / score.total if score.total else 0.0

    return ReproduceCorpusReport(
        total=total,
        correct=correct,
        claim_match_rate=correct / total if total else 0.0,
        cases=len(labeled),
        per_family=per_family,
        mismatches=[r for r in results if not r.matched],
    )


def snapshot_from_reproduce_report(
    report: ReproduceCorpusReport,
    *,
    corpus_sha: str,
    timestamp: str,
    contig_version: str | None = None,
) -> ReproduceCorpusSnapshot:
    """Build a ReproduceCorpusSnapshot from a report plus the corpus identity.

    The timestamp and corpus_sha are passed in (computed by the caller) so
    this stays a pure projection of the report -- mirrors
    verify_corpus.py:snapshot_from_verify_report.
    """
    return ReproduceCorpusSnapshot(
        timestamp=timestamp,
        case_count=report.cases,
        corpus_sha=corpus_sha,
        claim_match_rate=report.claim_match_rate,
        per_family=report.per_family,
        contig_version=contig_version,
    )
