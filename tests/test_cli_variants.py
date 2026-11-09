"""CLI smoke tests for `contig variants`."""

import json
from pathlib import Path

from typer.testing import CliRunner

from tests.ansi import plain

from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "variants"
SAMPLE = str(FIX / "sample.vcf")
CLINVAR = str(FIX / "clinvar.vcf")
IRANOME = str(FIX / "iranome.tsv")
FREQ = str(FIX / "frequencies.tsv")


def _invoke(args):
    return CliRunner().invoke(app, ["variants", *args])


def test_help_lists_the_workbench_options():
    result = _invoke(["--help"])
    assert result.exit_code == 0
    assert "--clinvar" in plain(result.output)
    assert "--pass-only" in plain(result.output)
    assert "--save-spec" in plain(result.output)
    assert "--max-records" in plain(result.output)


def test_writes_a_tsv_and_prints_the_research_use_notice(tmp_path):
    out = tmp_path / "table.tsv"
    result = _invoke([
        SAMPLE, "--clinvar", CLINVAR, "--frequencies", FREQ,
        "--build", "GRCh38", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert out.read_text().startswith("chrom\tpos")
    combined = result.output + getattr(result, "stderr", "")
    assert "Research use only" in combined


def test_json_output_contains_meta(tmp_path):
    out = tmp_path / "table.json"
    result = _invoke([
        SAMPLE, "--clinvar", CLINVAR, "--frequencies", FREQ,
        "--build", "GRCh38", "--json", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    assert payload["meta"]["build"] == "GRCh38"
    assert len(payload["variants"]) == 7


def test_saved_spec_replays_the_same_rows(tmp_path):
    first = tmp_path / "first.tsv"
    spec = tmp_path / "spec.json"
    second = tmp_path / "second.tsv"
    base = [SAMPLE, "--clinvar", CLINVAR, "--frequencies", FREQ, "--build", "GRCh38"]
    one = _invoke([*base, "--gene", "BRCA1", "--save-spec", str(spec), "--out", str(first)])
    assert one.exit_code == 0, one.output
    two = _invoke([*base, "--spec", str(spec), "--out", str(second)])
    assert two.exit_code == 0, two.output
    assert first.read_text() == second.read_text()


def test_missing_vcf_exits_nonzero():
    result = _invoke([str(FIX / "missing.vcf")])
    assert result.exit_code == 1
    assert "not found" in plain(result.output).lower()


def test_wgs_cap_requires_a_region_or_gene():
    capped = _invoke([SAMPLE, "--max-records", "1"])
    assert capped.exit_code == 1
    assert "--region" in capped.output
    bounded = _invoke([
        SAMPLE, "--max-records", "1", "--region", "17:43000000-43100000",
    ])
    assert bounded.exit_code == 0, bounded.output
    assert bounded.output.count("BRCA1") >= 1


def test_build_mismatch_records_the_iranome_skip(tmp_path):
    out = tmp_path / "table.json"
    result = _invoke([
        SAMPLE, "--clinvar", CLINVAR, "--iranome", IRANOME,
        "--build", "GRCh38", "--json", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    iranome = next(source for source in payload["meta"]["sources"] if source["kind"] == "iranome")
    assert "skipped" in iranome["note"]
