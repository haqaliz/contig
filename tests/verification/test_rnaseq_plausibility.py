"""Tests for evaluate_rnaseq_plausibility (Phase 2, C3 RNA-seq slice).

All tests use synthetic metrics dicts — no files, no MultiQC parsing.
The contract:
- duplication_rate    → informational only, no band: any value in [0, 1]
                        passes verbatim (never rescaled); a present value
                        outside [0, 1] is refused as unverified rather than
                        rescaled (see the "unit": "fraction" guard in
                        evaluate_rnaseq_plausibility).
- rrna_contamination  → in-band pass, out-of-band warn, never fail
                        (WARN-capped plausibility pack, untouched by this
                        phase).
- metric absent       → unverified, value None, kind "metric"
- empty metrics dict  → empty list, no crash
"""

from contig.verification.rnaseq_plausibility import evaluate_rnaseq_plausibility


# ---------------------------------------------------------------------------
# duplication_rate / PERCENT_DUPLICATION (Picard, via MultiQC)
#
# Two compounding fixes are pinned here: the real MultiQC key is uppercase
# (PERCENT_DUPLICATION, not percent_duplication), and Picard's own value is a
# raw 0-1 fraction despite the name ("PERCENT"), so there is no band — only a
# range guard.
# ---------------------------------------------------------------------------


def test_duplication_rate_pass_reports_fraction_verbatim_no_rescale():
    """0.96 (96% duplicated) is reported as 0.96, never multiplied by 100."""
    results = evaluate_rnaseq_plausibility({"S1": {"PERCENT_DUPLICATION": 0.96}})
    matches = [r for r in results if r.check == "duplication_rate:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "pass"
    assert r.value == 0.96
    assert r.kind == "metric"


def test_duplication_rate_never_warns_or_fails_across_full_range():
    """Informational-only contract: every fraction in [0, 1] passes, no exceptions.

    A deep/high-input library legitimately exceeds 90% duplication (see the
    pack's own docstring), so a band would WARN on a protocol the pack itself
    calls legitimate. This sweep pins that no such band exists.
    """
    for frac in (0.0, 0.3, 0.9, 0.95, 1.0):
        results = evaluate_rnaseq_plausibility({"S1": {"PERCENT_DUPLICATION": frac}})
        matches = [r for r in results if r.check == "duplication_rate:S1"]
        assert len(matches) == 1
        assert matches[0].status == "pass"


def test_duplication_rate_boundary_1_0_is_valid_and_passes():
    """1.0 (100% duplicated) is a physically valid fraction, not a guard violation."""
    results = evaluate_rnaseq_plausibility({"S1": {"PERCENT_DUPLICATION": 1.0}})
    matches = [r for r in results if r.check == "duplication_rate:S1"]
    assert len(matches) == 1
    assert matches[0].status == "pass"
    assert matches[0].value == 1.0


def test_duplication_rate_above_1_is_unverified_never_rescaled():
    """A present value above 1.0 signals a pre-scaled (0-100) source.

    Refusing is the point: rescaling 95.0 down to 0.95 would assume the wrong
    thing silently, and a value like 0.5 would be ambiguous between "50%" and
    "0.5%" — there is no way to guess correctly, so the guard must refuse
    rather than transform.
    """
    results = evaluate_rnaseq_plausibility({"S1": {"PERCENT_DUPLICATION": 95.0}})
    matches = [r for r in results if r.check == "duplication_rate:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "unverified"
    assert r.value is None
    assert "[0, 1]" in r.message


def test_duplication_rate_below_0_is_unverified():
    """A negative fraction is physically impossible; refuse rather than pass it through."""
    results = evaluate_rnaseq_plausibility({"S1": {"PERCENT_DUPLICATION": -0.1}})
    matches = [r for r in results if r.check == "duplication_rate:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "unverified"
    assert r.value is None


def test_duplication_rate_old_lowercase_key_is_unverified_regression_lock():
    """The old `percent_duplication` key never matched MultiQC's real output.

    MultiQC publishes Picard's field verbatim as PERCENT_DUPLICATION
    (uppercase); the old lowercase key missed it forever. Feeding the OLD key
    must still read as unverified (metric absent under the real key), which
    proves the old lowercase-keyed test could never have caught this bug.
    """
    results = evaluate_rnaseq_plausibility({"S1": {"percent_duplication": 95.0}})
    matches = [r for r in results if r.check == "duplication_rate:S1"]
    assert len(matches) == 1
    r = matches[0]
    assert r.status == "unverified"
    assert r.value is None


def test_duplication_rate_missing_is_unverified():
    """Missing PERCENT_DUPLICATION → duplication_rate:<sample> unverified, value None."""
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
    """Two samples: S1 has PERCENT_DUPLICATION (valid fraction), S2 has neither.

    Asserts per-sample iteration: S1 gets a pass for duplication_rate,
    S2 gets an unverified for duplication_rate.
    """
    metrics = {
        "S1": {"PERCENT_DUPLICATION": 0.30},
        "S2": {},
    }
    results = evaluate_rnaseq_plausibility(metrics)

    s1_dup = [r for r in results if r.check == "duplication_rate:S1"]
    s2_dup = [r for r in results if r.check == "duplication_rate:S2"]

    assert len(s1_dup) == 1
    assert s1_dup[0].status == "pass"
    assert s1_dup[0].value == 0.30

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
