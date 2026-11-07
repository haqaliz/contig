"""Thin command layer for `contig family`."""

from __future__ import annotations

import typer

from contig.family.table import (
    RESEARCH_USE_NOTICE,
    build_family_table,
    render_json,
    render_tsv,
    write_table,
)


def run_family(vcf: str, ped: str, *, out: str | None = None, json_out: bool = False) -> None:
    typer.echo(RESEARCH_USE_NOTICE, err=True)
    table = build_family_table(vcf, ped)
    summary = table.meta.summary
    typer.echo(
        f"{summary.get('rows', 0)} row(s), {summary.get('evaluated', 0)} evaluated: "
        f"{summary.get('mendelian_inconsistent', 0)} Mendelian inconsistent, "
        f"{summary.get('de_novo_candidates', 0)} de novo candidate(s), "
        f"error rate {float(summary.get('mendelian_error_rate', 0.0)):.2%}",
        err=True,
    )
    if out:
        write_table(table, out, as_json=json_out)
        typer.echo(f"Wrote {out}")
        return
    typer.echo(render_json(table) if json_out else render_tsv(table), nl=False)
