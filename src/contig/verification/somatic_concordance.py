"""Cross-tool somatic PASS-site-overlap concordance (PRD C4 follow-on).

A second, independent somatic caller on the same tumor-normal pair is a standard
way to sanity-check a variant caller: a tool-specific systematic error can pass
every metric and structural threshold yet disagree with another caller. This
module measures that agreement deterministically over the Mutect2 and Strelka2
call sets, with no tool execution and no network.

The metric is conservative by design. Concordance corroborates; it is NOT ground
truth, so the worst it can do to a verdict in this slice is WARN, never FAIL.
Every result carries kind "concordance" so the dashboard groups it apart from the
metric and structural checks. This mirrors the germline `concordance.py` posture
exactly, but the parser is deliberately different: FILTER-aware (PASS-only) and
sample-agnostic (it reads no GT/sample columns at all — somatic concordance here
is about which sites each caller was confident enough to call, not what genotype
either caller assigned).

Slice 1 compares on the literal site key (CHROM, POS, REF, ALT). VCF
representation differences (normalization, multiallelic splitting, indel
left-alignment) are a known limitation, deliberately not "fixed" silently here.
"""

from __future__ import annotations

import gzip
import os
from pathlib import Path
from typing import Iterable

from contig.models import QCResult

# Documented engineering default (tunable like the rule packs), NOT a clinical
# claim. Below this we WARN; there is no FAIL band in this slice.
_OVERLAP_WARN_BELOW = 0.90

# Below this many union PASS sites, a Jaccard is meaningless (a couple of sites
# could report 1.0 -> a false PASS), so the check is UNVERIFIED instead. Mirrors
# count_concordance.py's _MIN_SHARED_GENES=10.
_MIN_SHARED_SITES = 10

# FILTER values counted as a confident call. "." is VCF's "not evaluated" filter
# value and is treated as PASS (mirrors upstream caller/tool convention).
_PASS_FILTERS = {"PASS", "."}

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


def _open_text(path: str | os.PathLike):
    """Open a VCF for text reading, transparently gunzipping a `.gz` path."""
    p = Path(path)
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt")
    return open(p)


def parse_pass_sites(path: str | os.PathLike) -> set[SiteKey]:
    """Parse a somatic VCF into the set of its FILTER-PASS site keys.

    Streams lines (gzip if the path ends with `.gz`), skips `#` headers and blank
    lines, and keeps a record only when its FILTER column (index 6) is in
    `_PASS_FILTERS`. Reads no sample columns (sample-agnostic) — this is purely
    about which sites the caller was confident enough to call.
    """
    sites: set[SiteKey] = set()
    with _open_text(path) as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            line = line.rstrip("\n")
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 7:
                continue
            if cols[6].strip() not in _PASS_FILTERS:
                continue
            sites.add((cols[0], cols[1], cols[3], cols[4]))
    return sites


def read_caller_sites(paths: Iterable[str | os.PathLike]) -> set[SiteKey]:
    """Union of `parse_pass_sites` over one caller's file(s).

    Strelka reports SNVs and indels in separate files; this unions them into one
    call set so the caller is compared as a whole.
    """
    sites: set[SiteKey] = set()
    for path in paths:
        sites |= parse_pass_sites(path)
    return sites


def _overlap(a: set[SiteKey], b: set[SiteKey]) -> tuple[int, int, float]:
    """Return (shared=|a∩b|, union=|a∪b|, jaccard = shared/union if union else 0.0)."""
    shared = len(a & b)
    union = len(a | b)
    jaccard = (shared / union) if union else 0.0
    return shared, union, jaccard


def evaluate_somatic_concordance(
    mutect2_paths: Iterable[str | os.PathLike],
    strelka_paths: Iterable[str | os.PathLike],
    *,
    label_a: str = "mutect2",
    label_b: str = "strelka",
) -> list[QCResult]:
    """Emit the one somatic PASS-site-overlap concordance check.

    UNVERIFIED (value=None) when the union of PASS sites is below
    `_MIN_SHARED_SITES` (too few to corroborate anything); otherwise WARN below
    `_OVERLAP_WARN_BELOW`, PASS at/above it. Never FAIL. Always `kind="concordance"`.
    """
    a = read_caller_sites(mutect2_paths)
    b = read_caller_sites(strelka_paths)
    shared, union, jaccard = _overlap(a, b)

    if union < _MIN_SHARED_SITES:
        return [
            _concordance(
                "somatic_site_overlap",
                "unverified",
                f"{label_a} and {label_b} share {union} PASS site(s) in their union "
                f"(< {_MIN_SHARED_SITES} needed); too few to corroborate "
                "(concordance is not ground truth)",
                value=None,
                expected_range=f">= {_OVERLAP_WARN_BELOW}",
            )
        ]

    jaccard = round(jaccard, 4)
    status = "warn" if jaccard < _OVERLAP_WARN_BELOW else "pass"
    return [
        _concordance(
            "somatic_site_overlap",
            status,
            f"{label_a} vs {label_b}: {shared}/{union} PASS site(s) agree "
            f"(overlap {jaccard}); FILTER-PASS-only (FILTER in 'PASS' or '.')",
            value=jaccard,
            expected_range=f">= {_OVERLAP_WARN_BELOW}",
        )
    ]
