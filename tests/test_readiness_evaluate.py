"""Tests for coverage metrics and readiness states."""

from pathlib import Path

from contig.readiness.caveats import load_caveats
from contig.readiness.depth import load_depth
from contig.readiness.evaluate import evaluate_target, evaluate_targets
from contig.readiness.models import ReadinessThresholds, Target
from contig.readiness.targets import load_bed_targets

FIX = Path(__file__).parent / "fixtures" / "readiness"
DEPTH = FIX / "depth.tsv"
PANEL = FIX / "panel.bed"
HOMOLOGY = FIX / "homology.bed"


def _rows():
    depths, _ = load_depth(DEPTH)
    targets = load_bed_targets(PANEL)
    caveats = load_caveats(HOMOLOGY)
    return {row.target.name: row for row in evaluate_targets(targets, depths, ReadinessThresholds(), caveats)}


def test_high_depth_without_a_caveat_is_ready():
    row = _rows()["GENE4"]
    assert row.readiness == "ready"
    assert row.mean_depth == 50
    assert row.pct_20x == 1.0
    assert row.pct_50x == 1.0
    assert row.pct_100x == 0.0
    assert row.zero_bases == 0


def test_high_depth_with_a_caveat_is_caution():
    row = _rows()["GENE1"]
    assert row.readiness == "caution"
    assert row.mean_depth == 30
    assert row.pct_20x == 1.0
    assert any("GENE1" in caveat for caveat in row.caveats)


def test_partial_coverage_is_caution_with_the_fraction_in_the_reason():
    row = _rows()["GENE2"]
    assert row.readiness == "caution"
    assert row.mean_depth == 17
    assert row.pct_20x == 0.8
    assert "80.0%" in row.reason


def test_zero_coverage_is_not_interpretable():
    row = _rows()["GENE3"]
    assert row.readiness == "not-interpretable"
    assert row.mean_depth == 0
    assert row.covered_bases == 0
    assert row.zero_bases == 50
    assert "0 covered bases" in row.reason


def test_missing_positions_are_zero_in_the_denominator():
    depths, _ = load_depth(DEPTH)
    row = evaluate_target(Target("1", 200, 250, "GENE5"), depths, ReadinessThresholds(), [])
    assert row.bases == 50
    assert row.covered_bases == 0
    assert row.zero_bases == 50
    assert row.readiness == "not-interpretable"


def test_empty_target_is_not_interpretable():
    row = evaluate_target(Target("1", 10, 10, "EMPTY"), {}, ReadinessThresholds(), [])
    assert row.bases == 0
    assert row.readiness == "not-interpretable"
    assert row.reason == "empty target"
