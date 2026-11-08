"""Tests for the report's compatibility preflight warnings."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.cli import app
from contig.models import ReferenceIdentity, RunRecord
from contig.reporting.build import build_report, compatibility_warnings
from contig.reporting.models import ReportSpec

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"
READINESS = FIX / "readiness.json"


def _record(**updates) -> RunRecord:
    record = RunRecord.model_validate_json(
        (RUNS / "r1" / "run_record.json").read_text()
    )
    return record.model_copy(update=updates)


def _tables() -> tuple[dict, dict]:
    return (
        json.loads(VARIANTS.read_text()),
        json.loads(READINESS.read_text()),
    )


def test_rnaseq_run_with_dna_tables_warns():
    variants, readiness = _tables()
    warnings = compatibility_warnings(_record(), variants, readiness)
    assert any("run assay is rnaseq" in warning for warning in warnings)
    assert any("DNA-oriented" in warning for warning in warnings)


def test_variant_calling_run_does_not_warn_on_assay():
    variants, readiness = _tables()
    warnings = compatibility_warnings(
        _record(assay="variant_calling"), variants, readiness
    )
    assert not any("DNA-oriented" in warning for warning in warnings)


def test_build_mismatch_warns_and_match_does_not():
    variants, readiness = _tables()
    variants["meta"]["build"] = "GRCh37"
    record = _record(
        assay="variant_calling",
        reference_identity=ReferenceIdentity(mode="igenomes", genome="GRCh38"),
    )
    warnings = compatibility_warnings(record, variants, readiness)
    assert any("variant table is GRCh37" in warning for warning in warnings)
    variants["meta"]["build"] = "GRCh38"
    warnings = compatibility_warnings(record, variants, readiness)
    assert not any("variant table is" in warning for warning in warnings)


def test_gene_mismatch_warns_and_match_does_not():
    variants, readiness = _tables()
    variants["meta"]["filters"]["genes"] = ["GENE1", "GENE3"]
    warnings = compatibility_warnings(
        _record(assay="variant_calling"), variants, readiness
    )
    assert not any("not covered" in warning for warning in warnings)
    variants["meta"]["filters"]["genes"] = ["BRCA1"]
    warnings = compatibility_warnings(
        _record(assay="variant_calling"), variants, readiness
    )
    assert any("BRCA1" in warning for warning in warnings)


def test_report_html_and_sidecar_include_warnings():
    html, meta = build_report(RUNS, "r1", ReportSpec(), variants_path=VARIANTS)
    assert meta.warnings
    assert "Compatibility warnings" in html
    assert meta.warnings[0].replace("&", "&amp;") in html


def test_report_command_prints_warnings(tmp_path):
    result = CliRunner().invoke(app, [
        "report", "r1", "--runs-dir", str(RUNS),
        "--variants", str(VARIANTS),
        "--out", str(tmp_path / "report.html"),
        "--meta", str(tmp_path / "report.json"),
    ])
    assert result.exit_code == 0, result.output
    combined = result.output + getattr(result, "stderr", "")
    assert "Compatibility warning" in combined
