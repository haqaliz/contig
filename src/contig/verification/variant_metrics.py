"""Deterministic germline variant metrics from a VCF (PRD C3, slice 1).

Computes two biological-plausibility metrics for a germline call set:

- ts_tv: transitions / transversions over biallelic SNV sites. Indels and
  multiallelic sites are excluded from the ratio (documented, not silently
  mishandled). None when there are no transversions (no divide-by-zero).
- het_hom: heterozygous genotypes / homozygous-alt genotypes. Homozygous-ref
  and missing genotypes are excluded from both counts. None when there are no
  homozygous-alt genotypes (no divide-by-zero).

Pure function of the VCF bytes: no tool execution, no network, no randomness.
Reuses concordance.parse_vcf, which yields {(CHROM, POS, REF, ALT): normalized_gt}.
ts_tv reads REF/ALT from the site key; het_hom reads the normalized GT. Reusing
that parser means there is exactly one VCF reader (gzip handling included).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from contig.verification.concordance import parse_vcf

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
    """

    ts_tv: float | None
    het_hom: float | None


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
    """Compute ts_tv and het_hom for the primary sample of a VCF.

    Deterministic and side effect free beyond reading the file (gzip transparent
    via parse_vcf). Returns a frozen VariantMetrics with None for any metric whose
    denominator is zero.
    """
    sites = parse_vcf(vcf_path)
    return VariantMetrics(
        ts_tv=_compute_ts_tv(sites),
        het_hom=_compute_het_hom(sites),
    )
