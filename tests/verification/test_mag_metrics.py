"""Tests for mag (QUAST + CheckM) stats parsers.

All fixtures in this file are synthetic inline strings written to ``tmp_path`` —
no real nf-core/mag run, no network. Structural difference from the
methylseq/Bismark parsers (one report file -> one sample): nf-core/mag's QUAST
`transposed_report.tsv` and CheckM summary are each a SINGLE file covering
MANY bins, so both parsers here return `{bin: {slug: float}}` directly. Phase
3 adds a belt-and-suspenders integration test against a committed realistic
fixture; these are the fast, isolated unit tests pinning the parsing logic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contig.verification.mag_metrics import (
    parse_checkm_summary,
    parse_quast_report,
)

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "mag"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


# --------------------------------------------------------------------------- #
# transposed_report.tsv — header-driven, multi-bin QUAST assembly-stats table.
# --------------------------------------------------------------------------- #

_TRANSPOSED_REPORT_HEALTHY = (
    "Assembly\t# contigs\tLargest contig\tTotal length\tN50\tL50\n"
    "bin.1\t42\t120000\t3500000\t8500\t12\n"
    "bin.2\t18\t95000\t2100000\t6200\t8\n"
)


def test_transposed_report_reads_n50_per_bin(tmp_path: Path) -> None:
    path = _write(tmp_path, "transposed_report.tsv", _TRANSPOSED_REPORT_HEALTHY)
    out = parse_quast_report(path)
    assert out == {
        "bin.1": {"n50": 8500.0},
        "bin.2": {"n50": 6200.0},
    }


def test_transposed_report_is_case_insensitive_on_header(tmp_path: Path) -> None:
    text = "assembly\tn50\nbin.1\t7000\n"
    path = _write(tmp_path, "transposed_report.tsv", text)
    out = parse_quast_report(path)
    assert out == {"bin.1": {"n50": 7000.0}}


def test_transposed_report_non_numeric_n50_is_omitted(tmp_path: Path) -> None:
    text = "Assembly\tN50\nbin.1\tN/A\n"
    path = _write(tmp_path, "transposed_report.tsv", text)
    out = parse_quast_report(path)
    assert out == {"bin.1": {}}


def test_transposed_report_unrecognized_file_returns_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, "unrelated.tsv", "foo\tbar\nbaz\tqux\n")
    assert parse_quast_report(path) == {}


def test_transposed_report_multi_bin_no_cross_bin_bleed(tmp_path: Path) -> None:
    path = _write(tmp_path, "transposed_report.tsv", _TRANSPOSED_REPORT_HEALTHY)
    out = parse_quast_report(path)
    assert set(out) == {"bin.1", "bin.2"}
    assert out["bin.1"] != out["bin.2"]


# --------------------------------------------------------------------------- #
# CheckM summary — header-driven, multi-bin bin-quality table. `Bin Id`,
# `Completeness`, `Contamination` columns.
# --------------------------------------------------------------------------- #

_CHECKM_SUMMARY_HEALTHY = (
    "Bin Id\tMarker lineage\t# genomes\t# markers\tCompleteness\tContamination\n"
    "bin.1\tk__Bacteria\t100\t120\t95.2\t1.3\n"
    "bin.2\tk__Bacteria\t100\t120\t88.0\t2.1\n"
)


def test_checkm_summary_reads_completeness_and_contamination_per_bin(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, "checkm_summary.tsv", _CHECKM_SUMMARY_HEALTHY)
    out = parse_checkm_summary(path)
    assert out == {
        "bin.1": {"completeness": 95.2, "contamination": 1.3},
        "bin.2": {"completeness": 88.0, "contamination": 2.1},
    }


def test_checkm_summary_is_case_insensitive_on_header(tmp_path: Path) -> None:
    text = "bin id\tcompleteness\tcontamination\nbin.1\t90.0\t3.0\n"
    path = _write(tmp_path, "checkm_summary.tsv", text)
    out = parse_checkm_summary(path)
    assert out == {"bin.1": {"completeness": 90.0, "contamination": 3.0}}


def test_checkm_summary_non_numeric_completeness_is_omitted(tmp_path: Path) -> None:
    text = "Bin Id\tCompleteness\tContamination\nbin.1\tN/A\t2.0\n"
    path = _write(tmp_path, "checkm_summary.tsv", text)
    out = parse_checkm_summary(path)
    assert out == {"bin.1": {"contamination": 2.0}}


def test_checkm_summary_unrecognized_file_returns_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, "unrelated.tsv", "nothing to see here\n")
    assert parse_checkm_summary(path) == {}


def test_checkm_summary_multi_bin_no_cross_bin_bleed(tmp_path: Path) -> None:
    path = _write(tmp_path, "checkm_summary.tsv", _CHECKM_SUMMARY_HEALTHY)
    out = parse_checkm_summary(path)
    assert set(out) == {"bin.1", "bin.2"}
    assert out["bin.1"] != out["bin.2"]


# --------------------------------------------------------------------------- #
# Integration: parse the committed realistic fixture set end-to-end
# (tests/fixtures/mag/), shaped like real nf-core/mag QUAST + CheckM output
# (includes an `unbinned` QUAST row, which has no CheckM counterpart). Belt-
# and-suspenders on the real field labels, per Phase 3 of the plan.
# --------------------------------------------------------------------------- #


def test_committed_transposed_report_fixture_parses_bins() -> None:
    path = _FIXTURES_DIR / "transposed_report.tsv"
    out = parse_quast_report(path)

    assert set(out) == {"bin.1", "bin.2", "bin.3", "unbinned"}
    assert out["bin.1"]["n50"] == 112340.0
    assert out["bin.2"]["n50"] == 54200.0
    assert out["bin.3"]["n50"] == 4210.0


def test_committed_checkm_summary_fixture_parses_bins() -> None:
    path = _FIXTURES_DIR / "checkm_summary.tsv"
    out = parse_checkm_summary(path)

    assert set(out) == {"bin.1", "bin.2", "bin.3"}
    assert out["bin.1"] == {"completeness": 98.28, "contamination": 1.72}
    assert out["bin.2"] == {"completeness": 89.45, "contamination": 1.10}
    assert out["bin.3"] == {"completeness": 52.30, "contamination": 3.85}
