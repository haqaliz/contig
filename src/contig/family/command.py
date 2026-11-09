"""Thin command layer for `contig family`."""

from __future__ import annotations

import typer

from contig.family.carriers import (
    RESEARCH_USE_NOTICE as CARRIER_NOTICE,
    build_carrier_report,
    render_json as render_carrier_json,
    render_tsv as render_carrier_tsv,
    write_report as write_carrier_report,
)
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
        f"{summary.get('families', 1)} family(ies), "
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


def run_carriers(
    vcf: str,
    ped: str,
    *,
    genes: str | None = None,
    panel: str | None = None,
    out: str | None = None,
    json_out: bool = False,
) -> None:
    gene_set = {
        part.strip() for part in (genes or "").split(",") if part.strip()
    }
    typer.echo(CARRIER_NOTICE, err=True)
    report = build_carrier_report(
        vcf, ped, genes=gene_set, panel_path=panel
    )
    summary = report.meta.summary
    typer.echo(
        f"{summary['families']} family(ies), {summary['couples']} couple(s), "
        f"{summary['person_carrier_rows']} person carrier row(s), "
        f"{summary['couple_carrier_rows']} shared-carrier row(s)",
        err=True,
    )
    if out:
        write_carrier_report(report, out, as_json=json_out)
        typer.echo(f"Wrote {out}")
        return
    typer.echo(
        render_carrier_json(report) if json_out else render_carrier_tsv(report),
        nl=False,
    )
