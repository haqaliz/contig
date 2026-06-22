from contig.models import QCResult
from contig.verification.rule_pack import (
    RNASEQ_RULE_PACK,
    SCRNASEQ_RULE_PACK,
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


def test_rnaseq_pack_covers_real_salmon_mapping_rate():
    # Real nf-core MultiQC reports the pseudo-alignment rate as salmon
    # `percent_mapped`, not the synthetic `uniquely_mapped_percent`. The pack
    # must verify it, or real runs are only structurally checked.
    assert "percent_mapped" in {c["metric"] for c in RNASEQ_RULE_PACK}


def test_real_healthy_salmon_mapping_rate_passes():
    # 80.99% pseudo-aligned (a real WT_REP1 value) is a healthy run.
    results = evaluate({"WT_REP1": {"percent_mapped": 80.99}}, RNASEQ_RULE_PACK)
    mapping = [r for r in results if r.value == 80.99]
    assert mapping and all(r.status == "pass" for r in mapping)


def test_low_salmon_mapping_rate_fails():
    # A sample that barely pseudo-aligned is the canonical "ran but wrong".
    results = evaluate({"BAD": {"percent_mapped": 12.0}}, RNASEQ_RULE_PACK)
    mapping = [r for r in results if r.value == 12.0]
    assert mapping and any(r.status == "fail" for r in mapping)


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


# --- scRNA-seq per-cell QC rule pack (PRD contract D) --------------------------


def test_rule_pack_for_scrnaseq_returns_the_scrnaseq_pack():
    assert rule_pack_for("scrnaseq") is SCRNASEQ_RULE_PACK


def test_scrnaseq_pack_covers_the_per_cell_qc_metrics():
    metrics = {c["metric"] for c in SCRNASEQ_RULE_PACK}
    assert "estimated_cells" in metrics
    assert "median_genes_per_cell" in metrics
    assert "fraction_reads_in_cells" in metrics
    assert "pct_reads_mito" in metrics


def _healthy_scrnaseq_sample():
    # A clean 10x run: thousands of cells, hundreds of median genes, most reads
    # inside cells, modest mitochondrial fraction.
    return {
        "estimated_cells": 5000.0,
        "median_genes_per_cell": 1800.0,
        "fraction_reads_in_cells": 0.85,
        "pct_reads_mito": 8.0,
    }


def test_healthy_scrnaseq_sample_passes_every_check():
    results = evaluate({"SAMPLE_10x": _healthy_scrnaseq_sample()}, SCRNASEQ_RULE_PACK)
    assert len(results) == 4
    assert all(r.status == "pass" for r in results)


def test_too_few_estimated_cells_fails():
    # A near-empty run (a failed capture) is the canonical "ran but wrong".
    sample = _healthy_scrnaseq_sample() | {"estimated_cells": 20.0}
    results = evaluate({"BAD": sample}, SCRNASEQ_RULE_PACK)
    cell = [r for r in results if r.value == 20.0]
    assert cell and any(r.status == "fail" for r in cell)


def test_low_median_genes_per_cell_fails():
    sample = _healthy_scrnaseq_sample() | {"median_genes_per_cell": 50.0}
    results = evaluate({"BAD": sample}, SCRNASEQ_RULE_PACK)
    genes = [r for r in results if r.value == 50.0]
    assert genes and any(r.status == "fail" for r in genes)


def test_low_fraction_reads_in_cells_fails():
    # Most reads landing in ambient/empty droplets signals a bad capture.
    sample = _healthy_scrnaseq_sample() | {"fraction_reads_in_cells": 0.20}
    results = evaluate({"BAD": sample}, SCRNASEQ_RULE_PACK)
    frac = [r for r in results if r.value == 0.20]
    assert frac and any(r.status == "fail" for r in frac)


def test_high_mito_fraction_fails():
    # A high mitochondrial read fraction flags stressed or dying cells.
    sample = _healthy_scrnaseq_sample() | {"pct_reads_mito": 60.0}
    results = evaluate({"BAD": sample}, SCRNASEQ_RULE_PACK)
    mito = [r for r in results if r.value == 60.0]
    assert mito and any(r.status == "fail" for r in mito)


def test_scrnaseq_goal_routes_through_registry_to_pack_that_fires_pass_and_fail():
    # End-to-end: a single-cell goal maps to the scrnaseq assay, whose pipeline
    # maps back to scrnaseq, whose rule pack passes a healthy sample and fails a
    # broken one. This is the path the CLI walks (goal -> assay -> rule_pack_for).
    from contig.registry import assay_for_pipeline, match_assay, select_pipeline

    assay = match_assay("cluster cells from a single-cell experiment")
    assert assay == "scrnaseq"
    pipeline = select_pipeline(assay).pipeline
    assert assay_for_pipeline(pipeline) == "scrnaseq"

    pack = rule_pack_for(assay)
    healthy = evaluate({"OK": _healthy_scrnaseq_sample()}, pack)
    assert healthy and all(r.status == "pass" for r in healthy)
    broken = evaluate({"BAD": _healthy_scrnaseq_sample() | {"estimated_cells": 5.0}}, pack)
    assert any(r.status == "fail" for r in broken)
