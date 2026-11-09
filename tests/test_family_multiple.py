"""Tests for multi-family PED support."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.cli import app
from contig.family.ped import load_families
from contig.family.table import build_family_table

FIX = Path(__file__).parent / "fixtures" / "family"
VCF = FIX / "multifamily.vcf"
PED = FIX / "multifamily.ped"


def test_loads_two_families():
    families = load_families(PED)
    assert [family.family_id for family in families] == ["FAM1", "FAM2"]
    assert [sample for family in families for sample in family.samples] == [
        "C1", "F1", "M1", "C2", "F2", "M2"
    ]


def test_builds_rows_for_each_family():
    table = build_family_table(VCF, PED)
    assert len(table.rows) == 6
    assert {row.family_id for row in table.rows} == {"FAM1", "FAM2"}
    assert table.meta.family_id == "FAM1"
    assert table.meta.family_ids == ["FAM1", "FAM2"]
    assert table.meta.summary["families"] == 2
    assert set(table.meta.summary["per_family"]) == {"FAM1", "FAM2"}
    assert table.meta.summary["per_family"]["FAM1"]["de_novo_candidates"] == 1
    assert table.meta.summary["per_family"]["FAM2"]["de_novo_candidates"] == 0


def test_concordance_is_per_family():
    table = build_family_table(VCF, PED)
    assert len(table.meta.concordance) == 6
    assert {item["family_id"] for item in table.meta.concordance} == {"FAM1", "FAM2"}


def test_cli_multifamily_json(tmp_path):
    out = tmp_path / "family.json"
    result = CliRunner().invoke(app, [
        "family", "--vcf", str(VCF), "--ped", str(PED), "--json", "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    assert payload["meta"]["family_ids"] == ["FAM1", "FAM2"]
    assert len(payload["rows"]) == 6
    assert "2 family(ies)" in (result.output + getattr(result, "stderr", ""))
