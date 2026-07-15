from contig.models import QCResult
from contig.verification.rule_pack import (
    AMPLISEQ_RULE_PACK,
    MAG_RULE_PACK,
    METHYLSEQ_RULE_PACK,
    RNASEQ_RULE_PACK,
    SCRNASEQ_RULE_PACK,
    SOMATIC_PLAUSIBILITY_PACK,
    VARIANT_RULE_PACK,
    _status_for,
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


def test_variant_pack_ts_tv_and_het_hom_have_fail_bands():
    # The germline plausibility rules now carry gross-implausibility FAIL bands
    # (WES-safe engineering tripwires), on top of their existing WARN bands.
    by_check = {c["check"]: c for c in VARIANT_RULE_PACK}
    assert by_check["ts_tv_ratio"]["fail_below"] == 1.2
    assert by_check["ts_tv_ratio"]["fail_above"] == 3.6
    assert by_check["het_hom_ratio"]["fail_below"] == 1.0
    assert by_check["het_hom_ratio"]["fail_above"] == 3.0


def test_variant_count_has_fail_below_only():
    # variant_count gains a hard floor (empty/near-empty call set FAILs) but keeps
    # its upper bound a SOFT WARN ceiling: no fail_above.
    by_check = {c["check"]: c for c in VARIANT_RULE_PACK}
    assert by_check["variant_count"]["fail_below"] == 1
    assert "fail_above" not in by_check["variant_count"]


def test_germline_bands_are_well_ordered():
    # Invariant (PRD R8): for every germline rule, the bounds that are present must
    # be ordered fail_below <= warn_below <= warn_above <= fail_above.
    for rule in VARIANT_RULE_PACK:
        bounds = [
            rule.get(key)
            for key in ("fail_below", "warn_below", "warn_above", "fail_above")
        ]
        present = [b for b in bounds if b is not None]
        assert present == sorted(present), f"{rule['check']!r} bands out of order"


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
    # Exactly the three "did it run" metrics the base nf-core/scrnaseq pipeline
    # actually emits. pct_reads_mito (and doublet rate) need a downstream scanpy/
    # scDblFinder step the base pipeline never runs, so they are deferred, not shipped.
    metrics = {c["metric"] for c in SCRNASEQ_RULE_PACK}
    assert metrics == {
        "estimated_cells",
        "median_genes_per_cell",
        "fraction_reads_in_cells",
    }


def test_scrnaseq_pack_has_no_dead_mito_check():
    # The base pipeline never produces pct_reads_mito, so no check may reference it.
    assert all(c["metric"] != "pct_reads_mito" for c in SCRNASEQ_RULE_PACK)
    assert all(c["check"] != "pct_reads_mito" for c in SCRNASEQ_RULE_PACK)


def test_scrnaseq_pack_has_exactly_three_checks_each_with_a_fail_band():
    assert len(SCRNASEQ_RULE_PACK) == 3
    # Each surviving check keeps its FAIL band (a legitimate did-it-run pack).
    assert all("fail_below" in c for c in SCRNASEQ_RULE_PACK)


def _healthy_scrnaseq_sample():
    # A clean 10x run: thousands of cells, hundreds of median genes, most reads
    # inside cells.
    return {
        "estimated_cells": 5000.0,
        "median_genes_per_cell": 1800.0,
        "fraction_reads_in_cells": 0.85,
    }


def test_healthy_scrnaseq_sample_passes_every_check():
    results = evaluate({"SAMPLE_10x": _healthy_scrnaseq_sample()}, SCRNASEQ_RULE_PACK)
    assert len(results) == 3
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


def _estimated_cells_check():
    return next(c for c in SCRNASEQ_RULE_PACK if c["metric"] == "estimated_cells")


def test_status_for_near_empty_estimated_cells_fails():
    # A near-empty capture (a failed run) lands below the fail band.
    assert _status_for(50.0, _estimated_cells_check()) == "fail"


def test_status_for_healthy_estimated_cells_passes():
    assert _status_for(5000.0, _estimated_cells_check()) == "pass"


def test_status_for_mid_band_estimated_cells_warns():
    # Between fail_below (100) and warn_below (500): a suspicious but not failed run.
    assert _status_for(300.0, _estimated_cells_check()) == "warn"


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


# --- RNA-seq biological-plausibility pack (C3 slice, Phase 1) ------------------


def test_rnaseq_plausibility_pack_is_importable():
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK

    assert RNASEQ_PLAUSIBILITY_PACK


def test_rnaseq_plausibility_pack_covers_duplication_and_rrna():
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK

    checks = {r["check"] for r in RNASEQ_PLAUSIBILITY_PACK}
    assert "duplication_rate" in checks
    assert "rrna_contamination" in checks


def test_rnaseq_plausibility_pack_rules_have_warn_above():
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK

    for rule in RNASEQ_PLAUSIBILITY_PACK:
        assert "warn_above" in rule, f"{rule['check']!r} missing warn_above"


def test_rnaseq_plausibility_pack_rules_have_no_fail_keys():
    # WARN-cap guarantee: no fail_below / fail_above in the plausibility pack.
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK

    for rule in RNASEQ_PLAUSIBILITY_PACK:
        assert "fail_below" not in rule, f"{rule['check']!r} has forbidden fail_below"
        assert "fail_above" not in rule, f"{rule['check']!r} has forbidden fail_above"


def test_rnaseq_plausibility_duplication_below_band_is_pass():
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK, _status_for

    rule = next(r for r in RNASEQ_PLAUSIBILITY_PACK if r["check"] == "duplication_rate")
    assert _status_for(30.0, rule) == "pass"


def test_rnaseq_plausibility_duplication_above_band_is_warn():
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK, _status_for

    rule = next(r for r in RNASEQ_PLAUSIBILITY_PACK if r["check"] == "duplication_rate")
    assert _status_for(95.0, rule) == "warn"


def test_rnaseq_plausibility_duplication_never_fails():
    # Even a value far above the band must not return "fail" (WARN-cap guarantee).
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK, _status_for

    rule = next(r for r in RNASEQ_PLAUSIBILITY_PACK if r["check"] == "duplication_rate")
    assert _status_for(99999.0, rule) != "fail"


def test_rnaseq_plausibility_rrna_below_band_is_pass():
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK, _status_for

    rule = next(r for r in RNASEQ_PLAUSIBILITY_PACK if r["check"] == "rrna_contamination")
    assert _status_for(5.0, rule) == "pass"


def test_rnaseq_plausibility_rrna_above_band_is_warn():
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK, _status_for

    rule = next(r for r in RNASEQ_PLAUSIBILITY_PACK if r["check"] == "rrna_contamination")
    assert _status_for(50.0, rule) == "warn"


def test_rnaseq_plausibility_rrna_never_fails():
    # Even a value far above the band must not return "fail" (WARN-cap guarantee).
    from contig.verification.rule_pack import RNASEQ_PLAUSIBILITY_PACK, _status_for

    rule = next(r for r in RNASEQ_PLAUSIBILITY_PACK if r["check"] == "rrna_contamination")
    assert _status_for(99999.0, rule) != "fail"


# --- RNA-seq read-composition plausibility pack (C3 slice, Phase 2) ------------


def _healthy_composition_sample():
    # A clean, CDS-dominated run (yeast test values from the plan): almost all
    # assigned tags are exonic, almost none intronic, a modest unassigned share.
    return {
        "exonic_fraction": 0.9998,
        "intronic_fraction": 0.0002,
        "unassigned_fraction": 0.112,
    }


def test_rnaseq_composition_pack_has_exactly_three_rules():
    from contig.verification.rule_pack import RNASEQ_COMPOSITION_PACK

    assert len(RNASEQ_COMPOSITION_PACK) == 3


def test_rnaseq_composition_pack_covers_exonic_intronic_unassigned():
    from contig.verification.rule_pack import RNASEQ_COMPOSITION_PACK

    metrics = {c["metric"] for c in RNASEQ_COMPOSITION_PACK}
    assert metrics == {"exonic_fraction", "intronic_fraction", "unassigned_fraction"}


def test_rnaseq_composition_pack_rules_have_no_fail_keys():
    # WARN-cap guarantee: no fail_below / fail_above anywhere in this pack.
    from contig.verification.rule_pack import RNASEQ_COMPOSITION_PACK

    for rule in RNASEQ_COMPOSITION_PACK:
        assert "fail_below" not in rule, f"{rule['check']!r} has forbidden fail_below"
        assert "fail_above" not in rule, f"{rule['check']!r} has forbidden fail_above"


def test_rnaseq_composition_pack_is_not_registered_in_rule_packs():
    # Like RNASEQ_PLAUSIBILITY_PACK/SOMATIC_PLAUSIBILITY_PACK/
    # ANNOTATION_PLAUSIBILITY_PACK, this pack is deliberately NOT selectable via
    # rule_pack_for; it is driven directly by the dedicated read_distribution gate.
    from contig.verification.rule_pack import RNASEQ_COMPOSITION_PACK, _RULE_PACKS

    assert RNASEQ_COMPOSITION_PACK not in _RULE_PACKS.values()


def test_healthy_composition_sample_passes_every_check():
    from contig.verification.rule_pack import RNASEQ_COMPOSITION_PACK

    results = evaluate({"WT_REP1": _healthy_composition_sample()}, RNASEQ_COMPOSITION_PACK)
    assert len(results) == 3
    assert all(r.status == "pass" for r in results)


def test_low_exonic_fraction_warns_never_fails():
    from contig.verification.rule_pack import RNASEQ_COMPOSITION_PACK

    sample = _healthy_composition_sample() | {"exonic_fraction": 0.10}
    results = evaluate({"BAD": sample}, RNASEQ_COMPOSITION_PACK)
    exonic = [r for r in results if r.value == 0.10]
    assert exonic and all(r.status == "warn" for r in exonic)


def test_high_intronic_fraction_warns_never_fails():
    from contig.verification.rule_pack import RNASEQ_COMPOSITION_PACK

    sample = _healthy_composition_sample() | {"intronic_fraction": 0.75}
    results = evaluate({"BAD": sample}, RNASEQ_COMPOSITION_PACK)
    intronic = [r for r in results if r.value == 0.75]
    assert intronic and all(r.status == "warn" for r in intronic)


def test_high_unassigned_fraction_warns_never_fails():
    from contig.verification.rule_pack import RNASEQ_COMPOSITION_PACK

    sample = _healthy_composition_sample() | {"unassigned_fraction": 0.90}
    results = evaluate({"BAD": sample}, RNASEQ_COMPOSITION_PACK)
    unassigned = [r for r in results if r.value == 0.90]
    assert unassigned and all(r.status == "warn" for r in unassigned)


def test_rnaseq_composition_extreme_values_never_fail():
    # WARN-cap guarantee at the scorer level: even wildly out-of-band values on
    # every metric must never produce a "fail" status.
    from contig.verification.rule_pack import RNASEQ_COMPOSITION_PACK

    sample = {
        "exonic_fraction": 0.0,
        "intronic_fraction": 1.0,
        "unassigned_fraction": 1.0,
    }
    results = evaluate({"WORST": sample}, RNASEQ_COMPOSITION_PACK)
    assert len(results) == 3
    assert all(r.status != "fail" for r in results)


# --- somatic biological-plausibility pack: fail-floor / WARN-cap guarantees ----


def test_somatic_variant_count_has_fail_below_only():
    # somatic_variant_count gains a hard floor (an empty call set FAILs) but
    # keeps its upper bound a SOFT, uncalibrated warn_above ceiling: a
    # hypermutator (MSI-high, POLE-mutant) or a WGS tumor legitimately exceeds
    # it, so a fail_above would false-FAIL real science.
    by_check = {c["check"]: c for c in SOMATIC_PLAUSIBILITY_PACK}
    assert by_check["somatic_variant_count"]["fail_below"] == 1
    assert "fail_above" not in by_check["somatic_variant_count"]


def test_somatic_bands_are_well_ordered():
    # Invariant (PRD R8): for every somatic rule, the bounds that are present must
    # be ordered fail_below <= warn_below <= warn_above <= fail_above.
    for rule in SOMATIC_PLAUSIBILITY_PACK:
        bounds = [
            rule.get(key)
            for key in ("fail_below", "warn_below", "warn_above", "fail_above")
        ]
        present = [b for b in bounds if b is not None]
        assert present == sorted(present), f"{rule['check']!r} bands out of order"


def test_somatic_vaf_rules_have_no_fail_keys():
    # Deliberate guarantee, not an oversight: tumor VAF's expected value is a
    # function of purity and clonality the code never observes, so no band can
    # separate "broken" from "legitimately low" (a low-purity tumor or a
    # subclonal population is real science, not a failed run). Unlike
    # somatic_variant_count, these two rules must stay WARN-capped forever.
    # strelka_median_vaf is additionally bounded to [0, 1] by construction, so
    # a fail_above: 1.0 there would be provably dead code on top of being
    # scientifically wrong.
    by_check = {c["check"]: c for c in SOMATIC_PLAUSIBILITY_PACK}
    for check in ("median_vaf", "strelka_median_vaf"):
        rule = by_check[check]
        assert "fail_below" not in rule, f"{check!r} has forbidden fail_below"
        assert "fail_above" not in rule, f"{check!r} has forbidden fail_above"
