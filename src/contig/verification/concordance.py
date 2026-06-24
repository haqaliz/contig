"""Cross-tool genotype-concordance QC (ARCHITECTURE §6; PRD C1, slice 1).

A second, independent call set on the same input is a standard way to sanity-check
a variant caller: a tool-specific systematic error can pass every metric and
structural threshold yet disagree with another caller. This module measures that
agreement deterministically over two provided VCFs, with no tool execution and no
network.

The metric is conservative by design. Concordance corroborates; it is NOT ground
truth, so the worst it can do to a verdict in this slice is WARN, never FAIL.
Every result carries kind "concordance" so the dashboard groups it apart from the
metric and structural checks.

Slice 1 compares on the literal site key (CHROM, POS, REF, ALT). VCF representation
differences (normalization, multiallelic splitting, indel left-alignment) are a
known limitation noted in the PRD, deliberately not "fixed" silently here.
"""

from __future__ import annotations

import gzip
import os
from dataclasses import dataclass
from pathlib import Path

from contig.models import QCResult

# Documented engineering defaults (tunable like the rule packs), NOT clinical
# claims. Below these we WARN; there is no FAIL band in this slice.
_CONCORDANCE_WARN_BELOW = 0.90
_OVERLAP_WARN_BELOW = 0.90

# Assays for which cross-tool concordance is defined. A second call set only
# corroborates where there IS a call set to compare (germline variants today);
# an RNA-seq quantification has no genotypes to agree on. Kept as a set so a new
# assay (e.g. somatic) is a one-line addition.
_CONCORDANCE_ASSAYS = {"variant_calling"}

# Site key: a variant site as the tuple of its coordinates and alleles.
SiteKey = tuple[str, str, str, str]


def _concordance(
    check: str,
    status: str,
    message: str,
    value: float | None = None,
    expected_range: str | None = None,
) -> QCResult:
    """Build a QCResult tagged as concordance so the dashboard groups it correctly."""
    return QCResult(
        check=check,
        status=status,
        message=message,
        value=value,
        expected_range=expected_range,
        kind="concordance",
    )


def _normalize_gt(gt: str | None) -> str | None:
    """Normalize a GT call so `0/1`, `0|1`, and `1/0` compare equal.

    Split on `/` or `|`, sort the allele tokens, rejoin with `/`. A missing or
    absent GT (`.`, empty, all-missing alleles) becomes None so the site is
    excluded from the concordance denominator rather than crashing it.
    """
    if gt is None:
        return None
    gt = gt.strip()
    if not gt or gt == ".":
        return None
    alleles = gt.replace("|", "/").split("/")
    if all(a == "." or a == "" for a in alleles):
        return None
    return "/".join(sorted(alleles))


def _open_text(path: str | os.PathLike):
    """Open a VCF for text reading, transparently gunzipping a `.gz` path."""
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt")
    return open(p)


def parse_vcf(path: str | os.PathLike) -> dict[SiteKey, str | None]:
    """Parse a small VCF into {site_key: normalized_genotype}.

    Streams lines (gzip if the path ends with `.gz`), skips `#` headers, and reads
    CHROM/POS/REF/ALT (columns 0,1,3,4) plus the GT of the first sample column,
    locating GT via the FORMAT field. A site whose GT is missing or whose sample
    column is absent stores None (its genotype is unknown).
    """
    sites: dict[SiteKey, str | None] = {}
    with _open_text(path) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 5:
                continue
            chrom, pos, _id, ref, alt = cols[0], cols[1], cols[2], cols[3], cols[4]
            key: SiteKey = (chrom, pos, ref, alt)
            gt = _genotype_from_columns(cols)
            sites[key] = _normalize_gt(gt)
    return sites


def _genotype_from_columns(cols: list[str]) -> str | None:
    """Pull the GT subfield of the first sample column using the FORMAT field.

    FORMAT is column 8, the first sample is column 9. We find GT's position in the
    colon-delimited FORMAT and read the matching subfield. Anything missing (no
    FORMAT, no sample, no GT key) yields None (an unknown genotype, not a crash).
    """
    if len(cols) < 10:
        return None
    fmt_keys = cols[8].split(":")
    try:
        gt_idx = fmt_keys.index("GT")
    except ValueError:
        return None
    sample_fields = cols[9].split(":")
    if gt_idx >= len(sample_fields):
        return None
    return sample_fields[gt_idx]


@dataclass(frozen=True)
class ConcordanceStats:
    """The deterministic outcome of comparing two call sets.

    - shared: number of site keys present in both call sets.
    - concordant: shared sites where both genotypes are known and equal.
    - rate: concordant / (shared sites with a known GT in both), or None when no
      shared site has a known GT in both (nothing could be corroborated).
    - overlap: |intersection| / |union| of site keys, 0.0 when both are empty.
    """

    shared: int
    concordant: int
    rate: float | None
    overlap: float


def genotype_concordance(
    vcf_a: str | os.PathLike, vcf_b: str | os.PathLike
) -> ConcordanceStats:
    """Compare two VCFs over their shared sites; deterministic, no I/O beyond reads."""
    a = parse_vcf(vcf_a)
    b = parse_vcf(vcf_b)

    keys_a = set(a)
    keys_b = set(b)
    shared_keys = keys_a & keys_b
    union_keys = keys_a | keys_b

    overlap = (len(shared_keys) / len(union_keys)) if union_keys else 0.0

    comparable = 0  # shared sites where both genotypes are known
    concordant = 0
    for key in shared_keys:
        gt_a = a[key]
        gt_b = b[key]
        if gt_a is None or gt_b is None:
            continue
        comparable += 1
        if gt_a == gt_b:
            concordant += 1

    rate = (concordant / comparable) if comparable else None

    return ConcordanceStats(
        shared=len(shared_keys),
        concordant=concordant,
        rate=rate,
        overlap=overlap,
    )


def concordance_results(
    vcf_a: str | os.PathLike, vcf_b: str | os.PathLike
) -> list[QCResult]:
    """Emit the two concordance checks for a pair of call sets.

    `genotype_concordance`: PASS at/above the threshold, WARN below it; UNVERIFIED
    when no shared site had a known genotype in both (nothing was corroborated, so
    we must not claim a pass, and there is no 0/0). `site_overlap`: PASS at/above the
    threshold, WARN below it (0.0 overlap is itself a signal that the two callers
    found disjoint sites). The message names both call sets by basename so the
    comparison is auditable.
    """
    stats = genotype_concordance(vcf_a, vcf_b)
    name_a = Path(vcf_a).name
    name_b = Path(vcf_b).name

    if stats.rate is None:
        genotype_result = _concordance(
            "genotype_concordance",
            "unverified",
            f"{name_a} and {name_b} share no sites with a known genotype; "
            "nothing was corroborated (concordance is not ground truth)",
            value=None,
            expected_range=f">= {_CONCORDANCE_WARN_BELOW}",
        )
    else:
        rate = round(stats.rate, 4)
        status = "warn" if stats.rate < _CONCORDANCE_WARN_BELOW else "pass"
        genotype_result = _concordance(
            "genotype_concordance",
            status,
            f"{name_a} vs {name_b}: genotypes agree at "
            f"{stats.concordant}/{stats.shared} shared site(s) (rate {rate})",
            value=rate,
            expected_range=f">= {_CONCORDANCE_WARN_BELOW}",
        )

    overlap = round(stats.overlap, 4)
    overlap_status = "warn" if stats.overlap < _OVERLAP_WARN_BELOW else "pass"
    overlap_result = _concordance(
        "site_overlap",
        overlap_status,
        f"{name_a} vs {name_b}: {stats.shared} shared site(s); "
        f"site overlap {overlap}",
        value=overlap,
        expected_range=f">= {_OVERLAP_WARN_BELOW}",
    )

    return [genotype_result, overlap_result]


def evaluate_concordance(
    primary_vcf: str | os.PathLike,
    second_vcf: str | os.PathLike,
    assay: str,
) -> list[QCResult]:
    """Assay-gated entry point: concordance checks where the assay defines a comparison.

    Returns the two `concordance_results` for an assay in `_CONCORDANCE_ASSAYS`
    (germline variant calling today), else an empty list. Gating here keeps the
    caller (run_qc) from having to know which assays support concordance.
    """
    if assay not in _CONCORDANCE_ASSAYS:
        return []
    return concordance_results(primary_vcf, second_vcf)
