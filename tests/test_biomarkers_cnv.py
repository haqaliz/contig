"""Tests for CNV segment comparison."""

from pathlib import Path

import pytest

from contig.biomarkers.cnv import Segment, compare_files, compare_segments, load_segments
from contig.biomarkers.report import build_report

FIX = Path(__file__).parent / "fixtures" / "biomarkers"
VCF = FIX / "variants.vcf"
BED = FIX / "callable.bed"
TRUTH = FIX / "cnv_truth.tsv"
MATCH = FIX / "cnv_call_match.tsv"
DIVERGENT = FIX / "cnv_call_divergent.tsv"
COPY_NUMBER = FIX / "cnv_copy_number.tsv"


def test_load_segments_auto_detects_value_column():
    segments, column = load_segments(TRUTH)
    assert column == "log2"
    assert len(segments) == 3
    assert segments[0].chrom == "1"


def test_load_segments_explicit_value_column():
    segments, column = load_segments(COPY_NUMBER, value_column="copy_number")
    assert column == "copy_number"
    assert len(segments) == 2


def test_concordant_segments_match():
    result = compare_files(MATCH, TRUTH)
    assert result.status == "match"
    assert result.concordance == 1.0
    assert result.mean_abs_delta == 0.0


def test_divergent_segments_are_reported():
    result = compare_files(DIVERGENT, TRUTH)
    assert result.status == "divergent"
    assert result.concordance < 0.9
    assert result.mean_abs_delta > 0.1


def test_no_overlap_is_unverified():
    result = compare_segments([Segment("3", 0, 100, 0.0)], [Segment("1", 0, 100, 0.0)])
    assert result.status == "unverified"
    assert result.compared_bases == 0


def test_report_cnv_entry():
    result = compare_files(MATCH, TRUTH)
    report = build_report(VCF, BED, cnv_result=result)
    cnv = next(entry for entry in report.entries if entry.name == "CNV")
    assert cnv.value == "100.00%"
    assert cnv.status == "match"
    assert any(source.kind == "cnv_call" for source in report.meta.sources)
    assert any(source.kind == "cnv_truth" for source in report.meta.sources)


def test_missing_segments_are_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_segments(tmp_path / "missing.tsv")
