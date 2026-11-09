"""Research-use carrier and couple shared-carrier views.

Per-person rows list every member with an ALT genotype in a recessive-panel
gene. Couple rows list variants where both parents carry an ALT allele, with the
children's genotypes for context. Autosomes only in this slice; X/Y/MT are
skipped and noted, never guessed. No risk estimate, diagnosis, or counselling.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

from pydantic import BaseModel, Field

from contig.family.analyze import alleles
from contig.family.models import SourceProvenance
from contig.family.ped import load_families
from contig.family.vcf import read_family_variants
from contig.models import sha256_file
from contig.variants.models import VariantKey
from contig.variants.vcf import normalize_chrom

COLUMNS = [
    "view", "family_id", "sample", "father", "mother", "children",
    "chrom", "pos", "ref", "alt", "gene", "consequence", "genotype",
    "father_gt", "mother_gt", "child_gt", "status", "child_status",
]

RESEARCH_USE_NOTICE = (
    "Research use only: carrier and couple views are genotype calculations, "
    "not a risk estimate, clinical interpretation, or reproductive advice."
)

SEX_CHROMS = {"X", "Y", "MT"}


@dataclass
class CarrierRow:
    view: str
    family_id: str
    sample: str
    father: str
    mother: str
    children: str
    key: VariantKey
    gene: str | None
    consequence: str | None
    genotype: str | None
    father_gt: str | None
    mother_gt: str | None
    child_gt: str
    status: str
    child_status: str


class CarrierMeta(BaseModel):
    family_ids: list[str] = Field(default_factory=list)
    samples: list[str] = Field(default_factory=list)
    panel_genes: list[str] = Field(default_factory=list)
    sources: list[SourceProvenance] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    contig_version: str = ""
    notes: list[str] = Field(default_factory=list)


@dataclass
class CarrierReport:
    rows: list[CarrierRow]
    meta: CarrierMeta


def _contig_version() -> str:
    try:
        return pkg_version("contig")
    except PackageNotFoundError:
        return "unknown"


def _source(kind: str, path: str | Path, note: str) -> SourceProvenance:
    return SourceProvenance(kind=kind, path=str(path), sha256=sha256_file(path), note=note)


def _alt_count(gt: str | None) -> int | None:
    values = alleles(gt)
    if values is None:
        return None
    return sum(1 for value in values if value > 0)


def _person_status(gt: str | None) -> str | None:
    values = alleles(gt)
    count = _alt_count(gt)
    if values is None or count is None or count == 0:
        return None
    if len(values) == 1:
        return "hemizygous"
    return "homozygous_alt" if count >= 2 else "carrier"


def _couple_status(father_gt: str | None, mother_gt: str | None) -> str | None:
    father = _alt_count(father_gt)
    mother = _alt_count(mother_gt)
    if father is None or mother is None or father == 0 or mother == 0:
        return None
    if father >= 2 and mother >= 2:
        return "both_homozygous"
    if father >= 2 or mother >= 2:
        return "one_homozygous"
    return "both_carriers"


def _child_status(child_gt: dict[str, str | None]) -> str:
    statuses = [_person_status(gt) for gt in child_gt.values()]
    if any(status == "homozygous_alt" for status in statuses):
        return "homozygous_alt"
    if any(status in {"carrier", "hemizygous"} for status in statuses):
        return "carrier"
    if any(alleles(gt) is None for gt in child_gt.values()):
        return "unknown"
    return "not_carried"


def load_panel_genes(path: str | Path) -> set[str]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"recessive panel BED not found: {path}")
    genes: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith(("#", "track", "browser")):
            continue
        fields = line.split("\t") if "\t" in line else line.split()
        if len(fields) < 4:
            continue
        gene = fields[3].strip()
        if gene and gene != ".":
            genes.add(gene.upper())
    if not genes:
        raise ValueError(f"panel BED has no gene names in column 4: {path}")
    return genes


def build_carrier_report(
    vcf_path: str | Path,
    ped_path: str | Path,
    *,
    genes: set[str] | list[str] | None = None,
    panel_path: str | Path | None = None,
) -> CarrierReport:
    panel_genes = {gene.upper() for gene in (genes or []) if gene}
    panel_source = None
    if panel_path:
        panel_genes.update(load_panel_genes(panel_path))
        panel_source = panel_path

    families = load_families(ped_path)
    samples = [sample for family in families for sample in family.samples]
    variants, stats = read_family_variants(vcf_path, samples)

    rows: list[CarrierRow] = []
    sex_chrom_skipped = 0
    panel_skipped = 0
    for variant in variants:
        if normalize_chrom(variant.key.chrom) in SEX_CHROMS:
            sex_chrom_skipped += 1
            continue
        if panel_genes:
            gene = (variant.gene or "").upper()
            if gene not in panel_genes:
                panel_skipped += 1
                continue
        for family in families:
            pairs: dict[tuple[str, str], list[str]] = {}
            for child in family.children:
                pairs.setdefault((child.father_id, child.mother_id), []).append(
                    child.sample_id
                )
            for (father_id, mother_id), child_ids in pairs.items():
                father_gt = variant.genotypes.get(father_id)
                mother_gt = variant.genotypes.get(mother_id)
                couple = _couple_status(father_gt, mother_gt)
                if couple:
                    children_gt = {
                        child_id: variant.genotypes.get(child_id)
                        for child_id in child_ids
                    }
                    rows.append(CarrierRow(
                        view="couple",
                        family_id=family.family_id,
                        sample="",
                        father=father_id,
                        mother=mother_id,
                        children=",".join(child_ids),
                        key=variant.key,
                        gene=variant.gene,
                        consequence=variant.consequence,
                        genotype="",
                        father_gt=father_gt,
                        mother_gt=mother_gt,
                        child_gt=";".join(
                            f"{child_id}={gt or './.'}"
                            for child_id, gt in children_gt.items()
                        ),
                        status=couple,
                        child_status=_child_status(children_gt),
                    ))
            for sample in family.samples:
                genotype = variant.genotypes.get(sample)
                status = _person_status(genotype)
                if not status:
                    continue
                rows.append(CarrierRow(
                    view="person",
                    family_id=family.family_id,
                    sample=sample,
                    father="",
                    mother="",
                    children="",
                    key=variant.key,
                    gene=variant.gene,
                    consequence=variant.consequence,
                    genotype=genotype,
                    father_gt="",
                    mother_gt="",
                    child_gt="",
                    status=status,
                    child_status="",
                ))

    couples = {
        (family.family_id, child.father_id, child.mother_id)
        for family in families
        for child in family.children
    }
    notes = []
    if not panel_genes:
        notes.append("no recessive panel filter applied")
    if sex_chrom_skipped:
        notes.append(
            f"{sex_chrom_skipped} X/Y/MT variant(s) skipped; this slice is autosomal only"
        )
    if panel_skipped:
        notes.append(
            f"{panel_skipped} variant(s) outside the recessive panel skipped"
        )
    sources = [
        _source("vcf", vcf_path, f"{stats.total_records} records; {stats.emitted_rows} ALT rows"),
        _source("ped", ped_path, f"{len(families)} families; {len(samples)} samples"),
    ]
    if panel_source:
        sources.append(_source(
            "recessive_panel",
            panel_source,
            f"{len(panel_genes)} gene(s) in column 4",
        ))

    person_rows = [row for row in rows if row.view == "person"]
    couple_rows = [row for row in rows if row.view == "couple"]
    meta = CarrierMeta(
        family_ids=[family.family_id for family in families],
        samples=samples,
        panel_genes=sorted(panel_genes),
        sources=sources,
        summary={
            "families": len(families),
            "samples": len(samples),
            "couples": len(couples),
            "person_carrier_rows": len(person_rows),
            "couple_carrier_rows": len(couple_rows),
            "homozygous_alt_persons": sum(
                1 for row in person_rows if row.status == "homozygous_alt"
            ),
            "child_homozygous_rows": sum(
                1 for row in couple_rows if row.child_status == "homozygous_alt"
            ),
            "sex_chrom_skipped": sex_chrom_skipped,
            "panel_skipped": panel_skipped,
        },
        contig_version=_contig_version(),
        notes=notes,
    )
    return CarrierReport(rows=rows, meta=meta)


def render_tsv(report: CarrierReport) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in report.rows:
        lines.append("\t".join(str(value) for value in [
            row.view,
            row.family_id,
            row.sample,
            row.father,
            row.mother,
            row.children,
            row.key.chrom,
            row.key.pos,
            row.key.ref,
            row.key.alt,
            row.gene or "",
            row.consequence or "unannotated",
            row.genotype or "",
            row.father_gt or "",
            row.mother_gt or "",
            row.child_gt,
            row.status,
            row.child_status,
        ]))
    return "\n".join(lines) + "\n"


def render_json(report: CarrierReport) -> str:
    payload = {
        "meta": report.meta.model_dump(mode="json"),
        "rows": [asdict(row) for row in report.rows],
    }
    return json.dumps(payload, indent=2) + "\n"


def write_report(report: CarrierReport, path: str | Path, *, as_json: bool = False) -> None:
    Path(path).write_text(
        render_json(report) if as_json else render_tsv(report), encoding="utf-8"
    )
