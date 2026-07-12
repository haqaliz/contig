"""Deterministic germline variant metrics from a VCF (PRD C3, slice 1).

Computes biological-plausibility metrics for a germline call set:

- ts_tv: transitions / transversions over biallelic SNV sites. Indels and
  multiallelic sites are excluded from the ratio (documented, not silently
  mishandled). None when there are no transversions (no divide-by-zero).
- het_hom: heterozygous genotypes / homozygous-alt genotypes. Homozygous-ref
  and missing genotypes are excluded from both counts. None when there are no
  homozygous-alt genotypes (no divide-by-zero).
- variant_count: number of distinct primary-sample variant sites,
  `len(parse_vcf(...))`. Keyed by (CHROM, POS, REF, ALT), so a duplicated site
  line is deduped to one and a multiallelic (comma-ALT) record is a single
  site; not PASS-filtered. Always an int, so unlike the two ratios it never
  yields None / unverified.

Pure function of the VCF bytes: no tool execution, no network, no randomness.
Reuses concordance.parse_vcf, which yields {(CHROM, POS, REF, ALT): normalized_gt}.
ts_tv reads REF/ALT from the site key; het_hom reads the normalized GT. Reusing
that parser means there is exactly one VCF reader (gzip handling included).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from contig.models import QCResult
from contig.verification.concordance import parse_vcf
from contig.verification.rule_pack import VARIANT_RULE_PACK, evaluate

# The four single-base alleles a biallelic SNV can carry.
_BASES = {"A", "C", "G", "T"}

# The two unordered base pairs that are transitions (purine<->purine A<->G,
# pyrimidine<->pyrimidine C<->T). Anything else over two ACGT bases is a
# transversion.
_TRANSITION_PAIRS = (frozenset({"A", "G"}), frozenset({"C", "T"}))


@dataclass(frozen=True)
class VariantMetrics:
    """The deterministic metrics computed from a single VCF (primary sample).

    - ts_tv: transitions / transversions over biallelic SNVs, or None when no
      transversion was observed (the denominator would be zero).
    - het_hom: het count / hom-alt count, or None when no homozygous-alt
      genotype was observed (the denominator would be zero).
    - variant_count: number of distinct primary-sample variant sites
      (`len(parse_vcf(...))`). A site key is (CHROM, POS, REF, ALT), so a
      repeated site line counts once and a multiallelic record (comma-ALT) is
      one site; not PASS-filtered. Always an int (0 for a header-only VCF).
    """

    ts_tv: float | None
    het_hom: float | None
    variant_count: int


def _is_biallelic_snv(ref: str, alt: str) -> bool:
    """True only for a single-base REF and a single-base ALT, both in ACGT.

    A comma in ALT (multiallelic) makes ALT multi-character, so it fails the
    single-base check; indels (multi-base REF or ALT) fail it too.
    """
    return ref in _BASES and alt in _BASES


def _is_transition(ref: str, alt: str) -> bool:
    """True when the unordered {REF, ALT} pair is A<->G or C<->T."""
    return frozenset({ref, alt}) in _TRANSITION_PAIRS


def _compute_ts_tv(sites: dict[tuple[str, str, str, str], str | None]) -> float | None:
    """transitions / transversions over biallelic SNV site keys, or None."""
    transitions = 0
    transversions = 0
    for (_chrom, _pos, ref, alt) in sites:
        if not _is_biallelic_snv(ref, alt):
            continue
        if _is_transition(ref, alt):
            transitions += 1
        else:
            transversions += 1
    if transversions == 0:
        return None
    return transitions / transversions


def _compute_het_hom(sites: dict[tuple[str, str, str, str], str | None]) -> float | None:
    """het count / hom-alt count over normalized genotypes, or None.

    A genotype is heterozygous when its two alleles differ (e.g. 0/1, and also a
    multiallelic 1/2 whose alleles differ: counted as het, documented decision).
    It is homozygous-alt when both alleles are equal and non-zero (e.g. 1/1).
    Homozygous-ref (0/0) and missing (None after normalization) are excluded.
    """
    het = 0
    hom_alt = 0
    for gt in sites.values():
        if gt is None:
            continue
        alleles = gt.split("/")
        if len(alleles) != 2:
            continue
        a, b = alleles
        if a != b:
            het += 1
        elif a != "0":
            hom_alt += 1
        # a == b == "0" is homozygous-ref: excluded from both counts.
    if hom_alt == 0:
        return None
    return het / hom_alt


def variant_metrics(vcf_path: str | os.PathLike) -> VariantMetrics:
    """Compute ts_tv, het_hom, and variant_count for the primary sample of a VCF.

    Deterministic and side effect free beyond reading the file (gzip transparent
    via parse_vcf). Returns a frozen VariantMetrics with None for any ratio whose
    denominator is zero; variant_count is the distinct-site total and is always an
    int (0 for a header-only VCF).
    """
    sites = parse_vcf(vcf_path)
    return VariantMetrics(
        ts_tv=_compute_ts_tv(sites),
        het_hom=_compute_het_hom(sites),
        variant_count=len(sites),
    )


# The germline plausibility rules, sourced from the shared pack by their
# "check" field so the bands stay single-sourced in rule_pack.py (this module
# never hardcodes a threshold). Each VariantMetrics field maps to one rule via the
# rule's "metric" key. variant_count is always an int, so unlike the two ratios it
# is always computable and never yields an unverified result. mean_coverage is
# intentionally absent: it is a MultiQC metric, not VCF-derived, so it is not part
# of the VCF plausibility pass.
_PLAUSIBILITY_CHECKS = ("ts_tv_ratio", "het_hom_ratio", "variant_count")


def _rule_by_check(check_name: str) -> dict:
    """Look up one rule in VARIANT_RULE_PACK by its check name."""
    for rule in VARIANT_RULE_PACK:
        if rule["check"] == check_name:
            return rule
    raise KeyError(check_name)


def evaluate_variant_plausibility(
    vcf_path: str | os.PathLike, sample: str = "sample"
) -> list[QCResult]:
    """Evaluate the germline plausibility rules over a VCF, capped at WARN.

    Computes ts_tv, het_hom, and variant_count, then runs the three WARN-capped
    germline rules from VARIANT_RULE_PACK over the COMPUTABLE metrics via the
    shared evaluate() (so the band logic and check naming, "<check>:<sample>",
    stay single-sourced). The two ratios can be None (no transversion, or no
    homozygous-alt genotype); such a metric is NOT silently skipped but gets an
    explicit "unverified" QCResult, which carries no severity and so can never
    read as a pass (PRODUCT_SPEC false-pass rate ~0). variant_count is always an
    int, so it is always computable — a real 0 (empty call set) rides the band as
    a WARN and never routes into the unverified branch. Every result is kind
    "metric".
    """
    metrics = variant_metrics(vcf_path)
    rules = [_rule_by_check(name) for name in _PLAUSIBILITY_CHECKS]

    # The computable metrics, keyed by each rule's "metric" so evaluate() picks
    # them up; a None metric is omitted here and handled as unverified below.
    by_metric = {
        "ts_tv": metrics.ts_tv,
        "het_hom": metrics.het_hom,
        "variant_count": metrics.variant_count,
    }
    computable = {
        metric: value for metric, value in by_metric.items() if value is not None
    }

    results = evaluate({sample: computable}, rules)

    # Reasons keyed by the rule's "metric" so the message matches the missing one.
    _uncomputable_reason = {
        "ts_tv": "no transversions to compute ts_tv",
        "het_hom": "no homozygous-alt genotypes to compute het_hom",
    }
    for rule in rules:
        metric = rule["metric"]
        if by_metric[metric] is None:
            results.append(
                QCResult(
                    check=f"{rule['check']}:{sample}",
                    status="unverified",
                    message=f"{sample}: {_uncomputable_reason[metric]}",
                    value=None,
                    kind="metric",
                )
            )
    return results
