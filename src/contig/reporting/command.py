"""Thin command layer for `contig report` and `contig report-check`."""

from __future__ import annotations

from pathlib import Path

import typer

from contig.reporting.build import (
    build_report,
    check_report,
    check_report_outputs,
    check_report_signature,
    check_report_sources,
    write_report,
)
from contig.reporting.models import ReportSpec

RESEARCH_USE_NOTICE = (
    "Research use only: this report is not a clinical report, diagnosis, or "
    "treatment recommendation."
)


def run_report(
    run_id: str,
    *,
    runs_dir: str = "runs",
    variants: str | None = None,
    readiness: str | None = None,
    spec_path: str | None = None,
    template: str | None = None,
    out: str | None = None,
    meta_path: str | None = None,
) -> None:
    spec = ReportSpec()
    if spec_path:
        spec = ReportSpec.model_validate_json(Path(spec_path).read_text(encoding="utf-8"))
    if template:
        spec = ReportSpec.model_validate({**spec.model_dump(), "template": template})

    typer.echo(RESEARCH_USE_NOTICE, err=True)
    html, meta = build_report(
        runs_dir,
        run_id,
        spec,
        variants_path=variants,
        readiness_path=readiness,
    )
    for warning in meta.warnings:
        typer.echo(f"Compatibility warning: {warning}", err=True)
    out_path = out or str(Path(runs_dir) / run_id / "report.html")
    meta_path = meta_path or str(Path(runs_dir) / run_id / "report.json")
    sig_path = write_report(html, meta, out_path, meta_path)
    typer.echo(f"Wrote {out_path}")
    typer.echo(f"Wrote {meta_path}")
    if sig_path is not None:
        typer.echo(f"Wrote {sig_path} (Ed25519 signature)")


def run_report_check(
    meta_path: str,
    *,
    require_signature: bool = False,
    base_dir: str | None = None,
    check_outputs: bool = False,
    check_sources: bool = False,
) -> None:
    results = check_report(meta_path, base_dir=base_dir)
    if check_outputs:
        results.extend(check_report_outputs(meta_path, base_dir=base_dir))
    if check_sources:
        results.extend(check_report_sources(meta_path, base_dir=base_dir))
    stale = [item for item in results if item["status"] in {"stale", "missing"}]
    unverified = [item for item in results if item["status"] == "unverified"]
    for item in results:
        typer.echo(f"{item['status']:>8}  {item['kind']}: {item['path']}")
        if item["status"] in {"stale", "missing"}:
            typer.echo(f"          expected {item['expected']} actual {item['actual']}")
        elif item.get("note"):
            typer.echo(f"          {item['note']}")
    signature = check_report_signature(meta_path)
    signature_bad = False
    if not signature["signed"]:
        typer.echo("signature: unsigned (no report signature sidecar)")
    elif signature["ok"]:
        typer.echo(f"signature: verified (ed25519, public key {signature['public_key']})")
    else:
        signature_bad = True
        typer.echo(f"signature: INVALID ({signature['detail']})", err=True)
    if stale:
        typer.echo(f"{len(stale)} item(s) stale or missing.", err=True)
        raise typer.Exit(code=1)
    if signature_bad:
        raise typer.Exit(code=1)
    if require_signature and not signature["signed"]:
        typer.echo("A signed report manifest is required.", err=True)
        raise typer.Exit(code=1)
    if unverified:
        typer.echo(f"{len(unverified)} item(s) could not be verified.", err=True)
    typer.echo("All report inputs are current.")
