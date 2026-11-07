"""Tests for canonical panel BED building."""

from pathlib import Path

import pytest

from contig.panels.build import build_from_bed, build_from_genes, canonical_bed

FIX = Path(__file__).parent / "fixtures" / "panels"
GTF = FIX / "genes.gtf"
HGNC = FIX / "hgnc.tsv"
BED = FIX / "panel.bed"


def test_gene_build_prefers_mane_and_converts_to_bed():
    panel = build_from_genes(
        ["BRCA1", "BRCA2"], GTF, name="Hereditary cancer", hgnc_path=HGNC, transcripts="mane"
    )
    lines = panel.bed_text.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("13\t32314999\t32315500\tBRCA2")
    assert panel.meta.genes == ["BRCA1", "BRCA2"]
    assert panel.meta.transcripts == ["ENST1", "ENST3"]
    assert "MANE" in panel.meta.method
    assert panel.meta.checksum


def test_gene_build_all_transcripts_keeps_the_extra_transcript():
    mane = build_from_genes(["BRCA1"], GTF, name="Mane")
    all_tx = build_from_genes(["BRCA1"], GTF, name="All", transcripts="all")
    assert len(all_tx.bed_text.splitlines()) == len(mane.bed_text.splitlines()) + 1
    assert "all protein-coding" in all_tx.meta.method


def test_alias_resolves_to_the_approved_symbol():
    panel = build_from_genes(["RNF53"], GTF, name="Alias", hgnc_path=HGNC)
    assert panel.meta.genes == ["BRCA1"]


def test_unknown_gene_fails():
    with pytest.raises(ValueError, match="unknown HGNC"):
        build_from_genes(["NOTAGENE"], GTF, name="Bad", hgnc_path=HGNC)


def test_bed_build_sorts_dedupes_and_normalizes():
    panel = build_from_bed(BED, "Existing panel")
    lines = panel.bed_text.splitlines()
    assert len(lines) == 2
    assert lines[0] == "17\t50\t100\tA\t\t"
    assert lines[1] == "17\t100\t200\tB\t\t"
    assert panel.meta.source == "bed"


def test_same_inputs_produce_the_same_id_and_checksum():
    one = build_from_genes(["BRCA1"], GTF, name="Stable")
    two = build_from_genes(["BRCA1"], GTF, name="Stable")
    assert one.meta.id == two.meta.id
    assert one.meta.checksum == two.meta.checksum


def test_missing_inputs_are_honest_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_from_bed(tmp_path / "missing.bed", "X")
    with pytest.raises(FileNotFoundError):
        build_from_genes(["BRCA1"], tmp_path / "missing.gtf", name="X")


def test_canonical_bed_dedupes_rows():
    rows = [
        ("1", 10, 20, "B", "", ""),
        ("1", 0, 10, "A", "", ""),
        ("1", 10, 20, "B", "", ""),
    ]
    assert canonical_bed(rows) == "1\t0\t10\tA\t\t\n1\t10\t20\tB\t\t\n"


def test_gene_build_keeps_a_version_label():
    panel = build_from_genes(["BRCA1"], GTF, name="Versioned", version="2")
    assert panel.meta.version == "2"
