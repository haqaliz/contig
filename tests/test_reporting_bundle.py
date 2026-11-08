"""Tests for portable report bundles."""

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from contig.bundle import SIGNING_KEY_ENV
from contig.cli import app
from contig.reporting.build import (
    build_report,
    check_report,
    check_report_signature,
    write_report,
)
from contig.reporting.bundle import bundle_report
from contig.reporting.models import ReportSpec
from contig.signing import generate_keypair

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"
READINESS = FIX / "readiness.json"


def _sidecar(tmp_path: Path) -> Path:
    html, meta = build_report(
        RUNS, "r1", ReportSpec(max_rows=2),
        variants_path=VARIANTS, readiness_path=READINESS,
    )
    sidecar = tmp_path / "report.json"
    write_report(html, meta, tmp_path / "report.html", sidecar)
    return sidecar


def test_bundle_contains_the_report_sidecar_and_tables(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    sidecar = _sidecar(tmp_path)
    result = bundle_report(sidecar, tmp_path / "bundle")
    out = tmp_path / "bundle"
    assert result["out"] == str(out)
    assert result["signed"] is False
    for name in (
        "report.html",
        "report.json",
        "run_record.json",
        "tables/variants.json",
        "tables/readiness.json",
    ):
        assert (out / name).is_file(), name
    payload = json.loads((out / "report.json").read_text())
    assert payload["html_path"] == "report.html"
    assert {item["path"] for item in payload["inputs"]} == {
        "run_record.json",
        "tables/variants.json",
        "tables/readiness.json",
    }
    assert payload["warnings"]
    html = (out / "report.html").read_text()
    assert "tables/variants.json" in html
    assert str(VARIANTS) not in html


def test_bundled_check_is_current_after_a_move(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    sidecar = _sidecar(tmp_path)
    bundle_report(sidecar, tmp_path / "bundle")
    moved = tmp_path / "moved"
    shutil.move(str(tmp_path / "bundle"), moved)
    results = check_report(moved / "report.json")
    assert results
    assert all(item["status"] == "current" for item in results)


def test_bundle_keeps_rows_beyond_the_html_cap(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    sidecar = _sidecar(tmp_path)
    bundle_report(sidecar, tmp_path / "bundle")
    variants = json.loads((tmp_path / "bundle/tables/variants.json").read_text())
    readiness = json.loads((tmp_path / "bundle/tables/readiness.json").read_text())
    assert len(variants["variants"]) == 3
    assert len(readiness["targets"]) == 3


def test_bundle_can_be_signed(tmp_path, monkeypatch):
    private, public = generate_keypair()
    monkeypatch.setenv(SIGNING_KEY_ENV, private)
    sidecar = _sidecar(tmp_path)
    result = bundle_report(sidecar, tmp_path / "bundle")
    assert result["signed"] is True
    state = check_report_signature(tmp_path / "bundle/report.json")
    assert state["ok"] is True
    assert state["public_key"] == public


def test_report_bundle_command(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    sidecar = _sidecar(tmp_path)
    result = CliRunner().invoke(
        app, ["report-bundle", str(sidecar), "--out", str(tmp_path / "bundle")]
    )
    assert result.exit_code == 0, result.output
    assert "Wrote report bundle" in result.output
    assert (tmp_path / "bundle/report.html").is_file()
