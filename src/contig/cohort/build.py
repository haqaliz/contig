"""Build the local cohort index from M1 variants JSON files."""

from __future__ import annotations

import re
from collections import defaultdict
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.cohort.models import Cohort, CohortMeta, CohortRun, CohortVariant, GeneSummary
from contig.models import sha256_file
from contig.reporting.inputs import load_variants_json
from contig.variants.vcf import normalize_chrom


def _contig_version() -> str:
    try:
        return pkg_version("contig")
    except PackageNotFoundError:
        return "unknown"


def _chrom_sort(chrom: str) -> tuple[int, str]:
    match = re.fullmatch(r"(\d+)(.*)", chrom)
    if match:
        return (int(match.group(1)), match.group(2))
    order = {"X": 23, "Y": 24, "MT": 25}
    return (order.get(chrom, 26), chrom)


def build_cohort(name: str, paths: list[str], *, anonymize: bool = False) -> Cohort:
    if not paths:
        raise ValueError("at least one variants JSON is required")

    runs: list[CohortRun] = []
    variant_runs: dict[tuple[str, int, str, str], set[str]] = defaultdict(set)
    variant_genes: dict[tuple[str, int, str, str], set[str]] = defaultdict(set)
    variant_consequences: dict[tuple[str, int, str, str], set[str]] = defaultdict(set)
    variant_clinvar: dict[tuple[str, int, str, str], set[str]] = defaultdict(set)
    gene_runs: dict[str, set[str]] = defaultdict(set)
    gene_variants: dict[str, set[tuple[str, int, str, str]]] = defaultdict(set)
    used_labels: set[str] = set()
    seen_digests: dict[str, str] = {}
    duplicate_notes: list[str] = []

    for raw_path in paths:
        path = Path(raw_path)
        payload = load_variants_json(path)
        digest = sha256_file(path)
        if digest in seen_digests:
            duplicate_notes.append(
                f"duplicate input skipped: {path} (same content as {seen_digests[digest]})"
            )
            continue
        seen_digests[digest] = str(path)
        label = digest[:12] if anonymize else path.stem
        if label in used_labels:
            label = f"{label}-{digest[:6]}"
        used_labels.add(label)
        runs.append(CohortRun(
            label=label,
            path="" if anonymize else str(path),
            sha256=digest,
        ))

        for row in payload.get("variants", []):
            raw_key = row.get("key") or {}
            try:
                key = (
                    normalize_chrom(str(raw_key["chrom"])),
                    int(raw_key["pos"]),
                    str(raw_key["ref"]),
                    str(raw_key["alt"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            variant_runs[key].add(label)
            gene = row.get("gene")
            if gene:
                gene = str(gene)
                variant_genes[key].add(gene)
                gene_runs[gene].add(label)
                gene_variants[gene].add(key)
            consequence = row.get("consequence")
            if consequence:
                variant_consequences[key].add(str(consequence))
            significance = row.get("clinvar_significance")
            if significance:
                variant_clinvar[key].add(str(significance))

    total_runs = len(runs)
    variants = [
        CohortVariant(
            chrom=chrom,
            pos=pos,
            ref=ref,
            alt=alt,
            seen_runs=len(variant_runs[(chrom, pos, ref, alt)]),
            frequency=len(variant_runs[(chrom, pos, ref, alt)]) / total_runs,
            genes=sorted(variant_genes[(chrom, pos, ref, alt)]),
            consequences=sorted(variant_consequences[(chrom, pos, ref, alt)]),
            clinvar_significance=sorted(variant_clinvar[(chrom, pos, ref, alt)]),
        )
        for (chrom, pos, ref, alt) in variant_runs
    ]
    variants.sort(key=lambda v: (_chrom_sort(v.chrom), v.pos, v.ref, v.alt))

    genes = [
        GeneSummary(
            gene=gene,
            variant_count=len(gene_variants[gene]),
            runs_with_gene=len(gene_runs[gene]),
        )
        for gene in gene_variants
    ]
    genes.sort(key=lambda g: g.gene)

    return Cohort(
        meta=CohortMeta(
            name=name,
            runs=runs,
            total_runs=total_runs,
            contig_version=_contig_version(),
            anonymized=anonymize,
            notes=[
                "Local-only cohort: no data leaves this machine.",
                f"{len(variants)} variant(s) across {total_runs} unique run(s).",
                *duplicate_notes,
            ],
        ),
        variants=variants,
        genes=genes,
    )


def write_cohort(cohort: Cohort, path: str | Path) -> None:
    Path(path).write_text(cohort.model_dump_json(indent=2), encoding="utf-8")
