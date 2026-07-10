"""Deterministic CSQ/ANN consequence-parsing plausibility metrics.

The structural verifier (`annotation_structural.py`) proves an annotation step
ran; it says nothing about what the annotation *found*. This module adds a
biological-plausibility axis on top: it reads the VEP `CSQ` or SnpEff `ANN`
INFO field, resolves each variant's most-severe consequence against a small
fixed severity ordering, and reports what fraction of annotated records
received a "real" (non-intergenic) consequence vs. an intergenic one.

Research-use only: this is a plausibility smell test, not a pathogenicity or
clinical judgement. Every metric degrades to `None` (never a false pass) when
it cannot be honestly computed — an unresolvable CSQ `Format:` string, or no
record carrying the annotation field at all.

This module carries its own small VCF pass; per the codebase's convention
(see `somatic_plausibility.py:20-23`), it does not add a shared VCF
abstraction. It reuses `_open_text` (gzip-transparent open), `_declared_key`
(header key detection), and `_record_has_key` (INFO-field presence) from
`annotation_structural.py`. The evaluator wrapper below runs the WARN-capped
`ANNOTATION_PLAUSIBILITY_PACK` (see `rule_pack.py`) over the computable
metrics and, per the never-a-false-pass guarantee, emits an explicit
`unverified` result for any metric the parser could not honestly compute.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from contig.models import QCResult
from contig.verification.annotation_structural import (
    _declared_key,
    _open_text,
    _record_has_key,
)
from contig.verification.rule_pack import ANNOTATION_PLAUSIBILITY_PACK, evaluate

# D1 — minimal SO-severity ordering for "most-severe consequence per variant".
# Least -> most severe; intergenic_variant is the unique rank 0. An unknown,
# non-empty term ranks ABOVE intergenic (rank _UNKNOWN_RANK == 1) — the
# conservative choice: it counts as a real consequence, never as intergenic.
_SEVERITY_ORDER = (            # index = severity rank; 0 = least severe
    "intergenic_variant",     # rank 0 — the ONLY term that marks a variant "intergenic"
    "downstream_gene_variant",
    "upstream_gene_variant",
    "intron_variant",
    "non_coding_transcript_exon_variant",
    "non_coding_transcript_variant",
    "3_prime_UTR_variant",
    "5_prime_UTR_variant",
    "synonymous_variant",
    "stop_retained_variant",
    "start_retained_variant",
    "splice_region_variant",
    "protein_altering_variant",
    "inframe_deletion",
    "inframe_insertion",
    "missense_variant",
    "start_lost",
    "stop_lost",
    "frameshift_variant",
    "stop_gained",
    "splice_donor_variant",
    "splice_acceptor_variant",
    "transcript_ablation",
)
_SEVERITY_RANK = {term: i for i, term in enumerate(_SEVERITY_ORDER)}
_UNKNOWN_RANK = 1             # unknown non-empty term > intergenic ⇒ treated as "real"

# SnpEff ANN has a fixed column layout: Allele|Annotation|Annotation_Impact|...
# ("Annotation" is SnpEff's name for the consequence term). Unlike CSQ, this
# index is never header-resolved — nf-core/sarek's SnpEff output is fixed.
_ANN_CONSEQUENCE_INDEX = 1


@dataclass(frozen=True)
class AnnotationPlausibilityMetrics:
    """Consequence-distribution metrics over records that carry CSQ/ANN.

    Both fields are None together whenever they cannot be honestly computed:
    the CSQ Format string doesn't declare a Consequence subfield, or no record
    carries the annotation field at all (UNVERIFIED, never a guessed value).
    """

    real_consequence_fraction: float | None
    intergenic_fraction: float | None


_UNCOMPUTABLE = AnnotationPlausibilityMetrics(
    real_consequence_fraction=None, intergenic_fraction=None
)


def _consequence_index_csq(header_lines: list[str]) -> int | None:
    """Resolve the `Consequence` subfield index from the CSQ INFO header line.

    Parses `##INFO=<ID=CSQ,...Description="...Format: A|B|C">`'s `Format:`
    string, splits it on `|`, and returns the index of the `Consequence`
    column. Returns None when there is no CSQ INFO header line, or its Format
    string does not declare a `Consequence` subfield (never guess an index).
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
            return fields.index("Consequence")
        except ValueError:
            return None
    return None


def _variant_terms(info_value: str, key: str, cons_index: int) -> list[str]:
    """Extract lowercased consequence terms for `key` from one INFO string.

    Pulls the `KEY=...` value, splits entries on `,` (one per transcript),
    takes each entry's subfield at `cons_index`, splits that on `&` (VEP's
    multi-consequence join), and returns the lowercased non-empty terms.
    Returns `[]` when `key` is absent, or when every entry's subfield at
    `cons_index` is missing/empty (an "empty" consequence, not "no field").
    """
    raw: str | None = None
    for field in info_value.split(";"):
        parts = field.split("=", 1)
        if parts[0] == key and len(parts) == 2:
            raw = parts[1]
            break
    if raw is None:
        return []

    terms: list[str] = []
    for entry in raw.split(","):
        subfields = entry.split("|")
        if cons_index >= len(subfields):
            continue
        for term in subfields[cons_index].split("&"):
            term = term.strip().lower()
            if term:
                terms.append(term)
    return terms


def _most_severe_rank(terms: list[str]) -> int | None:
    """The highest severity rank across `terms`, or None if `terms` is empty.

    An unknown term (not in `_SEVERITY_ORDER`) ranks `_UNKNOWN_RANK` (1),
    above intergenic_variant's rank 0 — it is conservatively treated as real.
    """
    if not terms:
        return None
    return max(_SEVERITY_RANK.get(term, _UNKNOWN_RANK) for term in terms)


def _resolve_consequence_index(key: str, header_lines: list[str]) -> int | None:
    """The consequence subfield index for `key` ("CSQ" or "ANN"), or None."""
    if key == "CSQ":
        return _consequence_index_csq(header_lines)
    if key == "ANN":
        return _ANN_CONSEQUENCE_INDEX
    return None


def annotation_plausibility_metrics(
    vcf_path: str | os.PathLike,
) -> AnnotationPlausibilityMetrics:
    """Stream an annotated VCF once; compute the consequence-distribution metrics.

    Resolves the annotation key the same way `annotation_metrics` does: the
    header-declared CSQ/ANN INFO key via `_declared_key`, else sniffed from the
    first data record that carries either key. For CSQ, the consequence index
    must also resolve (via the header `Format:` string) — if it does not, both
    metrics are None (UNVERIFIED) rather than guessed.

    Over the records that carry the resolved key ("annotated"), each is:
    - real: most-severe rank >= 1 (a parseable, non-intergenic consequence);
    - intergenic: has >= 1 parseable term and most-severe rank == 0;
    - empty: carries the field but no parseable consequence term.

    `real_consequence_fraction = real / annotated`,
    `intergenic_fraction = intergenic / annotated`; both None when
    `annotated == 0`.
    """
    header_lines: list[str] = []
    key: str | None = None
    cons_index: int | None = None
    resolved = False
    real = 0
    intergenic = 0
    annotated = 0

    with _open_text(vcf_path) as fh:
        for line in fh:
            if line.startswith("#"):
                header_lines.append(line)
                continue

            if not resolved:
                key = _declared_key(header_lines)
                resolved = True
                if key is not None:
                    cons_index = _resolve_consequence_index(key, header_lines)
                    if cons_index is None:
                        return _UNCOMPUTABLE

            data_line = line.rstrip("\n")
            if not data_line:
                continue
            cols = data_line.split("\t")
            if len(cols) < 8:
                continue
            info = cols[7]

            if key is None:
                for candidate in ("CSQ", "ANN"):
                    if _record_has_key(info, candidate):
                        key = candidate
                        cons_index = _resolve_consequence_index(key, header_lines)
                        if cons_index is None:
                            return _UNCOMPUTABLE
                        break

            if key is None or cons_index is None or not _record_has_key(info, key):
                continue

            annotated += 1
            terms = _variant_terms(info, key, cons_index)
            if not terms:
                continue  # field present, no parseable term -> "empty"
            rank = _most_severe_rank(terms)
            if rank == 0:
                intergenic += 1
            else:
                real += 1

    if annotated == 0:
        return _UNCOMPUTABLE

    return AnnotationPlausibilityMetrics(
        real_consequence_fraction=real / annotated,
        intergenic_fraction=intergenic / annotated,
    )


def evaluate_annotation_plausibility(
    vcf_path: str | os.PathLike, label: str = "sample"
) -> list[QCResult]:
    """Evaluate the annotation plausibility rules over a VCF, capped at WARN.

    Computes `AnnotationPlausibilityMetrics` from the CSQ/ANN consequence parse,
    then runs the WARN-capped ANNOTATION_PLAUSIBILITY_PACK over the COMPUTABLE
    metrics via the shared evaluate() (band logic and "<check>:<label>" naming
    stay single-sourced). A None metric is NOT silently skipped: the shared
    evaluate() only sees computable metrics, so each rule whose metric is None
    gets an explicit "unverified" QCResult here instead (never a false pass).
    Every result is kind "metric".
    """
    metrics = annotation_plausibility_metrics(vcf_path)

    by_metric = {
        "real_consequence_fraction": metrics.real_consequence_fraction,
        "intergenic_fraction": metrics.intergenic_fraction,
    }
    computable = {
        metric: value for metric, value in by_metric.items() if value is not None
    }

    results = evaluate({label: computable}, ANNOTATION_PLAUSIBILITY_PACK)

    for rule in ANNOTATION_PLAUSIBILITY_PACK:
        metric = rule["metric"]
        if by_metric[metric] is None:
            results.append(
                QCResult(
                    check=f"{rule['check']}:{label}",
                    status="unverified",
                    message=(
                        f"{label}: {metric} could not be computed "
                        "(unresolvable CSQ Format or no annotated records)"
                    ),
                    value=None,
                    kind="metric",
                )
            )

    return results
