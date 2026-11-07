"""Tests for the panel registry."""

from pathlib import Path

import pytest

from contig.panels.build import build_from_genes, list_panels, load_panel, write_panel

FIX = Path(__file__).parent / "fixtures" / "panels"
GTF = FIX / "genes.gtf"
HGNC = FIX / "hgnc.tsv"


def test_write_list_and_load_round_trip(tmp_path):
    panel = build_from_genes(["BRCA1", "BRCA2"], GTF, name="Hereditary", hgnc_path=HGNC)
    bed_path, meta_path = write_panel(panel, tmp_path)
    assert bed_path.is_file() and meta_path.is_file()
    assert [meta.id for meta in list_panels(tmp_path)] == [panel.meta.id]
    loaded = load_panel(tmp_path, panel.meta.id)
    assert loaded.meta == panel.meta
    assert loaded.bed_text == panel.bed_text


def test_tampered_bed_is_refused(tmp_path):
    panel = build_from_genes(["BRCA1"], GTF, name="Stable")
    bed_path, _ = write_panel(panel, tmp_path)
    bed_path.write_text(bed_path.read_text() + "1\t0\t1\tX\t\t\n")
    with pytest.raises(ValueError, match="checksum"):
        load_panel(tmp_path, panel.meta.id)


def test_missing_panel_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_panel(tmp_path, "missing")


def test_empty_registry_lists_nothing(tmp_path):
    assert list_panels(tmp_path) == []
