"""Tests for allele-specific LOH verification."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.biomarkers.loh import (
    compare_loh,
    compare_loh_files,
    load_allele_specific_segments,
)
from contig.cli import app

FIX = Path(__file__).parent / "fixtures" / "biomarkers"
VCF = str(FIX / "variants.vcf")
BED = str(FIX / "callable.bed")

HEADER = (
    "Chromosome\tStart\tEnd\tCopy_Number\tMajor_Copy_Number\tMinor_Copy_Number\n"
)
TRUTH = HEADER + (
    "chr1\t100\t200\t2\t1\t1\n"
    "chr1\t200\t300\t1\t1\t0\n"
    "chr2\t100\t400\t2\t2\t0\n"
)


def _write(tmp_path: Path, text: str, name: str = "segments.tsv") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_loads_allele_specific_segments(tmp_path):
    segments, column = load_allele_specific_segments(_write(tmp_path, TRUTH))
    assert len(segments) == 3
    assert column == "minor_copy_number"
    assert [segment.minor_cn for segment in segments] == [1.0, 0.0, 0.0]


def test_self_comparison_matches(tmp_path):
    segments, _ = load_allele_specific_segments(_write(tmp_path, TRUTH))
    result = compare_loh(segments, segments)
    assert result.status == "match"
    assert result.jaccard == 1.0
    assert result.truth_loh_bases == 400
    assert result.overlap_bases == 400


def test_missing_loh_is_divergent(tmp_path):
    call_text = HEADER + (
        "chr1\t100\t200\t2\t1\t1\n"
        "chr1\t200\t300\t1\t1\t0\n"
        "chr2\t100\t400\t2\t1\t1\n"
    )
    call, _ = load_allele_specific_segments(_write(tmp_path, call_text, "call.tsv"))
    truth, _ = load_allele_specific_segments(_write(tmp_path, TRUTH, "truth.tsv"))
    result = compare_loh(call, truth)
    assert result.status == "divergent"
    assert result.call_loh_bases == 100
    assert result.truth_loh_bases == 400
    assert result.recall == 0.25


def test_empty_call_loh_is_divergent(tmp_path):
    call_text = HEADER + "chr2\t100\t400\t2\t1\t1\n"
    call, _ = load_allele_specific_segments(_write(tmp_path, call_text, "call.tsv"))
    truth, _ = load_allele_specific_segments(_write(tmp_path, TRUTH, "truth.tsv"))
    result = compare_loh(call, truth)
    assert result.status == "divergent"
    assert "call has no LOH" in result.detail


def test_empty_truth_loh_is_unverified(tmp_path):
    truth_text = HEADER + "chr2\t100\t400\t2\t1\t1\n"
    call, _ = load_allele_specific_segments(_write(tmp_path, TRUTH, "call.tsv"))
    truth, _ = load_allele_specific_segments(_write(tmp_path, truth_text, "truth.tsv"))
    assert compare_loh(call, truth).status == "unverified"


def test_total_copy_number_only_is_refused(tmp_path):
    text = "Chromosome\tStart\tEnd\tCopy_Number\nchr1\t100\t300\t2\n"
    with pytest.raises(ValueError, match="minor-copy-number"):
        load_allele_specific_segments(_write(tmp_path, text))


def test_cli_reports_loh_status(tmp_path):
    call = _write(tmp_path, TRUTH, "call.tsv")
    truth = _write(tmp_path, TRUTH, "truth.tsv")
    out = tmp_path / "biomarkers.json"
    result = CliRunner().invoke(app, [
        "biomarkers",
        "--vcf", VCF,
        "--callable-bed", BED,
        "--loh-segments", str(call),
        "--loh-truth", str(truth),
        "--json",
        "--out", str(out),
    ])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text())
    loh = next(entry for entry in payload["biomarkers"] if entry["name"] == "LOH")
    assert loh["status"] == "match"
    assert loh["value"] == "100.00%"
    assert loh["unit"] == "LOH Jaccard"
