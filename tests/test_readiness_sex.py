"""Tests for the readiness VCF sex check and sample-swap caveat."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.readiness.table import build_readiness
from tests.ansi import plain

FIX = Path(__file__).parent / "fixtures" / "readiness"
DEPTH = FIX / "depth.tsv"
PANEL = FIX / "panel.bed"

HEADER = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chrX,length=156040895>\n"
    "##contig=<ID=chrY,length=57227415>\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
)


def _write_vcf(path: Path, rows: list[tuple[str, int, str, str, str]]) -> Path:
    body = "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\tGT\t{gt}\n"
        for chrom, pos, ref, alt, gt in rows
    )
    path.write_text(HEADER + body)
    return path


def _female(tmp_path: Path) -> Path:
    rows = [("chrX", 5_000_000 + i, "A", "G", "0/1") for i in range(25)]
    return _write_vcf(tmp_path / "female.vcf", rows)


def _male(tmp_path: Path) -> Path:
    rows = [("chrX", 5_000_000 + i, "A", "G", "0/0") for i in range(25)]
    rows += [("chrY", 10_000_000 + i, "A", "G", "0/1") for i in range(6)]
    return _write_vcf(tmp_path / "male.vcf", rows)


def test_male_vcf_with_female_expected_flags_possible_swap(tmp_path):
    table = build_readiness(
        DEPTH, bed=PANEL, sex_vcf=_male(tmp_path), expected_sex="female"
    )
    assert table.meta.sample_qc is not None
    assert table.meta.sample_qc.inferred_sex == "XY"
    assert table.meta.sample_qc.expected_sex == "XX"
    assert table.meta.sample_qc.possible_swap is True
    assert table.meta.sample_qc.sex_concordance is False
    assert any(source.kind == "sex_vcf" for source in table.meta.sources)
    genes = {gene.gene: gene for gene in table.genes}
    assert genes["GENE4"].readiness == "caution"
    assert any("possible sample swap" in caveat for caveat in genes["GENE4"].caveats)
    assert any("possible sample swap" in note for note in table.meta.notes)


def test_male_vcf_with_male_expected_is_concordant(tmp_path):
    table = build_readiness(
        DEPTH, bed=PANEL, sex_vcf=_male(tmp_path), expected_sex="male"
    )
    assert table.meta.sample_qc.inferred_sex == "XY"
    assert table.meta.sample_qc.expected_sex == "XY"
    assert table.meta.sample_qc.possible_swap is False
    assert table.meta.sample_qc.sex_concordance is True
    genes = {gene.gene: gene for gene in table.genes}
    assert genes["GENE4"].readiness == "ready"


def test_female_vcf_with_female_expected_is_concordant(tmp_path):
    table = build_readiness(
        DEPTH, bed=PANEL, sex_vcf=_female(tmp_path), expected_sex="XX"
    )
    assert table.meta.sample_qc.inferred_sex == "XX"
    assert table.meta.sample_qc.possible_swap is False


def test_expected_sex_without_vcf_is_refused():
    with pytest.raises(ValueError, match="requires --sex-vcf"):
        build_readiness(DEPTH, bed=PANEL, expected_sex="XX")


def test_invalid_expected_sex_is_refused(tmp_path):
    with pytest.raises(ValueError, match="expected_sex"):
        build_readiness(
            DEPTH, bed=PANEL, sex_vcf=_male(tmp_path), expected_sex="unknown"
        )


def test_indeterminate_sex_does_not_flag_a_swap(tmp_path):
    vcf = _write_vcf(
        tmp_path / "few.vcf",
        [("chrX", 5_000_000 + i, "A", "G", "0/1") for i in range(5)],
    )
    table = build_readiness(DEPTH, bed=PANEL, sex_vcf=vcf, expected_sex="XX")
    assert table.meta.sample_qc.inferred_sex == "indeterminate"
    assert table.meta.sample_qc.possible_swap is False
    assert "inconclusive" in table.meta.sample_qc.note


def test_cli_json_includes_sample_qc(tmp_path):
    out = tmp_path / "readiness.json"
    result = CliRunner().invoke(app, [
        "readiness", "--depth", str(DEPTH), "--bed", str(PANEL),
        "--sex-vcf", str(_male(tmp_path)), "--expected-sex", "XX",
        "--json", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    assert payload["meta"]["sample_qc"]["inferred_sex"] == "XY"
    assert payload["meta"]["sample_qc"]["possible_swap"] is True
    assert any("possible sample swap" in note for note in payload["meta"]["notes"])


def test_help_lists_sex_options():
    result = CliRunner().invoke(app, ["readiness", "--help"])
    assert result.exit_code == 0
    assert "--sex-vcf" in plain(result.output)
    assert "--expected-sex" in plain(result.output)
