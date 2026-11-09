"""Build and render the family/trio table."""

from __future__ import annotations

import json
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from contig.family.analyze import analyze_variant, pairwise_concordance, summarize
from contig.family.models import FamilyMeta, FamilyRow, FamilyTable, SourceProvenance
from contig.family.ped import load_families
from contig.family.vcf import read_family_variants
from contig.models import sha256_file

COLUMNS = [
    "family_id", "child", "chrom", "pos", "ref", "alt", "gene", "consequence",
    "child_gt", "father_gt", "mother_gt", "inheritance",
    "mendelian_consistent", "de_novo_candidate",
]

RESEARCH_USE_NOTICE = (
    "Research use only: inheritance and Mendelian checks are genotype "
    "calculations, not a clinical interpretation or diagnosis."
)


def _contig_version() -> str:
    try:
        return pkg_version("contig")
    except PackageNotFoundError:
        return "unknown"


def _source(kind: str, path: str | Path, note: str) -> SourceProvenance:
    return SourceProvenance(kind=kind, path=str(path), sha256=sha256_file(path), note=note)


def build_family_table(vcf_path: str | Path, ped_path: str | Path) -> FamilyTable:
    families = load_families(ped_path)
    samples = [sample for family in families for sample in family.samples]
    variants, stats = read_family_variants(vcf_path, samples)
    rows: list[FamilyRow] = []
    concordance: list[dict[str, object]] = []
    for family in families:
        for variant in variants:
            rows.extend(analyze_variant(family, variant))
        concordance.extend(pairwise_concordance(family, variants))

    summary = summarize(rows)
    summary["families"] = len(families)
    summary["per_family"] = {
        family.family_id: summarize(
            [row for row in rows if row.family_id == family.family_id]
        )
        for family in families
    }
    child_count = sum(len(family.children) for family in families)
    meta = FamilyMeta(
        family_id=families[0].family_id,
        family_ids=[family.family_id for family in families],
        samples=samples,
        sources=[
            _source("vcf", vcf_path, f"{stats.total_records} records; {stats.emitted_rows} ALT rows"),
            _source(
                "ped",
                ped_path,
                f"{len(families)} families; {len(samples)} samples; "
                f"{child_count} child(ren)",
            ),
        ],
        summary=summary,
        concordance=concordance,
        contig_version=_contig_version(),
        notes=(
            [f"{stats.skipped_lines} malformed VCF lines skipped"]
            if stats.skipped_lines else []
        ),
    )
    return FamilyTable(rows=rows, meta=meta)


def _consistent(value: bool | None) -> str:
    if value is None:
        return "not_evaluated"
    return "yes" if value else "no"


def render_tsv(table: FamilyTable) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in table.rows:
        values = [
            row.family_id,
            row.child,
            row.key.chrom,
            row.key.pos,
            row.key.ref,
            row.key.alt,
            row.gene or "",
            row.consequence or "unannotated",
            row.child_gt or "",
            row.father_gt or "",
            row.mother_gt or "",
            row.inheritance,
            _consistent(row.mendelian_consistent),
            "yes" if row.de_novo_candidate else "no",
        ]
        lines.append("\t".join(str(value) for value in values))
    return "\n".join(lines) + "\n"


def render_json(table: FamilyTable) -> str:
    payload = {
        "meta": table.meta.model_dump(mode="json"),
        "rows": [asdict(row) for row in table.rows],
    }
    return json.dumps(payload, indent=2) + "\n"


def write_table(table: FamilyTable, path: str | Path, *, as_json: bool = False) -> None:
    Path(path).write_text(render_json(table) if as_json else render_tsv(table), encoding="utf-8")
