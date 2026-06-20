"""Contig command-line interface (skeleton).

This is intentionally a thin surface: it constructs and echoes execution
*intent* (see ARCHITECTURE §4.1) but does not yet drive Nextflow. The real
run-and-verify engine lands once the toolchain is wired up.
"""

from __future__ import annotations

from importlib.metadata import version as _pkg_version

import typer
from pydantic import ValidationError

from contig.models import ExecutionTarget, RunSummary
from contig.planner import PlanningError
from contig.planner import plan as build_plan
from contig.reference import ReferenceError, resolve_reference
from contig.registry import assay_for_pipeline
from contig.report import render_run_report
from contig.runner import PipelineExecutionError, default_executor
from contig.samplesheet import fastq_paths, validate_samplesheet
from contig.self_heal import self_heal_run
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
    goal: str = typer.Option(..., "--goal", help="What you want to find out, in plain language."),
    input: str = typer.Option(..., "--input", help="Sample sheet CSV."),
    genome: str = typer.Option(None, "--genome", help="iGenomes reference key (e.g. GRCh38)."),
    fasta: str = typer.Option(None, "--fasta", help="Reference FASTA (with --gtf)."),
    gtf: str = typer.Option(None, "--gtf", help="Reference GTF annotation (with --fasta)."),
) -> None:
    """Propose an analysis plan (pipeline + params) from a goal + data, to approve before running."""
    reference = None
    if genome or fasta or gtf:
        try:
            reference = resolve_reference(genome=genome, fasta=fasta, gtf=gtf)
        except ReferenceError as exc:
            typer.echo(f"Reference error: {exc}", err=True)
            raise typer.Exit(code=1)
    try:
        proposed = build_plan(goal, input, reference_params=reference)
    except PlanningError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Plan: {proposed.pipeline} @ {proposed.revision}  (assay: {proposed.assay})")
    typer.echo(f"  {proposed.rationale}")
    params_str = ", ".join(f"{k}={v}" for k, v in proposed.params.items())
    typer.echo(f"  params: {params_str}")
    for warning in proposed.warnings:
        typer.echo(f"  ⚠ {warning}")


@app.command()
def run(
    run_id: str = typer.Option(..., "--run-id", help="Identifier for this run."),
    pipeline: str = typer.Option("nf-core/rnaseq", "--pipeline", help="Pipeline to run."),
    revision: str = typer.Option("3.26.0", "--revision", help="Pipeline revision."),
    profiles: str = typer.Option(None, "--profiles", help="Comma-separated Nextflow profiles."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    backend: str = typer.Option("local", "--backend", help="Execution backend."),
    container_runtime: str = typer.Option("docker", "--container-runtime", help="Container runtime."),
    input: str = typer.Option(None, "--input", help="Sample sheet CSV (real-data run)."),
    genome: str = typer.Option(None, "--genome", help="iGenomes reference key (e.g. GRCh38)."),
    fasta: str = typer.Option(None, "--fasta", help="Reference FASTA (with --gtf)."),
    gtf: str = typer.Option(None, "--gtf", help="Reference GTF annotation (with --fasta)."),
    outdir: str = typer.Option(None, "--outdir", help="Pipeline output directory (pipeline --outdir)."),
    max_memory: str = typer.Option(None, "--max-memory", help="Cap per-process memory (e.g. '6.GB') — needed to fit nf-core on a laptop."),
    max_cpus: int = typer.Option(None, "--max-cpus", help="Cap per-process CPUs."),
    max_attempts: int = typer.Option(3, "--max-attempts", help="Max self-heal attempts."),
) -> None:
    """Run a pipeline, self-heal recoverable failures, verify it, and report the verdict.

    With --input (a sample sheet) Contig runs on your real data: it pre-flight
    validates the sheet, requires a reference (--genome OR --fasta/--gtf), and
    checksums every input into the provenance. Without --input it runs nf-core's
    bundled test profile.
    """
    try:
        target = ExecutionTarget(
            backend=backend, container_runtime=container_runtime, work_dir=f"{runs_dir}/{run_id}/work"
        )
    except ValidationError as exc:
        typer.echo(f"Invalid execution target: {exc}", err=True)
        raise typer.Exit(code=1)

    params: dict[str, object] = {}
    input_paths: list = []
    if input:
        issues = validate_samplesheet(input)
        if issues:
            typer.echo("Sample sheet is invalid:", err=True)
            for issue in issues:
                typer.echo(f"  - {issue}", err=True)
            raise typer.Exit(code=1)
        try:
            params.update(resolve_reference(genome=genome, fasta=fasta, gtf=gtf))
        except ReferenceError as exc:
            typer.echo(f"Reference error: {exc}", err=True)
            raise typer.Exit(code=1)
        params["input"] = input
        input_paths = [input, *fastq_paths(input)]
    selected_profiles = profiles or ("docker" if input else "test,docker")
    if outdir:
        params["outdir"] = outdir
    if max_memory:
        params["max_memory"] = max_memory
    if max_cpus:
        params["max_cpus"] = max_cpus
    try:
        record = self_heal_run(
            pipeline=pipeline,
            revision=revision,
            profiles=selected_profiles.split(","),
            target=target,
            input_paths=input_paths,
            runs_dir=runs_dir,
            run_id=run_id,
            executor=default_executor,
            params=params or None,
            max_attempts=max_attempts,
            assay=assay_for_pipeline(pipeline) or "rnaseq",
        )
    except PipelineExecutionError as exc:
        typer.echo(f"Run failed before producing any output (Nextflow exit {exc.returncode}).", err=True)
        raise typer.Exit(code=1)

    typer.echo(render_run_report(record))
    if not RunSummary.from_events(record.events).succeeded:
        raise typer.Exit(code=1)


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
