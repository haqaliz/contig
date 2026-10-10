"""Tests for the triage calibration ledger — the pure report builder, the
tolerant loader, and the `contig triage-stats` command (C9 aspect `ledger`).

The report's honesty contract: counts are counts, every bucket carries its
denominator, an absent/empty ledger is "nothing measurable yet", and nothing
here ever claims a calibration curve.
"""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.triage import append_ledger_row, load_triage_ledger, triage_stats_report

runner = CliRunner()


def _row(
    run_id="r1",
    *,
    surface="qc_anomaly",
    mode="shadow",
    confidence=None,
    actual="QC-FAIL: ts_tv",
):
    """A real row shape (the wiring's `append_ledger_row` call sites)."""
    return {
        "run_id": run_id,
        "attempt": 1,
        "surface": surface,
        "mode": mode,
        "confidence": confidence,
        "reason": None,
        "checks": [f"{run_id}:{surface}:ts_tv"],
        "actual": actual,
    }


# --- the pure report builder -------------------------------------------------


def test_report_over_zero_rows_is_empty_but_shaped():
    assert triage_stats_report([]) == {
        "total": 0,
        "by_surface": {},
        "by_mode": {},
        "skipped": 0,
        "skipped_lines": 0,
        "confidence_vs_actual": [],
    }


def test_report_counts_rows_by_surface_and_mode():
    rows = [
        _row("r1", surface="qc_anomaly", mode="shadow"),
        _row("r2", surface="qc_anomaly", mode="active"),
        _row("r3", surface="verify_concordance", mode="active"),
    ]
    report = triage_stats_report(rows)
    assert report["total"] == 3
    assert report["by_surface"] == {"qc_anomaly": 2, "verify_concordance": 1}
    assert report["by_mode"] == {"shadow": 1, "active": 2}


def test_report_counts_only_exact_skipped_decisions():
    rows = [
        _row("r1", surface="verify_concordance", actual="skipped"),
        _row("r2", surface="verify_concordance", actual="unverified"),
        _row("r3", surface="qc_anomaly", actual="QC-FAIL: ts_tv"),
    ]
    report = triage_stats_report(rows)
    assert report["skipped"] == 1
    assert report["total"] == 3


def test_report_skipped_lines_carries_the_loader_tolerance_count():
    assert triage_stats_report([], skipped_lines=2)["skipped_lines"] == 2


def test_confidence_buckets_mean_and_row_counts():
    rows = [
        _row("r1", actual="QC-FAIL: ts_tv", confidence=0.8),
        _row("r2", actual="QC-FAIL: ts_tv", confidence=0.9),
        _row("r3", surface="verify_concordance", actual="skipped", confidence=0.4),
    ]
    report = triage_stats_report(rows)
    assert [bucket["actual"] for bucket in report["confidence_vs_actual"]] == [
        "QC-FAIL: ts_tv",
        "skipped",
    ]
    assert [bucket["rows"] for bucket in report["confidence_vs_actual"]] == [2, 1]
    assert report["confidence_vs_actual"][0]["mean_confidence"] == pytest.approx(0.85)
    assert report["confidence_vs_actual"][1]["mean_confidence"] == pytest.approx(0.4)


def test_rows_without_a_confidence_never_reach_the_cross_tab():
    rows = [
        _row("r1"),
        _row("r2", surface="verify_concordance", actual="skipped"),
    ]
    report = triage_stats_report(rows)
    assert report["total"] == 2
    assert report["confidence_vs_actual"] == []


def test_non_numeric_and_non_finite_confidences_are_excluded_from_the_cross_tab():
    rows = [
        _row("r1", confidence=None),
        _row("r2", confidence="0.5"),  # a string is not a metric
        _row("r3", confidence=True),  # a boolean is not a metric
        _row("r4", confidence=float("nan")),
        _row("r5", confidence=float("inf")),
    ]
    report = triage_stats_report(rows)
    assert report["total"] == 5
    assert report["confidence_vs_actual"] == []


def test_a_non_string_actual_is_excluded_from_the_cross_tab():
    rows = [_row("r1", actual=None, confidence=0.9)]
    report = triage_stats_report(rows)
    assert report["total"] == 1
    assert report["confidence_vs_actual"] == []


def test_non_string_surface_and_mode_do_not_enter_the_count_buckets():
    rows = [
        {"run_id": "r1", "surface": 7, "mode": None, "actual": "skipped"},
        {"run_id": "r2", "surface": "qc_anomaly", "mode": "shadow", "actual": "x"},
    ]
    report = triage_stats_report(rows)
    assert report["total"] == 2
    assert report["by_surface"] == {"qc_anomaly": 1}
    assert report["by_mode"] == {"shadow": 1}


# --- the tolerant loader ------------------------------------------------------


def test_loader_missing_file_is_empty_and_zero_skipped(tmp_path):
    assert load_triage_ledger(tmp_path) == ([], 0)


def test_loader_round_trips_rows_written_by_append_ledger_row(tmp_path):
    rows = [
        _row("r1", surface="qc_anomaly", mode="shadow", confidence=0.71),
        _row("r2", surface="verify_concordance", mode="active", actual="skipped"),
    ]
    for row in rows:
        append_ledger_row(tmp_path, row)
    loaded, skipped = load_triage_ledger(tmp_path)
    assert skipped == 0
    assert loaded == rows


def test_loader_skips_and_counts_malformed_lines(tmp_path):
    (tmp_path / "triage-ledger.jsonl").write_text(
        json.dumps(_row("r1", confidence=0.5)) + "\n"
        "this is not json\n"
        '{"run_id": "truncated",\n'
    )
    loaded, skipped = load_triage_ledger(tmp_path)
    assert skipped == 2
    assert [row["run_id"] for row in loaded] == ["r1"]


def test_loader_skips_and_counts_non_dict_json_lines(tmp_path):
    (tmp_path / "triage-ledger.jsonl").write_text(
        "[1, 2]\n"
        "42\n"
        "\"a string\"\n"
        + json.dumps(_row("r1"))
    )
    loaded, skipped = load_triage_ledger(tmp_path)
    assert skipped == 3
    assert [row["run_id"] for row in loaded] == ["r1"]


def test_loader_skips_and_counts_non_utf8_lines(tmp_path):
    path = tmp_path / "triage-ledger.jsonl"
    path.write_bytes(
        json.dumps(_row("r1")).encode() + b"\n" + b"\xff\xfe\x80 not utf-8\n"
    )
    loaded, skipped = load_triage_ledger(tmp_path)
    assert skipped == 1
    assert [row["run_id"] for row in loaded] == ["r1"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_loader_surfaces_an_existing_but_unreadable_file(tmp_path):
    path = tmp_path / "triage-ledger.jsonl"
    path.write_text(json.dumps(_row("r1")))
    path.chmod(0)
    try:
        with pytest.raises(OSError):
            load_triage_ledger(tmp_path)
    finally:
        path.chmod(0o644)


# --- the CLI: `contig triage-stats` -------------------------------------------


def test_absent_ledger_exits_zero_with_an_honest_note(tmp_path):
    result = runner.invoke(app, ["triage-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "No triage ledger rows yet" in result.output
    assert "%" not in result.output


def test_absent_runs_dir_exits_zero_with_the_honest_note(tmp_path):
    missing = tmp_path / "absent"
    result = runner.invoke(app, ["triage-stats", "--runs-dir", str(missing)])
    assert result.exit_code == 0
    assert "No triage ledger rows yet" in result.output


def test_empty_ledger_exits_zero_with_the_honest_note(tmp_path):
    (tmp_path / "triage-ledger.jsonl").write_text("")
    result = runner.invoke(app, ["triage-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "No triage ledger rows yet" in result.output
    assert "%" not in result.output


def test_an_entirely_malformed_ledger_is_still_nothing_measurable(tmp_path):
    (tmp_path / "triage-ledger.jsonl").write_text("garbage\nmore garbage\n")
    result = runner.invoke(app, ["triage-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "No triage ledger rows yet" in result.output
    assert "2 line(s) skipped as malformed" in result.output


def test_the_text_report_over_a_real_ledger(tmp_path):
    append_ledger_row(
        tmp_path,
        _row("r1", surface="qc_anomaly", mode="shadow", confidence=0.85),
    )
    append_ledger_row(
        tmp_path,
        _row(
            "r2",
            surface="verify_concordance",
            mode="active",
            confidence=0.4,
            actual="skipped",
        ),
    )
    result = runner.invoke(app, ["triage-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "Triage stats: 2 row(s) in" in result.output
    assert "by surface: qc_anomaly=1, verify_concordance=1" in result.output
    assert "by mode: active=1, shadow=1" in result.output
    assert "skipped (active-mode): 1" in result.output
    assert "QC-FAIL: ts_tv: 1 row(s), mean confidence 0.8500" in result.output
    assert "skipped: 1 row(s), mean confidence 0.4000" in result.output


def test_the_cross_tab_never_claims_a_calibration_curve(tmp_path):
    append_ledger_row(tmp_path, _row("r1", confidence=0.85))
    result = runner.invoke(app, ["triage-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "not a calibration curve" in result.output


def test_rows_without_confidence_get_an_honest_no_cross_tab_line(tmp_path):
    append_ledger_row(tmp_path, _row("r1"))
    result = runner.invoke(app, ["triage-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "no row carries a confidence yet" in result.output


def test_skipped_malformed_lines_are_surfaced_in_the_text_report(tmp_path):
    append_ledger_row(tmp_path, _row("r1", confidence=0.5))
    with open(tmp_path / "triage-ledger.jsonl", "a") as fh:
        fh.write("not json\n")
    result = runner.invoke(app, ["triage-stats", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "1 line(s) skipped as malformed/non-UTF-8" in result.output


def test_json_mode_is_a_stable_report_dict_even_on_an_absent_ledger(tmp_path):
    result = runner.invoke(
        app, ["triage-stats", "--runs-dir", str(tmp_path), "--json"]
    )
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert set(report) == {
        "total",
        "by_surface",
        "by_mode",
        "skipped",
        "skipped_lines",
        "confidence_vs_actual",
    }
    assert report == {
        "total": 0,
        "by_surface": {},
        "by_mode": {},
        "skipped": 0,
        "skipped_lines": 0,
        "confidence_vs_actual": [],
    }


def test_json_mode_reports_counts_and_the_loader_tolerance(tmp_path):
    append_ledger_row(tmp_path, _row("r1", confidence=0.85))
    with open(tmp_path / "triage-ledger.jsonl", "a") as fh:
        fh.write("garbage\n")
    result = runner.invoke(
        app, ["triage-stats", "--runs-dir", str(tmp_path), "--json"]
    )
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["total"] == 1
    assert report["by_surface"] == {"qc_anomaly": 1}
    assert report["by_mode"] == {"shadow": 1}
    assert report["skipped"] == 0
    assert report["skipped_lines"] == 1
    assert report["confidence_vs_actual"] == [
        {"actual": "QC-FAIL: ts_tv", "rows": 1, "mean_confidence": 0.85}
    ]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_an_unreadable_ledger_exits_nonzero_with_an_honest_error(tmp_path):
    path = tmp_path / "triage-ledger.jsonl"
    path.write_text(json.dumps(_row("r1")))
    path.chmod(0)
    try:
        result = runner.invoke(app, ["triage-stats", "--runs-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "Cannot read triage ledger" in result.output
    finally:
        path.chmod(0o644)