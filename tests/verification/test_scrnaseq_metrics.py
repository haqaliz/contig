"""Tests for single-cell (scrnaseq) cell-QC parsers.

All fixtures are synthetic inline strings written to ``tmp_path`` — no real
nf-core/scrnaseq run, no network. Each parser turns ONE aligner's per-sample
cell-QC file into ``{slug: float}`` for the three slugs the scrnaseq rule pack
scores: ``estimated_cells``, ``median_genes_per_cell``, ``fraction_reads_in_cells``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contig.verification.scrnaseq_metrics import (
    parse_cellranger_metrics,
    parse_simpleaf_metrics,
    parse_starsolo_summary,
)


# --------------------------------------------------------------------------- #
# STARsolo Summary.csv — headerless two-column `Field,Value` rows.
# --------------------------------------------------------------------------- #

_STARSOLO_FULL = """\
Number of Reads,1000000
Reads With Valid Barcodes,0.98
Sequencing Saturation,0.5
Estimated Number of Cells,5000
Fraction of Unique Reads in Cells,0.85
Mean Gene per Cell,2100
Median Gene per Cell,1800
Total Gene Detected,25000
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_starsolo_maps_all_three_slugs(tmp_path: Path) -> None:
    path = _write(tmp_path, "Summary.csv", _STARSOLO_FULL)
    out = parse_starsolo_summary(path)
    assert out == {
        "estimated_cells": 5000.0,
        "median_genes_per_cell": 1800.0,
        "fraction_reads_in_cells": 0.85,
    }


def test_starsolo_tolerates_gene_plural(tmp_path: Path) -> None:
    text = "Estimated Number of Cells,4200\nMedian Genes per Cell,1500\n"
    path = _write(tmp_path, "Summary.csv", text)
    out = parse_starsolo_summary(path)
    assert out["median_genes_per_cell"] == 1500.0
    assert out["estimated_cells"] == 4200.0


def test_starsolo_missing_field_omits_slug(tmp_path: Path) -> None:
    text = "Estimated Number of Cells,3000\n"  # no genes/cell, no fraction
    path = _write(tmp_path, "Summary.csv", text)
    out = parse_starsolo_summary(path)
    assert out == {"estimated_cells": 3000.0}
    assert "median_genes_per_cell" not in out
    assert "fraction_reads_in_cells" not in out


def test_starsolo_skips_non_numeric_value(tmp_path: Path) -> None:
    text = "Estimated Number of Cells,NA\nMedian Gene per Cell,1200\n"
    path = _write(tmp_path, "Summary.csv", text)
    out = parse_starsolo_summary(path)
    assert "estimated_cells" not in out  # garbage skipped, never guessed to 0
    assert out["median_genes_per_cell"] == 1200.0


# --------------------------------------------------------------------------- #
# Cell Ranger metrics_summary.csv — quoted header row + quoted value row,
# comma-thousands and percent-suffixed values.
# --------------------------------------------------------------------------- #

_CELLRANGER = (
    '"Estimated Number of Cells","Mean Reads per Cell",'
    '"Median Genes per Cell","Fraction Reads in Cells"\n'
    '"5,000","20,000","1,800","92.3%"\n'
)


def test_cellranger_strips_comma_thousands(tmp_path: Path) -> None:
    path = _write(tmp_path, "metrics_summary.csv", _CELLRANGER)
    out = parse_cellranger_metrics(path)
    assert out["estimated_cells"] == 5000.0
    assert out["median_genes_per_cell"] == 1800.0


def test_cellranger_percent_becomes_fraction(tmp_path: Path) -> None:
    """The unit collision that would silently mis-verdict: 92.3% -> 0.923, NOT 92.3.

    The pack band is fraction_reads_in_cells warn_below 0.7 (a 0-1 fraction).
    """
    path = _write(tmp_path, "metrics_summary.csv", _CELLRANGER)
    out = parse_cellranger_metrics(path)
    assert out["fraction_reads_in_cells"] == pytest.approx(0.923)


def test_cellranger_missing_column_omits_slug(tmp_path: Path) -> None:
    text = '"Estimated Number of Cells","Mean Reads per Cell"\n"1,000","30,000"\n'
    path = _write(tmp_path, "metrics_summary.csv", text)
    out = parse_cellranger_metrics(path)
    assert out == {"estimated_cells": 1000.0}
    assert "fraction_reads_in_cells" not in out


# --------------------------------------------------------------------------- #
# simpleaf / alevin-fry — FLOOR ONLY. No confirmed machine-readable source
# (default path emits HTML), so any unrecognized/absent input -> {} which the
# caller turns into UNVERIFIED. Never a false pass; no HTML scraping.
# --------------------------------------------------------------------------- #


def test_simpleaf_unrecognized_returns_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, "alevin_report.html", "<html>not machine readable</html>")
    assert parse_simpleaf_metrics(path) == {}


def test_simpleaf_absent_path_returns_empty(tmp_path: Path) -> None:
    assert parse_simpleaf_metrics(tmp_path / "does_not_exist.json") == {}
