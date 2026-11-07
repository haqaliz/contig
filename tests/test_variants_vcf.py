"""Tests for the stdlib VCF reader and CSQ/ANN parsing."""

import gzip
import shutil
from pathlib import Path

from contig.variants.vcf import normalize_chrom, read_variants

FIX = Path(__file__).parent / "fixtures" / "variants"
SAMPLE = FIX / "sample.vcf"


def _rows():
    rows, _ = read_variants(SAMPLE)
    return rows


def test_reads_one_row_per_alt_and_counts_them():
    rows, stats = read_variants(SAMPLE)
    assert len(rows) == 7
    assert stats.total_records == 6
    assert stats.emitted_rows == 7
    assert stats.skipped_lines == 0


def test_parses_vep_csq_fields():
    row = next(r for r in _rows() if r.gene == "BRCA1")
    assert row.consequence == "frameshift_variant"
    assert row.impact == "HIGH"
    assert row.transcript == "ENST00000357654"
    assert row.hgvsc == "c.5266dupC"
    assert row.hgvsp == "p.Gln1756Profs*74"


def test_parses_genotype_depth_and_vaf():
    row = next(r for r in _rows() if r.gene == "BRCA1")
    assert row.genotype == "0/1"
    assert row.zygosity == "het"
    assert row.depth == 150
    assert row.vaf == 50 / 150


def test_homozygous_and_hemizygous_zygosity():
    rows = _rows()
    gjb2 = next(r for r in rows if r.gene == "GJB2")
    assert gjb2.zygosity == "hom"
    assert gjb2.vaf == 1.0
    hemi = next(r for r in rows if r.key.chrom == "X")
    assert hemi.zygosity == "hemi"


def test_parses_snpeff_ann():
    row = next(r for r in _rows() if r.gene == "EGFR")
    assert row.consequence == "missense_variant"
    assert row.impact == "MODERATE"
    assert row.hgvsc == "c.2573T>G"
    assert row.hgvsp == "p.Leu858Arg"
    assert row.filter == "q10"


def test_unannotated_variant_is_kept_not_dropped():
    row = next(r for r in _rows() if r.key.pos == 100)
    assert row.consequence is None
    assert row.gene is None
    assert row.zygosity is None


def test_multiallelic_alt_splits_and_picks_the_matching_csq_entry():
    rows = [r for r in _rows() if r.key.pos == 200]
    assert len(rows) == 2
    by_alt = {r.key.alt: r for r in rows}
    assert by_alt["T"].consequence == "missense_variant"
    assert by_alt["T"].vaf == 20 / 50
    assert by_alt["G"].consequence == "synonymous_variant"
    assert by_alt["G"].vaf == 10 / 40
    assert by_alt["T"].zygosity == "het"
    assert by_alt["G"].zygosity == "het"


def test_gzipped_vcf_matches_plain(tmp_path):
    gz = tmp_path / "sample.vcf.gz"
    with SAMPLE.open("rb") as src, gzip.open(gz, "wb") as dst:
        shutil.copyfileobj(src, dst)
    plain, _ = read_variants(SAMPLE)
    packed, _ = read_variants(gz)
    assert [r.key for r in plain] == [r.key for r in packed]


def test_malformed_line_is_skipped_and_counted(tmp_path):
    broken = tmp_path / "broken.vcf"
    broken.write_text(
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "1\tnot-a-pos\t.\tA\tG\t.\t.\t.\n"
    )
    rows, stats = read_variants(broken)
    assert rows == []
    assert stats.skipped_lines == 1
    assert stats.total_records == 1


def test_normalize_chrom_handles_prefixes_and_mito():
    assert normalize_chrom("chr17") == "17"
    assert normalize_chrom("17") == "17"
    assert normalize_chrom("chrM") == "MT"
    assert normalize_chrom("MT") == "MT"
