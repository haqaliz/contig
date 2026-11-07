"""Deterministic filters and sort order for the variant workbench.

There is no learned ranking here. The order is documented and stable:
ClinVar significance severity, then population AF (rarest first), then
consequence severity, then genomic position.
"""

from __future__ import annotations

import re

from contig.variants.models import FilterSpec, VariantRecord
from contig.variants.vcf import CONSEQUENCE_SEVERITY, normalize_chrom

_CONSEQUENCE_RANK = {term: index for index, term in enumerate(CONSEQUENCE_SEVERITY)}


def _norm(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("|", " ").replace("/", " ")).strip().lower()


def _term_in(value: str | None, term: str) -> bool:
    """Token-boundary match so `pathogenic` does not match `pathogenicity`."""
    normalized = _norm(value)
    needle = _norm(term)
    if not normalized or not needle:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", normalized) is not None


def clinvar_rank(significance: str | None) -> int:
    """0 is the most actionable ClinVar bucket, 7 is absent. Not a Contig call."""
    value = _norm(significance)
    if not value:
        return 7
    if "conflicting" in value:
        return 2
    if "likely pathogenic" in value:
        return 1
    if "pathogenic" in value:
        return 0
    if "uncertain" in value or "vus" in value:
        return 3
    if "likely benign" in value:
        return 4
    if "benign" in value:
        return 5
    if "not provided" in value or "not in clinvar" in value:
        return 6
    return 6


def consequence_rank(consequence: str | None) -> int:
    if not consequence:
        return len(CONSEQUENCE_SEVERITY) + 1
    return _CONSEQUENCE_RANK.get(consequence, len(CONSEQUENCE_SEVERITY))


def _af(record: VariantRecord) -> float | None:
    if record.gnomad_af is not None:
        return record.gnomad_af
    return record.iranome_af


def _matches_region(record: VariantRecord, region: str | None) -> bool:
    if not region:
        return True
    match = re.fullmatch(r"\s*([^:]+):([\d,]+)-([\d,]+)\s*", region)
    if not match:
        raise ValueError("region must look like CHROM:START-END (for example 17:43000000-43100000)")
    chrom = normalize_chrom(match.group(1))
    start = int(match.group(2).replace(",", ""))
    end = int(match.group(3).replace(",", ""))
    if start > end:
        raise ValueError("region start must be <= end")
    return normalize_chrom(record.key.chrom) == chrom and start <= record.key.pos <= end


def matches(record: VariantRecord, spec: FilterSpec) -> bool:
    if not _matches_region(record, spec.region):
        return False

    if spec.genes and (record.gene or "").upper() not in {g.upper() for g in spec.genes}:
        return False

    if spec.consequences:
        consequence = _norm(record.consequence)
        if not consequence or not any(_norm(term) in consequence for term in spec.consequences):
            return False

    if spec.max_af is not None:
        af = _af(record)
        if af is not None and af > spec.max_af:
            return False

    if spec.clinvar_significance:
        if not any(_term_in(record.clinvar_significance, term) for term in spec.clinvar_significance):
            return False

    if spec.pass_only and record.filter not in {"PASS", "."}:
        return False

    if spec.min_depth is not None:
        if record.depth is None or record.depth < spec.min_depth:
            return False

    if spec.min_vaf is not None:
        if record.vaf is None or record.vaf < spec.min_vaf:
            return False

    if spec.zygosity and record.zygosity != spec.zygosity:
        return False

    return True


def apply_filters(rows: list[VariantRecord], spec: FilterSpec) -> list[VariantRecord]:
    return [row for row in rows if matches(row, spec)]


def _chrom_sort(chrom: str) -> tuple[int, str]:
    value = normalize_chrom(chrom)
    match = re.fullmatch(r"(\d+)(.*)", value)
    if match:
        return (int(match.group(1)), match.group(2))
    order = {"X": 23, "Y": 24, "MT": 25}
    return (order.get(value, 26), value)


def sort_rows(rows: list[VariantRecord]) -> list[VariantRecord]:
    return sorted(
        rows,
        key=lambda row: (
            clinvar_rank(row.clinvar_significance),
            _af(row) if _af(row) is not None else 2.0,
            consequence_rank(row.consequence),
            _chrom_sort(row.key.chrom),
            row.key.pos,
            row.key.ref,
            row.key.alt,
        ),
    )
