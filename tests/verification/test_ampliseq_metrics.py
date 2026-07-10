"""Tests for ampliseq (DADA2) stats parsers.

All fixtures in this file are synthetic inline strings written to ``tmp_path`` —
no real nf-core/ampliseq run, no network. Unlike the methylseq/Bismark parsers
(one report file -> one sample), DADA2's `overall_summary.tsv` and ASV table
are MULTI-sample files, so both parsers here return `{sample: {slug: float}}`
directly. Phase 3 adds a belt-and-suspenders integration test against a
committed realistic fixture; these are the fast, isolated unit tests pinning
the parsing logic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contig.verification.ampliseq_metrics import (
    parse_asv_table,
    parse_dada2_overall_summary,
)

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "ampliseq"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


# --------------------------------------------------------------------------- #
# overall_summary.tsv — header-driven, multi-sample DADA2 track table.
# `input` is the DADA2-input read count; `nonchim` is the post-chimera-removal
# count; percent_retained = nonchim / input * 100.
# --------------------------------------------------------------------------- #

_OVERALL_SUMMARY_HEALTHY = (
    "sample\tinput\tfiltered\tdenoisedF\tdenoisedR\tmerged\ttabled\tnonchim\n"
    "S1\t100000\t95000\t94000\t94000\t92000\t92000\t90000\n"
    "S2\t50000\t48000\t47500\t47500\t46000\t46000\t45000\n"
)


def test_overall_summary_computes_input_reads_and_percent_retained(tmp_path: Path) -> None:
    path = _write(tmp_path, "overall_summary.tsv", _OVERALL_SUMMARY_HEALTHY)
    out = parse_dada2_overall_summary(path)
    assert out == {
        "S1": {"input_reads": 100000.0, "percent_retained": 90.0},
        "S2": {"input_reads": 50000.0, "percent_retained": 90.0},
    }


def test_overall_summary_is_case_insensitive_and_tolerates_column_variants(
    tmp_path: Path,
) -> None:
    # Real nf-core/ampliseq output varies casing / uses non-chim spellings; the
    # parser must key off the header, not a fixed column position.
    text = (
        "Sample\tInput\tFiltered\tNon-Chim\n"
        "S1\t20000\t19000\t18000\n"
    )
    path = _write(tmp_path, "overall_summary.tsv", text)
    out = parse_dada2_overall_summary(path)
    assert out == {"S1": {"input_reads": 20000.0, "percent_retained": 90.0}}


def test_overall_summary_omits_percent_retained_when_input_is_zero(tmp_path: Path) -> None:
    text = "sample\tinput\tnonchim\nS1\t0\t0\n"
    path = _write(tmp_path, "overall_summary.tsv", text)
    out = parse_dada2_overall_summary(path)
    assert out == {"S1": {"input_reads": 0.0}}


def test_overall_summary_omits_percent_retained_when_nonchim_missing(tmp_path: Path) -> None:
    text = "sample\tinput\tfiltered\nS1\t20000\t19000\n"
    path = _write(tmp_path, "overall_summary.tsv", text)
    out = parse_dada2_overall_summary(path)
    assert out == {"S1": {"input_reads": 20000.0}}


def test_overall_summary_non_numeric_input_is_omitted(tmp_path: Path) -> None:
    text = "sample\tinput\tnonchim\nS1\tN/A\t18000\n"
    path = _write(tmp_path, "overall_summary.tsv", text)
    out = parse_dada2_overall_summary(path)
    assert out == {"S1": {}}


def test_overall_summary_unrecognized_file_returns_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, "unrelated.tsv", "foo\tbar\nbaz\tqux\n")
    assert parse_dada2_overall_summary(path) == {}


def test_overall_summary_multi_sample_no_cross_sample_bleed(tmp_path: Path) -> None:
    path = _write(tmp_path, "overall_summary.tsv", _OVERALL_SUMMARY_HEALTHY)
    out = parse_dada2_overall_summary(path)
    assert set(out) == {"S1", "S2"}
    assert out["S1"] != out["S2"]


# --------------------------------------------------------------------------- #
# ASV table — rows=ASVs, columns=samples, integer counts. Per-sample asv_count
# = number of ASV rows with a non-zero count for that sample's column.
# --------------------------------------------------------------------------- #

_ASV_TABLE_HEALTHY = (
    "ASV_ID\tS1\tS2\tsequence\n"
    "ASV1\t120\t0\tACGT\n"
    "ASV2\t45\t80\tTTAA\n"
    "ASV3\t0\t30\tGGCC\n"
    "ASV4\t10\t0\tCCGG\n"
)


def test_asv_table_counts_non_zero_rows_per_sample(tmp_path: Path) -> None:
    path = _write(tmp_path, "ASV_table.tsv", _ASV_TABLE_HEALTHY)
    out = parse_asv_table(path)
    assert out == {"S1": {"asv_count": 3.0}, "S2": {"asv_count": 2.0}}


def test_asv_table_excludes_sequence_column_from_samples(tmp_path: Path) -> None:
    path = _write(tmp_path, "ASV_table.tsv", _ASV_TABLE_HEALTHY)
    out = parse_asv_table(path)
    assert "sequence" not in out
    assert "ACGT" not in out


def test_asv_table_no_data_rows_returns_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, "ASV_table.tsv", "ASV_ID\tS1\tS2\n")
    assert parse_asv_table(path) == {}


def test_asv_table_unrecognized_file_returns_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, "unrelated.tsv", "nothing to see here\n")
    assert parse_asv_table(path) == {}


def test_asv_table_multi_sample_no_cross_sample_bleed(tmp_path: Path) -> None:
    path = _write(tmp_path, "ASV_table.tsv", _ASV_TABLE_HEALTHY)
    out = parse_asv_table(path)
    assert set(out) == {"S1", "S2"}
    assert out["S1"] != out["S2"]


# --------------------------------------------------------------------------- #
# Integration: parse the committed realistic fixture set end-to-end
# (tests/fixtures/ampliseq/), shaped like real nf-core/ampliseq v2 DADA2
# output. Belt-and-suspenders on the real field labels, per Phase 3 of the
# plan.
# --------------------------------------------------------------------------- #


def test_committed_overall_summary_fixture_parses_three_samples() -> None:
    path = _FIXTURES_DIR / "overall_summary.tsv"
    out = parse_dada2_overall_summary(path)

    assert set(out) == {"S1", "S2", "S3"}
    assert out["S1"]["input_reads"] == 124582.0
    assert out["S1"]["percent_retained"] == pytest.approx(88.21916, rel=1e-4)
    # S3 is the shallow sample: still parses cleanly, no special-casing.
    assert out["S3"]["input_reads"] == 5210.0
    assert out["S3"]["percent_retained"] == pytest.approx(76.39155, rel=1e-4)


def test_committed_asv_table_fixture_parses_three_samples() -> None:
    path = _FIXTURES_DIR / "ASV_table.tsv"
    out = parse_asv_table(path)

    assert set(out) == {"S1", "S2", "S3"}
    assert out["S1"]["asv_count"] == 6.0
    assert out["S2"]["asv_count"] == 6.0
    assert out["S3"]["asv_count"] == 4.0
    # The trailing `sequence` metadata column must never be mistaken for a
    # sample.
    assert "sequence" not in out
