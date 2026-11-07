"""Tests for BED and GTF target readers."""

from pathlib import Path

import pytest

from contig.readiness.targets import load_bed_targets, load_gtf_targets

FIX = Path(__file__).parent / "fixtures" / "readiness"
PANEL = FIX / "panel.bed"
GTF = FIX / "genes.gtf"


def test_bed4_uses_the_name_and_keeps_half_open_coordinates():
    targets = load_bed_targets(PANEL)
    assert len(targets) == 4
    gene1 = targets[0]
    assert gene1.name == "GENE1"
    assert (gene1.chrom, gene1.start, gene1.end) == ("1", 0, 50)


def test_bed3_gets_a_coordinate_name(tmp_path):
    path = tmp_path / "panel.bed"
    path.write_text("chr1\t10\t20\n")
    targets = load_bed_targets(path)
    assert targets[0].name == "1:10-20"


def test_gtf_prefers_mane_select_exons():
    targets = load_gtf_targets(GTF, {"GENE1"})
    assert len(targets) == 2
    assert {target.transcript for target in targets} == {"ENST1"}
    assert {target.exon for target in targets} == {"1", "2"}
    assert targets[0].start == 0
    assert targets[0].end == 25


def test_gtf_requires_a_gene_list():
    with pytest.raises(ValueError):
        load_gtf_targets(GTF, set())


def test_missing_bed_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_bed_targets(tmp_path / "missing.bed")
