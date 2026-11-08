"""Query a local cohort index."""

from __future__ import annotations

import json
from pathlib import Path

from contig.cohort.models import Cohort, CohortVariant
from contig.variants.vcf import normalize_chrom

COLUMNS = [
    "chrom", "pos", "ref", "alt", "genes", "consequences",
    "clinvar_significance", "seen_runs", "frequency", "run_labels",
]


def load_cohort(path: str | Path) -> Cohort:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"cohort not found: {path}")
    return Cohort.model_validate_json(path.read_text(encoding="utf-8"))


def query_cohort(
    cohort: Cohort,
    *,
    gene: str | None = None,
    variant: str | None = None,
    min_runs: int | None = None,
) -> list[CohortVariant]:
    rows = cohort.variants
    if gene:
        gene_upper = gene.upper()
        rows = [row for row in rows if any(g.upper() == gene_upper for g in row.genes)]
    if variant:
        parts = variant.split("-", 3)
        if len(parts) != 4:
            raise ValueError("variant must look like CHROM-POS-REF-ALT")
        try:
            key = (normalize_chrom(parts[0]), int(parts[1]), parts[2], parts[3])
        except ValueError as exc:
            raise ValueError("variant position must be an integer") from exc
        rows = [
            row for row in rows
            if (row.chrom, row.pos, row.ref, row.alt) == key
        ]
    if min_runs is not None:
        if min_runs < 0:
            raise ValueError("min_runs must be non-negative")
        rows = [row for row in rows if row.seen_runs >= min_runs]
    return rows


def render_tsv(rows: list[CohortVariant]) -> str:
    lines = ["\t".join(COLUMNS)]
    for row in rows:
        lines.append("\t".join(str(value) for value in [
            row.chrom, row.pos, row.ref, row.alt,
            ",".join(row.genes), ",".join(row.consequences),
            ",".join(row.clinvar_significance), row.seen_runs, f"{row.frequency:.4f}",
            ",".join(row.run_labels),
        ]))
    return "\n".join(lines) + "\n"


def render_runs(cohort: Cohort) -> str:
    lines = ["label\tsha256\tpath"]
    for run in cohort.meta.runs:
        lines.append(f"{run.label}\t{run.sha256}\t{run.path or '-'}")
    return "\n".join(lines) + "\n"


def render_json(cohort: Cohort, rows: list[CohortVariant]) -> str:
    payload = {
        "meta": cohort.meta.model_dump(mode="json"),
        "variants": [row.model_dump(mode="json") for row in rows],
    }
    return json.dumps(payload, indent=2) + "\n"


def write_query(cohort: Cohort, rows: list[CohortVariant], path: str | Path, *, as_json: bool = False) -> None:
    Path(path).write_text(render_json(cohort, rows) if as_json else render_tsv(rows), encoding="utf-8")
