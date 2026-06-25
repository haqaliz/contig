from contig.models import QCResult
from contig.verification.rule_pack import (
    AMPLISEQ_RULE_PACK,
    MAG_RULE_PACK,
    METHYLSEQ_RULE_PACK,
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


def test_variant_pack_ts_tv_and_het_hom_are_warn_only():
    # The activated germline plausibility rules are WARN-capped in this slice: no
    # FAIL band. mean_coverage is unchanged (it may keep its fail band).
    by_check = {c["check"]: c for c in VARIANT_RULE_PACK}
    for name in ("ts_tv_ratio", "het_hom_ratio"):
        assert "fail_below" not in by_check[name]
        assert "fail_above" not in by_check[name]


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


# --- methyl-seq QC rule pack (PRD contract D) ----------------------------------


def test_rule_pack_for_methylseq_returns_the_methylseq_pack():
    assert rule_pack_for("methylseq") is METHYLSEQ_RULE_PACK


def test_methylseq_pack_covers_the_core_bisulfite_metrics():
    metrics = {c["metric"] for c in METHYLSEQ_RULE_PACK}
    assert "percent_bs_conversion" in metrics
    assert "percent_aligned" in metrics
    assert "percent_duplication" in metrics


def _healthy_methylseq_sample():
    # A clean bisulfite run: near-complete conversion, good mapping efficiency,
    # modest duplication.
    return {
        "percent_bs_conversion": 99.5,
        "percent_aligned": 75.0,
        "percent_duplication": 12.0,
    }


def test_healthy_methylseq_sample_passes_every_check():
    results = evaluate({"BS1": _healthy_methylseq_sample()}, METHYLSEQ_RULE_PACK)
    assert len(results) == 3
    assert all(r.status == "pass" for r in results)


def test_low_bisulfite_conversion_fails():
    # Incomplete conversion leaves unconverted cytosines read as methylated, the
    # canonical methyl-seq "ran but wrong".
    sample = _healthy_methylseq_sample() | {"percent_bs_conversion": 90.0}
    results = evaluate({"BAD": sample}, METHYLSEQ_RULE_PACK)
    conv = [r for r in results if r.value == 90.0]
    assert conv and any(r.status == "fail" for r in conv)


def test_low_mapping_efficiency_fails():
    sample = _healthy_methylseq_sample() | {"percent_aligned": 20.0}
    results = evaluate({"BAD": sample}, METHYLSEQ_RULE_PACK)
    aln = [r for r in results if r.value == 20.0]
    assert aln and any(r.status == "fail" for r in aln)


def test_high_duplication_fails():
    sample = _healthy_methylseq_sample() | {"percent_duplication": 85.0}
    results = evaluate({"BAD": sample}, METHYLSEQ_RULE_PACK)
    dup = [r for r in results if r.value == 85.0]
    assert dup and any(r.status == "fail" for r in dup)


def test_methylseq_goal_routes_through_registry_to_pack_that_fires_pass_and_fail():
    from contig.registry import assay_for_pipeline, match_assay, select_pipeline

    assay = match_assay("measure DNA methylation with bisulfite sequencing")
    assert assay == "methylseq"
    pipeline = select_pipeline(assay).pipeline
    assert assay_for_pipeline(pipeline) == "methylseq"

    pack = rule_pack_for(assay)
    healthy = evaluate({"OK": _healthy_methylseq_sample()}, pack)
    assert healthy and all(r.status == "pass" for r in healthy)
    broken = evaluate(
        {"BAD": _healthy_methylseq_sample() | {"percent_bs_conversion": 80.0}}, pack
    )
    assert any(r.status == "fail" for r in broken)


# --- 16S amplicon QC rule pack (PRD contract D) --------------------------------


def test_rule_pack_for_ampliseq_returns_the_ampliseq_pack():
    assert rule_pack_for("ampliseq") is AMPLISEQ_RULE_PACK


def test_ampliseq_pack_covers_the_core_dada2_metrics():
    metrics = {c["metric"] for c in AMPLISEQ_RULE_PACK}
    assert "percent_retained" in metrics
    assert "asv_count" in metrics
    assert "input_reads" in metrics


def _healthy_ampliseq_sample():
    # A clean 16S run: most reads survive DADA2, a reasonable ASV count, and
    # enough depth per sample.
    return {
        "percent_retained": 75.0,
        "asv_count": 450.0,
        "input_reads": 40000.0,
    }


def test_healthy_ampliseq_sample_passes_every_check():
    results = evaluate({"M1": _healthy_ampliseq_sample()}, AMPLISEQ_RULE_PACK)
    assert len(results) == 3
    assert all(r.status == "pass" for r in results)


def test_low_read_retention_through_dada2_fails():
    # Most reads discarded by DADA2 filtering/denoising signals a bad run.
    sample = _healthy_ampliseq_sample() | {"percent_retained": 10.0}
    results = evaluate({"BAD": sample}, AMPLISEQ_RULE_PACK)
    ret = [r for r in results if r.value == 10.0]
    assert ret and any(r.status == "fail" for r in ret)


def test_too_few_asvs_fails():
    sample = _healthy_ampliseq_sample() | {"asv_count": 3.0}
    results = evaluate({"BAD": sample}, AMPLISEQ_RULE_PACK)
    asv = [r for r in results if r.value == 3.0]
    assert asv and any(r.status == "fail" for r in asv)


def test_too_shallow_sample_read_depth_fails():
    sample = _healthy_ampliseq_sample() | {"input_reads": 200.0}
    results = evaluate({"BAD": sample}, AMPLISEQ_RULE_PACK)
    depth = [r for r in results if r.value == 200.0]
    assert depth and any(r.status == "fail" for r in depth)


def test_ampliseq_goal_routes_through_registry_to_pack_that_fires_pass_and_fail():
    from contig.registry import assay_for_pipeline, match_assay, select_pipeline

    assay = match_assay("profile the 16S microbiome with DADA2")
    assert assay == "ampliseq"
    pipeline = select_pipeline(assay).pipeline
    assert assay_for_pipeline(pipeline) == "ampliseq"

    pack = rule_pack_for(assay)
    healthy = evaluate({"OK": _healthy_ampliseq_sample()}, pack)
    assert healthy and all(r.status == "pass" for r in healthy)
    broken = evaluate(
        {"BAD": _healthy_ampliseq_sample() | {"percent_retained": 5.0}}, pack
    )
    assert any(r.status == "fail" for r in broken)


# --- shotgun metagenomics QC rule pack (PRD contract D) ------------------------


def test_rule_pack_for_mag_returns_the_mag_pack():
    assert rule_pack_for("mag") is MAG_RULE_PACK


def test_mag_pack_covers_the_core_assembly_and_bin_metrics():
    metrics = {c["metric"] for c in MAG_RULE_PACK}
    assert "n50" in metrics
    assert "completeness" in metrics
    assert "contamination" in metrics


def _healthy_mag_sample():
    # A clean metagenome assembly: a decent N50, a near-complete bin with low
    # contamination (CheckM style completeness/contamination percentages).
    return {
        "n50": 25000.0,
        "completeness": 92.0,
        "contamination": 2.0,
    }


def test_healthy_mag_sample_passes_every_check():
    results = evaluate({"BIN1": _healthy_mag_sample()}, MAG_RULE_PACK)
    assert len(results) == 3
    assert all(r.status == "pass" for r in results)


def test_low_assembly_n50_fails():
    # A fragmented assembly (tiny N50) is the canonical metagenomics "ran but wrong".
    sample = _healthy_mag_sample() | {"n50": 300.0}
    results = evaluate({"BAD": sample}, MAG_RULE_PACK)
    n50 = [r for r in results if r.value == 300.0]
    assert n50 and any(r.status == "fail" for r in n50)


def test_low_bin_completeness_fails():
    sample = _healthy_mag_sample() | {"completeness": 30.0}
    results = evaluate({"BAD": sample}, MAG_RULE_PACK)
    comp = [r for r in results if r.value == 30.0]
    assert comp and any(r.status == "fail" for r in comp)


def test_high_bin_contamination_fails():
    sample = _healthy_mag_sample() | {"contamination": 40.0}
    results = evaluate({"BAD": sample}, MAG_RULE_PACK)
    cont = [r for r in results if r.value == 40.0]
    assert cont and any(r.status == "fail" for r in cont)


def test_mag_goal_routes_through_registry_to_pack_that_fires_pass_and_fail():
    from contig.registry import assay_for_pipeline, match_assay, select_pipeline

    assay = match_assay("assemble a shotgun metagenome and recover MAGs")
    assert assay == "mag"
    pipeline = select_pipeline(assay).pipeline
    assert assay_for_pipeline(pipeline) == "mag"

    pack = rule_pack_for(assay)
    healthy = evaluate({"OK": _healthy_mag_sample()}, pack)
    assert healthy and all(r.status == "pass" for r in healthy)
    broken = evaluate({"BAD": _healthy_mag_sample() | {"contamination": 50.0}}, pack)
    assert any(r.status == "fail" for r in broken)
