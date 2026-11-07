"""Tests for the multi-sample family VCF reader."""

from pathlib import Path

import pytest

from contig.family.vcf import read_family_variants

FIX = Path(__file__).parent / "fixtures" / "family"
VCF = FIX / "trio.vcf"
SAMPLES = ["CHILD", "FATHER", "MOTHER"]


def test_reads_one_row_per_alt_with_per_sample_genotypes():
    variants, stats = read_family_variants(VCF, SAMPLES)
    assert len(variants) == 8
    assert stats.total_records == 8
    assert stats.emitted_rows == 8
    first = variants[0]
    assert first.key.chrom == "1"
    assert first.genotypes == {"CHILD": "0/1", "FATHER": "0/1", "MOTHER": "0/0"}
    assert first.gene == "GENE1"
    assert first.consequence == "missense_variant"


def test_missing_sample_is_an_honest_error():
    with pytest.raises(ValueError, match="missing sample"):
        read_family_variants(VCF, ["CHILD", "UNKNOWN"])


def test_missing_vcf_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_family_variants(tmp_path / "missing.vcf", SAMPLES)
