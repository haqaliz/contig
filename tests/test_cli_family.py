"""CLI smoke tests for `contig family`."""

import json
from pathlib import Path

from typer.testing import CliRunner

from tests.ansi import plain

from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "family"
VCF = str(FIX / "trio.vcf")
PED = str(FIX / "trio.ped")


def _invoke(args):
    return CliRunner().invoke(app, ["family", *args])


def test_help_lists_options():
    result = _invoke(["--help"])
    assert result.exit_code == 0
    assert "--vcf" in plain(result.output)
    assert "--ped" in plain(result.output)


def test_writes_a_tsv_and_summary(tmp_path):
    out = tmp_path / "family.tsv"
    result = _invoke(["--vcf", VCF, "--ped", PED, "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text().startswith("family_id\tchild")
    combined = result.output + getattr(result, "stderr", "")
    assert "Research use only" in combined
    assert "de novo" in combined


def test_json_output_contains_meta(tmp_path):
    out = tmp_path / "family.json"
    result = _invoke(["--vcf", VCF, "--ped", PED, "--json", "--out", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    assert payload["meta"]["family_id"] == "FAM1"
    assert len(payload["rows"]) == 8


def test_missing_vcf_exits_nonzero():
    result = _invoke(["--vcf", str(FIX / "missing.vcf"), "--ped", PED])
    assert result.exit_code == 1
    assert "not found" in plain(result.output).lower()
