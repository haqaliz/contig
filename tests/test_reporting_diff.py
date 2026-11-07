"""Tests for report-sidecar diffing."""

from pathlib import Path

import pytest

from contig.reporting.build import build_report, write_report
from contig.reporting.diff import diff_reports, render_diff
from contig.reporting.models import ReportSpec

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"


def _write(tmp_path, name, spec, variants=VARIANTS):
    html, meta = build_report(RUNS, "r1", spec, variants_path=variants)
    out = tmp_path / f"{name}.html"
    sidecar = tmp_path / f"{name}.json"
    write_report(html, meta, out, sidecar)
    return sidecar


def test_identical_sidecars_have_no_differences(tmp_path):
    a = _write(tmp_path, "a", ReportSpec(title="Same"))
    b = _write(tmp_path, "b", ReportSpec(title="Same"))
    result = diff_reports(a, b)
    assert result["same"] is True
    assert result["changes"] == []
    assert render_diff(result) == "No differences.\n"


def test_spec_changes_are_reported(tmp_path):
    a = _write(tmp_path, "a", ReportSpec(title="A"))
    b = _write(tmp_path, "b", ReportSpec(title="B"))
    result = diff_reports(a, b)
    assert result["same"] is False
    fields = {change["field"] for change in result["changes"]}
    assert "spec.title" in fields


def test_missing_sidecar_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        diff_reports(tmp_path / "a.json", tmp_path / "missing.json")
