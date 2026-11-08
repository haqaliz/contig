"""Build and render the research-use variant table."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.models import sha256_file
from contig.variants.filters import apply_filters, matches, sort_rows
from contig.variants.gnomad import GnomadClient, GraphQLGnomadClient, load_gnomad
from contig.variants.models import (
    FilterSpec,
    SourceProvenance,
    TableMeta,
    VariantRecord,
    VariantTable,
)
from contig.variants.sources import (
    infer_build_from_vcf,
    load_clinvar,
    load_frequencies,
    load_iranome,
)
from contig.variants.vcf import VariantCapExceeded, read_variants

COLUMNS = [
    "chrom", "pos", "ref", "alt", "rsid", "gene", "transcript",
    "consequence", "impact", "hgvsc", "hgvsp", "genotype", "zygosity",
    "depth", "vaf", "filter", "clinvar_significance", "clinvar_review_status",
    "clinvar_condition", "clinvar_variant_type", "clinvar_hgvs",
    "population_af", "population_an", "iranome_af", "iranome_ac", "iranome_an",
]

RESEARCH_USE_NOTICE = (
    "Research use only: this table reports what the named sources say. "
    "It is not a diagnosis, a clinical classification, or treatment advice."
)


def _contig_version() -> str:
    try:
        return pkg_version("contig")
    except PackageNotFoundError:
        return "unknown"


def build_table(
    calls: str | Path,
    *,
    clinvar: str | Path | None = None,
    iranome: str | Path | None = None,
    frequencies: str | Path | None = None,
    gnomad_api: bool = False,
    gnomad_client: GnomadClient | None = None,
    gnomad_cache: str | Path | None = None,
    gnomad_dataset: str = "gnomad_r4",
    build: str | None = None,
    spec: FilterSpec | None = None,
    max_records: int | None = 1_000_000,
) -> VariantTable:
    spec = spec or FilterSpec()
    calls = Path(calls)
    if not calls.is_file():
        raise FileNotFoundError(f"VCF not found: {calls}")
    if max_records is not None and max_records < 1:
        raise ValueError("max_records must be at least 1")
    build = build or infer_build_from_vcf(calls)

    early = FilterSpec(genes=spec.genes, region=spec.region)
    try:
        rows, stats = read_variants(
            calls,
            keep=lambda record: matches(record, early),
            max_records=max_records,
        )
    except VariantCapExceeded as exc:
        if spec.region or spec.genes:
            raise ValueError(
                f"the bounded query still exceeded the {exc.cap:,}-record cap; "
                "narrow --region/--genes or raise --max-records explicitly"
            ) from exc
        raise ValueError(
            f"VCF has more than {exc.cap:,} records; pass --region CHROM:START-END "
            "or --gene SYMBOL,... to bound a WGS input, or raise --max-records "
            "explicitly"
        ) from exc
    sites = {row.key for row in rows}
    sources = [
        SourceProvenance(
            kind="calls",
            path=str(calls),
            sha256=sha256_file(calls),
            build=build,
            note=(
                f"{len(rows)} ALT rows from {stats.total_records} records"
                + (f"; {stats.skipped_lines} malformed lines skipped" if stats.skipped_lines else "")
            ),
        )
    ]
    notes: list[str] = list(stats.notes)

    if clinvar:
        clinvar_build = infer_build_from_vcf(clinvar)
        if build and clinvar_build and clinvar_build != build:
            note = f"skipped: ClinVar is {clinvar_build}, input build is {build}"
            sources.append(
                SourceProvenance(
                    kind="clinvar",
                    path=str(clinvar),
                    sha256=sha256_file(clinvar),
                    build=clinvar_build,
                    note=note,
                )
            )
            notes.append(note)
        else:
            evidence, provenance = load_clinvar(clinvar, sites, build)
            sources.append(provenance)
            notes.append(provenance.note or "")
            rows = [
                dataclasses.replace(
                    row,
                    clinvar_significance=(evidence.get(row.key).significance if evidence.get(row.key) else None),
                    clinvar_review_status=(evidence.get(row.key).review_status if evidence.get(row.key) else None),
                    clinvar_condition=(evidence.get(row.key).condition if evidence.get(row.key) else None),
                    clinvar_variant_type=(evidence.get(row.key).variant_type if evidence.get(row.key) else None),
                    clinvar_hgvs=(evidence.get(row.key).hgvs if evidence.get(row.key) else None),
                )
                for row in rows
            ]

    if iranome:
        evidence, provenance = load_iranome(iranome, sites, build)
        sources.append(provenance)
        notes.append(provenance.note or "")
        rows = [
            dataclasses.replace(
                row,
                iranome_af=(evidence.get(row.key).af if evidence.get(row.key) else None),
                iranome_ac=(evidence.get(row.key).ac if evidence.get(row.key) else None),
                iranome_an=(evidence.get(row.key).an if evidence.get(row.key) else None),
            )
            for row in rows
        ]

    if frequencies:
        evidence, provenance = load_frequencies(frequencies, sites)
        sources.append(provenance)
        notes.append(provenance.note or "")
        rows = [
            dataclasses.replace(
                row,
                population_af=(evidence.get(row.key).af if evidence.get(row.key) else None),
                population_an=(evidence.get(row.key).an if evidence.get(row.key) else None),
            )
            for row in rows
        ]

    if gnomad_api:
        if frequencies:
            raise ValueError("use either --frequencies or --gnomad-api, not both")
        client = gnomad_client or GraphQLGnomadClient(dataset=gnomad_dataset)
        evidence, provenance = load_gnomad(
            sites, client, cache_path=gnomad_cache, dataset=gnomad_dataset
        )
        sources.append(provenance)
        notes.append(provenance.note or "")
        rows = [
            dataclasses.replace(
                row,
                population_af=(evidence.get(row.key).af if evidence.get(row.key) else None),
                population_an=(evidence.get(row.key).an if evidence.get(row.key) else None),
            )
            for row in rows
        ]

    rows = sort_rows(apply_filters(rows, spec))
    meta = TableMeta(
        sources=sources,
        filters=spec,
        build=build,
        contig_version=_contig_version(),
        notes=[note for note in notes if note],
    )
    return VariantTable(rows=rows, meta=meta)


def _has_source(table: VariantTable, kind: str) -> bool:
    return any(source.kind == kind for source in table.meta.sources)


def _format(value: object, *, missing: str = "") -> str:
    if value is None:
        return missing
    if isinstance(value, float):
        return str(value)
    return str(value)


def render_tsv(table: VariantTable) -> str:
    clinvar_present = _has_source(table, "clinvar")
    lines = ["\t".join(COLUMNS)]
    for row in table.rows:
        values = [
            row.key.chrom,
            row.key.pos,
            row.key.ref,
            row.key.alt,
            _format(row.rsid),
            _format(row.gene),
            _format(row.transcript),
            _format(row.consequence, missing="unannotated"),
            _format(row.impact),
            _format(row.hgvsc),
            _format(row.hgvsp),
            _format(row.genotype),
            _format(row.zygosity),
            _format(row.depth),
            _format(row.vaf),
            _format(row.filter),
            _format(row.clinvar_significance, missing="not in ClinVar" if clinvar_present else ""),
            _format(row.clinvar_review_status),
            _format(row.clinvar_condition),
            _format(row.clinvar_variant_type),
            _format(row.clinvar_hgvs),
            _format(row.population_af),
            _format(row.population_an),
            _format(row.iranome_af),
            _format(row.iranome_ac),
            _format(row.iranome_an),
        ]
        lines.append("\t".join(str(value) for value in values))
    return "\n".join(lines) + "\n"


def render_json(table: VariantTable) -> str:
    payload = {
        "meta": table.meta.model_dump(mode="json"),
        "variants": [asdict(row) for row in table.rows],
    }
    return json.dumps(payload, indent=2) + "\n"


def write_table(table: VariantTable, path: str | Path, *, as_json: bool = False) -> None:
    Path(path).write_text(render_json(table) if as_json else render_tsv(table), encoding="utf-8")
