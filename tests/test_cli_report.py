"""CLI smoke tests for `contig report` and `contig report-check`."""

import shutil
from pathlib import Path

from typer.testing import CliRunner

from tests.ansi import plain

from contig.cli import app
from contig.reporting.build import build_report, write_report
from contig.reporting.models import ReportSpec

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
    assert "--variants" in plain(result.output)
    assert "--readiness" in plain(result.output)
    assert "--template" in plain(result.output)


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
    assert "no bundled run" in plain(result.output).lower()


def test_audit_template_omits_variant_evidence(tmp_path):
    out = tmp_path / "audit.html"
    result = _invoke([
        "r1", "--runs-dir", RUNS, "--variants", VARIANTS, "--template", "audit",
        "--out", str(out), "--meta", str(tmp_path / "audit.json"),
    ])
    assert result.exit_code == 0, result.output
    assert "Variant evidence" not in out.read_text()
    assert "Provenance" in out.read_text()


def test_report_diff_command(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    html, meta = build_report(RUNS, "r1", ReportSpec(title="One"), variants_path=VARIANTS)
    write_report(html, meta, one.with_suffix(".html"), one.with_suffix(".json"))
    html, meta = build_report(RUNS, "r1", ReportSpec(title="Two"), variants_path=VARIANTS)
    write_report(html, meta, two.with_suffix(".html"), two.with_suffix(".json"))
    result = CliRunner().invoke(app, ["report-diff", str(one.with_suffix(".json")), str(two.with_suffix(".json"))])
    assert result.exit_code == 0, result.output
    assert "spec.title" in plain(result.output)
    json_result = CliRunner().invoke(app, [
        "report-diff", str(one.with_suffix(".json")), str(two.with_suffix(".json")), "--json",
    ])
    assert json_result.exit_code == 0
    assert '"same": false' in json_result.output
    gate = CliRunner().invoke(app, [
        "report-diff", str(one.with_suffix(".json")), str(two.with_suffix(".json")),
        "--fail-on-diff",
    ])
    assert gate.exit_code == 1


def test_report_check_catches_html_tampering(tmp_path):
    out = tmp_path / "report.html"
    meta = tmp_path / "report.json"
    built = _invoke([
        "r1", "--runs-dir", RUNS, "--variants", VARIANTS,
        "--out", str(out), "--meta", str(meta),
    ])
    assert built.exit_code == 0, built.output
    out.write_text(out.read_text() + "\n<!-- tampered -->\n")
    checked = CliRunner().invoke(app, ["report-check", str(meta)])
    assert checked.exit_code == 1
    assert "stale" in checked.output.lower()
