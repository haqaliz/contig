"""Thin command layer for the local cohort lifecycle."""

from __future__ import annotations

import json as _json

import typer

from contig.cohort.build import build_cohort, merge_cohorts, write_cohort
from contig.cohort.query import (
    load_cohort,
    query_cohort,
    render_json,
    render_runs,
    render_tsv,
    write_query,
)

LOCAL_NOTICE = "Local cohort only: this command does not send data anywhere."


def _paths(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def run_cohort_build(
    name: str,
    *,
    variants: str,
    anonymize: bool = False,
    trace: bool = False,
    out: str = "cohort.json",
) -> None:
    typer.echo(LOCAL_NOTICE, err=True)
    cohort = build_cohort(name, _paths(variants), anonymize=anonymize, trace=trace)
    write_cohort(cohort, out)
    typer.echo(
        f"Wrote {out}: {len(cohort.variants)} variant(s), "
        f"{len(cohort.genes)} gene(s), {cohort.meta.total_runs} run(s)."
    )


def run_cohort_append(
    cohort_path: str,
    *,
    variants: str,
    out: str | None = None,
) -> None:
    typer.echo(LOCAL_NOTICE, err=True)
    existing = load_cohort(cohort_path)
    new = build_cohort(
        existing.meta.name,
        _paths(variants),
        anonymize=existing.meta.anonymized,
        trace=True,
    )
    merged = merge_cohorts(existing, new, name=existing.meta.name)
    destination = out or cohort_path
    write_cohort(merged, destination)
    typer.echo(
        f"Wrote {destination}: {len(merged.variants)} variant(s), "
        f"{len(merged.genes)} gene(s), {merged.meta.total_runs} run(s)."
    )


def run_cohort_merge(
    a_path: str,
    b_path: str,
    *,
    out: str,
    name: str | None = None,
) -> None:
    typer.echo(LOCAL_NOTICE, err=True)
    merged = merge_cohorts(load_cohort(a_path), load_cohort(b_path), name=name)
    write_cohort(merged, out)
    typer.echo(
        f"Wrote {out}: {len(merged.variants)} variant(s), "
        f"{len(merged.genes)} gene(s), {merged.meta.total_runs} run(s)."
    )


def run_cohort_list(cohort_path: str, *, json_out: bool = False) -> None:
    typer.echo(LOCAL_NOTICE, err=True)
    cohort = load_cohort(cohort_path)
    if json_out:
        typer.echo(
            _json.dumps([run.model_dump(mode="json") for run in cohort.meta.runs], indent=2)
        )
        return
    typer.echo(render_runs(cohort), nl=False)


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
