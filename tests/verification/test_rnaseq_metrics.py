"""Tests for the RSeQC read_distribution.txt parser (RNA-seq read-composition).

All synthetic fixtures in this file are inline strings written to ``tmp_path``
— no real nf-core/rnaseq run, no network. `parse_read_distribution` turns ONE
RSeQC `read_distribution.txt` artifact into `{slug: float}` for the three
composition slugs the (not-yet-registered) RNASEQ_COMPOSITION_PACK scores:
``exonic_fraction``, ``intronic_fraction``, ``unassigned_fraction``. A real,
committed fixture (copied verbatim from a genuine nf-core/rnaseq yeast test
run) pins the parser against real RSeQC layout/whitespace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contig.verification.rnaseq_metrics import (
    EXONIC_FRACTION,
    INTRONIC_FRACTION,
    UNASSIGNED_FRACTION,
    parse_read_distribution,
)

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "rnaseq"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


# --------------------------------------------------------------------------- #
# Healthy fixture — the real committed yeast RSeQC output (Phase 4). CDS-
# dominated, near-zero intronic, low unassigned.
# --------------------------------------------------------------------------- #


def test_healthy_fixture_computes_expected_fractions() -> None:
    path = _FIXTURES_DIR / "WT_REP1.read_distribution.txt"
    out = parse_read_distribution(path)
    assert out[EXONIC_FRACTION] == pytest.approx(129779 / 129802)
    assert out[INTRONIC_FRACTION] == pytest.approx(23 / 129802)
    assert out[UNASSIGNED_FRACTION] == pytest.approx((146154 - 129802) / 146154)


# --------------------------------------------------------------------------- #
# Low-exonic / high-intronic synthetic — CDS_Exons small, Introns large.
# --------------------------------------------------------------------------- #

_LOW_EXONIC_HIGH_INTRONIC = """\
Total Reads                   100000
Total Tags                    100000
Total Assigned Tags           100000
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           1000                1000                1000.00
5'UTR_Exons         0                   0                   0.00
3'UTR_Exons         0                   0                   0.00
Introns             50000               50000               1000.00
TSS_up_1kb          0                   0                   0.00
TES_down_1kb        0                   0                   0.00
=====================================================================
"""


def test_low_exonic_high_intronic_synthetic(tmp_path: Path) -> None:
    path = _write(tmp_path, "S1.read_distribution.txt", _LOW_EXONIC_HIGH_INTRONIC)
    out = parse_read_distribution(path)
    assert out[EXONIC_FRACTION] < 0.50
    assert out[INTRONIC_FRACTION] > 0.30


# --------------------------------------------------------------------------- #
# High-unassigned synthetic — Total Assigned Tags much smaller than Total
# Tags.
# --------------------------------------------------------------------------- #

_HIGH_UNASSIGNED = """\
Total Reads                   100000
Total Tags                    100000
Total Assigned Tags           40000
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           1000                35000               1000.00
5'UTR_Exons         0                   0                   0.00
3'UTR_Exons         0                   0                   0.00
Introns             1000                5000                1000.00
=====================================================================
"""


def test_high_unassigned_synthetic(tmp_path: Path) -> None:
    path = _write(tmp_path, "S1.read_distribution.txt", _HIGH_UNASSIGNED)
    out = parse_read_distribution(path)
    assert out[UNASSIGNED_FRACTION] > 0.30


# --------------------------------------------------------------------------- #
# Omit-never-guess edges.
# --------------------------------------------------------------------------- #


def test_missing_total_assigned_tags_omits_exonic_and_intronic_only(
    tmp_path: Path,
) -> None:
    text = """\
Total Reads                   100000
Total Tags                    100000
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           1000                90000               1000.00
Introns             1000                5000                1000.00
=====================================================================
"""
    path = _write(tmp_path, "S1.read_distribution.txt", text)
    out = parse_read_distribution(path)
    assert EXONIC_FRACTION not in out
    assert INTRONIC_FRACTION not in out
    # unassigned needs `assigned` too (per the locked formula), so it is
    # ALSO omitted here since Total Assigned Tags is entirely absent.
    assert UNASSIGNED_FRACTION not in out


def test_missing_introns_row_omits_intronic_only(tmp_path: Path) -> None:
    text = """\
Total Reads                   100000
Total Tags                    100000
Total Assigned Tags           90000
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           1000                90000               1000.00
=====================================================================
"""
    path = _write(tmp_path, "S1.read_distribution.txt", text)
    out = parse_read_distribution(path)
    assert out[EXONIC_FRACTION] == pytest.approx(1.0)
    assert INTRONIC_FRACTION not in out
    assert UNASSIGNED_FRACTION in out


def test_zero_total_assigned_tags_omits_exonic_and_intronic(tmp_path: Path) -> None:
    text = """\
Total Reads                   100000
Total Tags                    100000
Total Assigned Tags           0
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           1000                0                   0.00
Introns             1000                0                   0.00
=====================================================================
"""
    path = _write(tmp_path, "S1.read_distribution.txt", text)
    out = parse_read_distribution(path)
    assert EXONIC_FRACTION not in out
    assert INTRONIC_FRACTION not in out


def test_zero_total_tags_omits_unassigned(tmp_path: Path) -> None:
    text = """\
Total Reads                   0
Total Tags                    0
Total Assigned Tags           0
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           0                   0                   0.00
Introns             0                   0                   0.00
=====================================================================
"""
    path = _write(tmp_path, "S1.read_distribution.txt", text)
    out = parse_read_distribution(path)
    assert UNASSIGNED_FRACTION not in out


def test_negative_unassigned_guard_omits_unassigned_only(tmp_path: Path) -> None:
    # Total Assigned Tags EXCEEDS Total Tags (malformed/inconsistent artifact).
    # exonic/intronic only need `assigned`, so they are still computed; the
    # `unassigned >= 0` guard omits UNASSIGNED_FRACTION rather than emitting a
    # negative fraction.
    text = """\
Total Reads                   100
Total Tags                    100
Total Assigned Tags           150
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           1000                120                 120.00
Introns             1000                30                  30.00
=====================================================================
"""
    path = _write(tmp_path, "S1.read_distribution.txt", text)
    out = parse_read_distribution(path)
    assert out[EXONIC_FRACTION] == pytest.approx(120 / 150)
    assert out[INTRONIC_FRACTION] == pytest.approx(30 / 150)
    assert UNASSIGNED_FRACTION not in out


def test_non_numeric_total_assigned_tags_omits_all_three(tmp_path: Path) -> None:
    # "Total Assigned Tags" trailing token is non-numeric -> `assigned` is
    # None. exonic/intronic require `assigned is not None`, so both are
    # omitted; unassigned's formula also requires `assigned is not None`, so
    # it is omitted too, even though Total Tags is present and valid.
    text = """\
Total Reads                   100000
Total Tags                    100000
Total Assigned Tags           abc
=====================================================================
Group               Total_bases         Tag_count           Tags/Kb
CDS_Exons           1000                90000               1000.00
Introns             1000                5000                1000.00
=====================================================================
"""
    path = _write(tmp_path, "S1.read_distribution.txt", text)
    out = parse_read_distribution(path)
    assert EXONIC_FRACTION not in out
    assert INTRONIC_FRACTION not in out
    assert UNASSIGNED_FRACTION not in out
    assert out == {}


# --------------------------------------------------------------------------- #
# Garbage / empty input.
# --------------------------------------------------------------------------- #


def test_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    path = _write(tmp_path, "S1.read_distribution.txt", "")
    assert parse_read_distribution(path) == {}


def test_garbage_file_returns_empty_dict(tmp_path: Path) -> None:
    path = _write(tmp_path, "S1.read_distribution.txt", "nothing to see here\nrandom text\n")
    assert parse_read_distribution(path) == {}


def test_only_rule_lines_returns_empty_dict(tmp_path: Path) -> None:
    text = "=====================================================================\n=====================================================================\n"
    path = _write(tmp_path, "S1.read_distribution.txt", text)
    assert parse_read_distribution(path) == {}


# --------------------------------------------------------------------------- #
# Determinism.
# --------------------------------------------------------------------------- #


def test_determinism_same_input_same_output(tmp_path: Path) -> None:
    path = _write(tmp_path, "S1.read_distribution.txt", _LOW_EXONIC_HIGH_INTRONIC)
    first = parse_read_distribution(path)
    second = parse_read_distribution(path)
    assert first == second
