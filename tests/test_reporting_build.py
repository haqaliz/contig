"""Tests for report build, sidecar, and staleness check."""

import hashlib
import shutil
from pathlib import Path

import pytest

from contig.reporting.build import build_report, check_report, write_report
from contig.reporting.models import ReportSpec
from contig.workspace import RunNotFoundError

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"
READINESS = FIX / "readiness.json"


def test_build_records_inputs_and_html_hash():
    spec = ReportSpec.model_validate_json((FIX / "spec.json").read_text())
    html, meta = build_report(
        RUNS, "r1", spec, variants_path=VARIANTS, readiness_path=READINESS
    )
    assert {item.kind for item in meta.inputs} == {"run_record", "variants", "readiness"}
    assert meta.html_sha256 == hashlib.sha256(html.encode()).hexdigest()
    assert len(meta.inputs[0].sha256) == 64


def test_write_and_check_current(tmp_path):
    html, meta = build_report(RUNS, "r1", ReportSpec(), variants_path=VARIANTS)
    out = tmp_path / "report.html"
    sidecar = tmp_path / "report.json"
    write_report(html, meta, out, sidecar)
    assert out.read_text() == html
    results = check_report(sidecar)
    assert all(item["status"] == "current" for item in results)


def test_check_reports_stale_after_an_input_changes(tmp_path):
    variants = tmp_path / "variants.json"
    shutil.copyfile(VARIANTS, variants)
    html, meta = build_report(RUNS, "r1", ReportSpec(), variants_path=variants)
    sidecar = tmp_path / "report.json"
    write_report(html, meta, tmp_path / "report.html", sidecar)

    variants.write_text(variants.read_text().replace("BRCA1", "BRCA2"))
    results = check_report(sidecar)
    stale = [item for item in results if item["status"] != "current"]
    assert len(stale) == 1
    assert stale[0]["kind"] == "variants"
    assert stale[0]["status"] == "stale"


def test_missing_run_is_a_domain_error(tmp_path):
    with pytest.raises(RunNotFoundError):
        build_report(tmp_path, "missing")


def test_missing_variants_file_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_report(RUNS, "r1", variants_path=tmp_path / "missing.json")


def test_missing_sidecar_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        check_report(tmp_path / "missing.json")


def test_check_verifies_the_html_hash(tmp_path):
    html, meta = build_report(RUNS, "r1", ReportSpec(), variants_path=VARIANTS)
    out = tmp_path / "report.html"
    sidecar = tmp_path / "report.json"
    write_report(html, meta, out, sidecar)
    out.write_text(out.read_text() + "\n<!-- tampered -->\n")
    results = check_report(sidecar)
    html_result = next(item for item in results if item["kind"] == "html")
    assert html_result["status"] == "stale"


def test_check_works_from_another_directory(tmp_path, monkeypatch):
    html, meta = build_report(RUNS, "r1", ReportSpec(), variants_path=VARIANTS)
    out = tmp_path / "report.html"
    sidecar = tmp_path / "report.json"
    write_report(html, meta, out, sidecar)
    monkeypatch.chdir(tmp_path.parent)
    results = check_report(sidecar)
    assert all(item["status"] == "current" for item in results)


def test_write_report_creates_parent_directories(tmp_path):
    html, meta = build_report(RUNS, "r1", ReportSpec())
    out = tmp_path / "nested" / "report.html"
    sidecar = tmp_path / "nested" / "report.json"
    write_report(html, meta, out, sidecar)
    assert out.is_file() and sidecar.is_file()
