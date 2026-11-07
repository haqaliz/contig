"""Tests for the family table builder and renderers."""

import json
from pathlib import Path

import pytest

from contig.family.table import COLUMNS, build_family_table, render_json, render_tsv

FIX = Path(__file__).parent / "fixtures" / "family"
VCF = FIX / "trio.vcf"
PED = FIX / "trio.ped"


def _table():
    return build_family_table(VCF, PED)


def test_builds_one_row_per_child_and_alt():
    table = _table()
    assert len(table.rows) == 8
    assert table.meta.family_id == "FAM1"
    assert table.meta.samples == ["CHILD", "FATHER", "MOTHER"]
    assert {source.kind for source in table.meta.sources} == {"vcf", "ped"}


def test_tsv_has_the_documented_header_and_states():
    text = render_tsv(_table())
    lines = text.splitlines()
    assert lines[0].split("\t") == COLUMNS
    assert "paternal" in text
    assert "maternal" in text
    assert "de_novo" in text
    assert "maternal" in text


def test_json_meta_has_summary_and_concordance():
    payload = json.loads(render_json(_table()))
    assert payload["meta"]["summary"]["de_novo_candidates"] == 1
    assert payload["meta"]["summary"]["mendelian_inconsistent"] == 1
    assert len(payload["meta"]["concordance"]) == 3
    assert len(payload["rows"]) == 8
    assert payload["meta"]["contig_version"]


def test_same_inputs_produce_identical_tsv():
    assert render_tsv(_table()) == render_tsv(_table())


def test_missing_inputs_are_honest_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_family_table(tmp_path / "missing.vcf", PED)
    with pytest.raises(FileNotFoundError):
        build_family_table(VCF, tmp_path / "missing.ped")
