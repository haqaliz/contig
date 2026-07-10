"""Cross-tool VEP-vs-SnpEff most-severe-consequence concordance (C7 M4).

`annotation_structural.py` proves an annotation step ran; `annotation_plausibility.py`
proves a single tool's consequence distribution looks plausible. This module
cross-checks the two annotators against each other: for the variant sites BOTH
VEP (CSQ) and SnpEff (ANN) annotated, do they agree on the most-severe
consequence term?

The metric is conservative by design, mirroring `somatic_concordance.py` exactly:
agreement corroborates, it is NOT ground truth, so the worst this check can do to
a verdict is WARN, never FAIL. Every result carries kind "concordance" so the
dashboard groups it apart from metric/structural checks. Below a minimum shared-
site floor, a fraction is meaningless (a couple of sites could report 1.0 -> a
false pass), so the check degrades to UNVERIFIED instead (never a false pass).

This is the PURE core: parsing + the fraction metric. No discovery, no runner
wiring.

Phase 3 adds a SECOND, independent metric: gene-symbol agreement between VEP
and SnpEff. Unlike consequence concordance above (WARN-capable),
`gene_symbol_concordance` is INFORMATIONAL-ONLY -- it ALWAYS reports "pass"
when computable (mirrors RNA-seq's always-pass `gene_overlap` in
`count_concordance.py`). VEP/SnpEff gene-symbol sources diverge enough
(different transcript sets, different gene models) that a WARN threshold here
would train users to ignore the signal; the fraction is reported for context,
never used as a verdict lever. It still degrades to UNVERIFIED (never a false
pass) when too few symbol pairs are resolvable on both sides.
"""

from __future__ import annotations

import os

from contig.models import QCResult
from contig.verification.annotation_plausibility import (
    _SEVERITY_RANK,
    _UNKNOWN_RANK,
    _resolve_consequence_index,
    _variant_terms,
)
from contig.verification.annotation_structural import _open_text

# Documented engineering default (tunable like the rule packs), NOT a clinical
# claim. Below this we WARN; there is no FAIL band in this slice.
_WARN_BELOW = 0.90

# Below this many shared variant sites, an agreement fraction is meaningless (a
# couple of sites could report 1.0 -> a false pass), so the check is UNVERIFIED
# instead. Mirrors somatic_concordance.py's _MIN_SHARED_SITES=10.
_MIN_SHARED_VARIANTS = 10

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


def _most_severe_term(terms: list[str]) -> str | None:
    """The term with the max severity rank across `terms`, or None if empty.

    Unknown, non-empty terms rank `_UNKNOWN_RANK` (above intergenic), matching
    `_most_severe_rank`'s treatment. Ties break deterministically: the first
    term encountered at the max rank, in a single stable left-to-right pass.
    """
    if not terms:
        return None
    best_term = terms[0]
    best_rank = _SEVERITY_RANK.get(best_term, _UNKNOWN_RANK)
    for term in terms[1:]:
        rank = _SEVERITY_RANK.get(term, _UNKNOWN_RANK)
        if rank > best_rank:
            best_rank = rank
            best_term = term
    return best_term


def parse_consequences(
    vcf_path: str | os.PathLike, key: str
) -> dict[SiteKey, str]:
    """Stream a (gzip-transparent) VCF; map each site to its most-severe `key` term.

    Collects header lines to resolve the consequence subfield index for `key`
    ("CSQ" or "ANN") via `_resolve_consequence_index`. If that index cannot be
    resolved (key undeclared, or CSQ's `Format:` string doesn't declare
    `Consequence`), returns `{}` (never guess an index).

    For each data record with >= 8 tab columns whose INFO (column 7, 0-based)
    carries a `key=` token, maps `(CHROM, POS, REF, ALT)` to the most-severe
    term for that key, skipping records where the term is None (field present
    but no parseable term). Records that don't carry `key` at all are skipped
    entirely -- so calling this with "CSQ" then "ANN" on the SAME file (the
    single-VCF-both layout) yields two independent, correct maps.
    """
    header_lines: list[str] = []
    cons_index: int | None = None
    resolved = False
    result: dict[SiteKey, str] = {}

    with _open_text(vcf_path) as fh:
        for line in fh:
            if line.startswith("#"):
                header_lines.append(line)
                continue

            if not resolved:
                cons_index = _resolve_consequence_index(key, header_lines)
                resolved = True
                if cons_index is None:
                    return {}

            data_line = line.rstrip("\n")
            if not data_line:
                continue
            cols = data_line.split("\t")
            if len(cols) < 8:
                continue
            info = cols[7]
            if not any(field.split("=", 1)[0] == key for field in info.split(";")):
                continue

            assert cons_index is not None  # resolved above once key is present
            terms = _variant_terms(info, key, cons_index)
            term = _most_severe_term(terms)
            if term is None:
                continue
            site: SiteKey = (cols[0], cols[1], cols[3], cols[4])
            result[site] = term

    return result


def evaluate_consequence_concordance(
    vep_map: dict[SiteKey, str],
    snpeff_map: dict[SiteKey, str],
    *,
    layout: str,
    label_a: str = "vep",
    label_b: str = "snpeff",
) -> list[QCResult]:
    """Emit the one consequence-concordance check between VEP and SnpEff.

    UNVERIFIED (value=None) when the two maps share fewer than
    `_MIN_SHARED_VARIANTS` sites (too few to corroborate anything); otherwise
    WARN below `_WARN_BELOW`, PASS at/above it. Never FAIL. Always
    `kind="concordance"`.
    """
    shared = set(vep_map) & set(snpeff_map)

    if len(shared) < _MIN_SHARED_VARIANTS:
        return [
            _concordance(
                "consequence_concordance",
                "unverified",
                f"{label_a} and {label_b} share {len(shared)} variant site(s) "
                f"(< {_MIN_SHARED_VARIANTS} needed); too few to corroborate "
                "(concordance is not ground truth)",
                value=None,
                expected_range=f">= {_WARN_BELOW}",
            )
        ]

    matches = sum(vep_map[k] == snpeff_map[k] for k in shared)
    raw = matches / len(shared)
    status = "warn" if raw < _WARN_BELOW else "pass"
    fraction = round(raw, 4)
    return [
        _concordance(
            "consequence_concordance",
            status,
            f"{label_a} vs {label_b}: {matches}/{len(shared)} shared site(s) agree "
            f"on the most-severe consequence (agreement {fraction}); layout={layout}",
            value=fraction,
            expected_range=f">= {_WARN_BELOW}",
        )
    ]


# --- gene_symbol_concordance (informational-only; phase 3) -----------------------

# SnpEff ANN has a fixed column layout: Allele|Annotation|Annotation_Impact|
# Gene_Name|... ("Gene_Name" is SnpEff's name for the gene symbol). Unlike CSQ,
# this index is never header-resolved -- nf-core/sarek's SnpEff output is fixed.
_ANN_SYMBOL_INDEX = 3


def _symbol_index_csq(header_lines: list[str]) -> int | None:
    """Resolve the `SYMBOL` subfield index from the CSQ INFO header line.

    Mirrors `annotation_plausibility._consequence_index_csq` exactly, but
    resolves `SYMBOL` instead of `Consequence`. Returns None when there is no
    CSQ INFO header line, or its `Format:` string does not declare a `SYMBOL`
    subfield (never guess an index).
    """
    marker = "Format:"
    for line in header_lines:
        if not line.startswith("##INFO=<ID=CSQ,"):
            continue
        idx = line.find(marker)
        if idx == -1:
            return None
        rest = line[idx + len(marker):]
        end = rest.find('"')
        if end != -1:
            rest = rest[:end]
        fields = [f.strip() for f in rest.split("|")]
        try:
            return fields.index("SYMBOL")
        except ValueError:
            return None
    return None


def _resolve_symbol_index(key: str, header_lines: list[str]) -> int | None:
    """The gene-symbol subfield index for `key` ("CSQ" or "ANN"), or None."""
    if key == "CSQ":
        return _symbol_index_csq(header_lines)
    if key == "ANN":
        return _ANN_SYMBOL_INDEX
    return None


def _normalize_symbol(s: str) -> str | None:
    """Fixed, minimal symbol normalization: strip, then casefold.

    Returns None (unresolvable) when the result is empty or literally ".".
    NOTHING else is done here -- no alias map, no gene-ID fallback (gap-fix 1;
    the FIXED minimal normalization is deliberate, not a placeholder). Any
    residual mismatch AFTER this fold (e.g. "BRCA1" vs "BRCA1P1", a real
    disagreement between VEP's and SnpEff's gene models) is counted as a
    GENUINE disagreement, not UNVERIFIED -- UNVERIFIED is reserved solely for
    the unresolvable/too-few-resolvable-pairs case below.
    """
    normalized = s.strip().casefold()
    if normalized == "" or normalized == ".":
        return None
    return normalized


def parse_symbols(vcf_path: str | os.PathLike, key: str) -> dict[SiteKey, str | None]:
    """Stream a (gzip-transparent) VCF; map each site to its normalized `key` symbol.

    Like `parse_consequences`, but extracts the gene symbol instead of the
    consequence term. Collects header lines to resolve the symbol subfield
    index for `key` ("CSQ" or "ANN") via `_resolve_symbol_index`. If that index
    cannot be resolved (key undeclared, or CSQ's `Format:` string doesn't
    declare `SYMBOL`), returns `{}` (never guess an index).

    For each data record with >= 8 tab columns whose INFO (column 7, 0-based)
    carries a `key=` token, splits the value on `,` (one entry per transcript),
    takes subfield `sym_index` of the FIRST transcript entry (a documented
    deterministic choice -- we do not attempt to reconcile symbols across a
    record's multiple transcripts), and `_normalize_symbol`s it. Maps
    `(CHROM, POS, REF, ALT)` to the normalized symbol, or None when the
    subfield is missing/empty/"." (unresolvable at that site -- still present
    in the map, so callers can distinguish "unresolvable" from "no signal at
    all"). Records that don't carry `key` at all are skipped entirely.
    """
    header_lines: list[str] = []
    sym_index: int | None = None
    resolved = False
    result: dict[SiteKey, str | None] = {}

    with _open_text(vcf_path) as fh:
        for line in fh:
            if line.startswith("#"):
                header_lines.append(line)
                continue

            if not resolved:
                sym_index = _resolve_symbol_index(key, header_lines)
                resolved = True
                if sym_index is None:
                    return {}

            data_line = line.rstrip("\n")
            if not data_line:
                continue
            cols = data_line.split("\t")
            if len(cols) < 8:
                continue
            info = cols[7]

            raw: str | None = None
            for field in info.split(";"):
                parts = field.split("=", 1)
                if parts[0] == key and len(parts) == 2:
                    raw = parts[1]
                    break
            if raw is None:
                continue  # record doesn't carry `key` at all -> skip entirely

            assert sym_index is not None  # resolved above once key is present
            first_entry = raw.split(",")[0]
            subfields = first_entry.split("|")
            raw_symbol = subfields[sym_index] if sym_index < len(subfields) else ""
            site: SiteKey = (cols[0], cols[1], cols[3], cols[4])
            result[site] = _normalize_symbol(raw_symbol)

    return result


def evaluate_gene_symbol_concordance(
    vep_syms: dict[SiteKey, str | None],
    snpeff_syms: dict[SiteKey, str | None],
    *,
    label_a: str = "vep",
    label_b: str = "snpeff",
) -> list[QCResult]:
    """Emit the one gene-symbol-concordance check between VEP and SnpEff.

    INFORMATIONAL-ONLY: unlike `evaluate_consequence_concordance`, the status
    is ALWAYS "pass" when computable -- VEP and SnpEff draw gene symbols from
    different transcript sets/gene models, so a WARN threshold here would
    train users to ignore the signal. The fraction is reported for context,
    never as a verdict lever (`expected_range=None`, no threshold).

    The denominator is the RESOLVABLE pair count -- shared sites where BOTH
    sides normalized to a non-None symbol -- NOT the raw shared-site count;
    unresolvable sides are excluded, never counted as mismatches. Below
    `_MIN_SHARED_VARIANTS` resolvable pairs, a fraction is meaningless (a
    couple of pairs could report 1.0 -> a false pass), so this degrades to
    UNVERIFIED (value=None) instead -- NEVER a false pass. Always
    `kind="concordance"`.
    """
    resolvable = [
        k
        for k in (set(vep_syms) & set(snpeff_syms))
        if vep_syms[k] is not None and snpeff_syms[k] is not None
    ]

    if len(resolvable) < _MIN_SHARED_VARIANTS:
        return [
            _concordance(
                "gene_symbol_concordance",
                "unverified",
                f"{label_a} and {label_b} have {len(resolvable)} resolvable gene-symbol "
                f"pair(s) (< {_MIN_SHARED_VARIANTS} needed); too few resolvable symbol "
                "pairs to corroborate (concordance is not ground truth)",
                value=None,
                expected_range=None,
            )
        ]

    matches = sum(vep_syms[k] == snpeff_syms[k] for k in resolvable)
    raw = matches / len(resolvable)
    fraction = round(raw, 4)
    return [
        _concordance(
            "gene_symbol_concordance",
            "pass",
            f"{label_a} vs {label_b}: {matches}/{len(resolvable)} resolvable gene-symbol "
            f"pair(s) agree (agreement {fraction}); informational only, never affects "
            "the verdict",
            value=fraction,
            expected_range=None,
        )
    ]
