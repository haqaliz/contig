"""Thin command layer for `contig biomarkers`."""

from __future__ import annotations

import typer

from contig.biomarkers.cnv import compare_files
from contig.biomarkers.loh import compare_loh_files
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
    cnv_segments: str | None = None,
    cnv_truth: str | None = None,
    cnv_value_column: str | None = None,
    cnv_tolerance: float = 0.2,
    cnv_min_concordance: float = 0.90,
    loh_segments: str | None = None,
    loh_truth: str | None = None,
    loh_min_agreement: float = 0.90,
    out: str | None = None,
    json_out: bool = False,
) -> None:
    if not 0.0 <= msi_threshold <= 100.0:
        raise ValueError("msi_threshold must be between 0 and 100")
    if bool(cnv_segments) != bool(cnv_truth):
        raise ValueError("CNV comparison requires both --cnv-segments and --cnv-truth")
    if bool(loh_segments) != bool(loh_truth):
        raise ValueError("LOH comparison requires both --loh-segments and --loh-truth")
    cnv_result = None
    if cnv_segments and cnv_truth:
        cnv_result = compare_files(
            cnv_segments, cnv_truth,
            value_column=cnv_value_column,
            tolerance=cnv_tolerance,
            min_concordance=cnv_min_concordance,
        )
    loh_result = None
    if loh_segments and loh_truth:
        loh_result = compare_loh_files(
            loh_segments, loh_truth, min_agreement=loh_min_agreement
        )
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
        loh_result=loh_result,
        cnv_result=cnv_result,
    )
    tmb = next(entry for entry in report.entries if entry.name == "TMB computed")
    msi = next(entry for entry in report.entries if entry.name == "MSI")
    loh = next(entry for entry in report.entries if entry.name == "LOH")
    cnv = next(entry for entry in report.entries if entry.name == "CNV")
    typer.echo(f"TMB: {tmb.value} mut/Mb ({tmb.status})", err=True)
    typer.echo(f"MSI: {msi.value or 'not attached'} ({msi.status})", err=True)
    typer.echo(f"LOH: {loh.value or 'not attached'} ({loh.status})", err=True)
    typer.echo(f"CNV: {cnv.value or 'not attached'} ({cnv.status})", err=True)

    if out:
        write_report(report, out, as_json=json_out)
        typer.echo(f"Wrote {out}")
        return
    typer.echo(render_json(report) if json_out else render_tsv(report), nl=False)
