"""CLI tests for `contig verify-case-promote` (C6 fold-in, aspect 3: PRD R5).

The human-confirmation channel: a reviewer confirms or corrects a pending
verification case's `expected_verdict` and the case moves from the pending
file into the golden corpus (`source` pending: -> confirmed:), with an
auto-snapshot of the grown golden corpus appended to the verify history.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from contig.cli import app
from contig.models import VerificationCase, VerifySnapshot
from contig.snapshot_history import load_jsonl
from contig.verify_corpus import append_verify_case, load_verify_cases

runner = CliRunner()

RUN_ID = "run-7"


def _pending_case(expected_verdict: str | None = None) -> VerificationCase:
    return VerificationCase(
        case_id=f"{RUN_ID}-verify",
        description="captured from run run-7 (nf-core/rnaseq): verdict fail over "
        "captured verification inputs (families: multiqc)",
        source=f"pending:{RUN_ID}",
        assay="rnaseq",
        inputs={"multiqc": {"S1": {"percent_assigned": 20.0}}},
        expected_verdict=expected_verdict,  # type: ignore[arg-type]
    )


def _seed_pending(tmp_path) -> object:
    pending_path = tmp_path / "pending_verify_corpus.jsonl"
    append_verify_case(_pending_case(), pending_path)
    return pending_path


def _promote(tmp_path, *extra_args):
    pending_path = _seed_pending(tmp_path)
    golden_path = tmp_path / "golden.jsonl"
    history_path = tmp_path / "verify_history.jsonl"
    args = [
        "verify-case-promote", f"{RUN_ID}-verify",
        "--pending", str(pending_path),
        "--golden", str(golden_path),
        "--history-file", str(history_path),
        *extra_args,
    ]
    result = runner.invoke(app, args)
    return result, pending_path, golden_path, history_path


# --- round-trip with a corrected verdict --------------------------------------


def test_promote_with_corrected_verdict_round_trips(tmp_path):
    result, pending_path, golden_path, history_path = _promote(
        tmp_path, "--expected-verdict", "warn"
    )

    assert result.exit_code == 0
    assert f"{RUN_ID}-verify" in result.output

    golden = load_verify_cases(golden_path)
    assert len(golden) == 1
    assert golden[0].source == f"confirmed:{RUN_ID}"
    assert golden[0].expected_verdict == "warn"
    assert golden[0].inputs["multiqc"]["S1"]["percent_assigned"] == 20.0

    pending = load_verify_cases(pending_path)
    assert pending == []  # removed from pending


# --- label-less confirmation ---------------------------------------------------


def test_promote_without_verdict_confirms_without_label(tmp_path):
    result, pending_path, golden_path, _ = _promote(tmp_path)

    assert result.exit_code == 0
    golden = load_verify_cases(golden_path)
    assert len(golden) == 1
    assert golden[0].source == f"confirmed:{RUN_ID}"
    assert golden[0].expected_verdict is None  # label-less confirmation is legal


# --- unknown id ----------------------------------------------------------------


def test_promote_unknown_id_exits_1_and_leaves_pending(tmp_path):
    pending_path = _seed_pending(tmp_path)
    golden_path = tmp_path / "golden.jsonl"
    before = pending_path.read_text()

    result = runner.invoke(
        app,
        ["verify-case-promote", "no-such-case",
         "--pending", str(pending_path), "--golden", str(golden_path)],
    )

    assert result.exit_code == 1
    assert "no-such-case" in result.output
    assert pending_path.read_text() == before  # pending untouched
    assert not golden_path.exists()


# --- dedupe ---------------------------------------------------------------------


def test_promote_duplicate_in_golden_exits_1(tmp_path):
    golden_path = tmp_path / "golden.jsonl"
    append_verify_case(_pending_case(expected_verdict="fail"), golden_path)

    result, pending_path, _, _ = _promote(tmp_path)

    assert result.exit_code == 1
    assert "already in the golden corpus" in result.output
    assert len(load_verify_cases(golden_path)) == 1  # no double append


# --- invalid verdict is rejected before any write ------------------------------


def test_promote_invalid_verdict_exits_1_before_any_write(tmp_path):
    pending_path = _seed_pending(tmp_path)
    golden_path = tmp_path / "golden.jsonl"
    history_path = tmp_path / "verify_history.jsonl"
    before = pending_path.read_text()

    result = runner.invoke(
        app,
        ["verify-case-promote", f"{RUN_ID}-verify",
         "--expected-verdict", "maybe",
         "--pending", str(pending_path),
         "--golden", str(golden_path),
         "--history-file", str(history_path)],
    )

    assert result.exit_code == 1
    assert "maybe" in result.output
    assert pending_path.read_text() == before  # nothing written
    assert not golden_path.exists()
    assert not history_path.exists()


# --- auto-snapshot ---------------------------------------------------------------


def test_promote_auto_snapshots_the_grown_golden(tmp_path):
    result, _, golden_path, history_path = _promote(tmp_path, "--expected-verdict", "fail")

    assert result.exit_code == 0
    snaps = load_jsonl(VerifySnapshot, history_path)
    assert len(snaps) == 1
    assert snaps[0].case_count == len(load_verify_cases(golden_path)) == 1
    # The promoted case scores 1/1: the captured multiqc family re-derives fail
    # from percent_assigned 20.0 (fail_below 40), matching the confirmed label.
    assert snaps[0].verdict_match_rate == 1.0


def test_promote_json_output_is_one_snapshot_line(tmp_path):
    _, pending_path, golden_path, history_path = _promote(tmp_path, "--expected-verdict", "fail")

    for line in history_path.read_text().splitlines():
        obj = json.loads(line)
        assert obj["case_count"] == 1
    assert pending_path.exists()  # rewritten (emptied), not deleted
