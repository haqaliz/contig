"""Thin command layer for `contig readiness`."""

from __future__ import annotations

import typer

from contig.readiness.models import ReadinessThresholds
from contig.readiness.table import (
    RESEARCH_USE_NOTICE,
    build_readiness,
    render_json,
    render_tsv,
    summarize,
    write_table,
)


def _genes(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


def run_readiness(
    depth: str,
    *,
    bed: str | None = None,
    gtf: str | None = None,
    genes: str | None = None,
    caveats: str | None = None,
    depth_threshold: int = 20,
    ready_fraction: float = 0.90,
    caution_fraction: float = 0.50,
    out: str | None = None,
    json_out: bool = False,
) -> None:
    thresholds = ReadinessThresholds(
        depth_threshold=depth_threshold,
        ready_fraction=ready_fraction,
        caution_fraction=caution_fraction,
    )

    typer.echo(RESEARCH_USE_NOTICE, err=True)
    table = build_readiness(
        depth,
        bed=bed,
        gtf=gtf,
        genes=_genes(genes),
        caveats=caveats,
        thresholds=thresholds,
    )
    counts = summarize(table.rows)
    typer.echo(
        f"{len(table.rows)} target(s): {counts['ready']} ready, "
        f"{counts['caution']} caution, {counts['not-interpretable']} not-interpretable",
        err=True,
    )

    if out:
        write_table(table, out, as_json=json_out)
        typer.echo(f"Wrote {out}")
        return

    typer.echo(render_json(table) if json_out else render_tsv(table), nl=False)
