"""Thin command layer for `contig cohort-build` and `cohort-query`."""

from __future__ import annotations

import typer

from contig.cohort.build import build_cohort, write_cohort
from contig.cohort.query import load_cohort, query_cohort, render_json, render_tsv, write_query

LOCAL_NOTICE = "Local cohort only: this command does not send data anywhere."


def _paths(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def run_cohort_build(
    name: str,
    *,
    variants: str,
    anonymize: bool = False,
    out: str = "cohort.json",
) -> None:
    typer.echo(LOCAL_NOTICE, err=True)
    cohort = build_cohort(name, _paths(variants), anonymize=anonymize)
    write_cohort(cohort, out)
    typer.echo(
        f"Wrote {out}: {len(cohort.variants)} variant(s), "
        f"{len(cohort.genes)} gene(s), {cohort.meta.total_runs} run(s)."
    )


def run_cohort_query(
    cohort_path: str,
    *,
    gene: str | None = None,
    variant: str | None = None,
    min_runs: int | None = None,
    out: str | None = None,
    json_out: bool = False,
) -> None:
    typer.echo(LOCAL_NOTICE, err=True)
    cohort = load_cohort(cohort_path)
    rows = query_cohort(cohort, gene=gene, variant=variant, min_runs=min_runs)
    if not rows:
        typer.echo("No matching variants.")
        return
    if out:
        write_query(cohort, rows, out, as_json=json_out)
        typer.echo(f"Wrote {out}")
        return
    typer.echo(render_json(cohort, rows) if json_out else render_tsv(rows), nl=False)
