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
from pathlib import Path
from typing import Iterable

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


# --- run-level discovery + auto-wire (phase 4, C7 M4) ---------------------------
#
# Everything above is the PURE core (parsing + the two metric functions); this is
# the run-level entry that DISCOVERS the annotation source(s) under a run dir and
# auto-wires both metrics -- no CLI flag, no user input (the "somatic auto" path,
# mirroring `somatic_concordance.evaluate_somatic_concordance_from_run` /
# `select_caller_vcfs` exactly).


def _declared_annotation_keys(vcf_path: str | os.PathLike) -> set[str]:
    """Which of {"CSQ", "ANN"} the VCF's header DECLARES, or an empty set.

    Unlike `annotation_structural._declared_key` (which returns only the FIRST
    key found -- by design for that module's single-key structural check), this
    returns the FULL declared set, because detecting a single VCF that declares
    BOTH (the single-vcf-both layout) requires knowing about both at once.
    """
    keys: set[str] = set()
    with _open_text(vcf_path) as fh:
        for line in fh:
            if not line.startswith("#"):
                break
            for key in ("CSQ", "ANN"):
                if line.startswith(f"##INFO=<ID={key},"):
                    keys.add(key)
    return keys


def _one_annotator_only(present_tool: str) -> list[QCResult]:
    """Both metrics, UNVERIFIED: only `present_tool` ran under this run."""
    message = (
        f"only {present_tool} annotation is present under this run; the other "
        "annotator did not run (e.g. a missing SnpEff cache) -- cannot compute "
        "concordance"
    )
    return [
        _concordance(
            "consequence_concordance",
            "unverified",
            message,
            value=None,
            expected_range=f">= {_WARN_BELOW}",
        ),
        _concordance(
            "gene_symbol_concordance",
            "unverified",
            message,
            value=None,
            expected_range=None,
        ),
    ]


def _ambiguous_layout(vep_count: int, snpeff_count: int) -> list[QCResult]:
    """Both metrics, UNVERIFIED: too many candidate files on one/both sides,
    even after path-component disambiguation -- mirrors
    `select_caller_vcfs`'s ambiguity -> UNVERIFIED (never an arbitrary pick)."""
    message = (
        f"cannot compute concordance: {vep_count} candidate VEP (CSQ) file(s) and "
        f"{snpeff_count} candidate SnpEff (ANN) file(s) remain ambiguous after "
        "path-component disambiguation; not computed for an ambiguous layout"
    )
    return [
        _concordance(
            "consequence_concordance",
            "unverified",
            message,
            value=None,
            expected_range=f">= {_WARN_BELOW}",
        ),
        _concordance(
            "gene_symbol_concordance",
            "unverified",
            message,
            value=None,
            expected_range=None,
        ),
    ]


def _evaluate_both_metrics(
    vep_path: str | os.PathLike,
    snpeff_path: str | os.PathLike,
    *,
    layout: str,
) -> list[QCResult]:
    vep_cons = parse_consequences(vep_path, "CSQ")
    snpeff_cons = parse_consequences(snpeff_path, "ANN")
    vep_syms = parse_symbols(vep_path, "CSQ")
    snpeff_syms = parse_symbols(snpeff_path, "ANN")
    return evaluate_consequence_concordance(
        vep_cons, snpeff_cons, layout=layout
    ) + evaluate_gene_symbol_concordance(vep_syms, snpeff_syms)


def evaluate_annotation_concordance_from_run(
    run_dir: str | os.PathLike,
    vcfs: Iterable[str | os.PathLike] | None = None,
) -> list[QCResult]:
    """Discover VEP/SnpEff annotation under a run dir and evaluate BOTH
    concordance metrics (consequence + gene-symbol) against each other.

    Header-key detection is PRIMARY: a candidate is any `*.vcf.gz` under
    `run_dir` (or the explicit `vcfs` list, rglob'd sorted when omitted) whose
    header declares CSQ and/or ANN. No candidate at all -> clean `[]` skip
    (annotation absent, or nothing to corroborate) -- never a spurious
    UNVERIFIED.

    Layout resolution, in order:
    1. single-vcf-both: some candidate declares BOTH CSQ and ANN -> use it.
    2. two-file: split the remaining candidates by declared key.
       - exactly one on each side -> use them directly.
       - one side EMPTY (only one annotator ran) -> `_one_annotator_only`.
       - multiple on a side -> path-component tie-break SECONDARY (a `vep` /
         `snpeff` path component below `run_dir`, mirroring
         `select_caller_vcfs`'s caller-name match); exactly one each after
         that -> use them; otherwise `_ambiguous_layout` (never an arbitrary
         pick).
    """
    run_dir = Path(run_dir)
    candidate_paths = [
        Path(v) for v in (vcfs if vcfs is not None else sorted(run_dir.rglob("*.vcf.gz")))
    ]
    keyed = [(v, _declared_annotation_keys(v)) for v in candidate_paths]
    keyed = [(v, keys) for v, keys in keyed if keys]

    if not keyed:
        return []

    both = next((v for v, keys in keyed if keys == {"CSQ", "ANN"}), None)
    if both is not None:
        return _evaluate_both_metrics(both, both, layout="single-vcf-both")

    vep_candidates = [v for v, keys in keyed if "CSQ" in keys]
    snpeff_candidates = [v for v, keys in keyed if "ANN" in keys]

    if not vep_candidates or not snpeff_candidates:
        present_tool = "VEP" if vep_candidates else "SnpEff"
        return _one_annotator_only(present_tool)

    if len(vep_candidates) == 1 and len(snpeff_candidates) == 1:
        return _evaluate_both_metrics(
            vep_candidates[0], snpeff_candidates[0], layout="two-file"
        )

    def _has_component(p: Path, name: str) -> bool:
        return name in {part.lower() for part in p.relative_to(run_dir).parts}

    vep_disambiguated = [v for v in vep_candidates if _has_component(v, "vep")]
    snpeff_disambiguated = [v for v in snpeff_candidates if _has_component(v, "snpeff")]
    if len(vep_disambiguated) == 1 and len(snpeff_disambiguated) == 1:
        return _evaluate_both_metrics(
            vep_disambiguated[0], snpeff_disambiguated[0], layout="two-file"
        )

    return _ambiguous_layout(len(vep_candidates), len(snpeff_candidates))
