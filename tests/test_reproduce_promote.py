"""CLI tests for `contig reproduce-case-promote` (C8 slice 2, Task 3B).

The human-confirmation channel for reproduce cases: a reviewer confirms a
pending case and labels some (or all) of its claims with expected statuses;
the case moves from the pending file into the golden corpus (`source`
pending: -> confirmed:) with an auto-snapshot of the grown golden corpus
appended to the reproduce history. Mirrors test_verify_promote.py's
CliRunner patterns.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from contig.cli import app
from contig.models import (
    ClaimResult,
    ReproduceCase,
    ReproduceCorpusSnapshot,
    ReproduceRecord,
)
from contig.reproduce_corpus import (
    append_reproduce_case,
    evaluate_reproduce_cases,
    load_reproduce_cases,
    reproduce_case_from_record,
)
from contig.snapshot_history import load_jsonl
from contig.verification.reproduce import Claim

runner = CliRunner()

RUN_ID = "run-7"
_CLAIMS_SHA256 = "a" * 64
_CREATED_AT = "2026-07-18T00:00:00Z"


def _claim_result(
    id_="c1",
    status="diverged",
    claimed=1.0,
    observed=3.0,
    tolerance=0.1,
    delta=2.0,
):
    return ClaimResult(
        id=id_,
        status=status,
        claimed=claimed,
        observed=observed,
        tolerance=tolerance,
        delta=delta,
        message="ok",
    )


def _record(**overrides) -> ReproduceRecord:
    base = dict(
        reproduce_id=RUN_ID,
        repo="https://github.com/example/paper",
        run_command="python train.py --seed 0",
        claims_sha256=_CLAIMS_SHA256,
        claim_results=[_claim_result()],
        exit_code=0,
        created_at=_CREATED_AT,
    )
    base.update(overrides)
    return ReproduceRecord(**base)


def _claims_list() -> list[Claim]:
    return [
        Claim(id="c1", value=1.0, tolerance=0.1),
        Claim(id="c2", value=5.0, tolerance=0.1),
    ]


def _pending_case() -> ReproduceCase:
    record = _record(
        claim_results=[
            _claim_result(),
            _claim_result(
                id_="c2",
                status="within_tolerance",
                claimed=5.0,
                observed=5.1,
                delta=0.02,
            ),
        ]
    )
    return reproduce_case_from_record(record, claims=_claims_list())


def _seed_pending(tmp_path) -> object:
    pending_path = tmp_path / "pending_reproduce_corpus.jsonl"
    append_reproduce_case(_pending_case(), pending_path)
    return pending_path


def _promote(tmp_path, *extra_args):
    pending_path = _seed_pending(tmp_path)
    golden_path = tmp_path / "golden.jsonl"
    history_path = tmp_path / "reproduce_history.jsonl"
    args = [
        "reproduce-case-promote",
        f"{RUN_ID}-reproduce",
        "--pending",
        str(pending_path),
        "--golden",
        str(golden_path),
        "--history-file",
        str(history_path),
        *extra_args,
    ]
    result = runner.invoke(app, args)
    return result, pending_path, golden_path, history_path


# --- round-trip with expected claims ------------------------------------------


def test_promote_with_expected_claims_round_trips(tmp_path):
    result, pending_path, golden_path, history_path = _promote(
        tmp_path, "--expected-claims", "c1:diverged"
    )

    assert result.exit_code == 0
    assert f"{RUN_ID}-reproduce" in result.output
    assert "c1:diverged" in result.output

    golden = load_reproduce_cases(golden_path)
    assert len(golden) == 1
    assert golden[0].source == f"confirmed:{RUN_ID}"
    assert golden[0].claims[0].claim_id == "c1"
    assert golden[0].claims[0].expected_status == "diverged"
    assert golden[0].claims[0].observed == 3.0  # inputs preserved

    pending = load_reproduce_cases(pending_path)
    assert pending == []  # removed from pending

    snaps = load_jsonl(ReproduceCorpusSnapshot, history_path)
    assert len(snaps) == 1
    assert snaps[0].case_count == 1
    # The labeled claim re-derives diverged under the shipped bands -> 1/1.
    assert snaps[0].claim_match_rate == 1.0


# --- label-less confirmation ---------------------------------------------------


def test_promote_without_labels_confirms_without_labeling(tmp_path):
    result, pending_path, golden_path, history_path = _promote(tmp_path)

    assert result.exit_code == 0
    golden = load_reproduce_cases(golden_path)
    assert len(golden) == 1
    assert golden[0].source == f"confirmed:{RUN_ID}"
    assert all(c.expected_status is None for c in golden[0].claims)

    snaps = load_jsonl(ReproduceCorpusSnapshot, history_path)
    assert len(snaps) == 1
    # No labeled claims -> no scored cases, match rate 0.0 (nothing counted wrong).
    assert snaps[0].case_count == 0
    assert snaps[0].claim_match_rate == 0.0


# --- unknown id ----------------------------------------------------------------


def test_promote_unknown_id_exits_1_and_leaves_pending(tmp_path):
    pending_path = _seed_pending(tmp_path)
    golden_path = tmp_path / "golden.jsonl"
    history_path = tmp_path / "reproduce_history.jsonl"
    before = pending_path.read_text()

    result = runner.invoke(
        app,
        [
            "reproduce-case-promote",
            "no-such-case",
            "--pending",
            str(pending_path),
            "--golden",
            str(golden_path),
            "--history-file",
            str(history_path),
        ],
    )

    assert result.exit_code == 1
    assert "no-such-case" in result.output
    assert pending_path.read_text() == before  # pending untouched
    assert not golden_path.exists()
    assert not history_path.exists()


# --- dedupe --------------------------------------------------------------------


def test_promote_duplicate_in_golden_exits_1(tmp_path):
    golden_path = tmp_path / "golden.jsonl"
    append_reproduce_case(_pending_case(), golden_path)

    result, pending_path, _, _ = _promote(tmp_path)

    assert result.exit_code == 1
    assert "already in the golden corpus" in result.output
    assert len(load_reproduce_cases(golden_path)) == 1  # no double append


# --- invalid inputs are rejected before any write ------------------------------


def test_promote_invalid_status_exits_1_before_any_write(tmp_path):
    pending_path = _seed_pending(tmp_path)
    golden_path = tmp_path / "golden.jsonl"
    history_path = tmp_path / "reproduce_history.jsonl"
    before = pending_path.read_text()

    result = runner.invoke(
        app,
        [
            "reproduce-case-promote",
            f"{RUN_ID}-reproduce",
            "--expected-claims",
            "c1:bogus",
            "--pending",
            str(pending_path),
            "--golden",
            str(golden_path),
            "--history-file",
            str(history_path),
        ],
    )

    assert result.exit_code == 1
    assert "bogus" in result.output
    assert pending_path.read_text() == before  # nothing written
    assert not golden_path.exists()
    assert not history_path.exists()


def test_promote_unknown_claim_id_exits_1_before_any_write(tmp_path):
    pending_path = _seed_pending(tmp_path)
    golden_path = tmp_path / "golden.jsonl"
    history_path = tmp_path / "reproduce_history.jsonl"
    before = pending_path.read_text()

    result = runner.invoke(
        app,
        [
            "reproduce-case-promote",
            f"{RUN_ID}-reproduce",
            "--expected-claims",
            "nope:diverged",
            "--pending",
            str(pending_path),
            "--golden",
            str(golden_path),
            "--history-file",
            str(history_path),
        ],
    )

    assert result.exit_code == 1
    assert "nope" in result.output
    assert pending_path.read_text() == before
    assert not golden_path.exists()
    assert not history_path.exists()


def test_promote_invalid_repair_exits_1_before_any_write(tmp_path):
    pending_path = _seed_pending(tmp_path)
    golden_path = tmp_path / "golden.jsonl"
    history_path = tmp_path / "reproduce_history.jsonl"
    before = pending_path.read_text()

    result = runner.invoke(
        app,
        [
            "reproduce-case-promote",
            f"{RUN_ID}-reproduce",
            "--expected-repair",
            "unsure",
            "--pending",
            str(pending_path),
            "--golden",
            str(golden_path),
            "--history-file",
            str(history_path),
        ],
    )

    assert result.exit_code == 1
    assert "unsure" in result.output
    assert pending_path.read_text() == before
    assert not golden_path.exists()
    assert not history_path.exists()


def test_promote_non_int_expected_exit_fails_parsing(tmp_path):
    pending_path = _seed_pending(tmp_path)
    golden_path = tmp_path / "golden.jsonl"
    history_path = tmp_path / "reproduce_history.jsonl"

    result = runner.invoke(
        app,
        [
            "reproduce-case-promote",
            f"{RUN_ID}-reproduce",
            "--expected-exit",
            "not-an-int",
            "--pending",
            str(pending_path),
            "--golden",
            str(golden_path),
            "--history-file",
            str(history_path),
        ],
    )

    assert result.exit_code != 0  # click/typer rejects the non-int at parse time
    assert not golden_path.exists()
    assert not history_path.exists()


# --- partial labeling ----------------------------------------------------------


def test_partial_labeling_leaves_unlabeled_and_flags_mismatch(tmp_path):
    result, pending_path, golden_path, _ = _promote(
        tmp_path, "--expected-claims", "c1:reproduced"
    )

    assert result.exit_code == 0
    golden = load_reproduce_cases(golden_path)
    assert len(golden) == 1
    by_id = {c.claim_id: c for c in golden[0].claims}
    assert by_id["c1"].expected_status == "reproduced"
    assert by_id["c2"].expected_status is None  # unlabeled stays unlabeled

    report = evaluate_reproduce_cases(golden)
    assert report.total == 1  # labeled claims only
    assert report.correct == 0
    assert report.claim_match_rate == 0.0
    assert len(report.mismatches) == 1
    assert report.mismatches[0].case_id == f"{RUN_ID}-reproduce"
    assert report.mismatches[0].matched is False


# --- --json report -------------------------------------------------------------


def test_promote_json_flag_prints_grown_corpus_report(tmp_path):
    result, _, _, _ = _promote(tmp_path, "--expected-claims", "c1:diverged", "--json")

    assert result.exit_code == 0
    report = json.loads(result.output.splitlines()[-1])
    assert report["total"] == 1
    assert report["correct"] == 1
    assert report["claim_match_rate"] == 1.0
    assert report["cases"] == 1
