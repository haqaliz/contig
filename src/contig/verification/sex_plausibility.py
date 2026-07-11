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
