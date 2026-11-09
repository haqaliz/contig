"""Tests for carrier and couple shared-carrier views."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.family.carriers import (
    build_carrier_report,
    load_panel_genes,
    render_json,
    render_tsv,
)
from tests.ansi import plain

FIX = Path(__file__).parent / "fixtures" / "family"
VCF = FIX / "multifamily.vcf"
PED = FIX / "multifamily.ped"


def _report(**kwargs):
    return build_carrier_report(VCF, PED, **kwargs)


def test_person_and_couple_views():
    report = _report()
    person = [row for row in report.rows if row.view == "person"]
    couple = [row for row in report.rows if row.view == "couple"]
    assert len(person) == 13
    assert len(couple) == 3
    assert report.meta.summary["couples"] == 2
    assert report.meta.summary["child_homozygous_rows"] == 2
    shared = next(
        row for row in couple
        if row.family_id == "FAM1" and row.key.pos == 200
    )
    assert shared.status == "both_carriers"
    assert shared.child_status == "homozygous_alt"
    assert shared.children == "C1"


def test_gene_filter_keeps_only_panel_variants():
    report = _report(genes={"GENE1"})
    assert report.meta.panel_genes == ["GENE1"]
    assert {row.gene for row in report.rows} == {"GENE1"}
    assert report.meta.summary["couple_carrier_rows"] == 1
    assert report.meta.summary["panel_skipped"] == 2


def test_panel_bed_genes(tmp_path):
    panel = tmp_path / "panel.bed"
    panel.write_text("1\t0\t100\tGENE2\n")
    report = _report(panel_path=panel)
    assert report.meta.panel_genes == ["GENE2"]
    assert {row.gene for row in report.rows} == {"GENE2"}
    assert report.meta.summary["couple_carrier_rows"] == 1


def test_panel_without_gene_column_is_refused(tmp_path):
    panel = tmp_path / "panel.bed"
    panel.write_text("1\t0\t100\n")
    with pytest.raises(ValueError, match="gene names"):
        load_panel_genes(panel)


def test_sex_chrom_variants_are_skipped(tmp_path):
    vcf = tmp_path / "x.vcf"
    vcf.write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tC1\tF1\tM1\tC2\tF2\tM2\n"
        "X\t100\t.\tA\tG\t.\t.\t.\tGT\t0/1\t0/0\t0/1\t0/0\t0/0\t0/0\n"
    )
    report = build_carrier_report(vcf, PED)
    assert report.rows == []
    assert report.meta.summary["sex_chrom_skipped"] == 1
    assert any("X/Y/MT" in note for note in report.meta.notes)


def test_renderers_and_cli_json(tmp_path):
    report = _report(genes={"GENE1"})
    assert render_tsv(report).startswith("view\tfamily_id")
    out = tmp_path / "carriers.json"
    result = CliRunner().invoke(app, [
        "carriers", "--vcf", str(VCF), "--ped", str(PED),
        "--genes", "GENE1", "--json", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    assert payload["meta"]["panel_genes"] == ["GENE1"]
    assert payload["meta"]["summary"]["couple_carrier_rows"] == 1
    assert sum(1 for row in payload["rows"] if row["view"] == "couple") == 1


def test_cli_help_lists_options():
    result = CliRunner().invoke(app, ["carriers", "--help"])
    assert result.exit_code == 0
    assert "--genes" in plain(result.output)
    assert "--panel" in plain(result.output)


def test_missing_child_genotype_is_unknown_not_not_carried(tmp_path):
    vcf = tmp_path / "missing-child.vcf"
    vcf.write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tC1\tF1\tM1\tC2\tF2\tM2\n"
        "1\t200\t.\tC\tT\t.\t.\t.\tGT\t.\t0/1\t0/1\t0/1\t0/0\t0/1\n"
    )
    report = build_carrier_report(vcf, PED)
    couple = next(row for row in report.rows if row.view == "couple")
    assert couple.child_status == "unknown"
