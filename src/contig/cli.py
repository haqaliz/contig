"""Contig command-line interface (skeleton).

This is intentionally a thin surface: it constructs and echoes execution
*intent* (see ARCHITECTURE §4.1) but does not yet drive Nextflow. The real
run-and-verify engine lands once the toolchain is wired up.
"""

from __future__ import annotations

from importlib.metadata import version as _pkg_version

import typer
from pydantic import ValidationError

from contig.models import ExecutionTarget
from contig.report import render_run_report
from contig.runner import PipelineExecutionError, default_executor, run_pipeline
from contig.workspace import RunNotFoundError, list_run_ids, load_run

app = typer.Typer(help="Contig — agentic bioinformatics analyst.")


@app.callback()
def main() -> None:
    """Contig — agentic bioinformatics analyst."""


@app.command()
def version() -> None:
    """Print the installed Contig version."""
    typer.echo(_pkg_version("contig"))


@app.command()
def plan(
    work_dir: str = typer.Option(..., "--work-dir", help="Run working directory."),
    backend: str = typer.Option("local", "--backend", help="Execution backend."),
    container_runtime: str = typer.Option(
        "docker", "--container-runtime", help="Container runtime."
    ),
    pipeline: str = typer.Option(
        "nf-core/rnaseq", "--pipeline", help="Pipeline to run."
    ),
) -> None:
    """Construct and echo the execution plan (no run is performed)."""
    try:
        target = ExecutionTarget(
            backend=backend,
            container_runtime=container_runtime,
            work_dir=work_dir,
        )
    except ValidationError as exc:
        typer.echo(f"Invalid execution target: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(
        f"Plan: run {pipeline} on {target.backend} "
        f"using {target.container_runtime} (work_dir={target.work_dir})"
    )


@app.command()
def run(
    run_id: str = typer.Option(..., "--run-id", help="Identifier for this run."),
    pipeline: str = typer.Option("nf-core/rnaseq", "--pipeline", help="Pipeline to run."),
    revision: str = typer.Option("3.26.0", "--revision", help="Pipeline revision."),
    profiles: str = typer.Option("test,docker", "--profiles", help="Comma-separated Nextflow profiles."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    backend: str = typer.Option("local", "--backend", help="Execution backend."),
    container_runtime: str = typer.Option("docker", "--container-runtime", help="Container runtime."),
    outdir: str = typer.Option(None, "--outdir", help="Pipeline output directory (pipeline --outdir)."),
    resume: bool = typer.Option(False, "--resume", help="Resume cached tasks from a prior run."),
) -> None:
    """Run a pipeline, capture it, verify it, and report the verdict."""
    try:
        target = ExecutionTarget(
            backend=backend, container_runtime=container_runtime, work_dir=f"{runs_dir}/{run_id}/work"
        )
    except ValidationError as exc:
        typer.echo(f"Invalid execution target: {exc}", err=True)
        raise typer.Exit(code=1)

    params = {"outdir": outdir} if outdir else None
    try:
        record = run_pipeline(
            pipeline=pipeline,
            revision=revision,
            profiles=profiles.split(","),
            target=target,
            input_paths=[],
            runs_dir=runs_dir,
            run_id=run_id,
            executor=default_executor,
            params=params,
            resume=resume,
        )
    except PipelineExecutionError as exc:
        typer.echo(f"Run failed (Nextflow exit {exc.returncode}).", err=True)
        if exc.record is not None:
            typer.echo("A provenance bundle was still captured:")
            typer.echo(render_run_report(exc.record))
        raise typer.Exit(code=1)

    typer.echo(render_run_report(record))


@app.command()
def show(
    run_id: str = typer.Argument(..., help="The run to inspect."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
) -> None:
    """Show the verdict and provenance of a past run."""
    try:
        record = load_run(runs_dir, run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(render_run_report(record))


@app.command(name="list")
def list_runs(
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
) -> None:
    """List the bundled runs in a runs directory."""
    ids = list_run_ids(runs_dir)
    if not ids:
        typer.echo(f"No runs found in {runs_dir}.")
        return
    for run_id in ids:
        typer.echo(run_id)
