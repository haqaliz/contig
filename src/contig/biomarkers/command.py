"""Thin command layer for `contig biomarkers`."""

from __future__ import annotations

import typer

from contig.biomarkers.msi import parse_msi_output, run_msisensor
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
    msi_tumor_bam: str | None = None,
    msi_normal_bam: str | None = None,
    msi_sites: str | None = None,
    msi_bed: str | None = None,
    msi_output: str | None = None,
    msi_threshold: float = 10.0,
    msisensor_bin: str = "msisensor",
    out: str | None = None,
    json_out: bool = False,
) -> None:
    if not 0.0 <= msi_threshold <= 100.0:
        raise ValueError("msi_threshold must be between 0 and 100")
    msi_result = None
    if any((msi_tumor_bam, msi_normal_bam, msi_sites, msi_bed)):
        if not all((msi_tumor_bam, msi_normal_bam, msi_sites, msi_bed)):
            raise ValueError("MSI run requires --msi-tumor-bam, --msi-normal-bam, --msi-sites and --msi-bed")
        msi_result = run_msisensor(
            msi_tumor_bam, msi_normal_bam, msi_sites, msi_bed,
            output=msi_output or "msi.output",
            msisensor_bin=msisensor_bin,
            threshold=msi_threshold,
        )
    elif msi_output:
        msi_result = parse_msi_output(msi_output, threshold=msi_threshold)
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
        msi_result=msi_result,
    )
    tmb = next(entry for entry in report.entries if entry.name == "TMB computed")
    msi = next(entry for entry in report.entries if entry.name == "MSI")
    typer.echo(f"TMB: {tmb.value} mut/Mb ({tmb.status})", err=True)
    typer.echo(f"MSI: {msi.value or 'not attached'} ({msi.status})", err=True)
    typer.echo("LOH/CNV: not_verified in v1", err=True)

    if out:
        write_report(report, out, as_json=json_out)
        typer.echo(f"Wrote {out}")
        return
    typer.echo(render_json(report) if json_out else render_tsv(report), nl=False)
