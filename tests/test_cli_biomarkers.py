"""CLI smoke tests for `contig biomarkers`."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "biomarkers"
VCF = str(FIX / "variants.vcf")
BED = str(FIX / "callable.bed")


def _invoke(args):
    return CliRunner().invoke(app, ["biomarkers", *args])


def test_help_lists_options():
    result = _invoke(["--help"])
    assert result.exit_code == 0
    assert "--vcf" in result.output
    assert "--callable-bed" in result.output
    assert "--reported-tmb" in result.output


def test_writes_tsv_and_summary(tmp_path):
    out = tmp_path / "biomarkers.tsv"
    result = _invoke(["--vcf", VCF, "--callable-bed", BED, "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text().startswith("biomarker\tvalue")
    combined = result.output + getattr(result, "stderr", "")
    assert "TMB: 5.00" in combined
    assert "not_verified" in combined


def test_json_output(tmp_path):
    out = tmp_path / "biomarkers.json"
    result = _invoke(["--vcf", VCF, "--callable-bed", BED, "--json", "--out", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    assert len(payload["biomarkers"]) == 4
    assert payload["meta"]["definition"]


def test_reported_tmb_match(tmp_path):
    out = tmp_path / "biomarkers.tsv"
    result = _invoke(["--vcf", VCF, "--callable-bed", BED, "--reported-tmb", "5.5", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "match" in out.read_text()


def test_missing_vcf_exits_nonzero():
    result = _invoke(["--vcf", str(FIX / "missing.vcf"), "--callable-bed", BED])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()
