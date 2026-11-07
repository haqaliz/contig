"""Tests for the depth TSV reader."""

from pathlib import Path

import pytest

from contig.readiness.depth import load_depth

FIX = Path(__file__).parent / "fixtures" / "readiness"
DEPTH = FIX / "depth.tsv"


def test_loads_positions_and_counts():
    depths, stats = load_depth(DEPTH)
    assert len(depths) == 150
    assert stats.lines == 150
    assert stats.positions == 150
    assert stats.skipped == 0
    assert depths[("1", 1)] == 30
    assert depths[("1", 60)] == 20


def test_skips_comments_header_and_malformed(tmp_path):
    path = tmp_path / "depth.tsv"
    path.write_text(
        "# comment\n"
        "chrom\tpos\tdepth\n"
        "chr1\t1\t10\n"
        "chr1\tbad\t10\n"
        "chr1\t2\t-1\n"
        "chr1\t3\t20\n"
    )
    depths, stats = load_depth(path)
    assert depths == {("1", 1): 10, ("1", 3): 20}
    assert stats.skipped == 2


def test_duplicate_position_keeps_last_and_counts(tmp_path):
    path = tmp_path / "depth.tsv"
    path.write_text("chr1\t1\t10\nchr1\t1\t20\n")
    depths, stats = load_depth(path)
    assert depths[("1", 1)] == 20
    assert stats.duplicates == 1


def test_missing_file_is_an_honest_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_depth(tmp_path / "missing.tsv")
