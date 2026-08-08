"""Tests for the verification-case scorer (C6 fold-in, aspect 1).

The scorer re-derives each case's verdict from its PRE-BAND stored signal
values under the CURRENT rule packs (threshold-sensitivity contract, PRD R1) —
never from stored statuses. The load-bearing test is the mutation control at
the top of this file: it proves a band change flips a stored value's status,
which is what separates the guard from a tautology (PRD goal 2, AC2).
"""

from __future__ import annotations

import pytest

from contig.models import VerificationCase
from contig.verify_corpus import (
    _FAMILY_PACKS,
    evaluate_verify,
    evaluate_verify_case,
)
from contig.verification.rule_pack import (
    ANNOTATION_PLAUSIBILITY_PACK,
    AMPLISEQ_RULE_PACK,
    MAG_RULE_PACK,
    METHYLSEQ_RULE_PACK,
    RNASEQ_COMPOSITION_PACK,
    RNASEQ_PLAUSIBILITY_PACK,
    RNASEQ_RULE_PACK,
    SCRNASEQ_RULE_PACK,
    SOMATIC_PLAUSIBILITY_PACK,
    VARIANT_RULE_PACK,
)


def _case(
    family: str,
    metrics: dict[str, float],
    *,
    expected: str,
    assay: str = "variant_calling",
    case_id: str = "verify-x",
) -> VerificationCase:
    return VerificationCase(
        case_id=case_id,
        description="test case",
        source="synthetic",
        assay=assay,
        inputs={family: {"S1": metrics}},
        expected_verdict=expected,  # type: ignore[arg-type]
    )


# --- mutation control (the anti-tautology pin, written FIRST) -----------------


def test_mutation_control_band_change_flips_predicted_verdict():
    # A stored ts_tv=0.5 crosses VARIANT_RULE_PACK's fail_below 1.2, so the
    # current bands predict "fail". Re-pointing the germline family at a pack
    # whose only band is fail_below 0.3 (the same check shape, one band moved)
    # must flip the SAME stored value to "pass" -- the guard is band-sensitive,
    # not a restatement of the labels. The override seam (`family_packs`) is
    # how the mutation happens without editing committed band data.
    case = _case(
        "germline",
        {"ts_tv": 0.5},
        expected="fail",
        case_id="verify-mutation-control",
    )

    assert evaluate_verify_case(case).predicted_verdict == "fail"

    mutated = [
        check for check in VARIANT_RULE_PACK if check["metric"] != "ts_tv"
    ] + [
        {
            "check": "ts_tv_ratio",
            "metric": "ts_tv",
            "fail_below": 0.3,
            "message": "mutated band for the mutation control",
        }
    ]
    flipped = evaluate_verify_case(case, family_packs={"germline": mutated})
    assert flipped.predicted_verdict == "pass"
    assert flipped.matched is False  # labeled "fail", now predicted "pass"


# --- family -> pack table ------------------------------------------------------


def test_family_pack_table_maps_each_static_family():
    assert _FAMILY_PACKS["germline"] is VARIANT_RULE_PACK
    assert _FAMILY_PACKS["rnaseq_plausibility"] is RNASEQ_PLAUSIBILITY_PACK
    assert _FAMILY_PACKS["rnaseq_composition"] is RNASEQ_COMPOSITION_PACK
    assert _FAMILY_PACKS["somatic_plausibility"] is SOMATIC_PLAUSIBILITY_PACK
    assert _FAMILY_PACKS["annotation_plausibility"] is ANNOTATION_PLAUSIBILITY_PACK
    assert _FAMILY_PACKS["scrnaseq"] is SCRNASEQ_RULE_PACK
    assert _FAMILY_PACKS["methylseq"] is METHYLSEQ_RULE_PACK
    assert _FAMILY_PACKS["ampliseq"] is AMPLISEQ_RULE_PACK
    assert _FAMILY_PACKS["mag"] is MAG_RULE_PACK


def test_multiqc_family_resolves_per_assay():
    case = _case(
        "multiqc",
        {"uniquely_mapped_percent": 75.0, "percent_assigned": 70.0, "percent_mapped": 80.0},
        expected="pass",
        assay="rnaseq",
    )
    result = evaluate_verify_case(case)
    assert result.families["multiqc"] == "pass"
    assert result.predicted_verdict == "pass"
    assert result.matched is True


# --- per-family reduction + predicted verdict ----------------------------------


def test_passing_case_matches():
    case = _case(
        "germline",
        {"ts_tv": 2.0, "het_hom": 1.8, "variant_count": 40000.0, "mean_coverage": 35.0},
        expected="pass",
    )
    result = evaluate_verify_case(case)
    assert result.predicted_verdict == "pass"
    assert result.matched is True
    assert result.divergence == []


def test_failing_case_matches():
    case = _case("germline", {"ts_tv": 0.5}, expected="fail")
    result = evaluate_verify_case(case)
    assert result.predicted_verdict == "fail"
    assert result.matched is True


def test_warn_case_matches():
    case = _case("germline", {"ts_tv": 1.5}, expected="warn")
    result = evaluate_verify_case(case)
    assert result.predicted_verdict == "warn"
    assert result.matched is True


def test_worst_status_dominates_within_a_family():
    # ts_tv warns but variant_count=0 fails: the family reduces to the worst
    # non-informational status, and the predicted verdict follows it.
    case = _case(
        "germline",
        {"ts_tv": 1.5, "variant_count": 0.0},
        expected="fail",
    )
    result = evaluate_verify_case(case)
    assert result.families["germline"] == "fail"
    assert result.predicted_verdict == "fail"


def test_informational_only_family_reduces_to_unverified():
    # The rnaseq_plausibility duplication_rate rule asserts nothing (no bands),
    # so an informational-only family reduces to "unverified", never "pass".
    case = _case(
        "rnaseq_plausibility",
        {"PERCENT_DUPLICATION": 0.5},
        expected="unverified",
        assay="rnaseq",
    )
    result = evaluate_verify_case(case)
    assert result.families["rnaseq_plausibility"] == "unverified"
    assert result.predicted_verdict == "unverified"
    assert result.matched is True
    assert any("unverified" in line for line in result.divergence)


def test_empty_inputs_predict_unverified():
    case = VerificationCase(
        case_id="verify-empty",
        description="no signal at all",
        source="synthetic",
        assay="variant_calling",
        inputs={},
        expected_verdict="unverified",
    )
    result = evaluate_verify_case(case)
    assert result.predicted_verdict == "unverified"
    assert result.families == {}
    assert result.matched is True


def test_unknown_assay_degrades_to_unverified_never_crashes():
    case = _case(
        "multiqc",
        {"uniquely_mapped_percent": 75.0},
        expected="pass",
        assay="not-a-registered-assay",
    )
    result = evaluate_verify_case(case)
    assert result.families["multiqc"] == "unverified"
    assert result.predicted_verdict == "unverified"
    assert result.matched is False  # labeled case counts as a mismatch (honest)
    assert any("unverified" in line for line in result.divergence)


def test_unknown_family_degrades_to_unverified():
    case = _case("no_such_family", {"anything": 1.0}, expected="pass")
    result = evaluate_verify_case(case)
    assert result.families["no_such_family"] == "unverified"
    assert result.predicted_verdict == "unverified"
    assert result.matched is False


def test_mismatch_records_divergence():
    case = _case("germline", {"ts_tv": 0.5}, expected="warn")
    result = evaluate_verify_case(case)
    assert result.matched is False
    assert "expected warn but predicted fail" in result.divergence


# --- concordance re-derivation -------------------------------------------------


def test_concordance_boundaries_n_shared_warn_pass():
    # n_shared below the 10-gene floor is unverified (nothing corroborated);
    # 0.89 is below the 0.90 warn threshold; 0.91 passes.
    low = _case("concordance_spearman", {"value": 1.0, "n_shared": 9.0}, expected="unverified")
    warn = _case("concordance_spearman", {"value": 0.89, "n_shared": 500.0}, expected="warn")
    ok = _case("concordance_spearman", {"value": 0.91, "n_shared": 500.0}, expected="pass")
    assert evaluate_verify_case(low).predicted_verdict == "unverified"
    assert evaluate_verify_case(warn).predicted_verdict == "warn"
    assert evaluate_verify_case(ok).predicted_verdict == "pass"


def test_concordance_other_kinds():
    genotype = _case("concordance_genotype", {"value": 0.85, "n_shared": 200.0}, expected="warn")
    overlap = _case(
        "concordance_somatic_overlap", {"value": 0.92, "n_shared": 100.0}, expected="pass"
    )
    consequence = _case(
        "concordance_consequence", {"value": 0.95, "n_shared": 5.0}, expected="unverified"
    )
    assert evaluate_verify_case(genotype).predicted_verdict == "warn"
    assert evaluate_verify_case(overlap).predicted_verdict == "pass"
    assert evaluate_verify_case(consequence).predicted_verdict == "unverified"


def test_concordance_missing_signal_keys_degrade_to_unverified():
    case = _case("concordance_spearman", {"value": 0.95}, expected="unverified")
    assert evaluate_verify_case(case).predicted_verdict == "unverified"


# --- evaluate_verify -----------------------------------------------------------


def test_evaluate_verify_excludes_unlabeled_cases():
    labeled = _case("germline", {"ts_tv": 2.0}, expected="pass")
    unlabeled = VerificationCase(
        case_id="verify-pending",
        description="not yet promoted",
        source="pending:run-1",
        assay="variant_calling",
        inputs={"germline": {"S1": {"ts_tv": 2.0}}},
    )
    report = evaluate_verify([labeled, unlabeled])
    assert report.total == 1
    assert report.correct == 1
    assert report.verdict_match_rate == pytest.approx(1.0)
    assert report.mismatches == []


def test_evaluate_verify_per_family_scores():
    ok = _case("germline", {"ts_tv": 2.0}, expected="pass", case_id="verify-a")
    bad = _case("germline", {"ts_tv": 0.5}, expected="pass", case_id="verify-b")
    rna = _case(
        "multiqc",
        {"uniquely_mapped_percent": 75.0},
        expected="pass",
        assay="rnaseq",
        case_id="verify-c",
    )
    report = evaluate_verify([ok, bad, rna])
    assert report.total == 3
    assert report.correct == 2
    assert report.verdict_match_rate == pytest.approx(2 / 3)
    assert report.per_family["germline"].total == 2
    assert report.per_family["germline"].matched == 1
    assert report.per_family["germline"].rate == pytest.approx(0.5)
    assert report.per_family["multiqc"].total == 1
    assert report.per_family["multiqc"].matched == 1
    assert [m.case_id for m in report.mismatches] == ["verify-b"]
