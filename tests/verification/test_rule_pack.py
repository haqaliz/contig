from contig.models import QCResult
from contig.verification.rule_pack import (
    RNASEQ_RULE_PACK,
    VARIANT_RULE_PACK,
    evaluate,
    rule_pack_for,
)


def test_value_at_or_above_warn_below_passes():
    pack = [
        {
            "check": "alignment_rate",
            "metric": "uniquely_mapped_percent",
            "warn_below": 60.0,
            "fail_below": 40.0,
            "message": "uniquely mapped reads",
        }
    ]
    results = evaluate({"S1": {"uniquely_mapped_percent": 92.5}}, pack)
    assert len(results) == 1
    assert results[0].status == "pass"


def _single_check_pack():
    return [
        {
            "check": "alignment_rate",
            "metric": "uniquely_mapped_percent",
            "warn_below": 60.0,
            "fail_below": 40.0,
            "message": "uniquely mapped reads",
        }
    ]


def test_value_below_fail_below_fails():
    results = evaluate({"S1": {"uniquely_mapped_percent": 12.0}}, _single_check_pack())
    assert results[0].status == "fail"


def test_value_between_fail_and_warn_warns():
    results = evaluate({"S1": {"uniquely_mapped_percent": 50.0}}, _single_check_pack())
    assert results[0].status == "warn"


def test_result_carries_value_and_expected_range():
    results = evaluate({"S1": {"uniquely_mapped_percent": 92.5}}, _single_check_pack())
    assert results[0].value == 92.5
    assert results[0].expected_range == ">= 60.0"


def test_missing_metric_is_skipped():
    pack = [
        {
            "check": "alignment_rate",
            "metric": "uniquely_mapped_percent",
            "warn_below": 60.0,
            "fail_below": 40.0,
            "message": "uniquely mapped reads",
        },
        {
            "check": "assignment_rate",
            "metric": "percent_assigned",
            "warn_below": 60.0,
            "fail_below": 40.0,
            "message": "assigned reads",
        },
    ]
    results = evaluate({"S1": {"uniquely_mapped_percent": 92.5}}, pack)
    assert len(results) == 1
    assert results[0].check == "alignment_rate:S1"


def test_two_samples_produce_results_for_both():
    metrics = {
        "S1": {"uniquely_mapped_percent": 92.5},
        "S2": {"uniquely_mapped_percent": 30.0},
    }
    results = evaluate(metrics, _single_check_pack())
    assert len(results) == 2
    checks = {r.check for r in results}
    assert checks == {"alignment_rate:S1", "alignment_rate:S2"}


def test_rnaseq_rule_pack_non_empty_and_covers_alignment():
    assert RNASEQ_RULE_PACK
    metrics = {c["metric"] for c in RNASEQ_RULE_PACK}
    assert "uniquely_mapped_percent" in metrics


def test_empty_rule_pack_yields_no_results():
    results = evaluate({"S1": {"uniquely_mapped_percent": 92.5}}, [])
    assert results == []


# --- range checks (optional upper bounds) --------------------------------------


def _ts_tv_range_pack():
    return [
        {
            "check": "ts_tv_ratio",
            "metric": "ts_tv",
            "fail_below": 1.5,
            "warn_below": 1.8,
            "warn_above": 2.4,
            "fail_above": 3.0,
            "message": "transition/transversion ratio",
        }
    ]


def test_value_inside_range_passes():
    results = evaluate({"S1": {"ts_tv": 2.0}}, _ts_tv_range_pack())
    assert results[0].status == "pass"


def test_value_below_fail_below_fails_in_range_check():
    results = evaluate({"S1": {"ts_tv": 1.4}}, _ts_tv_range_pack())
    assert results[0].status == "fail"


def test_value_above_fail_above_fails():
    results = evaluate({"S1": {"ts_tv": 3.5}}, _ts_tv_range_pack())
    assert results[0].status == "fail"


def test_value_above_warn_above_below_fail_above_warns():
    results = evaluate({"S1": {"ts_tv": 2.5}}, _ts_tv_range_pack())
    assert results[0].status == "warn"


def test_lower_bound_only_check_is_backward_compatible():
    # An existing-style check with no *_above keys still behaves as before.
    pack = _single_check_pack()
    fail = evaluate({"S1": {"uniquely_mapped_percent": 12.0}}, pack)
    assert fail[0].status == "fail"
    ok = evaluate({"S1": {"uniquely_mapped_percent": 92.5}}, pack)
    assert ok[0].status == "pass"


# --- variant-calling rule pack + selection -------------------------------------


def test_variant_rule_pack_non_empty_and_covers_ts_tv():
    assert VARIANT_RULE_PACK
    metrics = {c["metric"] for c in VARIANT_RULE_PACK}
    assert "ts_tv" in metrics


def test_rule_pack_for_known_assays():
    assert rule_pack_for("rnaseq") is RNASEQ_RULE_PACK
    assert rule_pack_for("variant_calling") is VARIANT_RULE_PACK


def test_rule_pack_for_unknown_assay_raises_naming_assay():
    try:
        rule_pack_for("nope")
    except ValueError as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown assay")
