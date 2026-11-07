"""Tests for callable BED parsing and TMB computation."""

from pathlib import Path

import pytest

from contig.biomarkers.tmb import compute_tmb, in_callable, load_callable_bed

FIX = Path(__file__).parent / "fixtures" / "biomarkers"
VCF = FIX / "variants.vcf"
BED = FIX / "callable.bed"


def test_callable_bed_and_boundaries():
    intervals, starts, mb = load_callable_bed(BED)
    assert mb == 1.0
    assert in_callable(intervals, starts, "1", 1)
    assert in_callable(intervals, starts, "chr1", 1_000_000)
    assert not in_callable(intervals, starts, "1", 0)
    assert not in_callable(intervals, starts, "1", 1_000_001)
    assert not in_callable(intervals, starts, "2", 500)


def test_tmb_counts_pass_variants_in_callable_regions():
    result = compute_tmb(VCF, BED)
    assert result["variant_count"] == 5
    assert result["callable_mb"] == 1.0
    assert result["tmb"] == 5.0
    assert result["outside_count"] == 2
    assert result["definition"].startswith("PASS variants")


def test_coding_only_excludes_unannotated():
    result = compute_tmb(VCF, BED, coding_only=True)
    assert result["variant_count"] == 3
    assert result["tmb"] == 3.0
    assert result["unannotated_count"] == 2
    assert "coding consequence" in result["definition"]


def test_missing_inputs_are_honest_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        compute_tmb(tmp_path / "missing.vcf", BED)
    with pytest.raises(FileNotFoundError):
        compute_tmb(VCF, tmp_path / "missing.bed")
