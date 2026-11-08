"""Thin command layer for `contig report` and `contig report-check`."""

from __future__ import annotations

from pathlib import Path

import typer

from contig.reporting.build import build_report, check_report, write_report
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
    out_path = out or str(Path(runs_dir) / run_id / "report.html")
    meta_path = meta_path or str(Path(runs_dir) / run_id / "report.json")
    write_report(html, meta, out_path, meta_path)
    typer.echo(f"Wrote {out_path}")
    typer.echo(f"Wrote {meta_path}")


def run_report_check(meta_path: str) -> None:
    results = check_report(meta_path)
    stale = [item for item in results if item["status"] != "current"]
    for item in results:
        typer.echo(f"{item['status']:>8}  {item['kind']}: {item['path']}")
        if item["status"] != "current":
            typer.echo(f"          expected {item['expected']} actual {item['actual']}")
    if stale:
        typer.echo(f"{len(stale)} input(s) stale or missing.", err=True)
        raise typer.Exit(code=1)
    typer.echo("All report inputs are current.")
