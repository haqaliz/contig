"""Germline karyotypic-sex plausibility from a VCF (PRD germline-sex-check-plausibility).

Infers karyotypic sex from a single germline VCF via the heterozygous fraction
of callable chrX genotypes (X-heterozygosity), corroborated by chrY variant
presence: a male-pattern sample is mostly hemizygous (low X-het) with chrY
calls present; a female-pattern sample is autosomal-level het on chrX (no chrY
to call). This is a research-use biological-plausibility signal, NOT a
clinical or diagnostic sex-chromosome-aneuploidy assay — it is deliberately
WARN-capped (never FAIL) and degrades to UNVERIFIED rather than guessing when
the VCF carries too little signal (PRODUCT_SPEC false-pass rate ~0).

Reuses concordance.parse_vcf for site parsing (one VCF reader, gzip handling
included). parse_vcf skips `#` header lines, so build detection (the
`##contig=<ID=...X,length=L>` line, needed to mask the pseudoautosomal
regions) is a separate light header scan here.

PAR (pseudoautosomal region) coordinates are 1-based inclusive, cited from the
Genome Reference Consortium / Ensembl PAR tables
(https://www.ncbi.nlm.nih.gov/grc/human, mart.ensembl.org/info/genome/genebuild/
human_PARS.html; cross-checked against the UCSC hg19/hg38 chromInfo groups
thread). GRCh37 is the one assembly where chrX's PAR1 and chrY's PAR1 do NOT
share coordinates (a documented ~50kb historical assembly offset) -- chrY PAR1
on GRCh37 is 10,001-2,649,520, NOT chrX's 60,001-2,699,520. Every other
PAR/build undetected -> `par_masked=False`, `reference_build=None`, and the
raw unmasked X-het ratio is used instead of guessing a build (never
silently disables masking without saying so).
"""

from __future__ import annotations

import gzip
import os
import re
from dataclasses import dataclass
from pathlib import Path

from contig.models import QCResult
from contig.verification.concordance import parse_vcf
from contig.verification.rule_pack import (
    MIN_X_SITES,
    X_HET_HIGH,
    X_HET_LOW,
    Y_PRESENT_FLOOR,
)

# chrX total length, used to identify the reference build from the VCF's own
# ##contig header line (see docstring for the citation).
_CHRX_LENGTH_GRCH37 = 155_270_560
_CHRX_LENGTH_GRCH38 = 156_040_895

# PAR coordinates, 1-based inclusive, keyed by build. chrX's PAR1/PAR2 are used
# to exclude PAR sites from the X-het denominator; chrY's PAR1/PAR2 are used to
# exclude PAR sites from the Y-presence count (a Y-PAR site is also present in
# an XX sample via chrX, so it carries no Y-specific signal).
_PAR_X: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "GRCh37": ((60_001, 2_699_520), (154_931_044, 155_260_560)),
    "GRCh38": ((10_001, 2_781_479), (155_701_383, 156_030_895)),
}
_PAR_Y: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    # GRCh37's chrY PAR1 does NOT share chrX's PAR1 bounds -- see docstring.
    "GRCh37": ((10_001, 2_649_520), (59_034_050, 59_373_566)),
    "GRCh38": ((10_001, 2_781_479), (56_887_903, 57_217_415)),
}

_CONTIG_RE = re.compile(r"##contig=<ID=(chr)?([XY]),length=(\d+)>", re.IGNORECASE)


def _open_text(path: str | os.PathLike):
    """Open a VCF for text reading, transparently gunzipping a `.gz` path."""
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt")
    return open(p)


def _detect_build(vcf_path: str | os.PathLike) -> str | None:
    """Read the reference build from the VCF's own ##contig chrX length.

    Scans header lines only (stops at the first non-`#` line, mirroring
    parse_vcf's header skip). Recognizes `chrX`/`X` (case-insensitive).
    Returns "GRCh37"/"GRCh38" on a recognized length, else None -- a build is
    never guessed from an absent or unrecognized ##contig line.
    """
    with _open_text(vcf_path) as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            match = _CONTIG_RE.match(line.strip())
            if not match or match.group(2).upper() != "X":
                continue
            length = int(match.group(3))
            if length == _CHRX_LENGTH_GRCH37:
                return "GRCh37"
            if length == _CHRX_LENGTH_GRCH38:
                return "GRCh38"
    return None


def _is_chrom(chrom: str, letter: str) -> bool:
    """True when CHROM names the given single-letter contig (`chrX`/`X`, etc.)."""
    c = chrom.lower()
    if c.startswith("chr"):
        c = c[3:]
    return c == letter.lower()


def _in_par(pos: int, par_ranges: tuple[tuple[int, int], tuple[int, int]]) -> bool:
    """True when a 1-based POS falls inside either PAR range of the pair."""
    return any(lo <= pos <= hi for lo, hi in par_ranges)


def _x_signals(
    sites: dict[tuple[str, str, str, str], str | None], build: str | None
) -> tuple[float | None, int]:
    """Het fraction + count over biallelic, non-missing, non-PAR chrX genotypes.

    "Biallelic" means a single ALT allele (no comma), matching
    concordance/somatic's convention; indels are included (like
    variant_metrics.het_hom, which does not restrict to SNVs -- only ts_tv
    does). PAR sites are excluded by POS when `build` resolved a PAR table;
    `build is None` (undetermined) leaves the ratio unmasked, never guessed.
    Returns `(None, x_sites)` when `x_sites < MIN_X_SITES` (too little signal
    to call), including the `(None, 0)` case of no chrX contig at all.
    """
    par_ranges = _PAR_X.get(build) if build else None
    het = 0
    total = 0
    for (chrom, pos, _ref, alt), gt in sites.items():
        if not _is_chrom(chrom, "X"):
            continue
        if "," in alt:
            continue
        if gt is None:
            continue
        alleles = gt.split("/")
        if len(alleles) != 2:
            continue
        if par_ranges and _in_par(int(pos), par_ranges):
            continue
        total += 1
        if alleles[0] != alleles[1]:
            het += 1
    if total < MIN_X_SITES:
        return None, total
    return het / total, total


def _y_count(
    sites: dict[tuple[str, str, str, str], str | None], build: str | None
) -> int:
    """Count non-PAR chrY variant sites (any record, not gated on GT).

    A record on chrY at all is the signal (something mapped and was called
    there); genotype content is not required. PAR-Y sites are excluded --
    they are also present on chrX in an XX sample, so they carry no
    Y-specific evidence.
    """
    par_ranges = _PAR_Y.get(build) if build else None
    count = 0
    for (chrom, pos, _ref, _alt) in sites:
        if not _is_chrom(chrom, "Y"):
            continue
        if par_ranges and _in_par(int(pos), par_ranges):
            continue
        count += 1
    return count


@dataclass(frozen=True)
class SexSignals:
    """The deterministic karyotypic-sex signal computed from a single VCF.

    - inferred_sex: "XY" | "XX" | "discordant" | "indeterminate".
    - x_het_ratio: heterozygous fraction of callable (non-PAR) chrX genotypes,
      or None when there was too little signal (see _x_signals).
    - x_sites: the callable (non-PAR) chrX genotype count behind the ratio.
    - y_variant_count: non-PAR chrY variant site count.
    - par_masked: whether PAR exclusion was applied (False when the build
      could not be determined from the VCF header -- unmasked fallback).
    - reference_build: "GRCh37" | "GRCh38" | None.
    """

    inferred_sex: str
    x_het_ratio: float | None
    x_sites: int
    y_variant_count: int
    par_masked: bool
    reference_build: str | None


def _infer_sex(x_het_ratio: float | None, y_variant_count: int) -> str:
    """Derive the karyotype call from the X-het ratio and Y-presence count.

    Y-ABSENCE never forces "discordant" -- a Y-less reference and a female
    sample are indistinguishable from the VCF alone, so only Y-PRESENCE
    (>= Y_PRESENT_FLOOR) at high X-het contradicts an XX read. A mid-band
    X-het ratio is implausible for either karyotype on its own, so it also
    reads discordant regardless of Y.
    """
    if x_het_ratio is None:
        return "indeterminate"
    if x_het_ratio <= X_HET_LOW:
        return "XY"
    if x_het_ratio >= X_HET_HIGH:
        return "discordant" if y_variant_count >= Y_PRESENT_FLOOR else "XX"
    return "discordant"  # mid-band: implausible for either karyotype


def sex_signals(vcf_path: str | os.PathLike) -> SexSignals:
    """Assemble the full karyotypic-sex signal for a single germline VCF.

    Pure function of the VCF bytes: parses once via parse_vcf, detects the
    build for PAR masking, computes X-het and Y-presence, and derives
    inferred_sex. Same input -> same SexSignals, always.
    """
    sites = parse_vcf(vcf_path)
    build = _detect_build(vcf_path)
    x_het_ratio, x_sites = _x_signals(sites, build)
    y_variant_count = _y_count(sites, build)
    return SexSignals(
        inferred_sex=_infer_sex(x_het_ratio, y_variant_count),
        x_het_ratio=x_het_ratio,
        x_sites=x_sites,
        y_variant_count=y_variant_count,
        par_masked=build is not None,
        reference_build=build,
    )
