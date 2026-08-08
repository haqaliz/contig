"""Verification-corpus scorer (C6 fold-in, aspect 1: verify-core).

The labeling design (PRD R1): a VerificationCase carries PRE-BAND signal
values (family -> sample -> metric -> value) plus a human-confirmed expected
verdict. The scorer re-derives each case's statuses from those stored values
under the CURRENT rule packs and concordance thresholds -- never from stored
statuses -- which is the threshold-sensitivity contract that keeps the future
`verify-guard` from being a tautology: a case whose stored value crosses a
changed band must flip status (pinned by the mutation-control test).

This module is pure (no I/O): the corpus/baseline persistence mirrors
holdout.py and lives alongside the scorer here so the guard command (aspect 2)
consumes one module, the same way heal.py bundles scenario eval + baseline I/O.

Honest scope: the first corpus is synthetic and self-graded; the corpus only
becomes non-tautological as real runs feed it through the capture/promote
channel (aspect 3, PRD R4/R5).
"""

from __future__ import annotations

from typing import Iterable

from contig.models import (
    FamilyScore,
    QCResult,
    QCStatus,
    VerificationCase,
    VerifyCaseResult,
    VerifyEvalReport,
)
from contig.verification.annotation_concordance import (
    _MIN_SHARED_VARIANTS,
    _WARN_BELOW as _ANNOTATION_CONCORDANCE_WARN_BELOW,
)
from contig.verification.concordance import _CONCORDANCE_WARN_BELOW
from contig.verification.count_concordance import _MIN_SHARED_GENES, _SPEARMAN_WARN_BELOW
from contig.verification.rule_pack import (
    ANNOTATION_PLAUSIBILITY_PACK,
    AMPLISEQ_RULE_PACK,
    MAG_RULE_PACK,
    METHYLSEQ_RULE_PACK,
    RNASEQ_COMPOSITION_PACK,
    RNASEQ_PLAUSIBILITY_PACK,
    SCRNASEQ_RULE_PACK,
    SOMATIC_PLAUSIBILITY_PACK,
    VARIANT_RULE_PACK,
    evaluate,
    rule_pack_for,
)
from contig.verification.somatic_concordance import _MIN_SHARED_SITES, _OVERLAP_WARN_BELOW


# --- family -> pack table ------------------------------------------------------
# Every family a VerificationCase may exercise maps to the pack (or re-deriver)
# whose CURRENT bands produce the status the guard scores. "multiqc" is
# deliberately absent: it resolves per assay via `rule_pack_for` at evaluation
# time (an assay's MultiQC pack is chosen by the assay, not by the family).
_FAMILY_PACKS: dict[str, list[dict]] = {
    "germline": VARIANT_RULE_PACK,
    "rnaseq_plausibility": RNASEQ_PLAUSIBILITY_PACK,
    "rnaseq_composition": RNASEQ_COMPOSITION_PACK,
    "somatic_plausibility": SOMATIC_PLAUSIBILITY_PACK,
    "annotation_plausibility": ANNOTATION_PLAUSIBILITY_PACK,
    "scrnaseq": SCRNASEQ_RULE_PACK,
    "methylseq": METHYLSEQ_RULE_PACK,
    "ampliseq": AMPLISEQ_RULE_PACK,
    "mag": MAG_RULE_PACK,
}

# The concordance families (PRD R4a: capture deferred, status DERIVATION in
# scope) re-derive status from stored signal values -- {"value", "n_shared"}
# per sample -- under the modules' current thresholds, one family per kind.
_CONCORDANCE_FAMILY_KINDS: dict[str, str] = {
    "concordance_spearman": "spearman",
    "concordance_genotype": "genotype",
    "concordance_somatic_overlap": "somatic_overlap",
    "concordance_consequence": "consequence",
}

# Per-kind (warn_below, min_shared) re-derived from the CURRENT constants in
# the concordance modules, so a band change there moves the guard here too
# (threshold-sensitivity contract). Below min_shared the rate is meaningless
# ("too few to corroborate") and the family is UNVERIFIED -- the modules' own
# semantics -- and below warn_below it WARNs; else PASS. Never FAIL:
# concordance is WARN-capped by contract in every module. The genotype kind
# has no MIN constant in concordance.py: its rate is undefined when no shared
# site has a known genotype in both (comparable == 0), so its floor is 1.
_CONCORDANCE_KIND_THRESHOLDS: dict[str, tuple[float, int]] = {
    "spearman": (_SPEARMAN_WARN_BELOW, _MIN_SHARED_GENES),
    "genotype": (_CONCORDANCE_WARN_BELOW, 1),
    "somatic_overlap": (_OVERLAP_WARN_BELOW, _MIN_SHARED_SITES),
    "consequence": (_ANNOTATION_CONCORDANCE_WARN_BELOW, _MIN_SHARED_VARIANTS),
}


def _resolve_family_pack(
    family: str, assay: str, overrides: dict[str, list[dict]] | None
) -> list[dict] | tuple[str, str] | None:
    """The pack (or ("concordance", kind) pair) that re-derives one family.

    `overrides` win over everything -- the mutation-control seam, so a test
    can re-point a family at a band-mutated pack without editing committed
    data. "multiqc" resolves per assay via `rule_pack_for`; an unknown assay
    degrades that family to None (unverified) rather than crashing the guard.
    None also covers an unknown family: the case degrades to unverified, never
    a false pass.
    """
    if overrides and family in overrides:
        return overrides[family]
    if family == "multiqc":
        try:
            return rule_pack_for(assay)
        except ValueError:
            return None
    kind = _CONCORDANCE_FAMILY_KINDS.get(family)
    if kind is not None:
        return ("concordance", kind)
    return _FAMILY_PACKS.get(family)


def _worst_status(statuses: Iterable[str]) -> QCStatus:
    """The worst status in a set under the shared severity order.

    Mirrors `overall_verdict`'s reduction order (fail > warn > pass) and
    treats unverified as the honest floor (an empty set reduces to
    "unverified", never "pass").
    """
    seen = set(statuses)
    if "fail" in seen:
        return "fail"
    if "warn" in seen:
        return "warn"
    if "pass" in seen:
        return "pass"
    return "unverified"


def _family_status(results: list[QCResult]) -> QCStatus:
    """Reduce one family's evaluate() results to its reduced status.

    Same severity order and informational exclusion as `overall_verdict`
    (models.py:85-111), but a family with no scoreable results degrades to
    "unverified" instead of raising -- a family with nothing to assert is a
    degraded family, not a crash.
    """
    return _worst_status(r.status for r in results if not r.informational)


def _concordance_status(samples: dict[str, dict[str, float]], kind: str) -> QCStatus:
    """Re-derive one concordance family's status from stored signal values.

    Each sample's metrics must carry `value` (the agreement rate) and
    `n_shared` (the comparable-site count); a missing key degrades that
    sample to unverified -- honest: nothing to score, never a false pass.
    """
    warn_below, min_shared = _CONCORDANCE_KIND_THRESHOLDS[kind]
    statuses: list[str] = []
    for metrics in samples.values():
        value = metrics.get("value")
        n_shared = metrics.get("n_shared")
        if value is None or n_shared is None:
            statuses.append("unverified")
            continue
        if n_shared < min_shared:
            statuses.append("unverified")
        elif value < warn_below:
            statuses.append("warn")
        else:
            statuses.append("pass")
    return _worst_status(statuses)


def evaluate_verify_case(
    case: VerificationCase,
    *,
    family_packs: dict[str, list[dict]] | None = None,
) -> VerifyCaseResult:
    """Re-derive one case's verdict from its stored pre-band inputs.

    Each family in `case.inputs` is scored under its current pack (or the
    concordance re-deriver) and reduced with the shared severity order;
    `predicted_verdict` is the worst status across families. A family that is
    not scoreable (unknown family/assay, missing metrics, informational-only)
    degrades to "unverified" and is named in `divergence` -- honest, never a
    false pass. `matched` is only meaningful for labeled cases; an unlabeled
    case is excluded from the report tally by `evaluate_verify`.
    """
    family_statuses: dict[str, str] = {}
    divergence: list[str] = []
    for family, samples in case.inputs.items():
        resolved = _resolve_family_pack(family, case.assay, family_packs)
        if resolved is None:
            status = "unverified"
            divergence.append(
                f"{family}: not scoreable (unknown family or no pack for assay "
                f"{case.assay!r})"
            )
        elif isinstance(resolved, tuple):
            status = _concordance_status(samples, resolved[1])
            if status == "unverified":
                divergence.append(f"{family}: unverified")
        else:
            results = evaluate(samples, resolved)
            status = _family_status(results)
            if status == "unverified":
                divergence.append(f"{family}: unverified")
        family_statuses[family] = status

    predicted = _worst_status(family_statuses.values()) if family_statuses else "unverified"
    expected = case.expected_verdict
    matched = expected is not None and predicted == expected
    if expected is not None and predicted != expected:
        divergence.append(f"expected {expected} but predicted {predicted}")
    return VerifyCaseResult(
        case_id=case.case_id,
        predicted_verdict=predicted,
        expected_verdict=expected,
        matched=matched,
        families=family_statuses,
        divergence=divergence,
    )


def evaluate_verify(
    cases: list[VerificationCase],
    *,
    family_packs: dict[str, list[dict]] | None = None,
) -> VerifyEvalReport:
    """Score the current verification rules over a case corpus (pure, no I/O).

    Unlabeled cases (`expected_verdict=None`) are skipped entirely -- never
    counted wrong (spec AC3). `verdict_match_rate` is the guarded headline;
    `per_family` rates and `mismatches` are informational (PRD R3).
    """
    labeled = [c for c in cases if c.expected_verdict is not None]
    results = [evaluate_verify_case(case, family_packs=family_packs) for case in labeled]
    correct = sum(1 for r in results if r.matched)
    total = len(results)

    per_family: dict[str, FamilyScore] = {}
    for result in results:
        for family in result.families:
            score = per_family.get(family)
            if score is None:
                score = per_family[family] = FamilyScore(matched=0, total=0, rate=0.0)
            score.total += 1
            if result.matched:
                score.matched += 1
    for score in per_family.values():
        score.rate = score.matched / score.total if score.total else 0.0

    return VerifyEvalReport(
        total=total,
        correct=correct,
        verdict_match_rate=correct / total if total else 0.0,
        per_family=per_family,
        mismatches=[r for r in results if not r.matched],
    )
