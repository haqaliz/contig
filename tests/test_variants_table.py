"""Tests for the table builder and renderers."""

import json
from pathlib import Path

import pytest

from contig.variants.models import FilterSpec
from contig.variants.table import COLUMNS, build_table, render_json, render_tsv, write_table

FIX = Path(__file__).parent / "fixtures" / "variants"
SAMPLE = FIX / "sample.vcf"
CLINVAR = FIX / "clinvar.vcf"
IRANOME = FIX / "iranome.tsv"
FREQ = FIX / "frequencies.tsv"


def _table(**kwargs):
    defaults = dict(
        clinvar=CLINVAR,
        iranome=IRANOME,
        frequencies=FREQ,
        build="GRCh37",
        spec=FilterSpec(),
    )
    defaults.update(kwargs)
    return build_table(SAMPLE, **defaults)


def test_table_joins_all_sources_and_keeps_every_alt():
    table = _table()
    assert len(table.rows) == 7
    kinds = {source.kind for source in table.meta.sources}
    assert kinds == {"calls", "clinvar", "iranome", "frequencies"}
    assert all(source.sha256 for source in table.meta.sources)


def test_tsv_has_the_documented_header_and_explicit_gaps():
    text = render_tsv(_table())
    lines = text.splitlines()
    assert lines[0].split("\t") == COLUMNS
    brca1 = next(line for line in lines if "BRCA1" in line)
    assert "Pathogenic" in brca1
    assert "not in ClinVar" in text
    assert "unannotated" in text


def test_json_meta_and_variants_are_machine_readable():
    payload = json.loads(render_json(_table()))
    assert payload["meta"]["build"] == "GRCh37"
    assert payload["meta"]["filters"]["genes"] == []
    assert payload["meta"]["generated_at"]
    assert payload["meta"]["contig_version"]
    assert len(payload["variants"]) == 7
    assert "pathogenic" not in payload["variants"][0]
    assert "diagnosis" not in payload["variants"][0]


def test_spec_filters_the_table():
    table = _table(spec=FilterSpec(genes=["BRCA1"]))
    assert len(table.rows) == 1
    assert table.rows[0].gene == "BRCA1"


def test_iranome_is_skipped_on_a_grch38_build_with_a_note():
    table = _table(build="GRCh38")
    iranome = next(source for source in table.meta.sources if source.kind == "iranome")
    assert "skipped" in iranome.note
    assert all(row.iranome_af is None for row in table.rows)


def test_without_a_clinvar_source_the_column_is_blank_not_benign():
    table = _table(clinvar=None)
    text = render_tsv(table)
    assert "not in ClinVar" not in text
    assert "Benign" not in text


def test_write_table_writes_tsv_and_json(tmp_path):
    table = _table()
    tsv = tmp_path / "table.tsv"
    write_table(table, tsv)
    assert tsv.read_text().startswith("chrom\tpos")
    as_json = tmp_path / "table.json"
    write_table(table, as_json, as_json=True)
    assert json.loads(as_json.read_text())["meta"]["build"] == "GRCh37"


def test_missing_vcf_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_table(tmp_path / "missing.vcf")
