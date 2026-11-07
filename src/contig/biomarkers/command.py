"""Thin command layer for `contig biomarkers`."""

from __future__ import annotations

import typer

from contig.biomarkers.report import (
    RESEARCH_USE_NOTICE,
    build_report,
    render_json,
    render_tsv,
    write_report,
)


def run_biomarkers(
    vcf: str,
    callable_bed: str,
    *,
    reported_tmb: float | None = None,
    tmb_tolerance: float = 0.20,
    reported_msi: str | None = None,
    reported_loh: str | None = None,
    reported_cnv: str | None = None,
    coding_only: bool = False,
    out: str | None = None,
    json_out: bool = False,
) -> None:
    typer.echo(RESEARCH_USE_NOTICE, err=True)
    report = build_report(
        vcf,
        callable_bed,
        reported_tmb=reported_tmb,
        tmb_tolerance=tmb_tolerance,
        reported_msi=reported_msi,
        reported_loh=reported_loh,
        reported_cnv=reported_cnv,
        coding_only=coding_only,
    )
    tmb = next(entry for entry in report.entries if entry.name == "TMB computed")
    typer.echo(f"TMB: {tmb.value} mut/Mb ({tmb.status})", err=True)
    typer.echo("MSI/LOH/CNV: not_verified in v1", err=True)

    if out:
        write_report(report, out, as_json=json_out)
        typer.echo(f"Wrote {out}")
        return
    typer.echo(render_json(report) if json_out else render_tsv(report), nl=False)
