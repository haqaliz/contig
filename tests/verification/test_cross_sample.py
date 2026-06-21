"""Tests for cross-sample QC consistency checks (ARCHITECTURE §6.4)."""

from __future__ import annotations

from contig.verification.cross_sample import (
    check_library_size_skew,
    check_metric_outliers,
    check_min_sample_count,
    evaluate_cross_sample,
)


def test_library_size_skew_balanced_passes() -> None:
    metrics = {
        "S1": {"total_reads": 1_000_000.0},
        "S2": {"total_reads": 1_200_000.0},
        "S3": {"total_reads": 900_000.0},
    }
    result = check_library_size_skew(metrics)
    assert result is not None
    assert result.status == "pass"


def test_library_size_skew_tiny_library_fails() -> None:
    metrics = {
        "S1": {"total_reads": 1_000_000.0},
        "S2": {"total_reads": 1_200_000.0},
        "S3": {"total_reads": 90_000.0},
    }
    result = check_library_size_skew(metrics)
    assert result is not None
    assert result.status == "fail"
    # value carries the ratio: 1.2M / 90k ~= 13.3, past fail_ratio of 10.
    assert result.value is not None
    assert result.value >= 10.0


def test_library_size_skew_warn_band_warns() -> None:
    # ratio = 5.0: past warn_ratio (3.0) but short of fail_ratio (10.0).
    metrics = {
        "S1": {"total_reads": 1_000_000.0},
        "S2": {"total_reads": 5_000_000.0},
    }
    result = check_library_size_skew(metrics)
    assert result is not None
    assert result.status == "warn"
    assert result.value == 5.0


def test_library_size_skew_none_when_under_two_samples() -> None:
    # Only one sample carries the metric -> nothing to compare against.
    metrics = {
        "S1": {"total_reads": 1_000_000.0},
        "S2": {"other_metric": 42.0},
    }
    assert check_library_size_skew(metrics) is None


def test_min_sample_count_below_threshold_fails() -> None:
    metrics = {"S1": {"total_reads": 1_000_000.0}}
    result = check_min_sample_count(metrics, min_samples=2)
    assert result.status == "fail"
    assert result.value == 1.0


def test_min_sample_count_at_threshold_passes() -> None:
    metrics = {
        "S1": {"total_reads": 1_000_000.0},
        "S2": {"total_reads": 1_200_000.0},
    }
    result = check_min_sample_count(metrics, min_samples=2)
    assert result.status == "pass"
    assert result.value == 2.0


def test_min_sample_count_collapses_fastqc_per_read_rows():
    # One biological sample with its two FastQC per-read rows must count as ONE,
    # so a single-sample run correctly fails the >=2 replicate gate.
    from contig.verification.cross_sample import check_min_sample_count
    metrics = {
        "WT_REP1": {"uniquely_mapped_percent": 90.0},
        "WT_REP1 Read 1": {"percent_gc": 48.0},
        "WT_REP1 Read 2": {"percent_gc": 47.0},
    }
    result = check_min_sample_count(metrics, min_samples=2)
    assert result.value == 1.0
    assert result.status == "fail"


def test_min_sample_count_counts_distinct_samples_not_read_rows():
    from contig.verification.cross_sample import check_min_sample_count
    metrics = {
        "WT_REP1": {"x": 1.0}, "WT_REP1 Read 1": {"x": 1.0}, "WT_REP1 Read 2": {"x": 1.0},
        "WT_REP2": {"x": 1.0}, "WT_REP2 Read 1": {"x": 1.0},
    }
    result = check_min_sample_count(metrics, min_samples=2)
    assert result.value == 2.0
    assert result.status == "pass"


def test_metric_outliers_flags_clear_outlier() -> None:
    # S4 sits far from a tight cluster -> flagged as a warn naming the sample.
    metrics = {
        "S1": {"gc_percent": 50.0},
        "S2": {"gc_percent": 51.0},
        "S3": {"gc_percent": 49.0},
        "S4": {"gc_percent": 90.0},
    }
    results = check_metric_outliers(metrics, metric="gc_percent")
    assert len(results) == 1
    flagged = results[0]
    assert flagged.status == "warn"
    assert flagged.check == "outlier:gc_percent:S4"
    assert flagged.value == 90.0


def test_metric_outliers_none_when_consistent() -> None:
    metrics = {
        "S1": {"gc_percent": 50.0},
        "S2": {"gc_percent": 51.0},
        "S3": {"gc_percent": 49.0},
    }
    assert check_metric_outliers(metrics, metric="gc_percent") == []


def test_evaluate_cross_sample_combines_checks_with_skew() -> None:
    # 3 balanced samples + one tiny library: expect the min-count check (pass)
    # plus a library-size skew check that is included because it is applicable.
    metrics = {
        "S1": {"total_reads": 1_000_000.0},
        "S2": {"total_reads": 1_200_000.0},
        "S3": {"total_reads": 90_000.0},
    }
    results = evaluate_cross_sample(metrics)
    checks = [r.check for r in results]
    assert "min_sample_count" in checks
    assert "library_size_skew:total_reads" in checks


def test_metric_outliers_none_when_under_three_samples() -> None:
    # Two samples is too few to establish a robust median/MAD baseline.
    metrics = {
        "S1": {"gc_percent": 50.0},
        "S2": {"gc_percent": 90.0},
    }
    assert check_metric_outliers(metrics, metric="gc_percent") == []
