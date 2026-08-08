"""Tests for the verification-case scorer (C6 fold-in, aspect 1).

The scorer re-derives each case's verdict from its PRE-BAND stored signal
values under the CURRENT rule packs (threshold-sensitivity contract, PRD R1) —
never from stored statuses. The load-bearing test is the mutation control at
the top of this file: it proves a band change flips a stored value's status,
which is what separates the guard from a tautology (PRD goal 2, AC2).
"""

from __future__ import annotations

import pytest

from contig.models import VerificationCase, VerifyEvalReport, VerifySnapshot
from contig.verify_corpus import (
    _FAMILY_PACKS,
    append_verify_case,
    compare_verify_to_baseline,
    default_verify_baseline_path,
    default_verify_golden_path,
    default_verify_history_path,
    default_verify_holdout_path,
    evaluate_verify,
    evaluate_verify_case,
    load_verify_baseline,
    load_verify_cases,
    save_verify_baseline,
    save_verify_cases,
    snapshot_from_verify_report,
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


# --- Phase 3: corpus I/O + baseline compare (mirrors holdout.py) ----------------


def _report(verdict_match_rate: float) -> VerifyEvalReport:
    return VerifyEvalReport(
        total=10,
        correct=round(verdict_match_rate * 10),
        verdict_match_rate=verdict_match_rate,
        per_family={},
        mismatches=[],
    )


def _baseline(
    verdict_match_rate: float, *, corpus_sha: str = "sha-a"
) -> VerifySnapshot:
    return VerifySnapshot(
        timestamp="2026-08-09T00:00:00+00:00",
        case_count=10,
        corpus_sha=corpus_sha,
        verdict_match_rate=verdict_match_rate,
        per_family={},
        contig_version="0.39.0",
    )


def test_default_paths_differ_and_named_correctly():
    assert default_verify_holdout_path() != default_verify_baseline_path()
    assert default_verify_holdout_path().name == "verify_corpus_holdout.jsonl"
    assert default_verify_baseline_path().name == "verify_baseline.json"
    assert default_verify_history_path().name == "verify_history.jsonl"
    assert default_verify_golden_path().name == "verify_corpus.jsonl"
    for p in (
        default_verify_holdout_path(),
        default_verify_baseline_path(),
        default_verify_history_path(),
        default_verify_golden_path(),
    ):
        assert "verify" in p.name


def test_save_and_load_verify_cases_round_trip(tmp_path):
    cases = [
        _case("germline", {"ts_tv": 2.0}, expected="pass", case_id="verify-a"),
        _case("germline", {"ts_tv": 0.5}, expected="fail", case_id="verify-b"),
    ]
    path = tmp_path / "cases.jsonl"
    save_verify_cases(cases, path)
    assert load_verify_cases(path) == cases


def test_load_verify_cases_skips_blank_and_malformed_lines(tmp_path):
    case_json = (
        '{"case_id": "verify-a", "description": "d", "source": "synthetic", '
        '"assay": "variant_calling", "inputs": {}, "expected_verdict": "pass"}'
    )
    path = tmp_path / "cases.jsonl"
    path.write_text(f"\n{case_json}\nnot json at all\n\n{case_json}\n")
    cases = load_verify_cases(path)
    assert len(cases) == 2
    assert cases[0].case_id == "verify-a"


def test_append_verify_case_adds_one_line(tmp_path):
    path = tmp_path / "cases.jsonl"
    save_verify_cases([_case("germline", {"ts_tv": 2.0}, expected="pass", case_id="verify-a")], path)
    append_verify_case(_case("germline", {"ts_tv": 0.5}, expected="fail", case_id="verify-b"), path)
    cases = load_verify_cases(path)
    assert [c.case_id for c in cases] == ["verify-a", "verify-b"]


def test_save_and_load_verify_baseline_round_trip(tmp_path):
    path = tmp_path / "baseline.json"
    assert load_verify_baseline(path) is None  # missing file -> None, not an error
    snapshot = _baseline(0.9)
    save_verify_baseline(snapshot, path)
    assert load_verify_baseline(path) == snapshot


def test_snapshot_from_verify_report_projects_fields():
    report = _report(0.8)
    snapshot = snapshot_from_verify_report(
        report,
        corpus_sha="sha-seed",
        contig_version="0.39.0",
        timestamp="2026-08-09T00:00:00+00:00",
    )
    assert snapshot.case_count == 10
    assert snapshot.corpus_sha == "sha-seed"
    assert snapshot.verdict_match_rate == pytest.approx(0.8)
    assert snapshot.contig_version == "0.39.0"
    assert snapshot.per_family == {}


def test_compare_verify_no_baseline():
    result = compare_verify_to_baseline(
        _report(0.5), baseline=None, corpus_sha="sha-a", tolerance=1e-9
    )
    assert result.has_baseline is False
    assert result.regressed is False
    assert result.improved is False
    assert result.baseline_rate is None
    assert result.delta is None
    assert result.baseline_sha is None
    assert result.sha_mismatch is False
    assert result.verdict_match_rate == pytest.approx(0.5)
    assert result.corpus_sha == "sha-a"


def test_compare_verify_equal_rate():
    baseline = _baseline(0.9)
    result = compare_verify_to_baseline(
        _report(0.9), baseline=baseline, corpus_sha="sha-a", tolerance=1e-9
    )
    assert result.regressed is False
    assert result.improved is False
    assert result.has_baseline is True
    assert result.baseline_rate == pytest.approx(0.9)
    assert result.delta == pytest.approx(0.0)
    assert result.sha_mismatch is False


def test_compare_verify_regression():
    baseline = _baseline(0.9)
    result = compare_verify_to_baseline(
        _report(0.5), baseline=baseline, corpus_sha="sha-a", tolerance=1e-9
    )
    assert result.regressed is True
    assert result.improved is False
    assert result.delta < 0


def test_compare_verify_improvement():
    baseline = _baseline(0.5)
    result = compare_verify_to_baseline(
        _report(0.9), baseline=baseline, corpus_sha="sha-a", tolerance=1e-9
    )
    assert result.improved is True
    assert result.regressed is False
    assert result.delta > 0


def test_compare_verify_tolerance_absorbs_float_noise():
    baseline = _baseline(0.9)
    # Exactly half the tolerance below baseline: must not count as a regression.
    result = compare_verify_to_baseline(
        _report(0.9 - 0.05), baseline=baseline, corpus_sha="sha-a", tolerance=0.1
    )
    assert result.regressed is False


def test_compare_verify_sha_mismatch():
    baseline = _baseline(0.9, corpus_sha="sha-old")
    result = compare_verify_to_baseline(
        _report(0.9), baseline=baseline, corpus_sha="sha-new", tolerance=1e-9
    )
    assert result.sha_mismatch is True
    assert result.baseline_sha == "sha-old"


def test_compare_verify_carries_mismatches_through():
    from contig.models import VerifyCaseResult

    mismatch = VerifyCaseResult(
        case_id="verify-b",
        predicted_verdict="fail",
        expected_verdict="warn",
        matched=False,
        families={"germline": "fail"},
        divergence=["expected warn but predicted fail"],
    )
    report = VerifyEvalReport(
        total=1, correct=0, verdict_match_rate=0.0, mismatches=[mismatch]
    )
    result = compare_verify_to_baseline(
        report, baseline=_baseline(0.9), corpus_sha="sha-a", tolerance=1e-9
    )
    assert result.mismatches == [mismatch]
