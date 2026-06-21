"""Contig command-line interface.

The on-ramp to the Layer-2 engine: `run` drives a real Nextflow pipeline through
the self-heal loop, verifies it, and reports a verdict; `plan`/`show`/`list`
round out the surface. The backend (local, aws_batch, ...) is selected by
generating a nextflow.config from the ExecutionTarget (ARCHITECTURE §4.1).
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from importlib.metadata import version as _pkg_version

import typer
from pydantic import ValidationError

from contig.corpus import (
    default_corpus_path,
    evaluate_detector,
    load_corpus,
    promote_pending_case,
)
from contig.models import ExecutionTarget, RunSummary
from contig.nfconfig import ConfigGenerationError
from contig.planner import PlanningError
from contig.planner import plan as build_plan
from contig.reference import ReferenceError, resolve_reference
from contig.registry import assay_for_pipeline
from contig.report import render_run_report, render_run_report_html
from contig.runner import PipelineExecutionError, default_executor
from contig.samplesheet import fastq_paths, validate_samplesheet
from contig.self_heal import self_heal_run
from contig.workspace import RunNotFoundError, list_run_ids, load_run

app = typer.Typer(help="Contig: agentic bioinformatics analyst.")


@app.callback()
def main() -> None:
    """Contig: agentic bioinformatics analyst."""


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
    json_out: bool = typer.Option(False, "--json", help="Emit the plan as JSON (for the dashboard)."),
) -> None:
    """Propose an analysis plan (pipeline + params) from a goal + data, to approve before running."""
    reference = None
    if genome or fasta or gtf:
        try:
            reference = resolve_reference(genome=genome, fasta=fasta, gtf=gtf)
        except ReferenceError as exc:
            if json_out:
                typer.echo(_json.dumps({"error": str(exc)}))
                raise typer.Exit(code=1)
            typer.echo(f"Reference error: {exc}", err=True)
            raise typer.Exit(code=1)
    try:
        proposed = build_plan(goal, input, reference_params=reference)
    except PlanningError as exc:
        if json_out:
            typer.echo(_json.dumps({"error": str(exc)}))
            raise typer.Exit(code=1)
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    if json_out:
        typer.echo(proposed.model_dump_json())
        return

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
    backend: str = typer.Option("local", "--backend", help="Execution backend (local, aws_batch, ...)."),
    container_runtime: str = typer.Option("docker", "--container-runtime", help="Container runtime."),
    work_dir: str = typer.Option(None, "--work-dir", help="Nextflow work dir (e.g. s3://bucket/work for aws_batch)."),
    queue: str = typer.Option(None, "--queue", help="Batch/HPC job queue (aws_batch/slurm)."),
    region: str = typer.Option(None, "--region", help="Cloud region (aws_batch)."),
    input: str = typer.Option(None, "--input", help="Sample sheet CSV (real-data run)."),
    genome: str = typer.Option(None, "--genome", help="iGenomes reference key (e.g. GRCh38)."),
    fasta: str = typer.Option(None, "--fasta", help="Reference FASTA (with --gtf)."),
    gtf: str = typer.Option(None, "--gtf", help="Reference GTF annotation (with --fasta)."),
    outdir: str = typer.Option(None, "--outdir", help="Pipeline output directory (pipeline --outdir)."),
    max_memory: str = typer.Option(None, "--max-memory", help="Cap per-process memory (e.g. '6.GB'), needed to fit nf-core on a laptop."),
    max_cpus: int = typer.Option(None, "--max-cpus", help="Cap per-process CPUs."),
    max_attempts: int = typer.Option(3, "--max-attempts", help="Max self-heal attempts."),
) -> None:
    """Run a pipeline, self-heal recoverable failures, verify it, and report the verdict.

    With --input (a sample sheet) Contig runs on your real data: it pre-flight
    validates the sheet, requires a reference (--genome OR --fasta/--gtf), and
    checksums every input into the provenance. Without --input it runs nf-core's
    bundled test profile.
    """
    backend_options = {k: v for k, v in (("queue", queue), ("region", region)) if v}
    # Caps ride in the generated config as process.resourceLimits; nf-core
    # ignores the old --max_memory/--max_cpus params.
    resource_limits = {}
    if max_memory:
        resource_limits["memory"] = max_memory
    if max_cpus:
        resource_limits["cpus"] = str(max_cpus)
    try:
        target = ExecutionTarget(
            backend=backend,
            container_runtime=container_runtime,
            work_dir=work_dir or f"{runs_dir}/{run_id}/work",
            backend_options=backend_options,
            resource_limits=resource_limits,
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
        # Absolutize the sheet: Nextflow runs with cwd=run_dir, so a relative
        # --input would fail nf-core's "file does not exist" validation.
        params["input"] = str(Path(input).resolve())
        input_paths = [input, *fastq_paths(input)]
    selected_profiles = profiles or ("docker" if input else "test,docker")
    # nf-core always requires --outdir; default it under the run dir. Absolute so
    # Nextflow (which runs in the run dir) writes to the right place.
    outdir_path = Path(outdir) if outdir else Path(runs_dir) / run_id / "results"
    params["outdir"] = str(outdir_path.resolve())
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
    except ConfigGenerationError as exc:
        typer.echo(f"Cannot configure the '{backend}' backend: {exc}", err=True)
        raise typer.Exit(code=1)
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
    html: bool = typer.Option(False, "--html", help="Render a self-contained HTML report instead of text."),
    output: str = typer.Option(None, "--output", help="Write the report to this file instead of stdout."),
) -> None:
    """Show the verdict and provenance of a past run.

    With --html, render a single self-contained HTML file (the shareable report a
    PI or reviewer can trust: verdict, QC, repair chain, pinned provenance). With
    --output, write the report to that path instead of printing it to stdout.
    """
    try:
        record = load_run(runs_dir, run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    rendered = render_run_report_html(record) if html else render_run_report(record)
    if output:
        Path(output).write_text(rendered)
        typer.echo(f"Wrote report to {output}")
        return
    typer.echo(rendered)


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


@app.command(name="corpus-promote")
def corpus_promote(
    case_id: str = typer.Argument(..., help="The pending case id to promote."),
    pending: str = typer.Option("runs/pending_corpus.jsonl", "--pending", help="Pending corpus JSONL."),
    label: str = typer.Option(None, "--label", help="Correct the failure class (default: keep the provisional one)."),
    golden: str = typer.Option(None, "--golden", help="Golden corpus JSONL (default: the shipped seed)."),
) -> None:
    """Promote a reviewed pending failure case into the golden corpus (moat #2).

    The human confirms the detector's provisional label or corrects it with
    --label; the case then moves from pending into the golden corpus that the
    eval scores against. This is how the corpus compounds from real runs.
    """
    try:
        promoted = promote_pending_case(
            case_id,
            pending_path=pending,
            golden_path=golden,
            corrected_class=label,
        )
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(f"Could not promote {case_id}: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Promoted {promoted.case_id} ({promoted.expected_class}) into the golden corpus.")


@app.command(name="eval-detector")
def eval_detector(
    corpus: str = typer.Option(None, "--corpus", help="Failure-corpus JSONL (defaults to the shipped seed)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the report as JSON (for the dashboard)."),
) -> None:
    """Score the failure detector against a labeled corpus (moat #2).

    Replays diagnose_failure over every labeled failure and reports accuracy,
    per-class precision/recall, and each miss. A drop in accuracy means the
    detector regressed or a real case exposed a gap worth a new rule.
    """
    path = Path(corpus) if corpus else default_corpus_path()
    try:
        cases = load_corpus(path)
    except FileNotFoundError:
        typer.echo(f"Corpus not found: {path}", err=True)
        raise typer.Exit(code=1)
    report = evaluate_detector(cases)
    if json_out:
        typer.echo(report.model_dump_json())
        return
    typer.echo(f"Detector eval: {report.correct}/{report.total} correct (accuracy {report.accuracy:.1%})")
    for cls, s in sorted(report.per_class.items()):
        typer.echo(f"  {cls}: precision {s.precision:.2f}  recall {s.recall:.2f}  (support {s.support})")
    for m in report.mismatches:
        typer.echo(f"  MISS {m.case_id}: expected {m.expected}, predicted {m.predicted}")
