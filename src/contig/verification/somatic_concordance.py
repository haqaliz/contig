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

    status = "warn" if jaccard < _OVERLAP_WARN_BELOW else "pass"
    jaccard = round(jaccard, 4)
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


def select_caller_vcfs(
    run_dir: str | os.PathLike, vcfs: Iterable[str | os.PathLike]
) -> tuple[list[Path], list[Path], str | None]:
    """Select each caller's VCF(s) out of a somatic run's already-globbed VCF list.

    Mirrors the runner's Mutect2 path-component match (`runner.py`'s somatic
    branch): a VCF belongs to a caller when that caller's name appears as a
    lowercased path COMPONENT below `run_dir` (sarek writes each caller's output
    under a `<caller>/` directory), not as a substring of the absolute path.

    UNVERIFIED, never an arbitrary pick, when either caller's VCFs span more than
    one distinct tumor-normal pair directory (`p.parent.name`), or when both
    callers are present but their single pair directories are different pairs
    (e.g. Mutect2 only `T1_vs_N`, Strelka only `T2_vs_N`): returns `([], [],
    reason)` instead of guessing which pair to compare or corroborating two
    unrelated tumor-normal pairs.
    """
    run_dir = Path(run_dir)

    def _has_component(p: Path, caller: str) -> bool:
        return caller in {part.lower() for part in p.relative_to(run_dir).parts}

    mutect2 = [Path(p) for p in vcfs if _has_component(Path(p), "mutect2")]
    strelka = [Path(p) for p in vcfs if _has_component(Path(p), "strelka")]

    pair_dirs_by_label = {}
    for label, paths in (("mutect2", mutect2), ("strelka", strelka)):
        pair_dirs = {p.parent.name for p in paths}
        if len(pair_dirs) > 1:
            reason = (
                f"{label} VCFs span {len(pair_dirs)} tumor-normal pair "
                f"directories ({sorted(pair_dirs)}); not computed for an "
                "ambiguous multi-pair layout"
            )
            return [], [], reason
        pair_dirs_by_label[label] = pair_dirs

    mutect2_pair = pair_dirs_by_label["mutect2"]
    strelka_pair = pair_dirs_by_label["strelka"]
    if mutect2_pair and strelka_pair and mutect2_pair != strelka_pair:
        reason = (
            f"mutect2 pair directory {sorted(mutect2_pair)} and strelka pair "
            f"directory {sorted(strelka_pair)} differ; not computed for "
            "mismatched tumor-normal pairs"
        )
        return [], [], reason

    return mutect2, strelka, None


def evaluate_somatic_concordance_from_run(
    run_dir: str | os.PathLike, vcfs: Iterable[str | os.PathLike]
) -> list[QCResult]:
    """Auto-select the Mutect2/Strelka VCFs from a somatic run and evaluate their
    PASS-site overlap.

    Clean skip (`[]`) when either caller's VCF is absent — one caller missing is
    already handled independently by VAF plausibility for Mutect2, and a
    corroboration check needs both callers present. UNVERIFIED, not an arbitrary
    compare, on an ambiguous multi tumor-normal pair layout, or when the callers'
    single pair directories don't match each other.
    """
    mutect2, strelka, reason = select_caller_vcfs(run_dir, vcfs)
    if reason is not None:
        return [
            _concordance(
                "somatic_site_overlap",
                "unverified",
                f"cannot compute concordance: {reason}",
                value=None,
                expected_range=f">= {_OVERLAP_WARN_BELOW}",
            )
        ]
    if not mutect2 or not strelka:
        return []
    return evaluate_somatic_concordance(mutect2, strelka)
