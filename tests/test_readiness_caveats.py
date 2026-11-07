"""Tests for caveat BED parsing and overlap."""

from pathlib import Path

from contig.readiness.caveats import load_caveats, overlapping_caveats
from contig.readiness.models import Target

FIX = Path(__file__).parent / "fixtures" / "readiness"
HOMOLOGY = FIX / "homology.bed"


def test_bed5_caveat_parses_name_and_reason():
    regions = load_caveats(HOMOLOGY)
    assert len(regions) == 1
    assert regions[0].name == "GENE1"
    assert "GENE1B" in regions[0].reason
    assert regions[0].chrom == "1"


def test_eight_column_homology_bed_parses(tmp_path):
    path = tmp_path / "caveats.bed"
    path.write_text("chr5\t0\t100\tSMN1\tENST1\t7\tSMN2\thomology with SMN2\n")
    regions = load_caveats(path)
    assert regions[0].name == "SMN1/SMN2"
    assert regions[0].reason == "homology with SMN2"


def test_overlap_is_half_open_at_the_boundaries():
    regions = load_caveats(HOMOLOGY)
    assert overlapping_caveats(Target("1", 0, 50, "GENE1"), regions)
    assert overlapping_caveats(Target("1", 50, 100, "GENE2"), regions) == []
    assert overlapping_caveats(Target("1", 49, 60, "GENE1"), regions)


def test_chrom_prefix_is_normalized():
    regions = load_caveats(HOMOLOGY)
    assert overlapping_caveats(Target("chr1", 0, 50, "GENE1"), regions)
