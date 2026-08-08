"""Tests for the committed verification holdout seed (C6 fold-in, aspect 1).

The seed is the PRD R2/R2a artifact: >= 12 synthetic, fully-labeled cases
covering the signal families, including EXACTLY ONE known-miss fixture (R2a)
whose expected verdict the CURRENT rules get wrong -- so the committed
baseline must be < 1.0 and the guard's first demonstration of liveness is
that it flags that case as a MISS.

The seed file's bytes are hard-pinned by sha256 (test_qc_anomaly_capture.py
precedent) so any edit forces an explicit re-pin, and the guard rate over the
seed is asserted to sit in (0.7, 1.0). The baseline->seed pin
(verify_baseline.json's corpus_sha == this file's sha, the eval-guard
"committed baseline passes clean" pattern) arrives with aspect 2
(verify-guard-command), which owns the `contig verify-guard --update-baseline`
command that produces the baseline -- this aspect deliberately does NOT
generate verify_baseline.json.
"""

from __future__ import annotations

import hashlib

import pytest

from contig.verify_corpus import (
    default_verify_holdout_path,
    evaluate_verify,
    load_verify_cases,
)

# Hard pin on the committed seed bytes: any edit to the corpus must be a
# deliberate act that re-pins this value (and, in aspect 2, re-freezes the
# baseline through the real command).
SEED_SHA256 = "0a51ddf4cc82da46dd8099fb20618b15c18f31e60d459ac5e1c0f75be326160c"


def _seed_sha() -> str:
    return hashlib.sha256(default_verify_holdout_path().read_bytes()).hexdigest()


def test_committed_seed_bytes_are_pinned():
    assert _seed_sha() == SEED_SHA256


def test_seed_has_at_least_twelve_labeled_synthetic_cases():
    cases = load_verify_cases(default_verify_holdout_path())
    assert len(cases) >= 12
    for case in cases:
        assert case.case_id.startswith("verify-")
        assert case.source == "synthetic"
        assert case.expected_verdict is not None


def test_seed_has_exactly_one_known_miss():
    cases = load_verify_cases(default_verify_holdout_path())
    known_misses = [c for c in cases if c.known_miss]
    assert len(known_misses) == 1
    case = known_misses[0]
    assert "known miss" in case.description.lower() or "known-miss" in case.description.lower()


def test_seed_verdict_match_rate_is_between_0_7_and_1_0():
    # The R2a known-miss forces the rate below 1.0 -- a 1.0 baseline over
    # self-authored fixtures would read as a frozen tautology regardless of
    # intent. The exact figure is the aspect-2 baseline's job to pin.
    cases = load_verify_cases(default_verify_holdout_path())
    report = evaluate_verify(cases)
    assert report.verdict_match_rate > 0.7
    assert report.verdict_match_rate < 1.0


def test_seed_known_miss_is_the_only_mismatch():
    # The instrument's first demonstration of liveness: the guard flags the
    # deliberate known-miss case and nothing else. Any other mismatch means a
    # seed case drifted from its own label -- an authoring error, not a pin.
    cases = load_verify_cases(default_verify_holdout_path())
    report = evaluate_verify(cases)
    miss_ids = [m.case_id for m in report.mismatches]
    known_miss_ids = [c.case_id for c in cases if c.known_miss]
    assert miss_ids == known_miss_ids
    assert len(miss_ids) == 1


def test_seed_covers_the_required_families():
    cases = load_verify_cases(default_verify_holdout_path())
    families = {family for case in cases for family in case.inputs}
    assert {"germline", "multiqc", "rnaseq_plausibility", "rnaseq_composition"} <= families
    assert {"somatic_plausibility", "scrnaseq", "annotation_plausibility"} <= families
    assert {
        "concordance_spearman",
        "concordance_genotype",
        "concordance_somatic_overlap",
        "concordance_consequence",
    } <= families
