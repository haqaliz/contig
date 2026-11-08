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
from contig.reporting.bundle import bundle_report
from contig.reporting.models import ReportSpec
from contig.reporting.project import load_project, report_paths, resolve
from contig.workspace import RunNotFoundError

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


def _check_one(
    meta_path: str | Path,
    *,
    base_dir: str | Path | None = None,
    check_outputs: bool = False,
    check_sources: bool = False,
    require_signature: bool = False,
) -> tuple[bool, list[str]]:
    results = check_report(meta_path, base_dir=base_dir)
    if check_outputs:
        results.extend(check_report_outputs(meta_path, base_dir=base_dir))
    if check_sources:
        results.extend(check_report_sources(meta_path, base_dir=base_dir))
    problems = [
        f"{item['status']}: {item['kind']}: {item['path']}"
        for item in results
        if item["status"] in {"stale", "missing"}
    ]
    signature = check_report_signature(meta_path)
    if signature["signed"] and not signature["ok"]:
        problems.append(f"signature INVALID: {signature['detail']}")
    if require_signature and not signature["signed"]:
        problems.append("a signed report manifest is required")
    return not problems, problems


def run_report_batch(
    project_path: str,
    *,
    check: bool = False,
    check_outputs: bool = False,
    check_sources: bool = False,
    require_signature: bool = False,
) -> None:
    manifest, base = load_project(project_path)
    typer.echo(f"Project {manifest.name}: {len(manifest.reports)} report(s).")
    failures = 0
    for entry in manifest.reports:
        out_dir, out_path, meta_path = report_paths(manifest, entry, base)
        try:
            spec = ReportSpec()
            spec_path = resolve(base, entry.spec)
            if spec_path:
                spec = ReportSpec.model_validate_json(
                    spec_path.read_text(encoding="utf-8")
                )
            if entry.template:
                spec = ReportSpec.model_validate(
                    {**spec.model_dump(), "template": entry.template}
                )
            variants_path = resolve(base, entry.variants)
            readiness_path = resolve(base, entry.readiness)
            html, meta = build_report(
                resolve(base, entry.runs_dir) or base / "runs",
                entry.run_id,
                spec,
                variants_path=variants_path,
                readiness_path=readiness_path,
            )
            write_report(html, meta, out_path, meta_path)
            if entry.bundle:
                bundle_report(meta_path, out_dir / entry.id)
            typer.echo(f"  built {entry.id}: {out_path}")
            if check:
                ok, problems = _check_one(
                    meta_path,
                    base_dir=base,
                    check_outputs=check_outputs,
                    check_sources=check_sources,
                    require_signature=require_signature,
                )
                if not ok:
                    failures += 1
                    typer.echo(f"  NOT CURRENT {entry.id}:", err=True)
                    for problem in problems:
                        typer.echo(f"    {problem}", err=True)
        except (FileNotFoundError, ValueError, OSError, RunNotFoundError) as exc:
            failures += 1
            typer.echo(f"  FAILED {entry.id}: {exc}", err=True)
    if failures:
        typer.echo(f"{failures} report(s) failed or are not current.", err=True)
        raise typer.Exit(code=1)
    typer.echo("All project reports are current.")


def run_report_check_batch(
    project_path: str,
    *,
    check_outputs: bool = False,
    check_sources: bool = False,
    require_signature: bool = False,
) -> None:
    manifest, base = load_project(project_path)
    typer.echo(f"Project {manifest.name}: {len(manifest.reports)} report(s).")
    failures = 0
    for entry in manifest.reports:
        _, _, meta_path = report_paths(manifest, entry, base)
        if not meta_path.is_file():
            failures += 1
            typer.echo(f"  MISSING {entry.id}: {meta_path}", err=True)
            continue
        ok, problems = _check_one(
            meta_path,
            base_dir=base,
            check_outputs=check_outputs,
            check_sources=check_sources,
            require_signature=require_signature,
        )
        if ok:
            typer.echo(f"  current {entry.id}: {meta_path}")
        else:
            failures += 1
            typer.echo(f"  NOT CURRENT {entry.id}:", err=True)
            for problem in problems:
                typer.echo(f"    {problem}", err=True)
    if failures:
        typer.echo(f"{failures} report(s) failed or are not current.", err=True)
        raise typer.Exit(code=1)
    typer.echo("All project reports are current.")
