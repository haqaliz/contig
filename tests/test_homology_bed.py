"""Integrity checks for the curated homology/pseudogene caveat BED."""

from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
HOMOLOGY = ROOT / "data" / "homology" / "homology_caveats_GRCh38.bed"

pytestmark = pytest.mark.skipif(
    not HOMOLOGY.is_file(), reason="derived homology BED not built"
)

EXPECTED_GENES = {
    "SMN1", "SMN2", "PMS2", "PMS2CL", "HBA1", "HBA2",
    "CYP21A2", "CYP21A1P", "GBA1", "GBA1LP", "PKD1",
    "PKD1P1", "PKD1P2", "PKD1P3", "PKD1P4", "PKD1P5", "PKD1P6",
    "STRC", "STRCP1", "NCF1", "NCF1B", "NCF1C",
    "CYP2D6", "CYP2D7", "CYP2D8P", "PTEN", "PTENP1",
    "GJB2", "GJB6", "IKBKG", "IKBKGP1", "HBB", "HBD",
}


def _rows() -> list[dict[str, str]]:
    with HOMOLOGY.open() as handle:
        header = handle.readline().lstrip("#").rstrip("\n").split("\t")
        return [
            dict(zip(header, line.rstrip("\n").split("\t")))
            for line in handle
            if line.strip()
        ]


def test_bed_is_eight_columns_and_covers_the_curated_genes():
    assert HOMOLOGY.is_file()
    rows = _rows()
    assert len(rows) > 400
    assert {row["gene"] for row in rows} == EXPECTED_GENES
    for row in rows:
        assert set(row) == {
            "chrom", "start", "end", "gene", "transcript", "exon",
            "partner", "reason",
        }
        assert row["chrom"] and not row["chrom"].startswith("chr")
        assert int(row["end"]) > int(row["start"])
        assert row["reason"]
        assert row["transcript"]


def test_every_gene_uses_one_representative_transcript():
    by_gene: dict[str, set[str]] = defaultdict(set)
    for row in _rows():
        by_gene[row["gene"]].add(row["transcript"])
    for gene, transcripts in by_gene.items():
        assert len(transcripts) == 1, f"{gene} uses {sorted(transcripts)}"


def test_partner_pairs_are_symmetric_and_reciprocal():
    pairs: dict[str, set[str]] = defaultdict(set)
    for row in _rows():
        pairs[row["gene"]].add(row["partner"])
    for gene, partners in pairs.items():
        assert partners, f"{gene} has no partner"
        for partner in partners:
            assert gene in pairs[partner], f"{gene} -> {partner} is not reciprocal"


def test_no_duplicate_exon_partner_rows():
    seen: set[tuple[str, int, int, str, str]] = set()
    for row in _rows():
        key = (
            row["chrom"], int(row["start"]), int(row["end"]),
            row["gene"], row["partner"],
        )
        assert key not in seen, f"duplicate row: {key}"
        seen.add(key)


@pytest.mark.parametrize(
    ("gene", "chrom", "low", "high"),
    [
        ("CYP21A2", "6", 32_030_000, 32_050_000),
        ("CYP21A1P", "6", 31_990_000, 32_020_000),
        ("GBA1", "1", 155_230_000, 155_245_000),
        ("GBA1LP", "1", 155_210_000, 155_225_000),
        ("PKD1", "16", 2_050_000, 2_160_000),
        ("STRC", "15", 43_590_000, 43_630_000),
        ("STRCP1", "15", 43_690_000, 43_730_000),
        ("NCF1", "7", 74_770_000, 74_800_000),
        ("PTEN", "10", 87_850_000, 87_990_000),
        ("PTENP1", "9", 33_660_000, 33_690_000),
        ("GJB2", "13", 20_180_000, 20_200_000),
        ("HBB", "11", 5_215_000, 5_240_000),
        ("IKBKG", "X", 154_540_000, 154_580_000),
    ],
)
def test_known_loci(gene, chrom, low, high):
    rows = [row for row in _rows() if row["gene"] == gene]
    assert rows
    assert {row["chrom"] for row in rows} == {chrom}
    assert low < min(int(row["start"]) for row in rows)
    assert max(int(row["end"]) for row in rows) < high
