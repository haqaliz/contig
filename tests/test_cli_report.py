"""CLI smoke tests for `contig report` and `contig report-check`."""

import shutil
from pathlib import Path

from typer.testing import CliRunner

from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = str(FIX / "runs")
VARIANTS = str(FIX / "variants.json")
READINESS = str(FIX / "readiness.json")
SPEC = str(FIX / "spec.json")


def _invoke(args):
    return CliRunner().invoke(app, ["report", *args])


def test_help_lists_the_report_options():
    result = _invoke(["--help"])
    assert result.exit_code == 0
    assert "--variants" in result.output
    assert "--readiness" in result.output
    assert "--template" in result.output


def test_builds_html_and_sidecar(tmp_path):
    out = tmp_path / "report.html"
    meta = tmp_path / "report.json"
    result = _invoke([
        "r1", "--runs-dir", RUNS, "--variants", VARIANTS, "--readiness", READINESS,
        "--spec", SPEC, "--out", str(out), "--meta", str(meta),
    ])
    assert result.exit_code == 0, result.output
    assert "BRCA1 panel review" in out.read_text()
    assert meta.is_file()
    combined = result.output + getattr(result, "stderr", "")
    assert "Research use only" in combined


def test_report_check_is_current_then_stale(tmp_path):
    variants = tmp_path / "variants.json"
    shutil.copyfile(VARIANTS, variants)
    out = tmp_path / "report.html"
    meta = tmp_path / "report.json"
    one = _invoke([
        "r1", "--runs-dir", RUNS, "--variants", str(variants),
        "--out", str(out), "--meta", str(meta),
    ])
    assert one.exit_code == 0, one.output

    current = CliRunner().invoke(app, ["report-check", str(meta)])
    assert current.exit_code == 0, current.output
    assert "current" in current.output.lower()

    variants.write_text(variants.read_text().replace("BRCA1", "BRCA2"))
    stale = CliRunner().invoke(app, ["report-check", str(meta)])
    assert stale.exit_code == 1
    assert "stale" in stale.output.lower()


def test_missing_run_exits_nonzero(tmp_path):
    result = _invoke(["missing", "--runs-dir", RUNS, "--out", str(tmp_path / "x.html"), "--meta", str(tmp_path / "x.json")])
    assert result.exit_code == 1
    assert "no bundled run" in result.output.lower()


def test_audit_template_omits_variant_evidence(tmp_path):
    out = tmp_path / "audit.html"
    result = _invoke([
        "r1", "--runs-dir", RUNS, "--variants", VARIANTS, "--template", "audit",
        "--out", str(out), "--meta", str(tmp_path / "audit.json"),
    ])
    assert result.exit_code == 0, result.output
    assert "Variant evidence" not in out.read_text()
    assert "Provenance" in out.read_text()
