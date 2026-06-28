"""Tests for evaluate_rnaseq_plausibility (Phase 2, C3 RNA-seq slice).

All tests use synthetic metrics dicts — no files, no MultiQC parsing.
The contract:
- in-band metric      → pass
- out-of-band metric  → warn, never fail (WARN-capped plausibility pack)
- metric absent       → unverified, value None, kind "metric"
- empty metrics dict  → empty list, no crash
"""

from contig.verification.rnaseq_plausibility import evaluate_rnaseq_plausibility


# ---------------------------------------------------------------------------
# duplication_rate / percent_duplication
# ---------------------------------------------------------------------------


def test_duplication_rate_inband_is_pass():
    """In-band percent_duplication → duplication_rate:<sample> pass, value preserved."""
    results = evaluate_rnaseq_plausibility({"S1": {"percent_duplication": 30.0}})
    matches = [r for r in results if r.check == "duplication_rate:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "pass"
    assert r.kind == "metric"
    assert r.value == 30.0


def test_duplication_rate_outofband_is_warn_never_fail():
    """Out-of-band percent_duplication (above warn_above=80) → warn, never fail."""
    results = evaluate_rnaseq_plausibility({"S1": {"percent_duplication": 95.0}})
    matches = [r for r in results if r.check == "duplication_rate:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "warn"
    assert r.status != "fail"


def test_duplication_rate_missing_is_unverified():
    """Missing percent_duplication → duplication_rate:<sample> unverified, value None."""
    results = evaluate_rnaseq_plausibility({"S1": {}})
    matches = [r for r in results if r.check == "duplication_rate:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "unverified"
    assert r.value is None
    assert r.kind == "metric"


# ---------------------------------------------------------------------------
# rrna_contamination / percent_rRNA
# ---------------------------------------------------------------------------


def test_rrna_contamination_inband_is_pass():
    """In-band percent_rRNA → rrna_contamination:<sample> pass, value preserved."""
    results = evaluate_rnaseq_plausibility({"S1": {"percent_rRNA": 2.0}})
    matches = [r for r in results if r.check == "rrna_contamination:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "pass"
    assert r.kind == "metric"
    assert r.value == 2.0


def test_rrna_contamination_outofband_is_warn_never_fail():
    """Out-of-band percent_rRNA (above warn_above=10) → warn, never fail."""
    results = evaluate_rnaseq_plausibility({"S1": {"percent_rRNA": 25.0}})
    matches = [r for r in results if r.check == "rrna_contamination:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "warn"
    assert r.status != "fail"


def test_rrna_contamination_missing_is_unverified():
    """Missing percent_rRNA → rrna_contamination:<sample> unverified, value None."""
    results = evaluate_rnaseq_plausibility({"S1": {}})
    matches = [r for r in results if r.check == "rrna_contamination:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "unverified"
    assert r.value is None
    assert r.kind == "metric"


# ---------------------------------------------------------------------------
# Both metrics absent → two unverified results, zero PASS
# ---------------------------------------------------------------------------


def test_both_metrics_absent_gives_two_unverified_no_pass():
    """Sample with both plausibility metrics absent → two unverified, no pass."""
    results = evaluate_rnaseq_plausibility({"S1": {}})
    assert len(results) == 2
    assert all(r.status == "unverified" for r in results)
    assert not any(r.status == "pass" for r in results)


# ---------------------------------------------------------------------------
# Multi-sample: one sample in-band, another missing the metric
# ---------------------------------------------------------------------------


def test_multisample_inband_and_missing():
    """Two samples: S1 has percent_duplication (in-band), S2 has neither.

    Asserts per-sample iteration: S1 gets a pass for duplication_rate,
    S2 gets an unverified for duplication_rate.
    """
    metrics = {
        "S1": {"percent_duplication": 30.0},
        "S2": {},
    }
    results = evaluate_rnaseq_plausibility(metrics)

    s1_dup = [r for r in results if r.check == "duplication_rate:S1"]
    s2_dup = [r for r in results if r.check == "duplication_rate:S2"]

    assert len(s1_dup) == 1
    assert s1_dup[0].status == "pass"
    assert s1_dup[0].value == 30.0

    assert len(s2_dup) == 1
    assert s2_dup[0].status == "unverified"
    assert s2_dup[0].value is None


# ---------------------------------------------------------------------------
# Empty metrics dict → empty list
# ---------------------------------------------------------------------------


def test_empty_metrics_returns_empty_list():
    """Empty top-level metrics dict → empty list, no crash."""
    results = evaluate_rnaseq_plausibility({})
    assert results == []
