"""Contig command-line interface.

The on-ramp to the Layer-2 engine: `run` drives a real Nextflow pipeline through
the self-heal loop, verifies it, and reports a verdict; `plan`/`show`/`list`
round out the surface. The backend (local, aws_batch, ...) is selected by
generating a nextflow.config from the ExecutionTarget (ARCHITECTURE §4.1).
"""

from __future__ import annotations

import json as _json
import re as _re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from importlib.metadata import version as _pkg_version

import typer
from pydantic import ValidationError

from contig.benchmark import (
    benchmark_run,
    default_reference_path,
    load_reference_registry,
    metrics_from_run,
    record_reference,
    save_reference_registry,
)
from contig.corpus import (
    cluster_failures,
    coverage_report,
    default_corpus_path,
    evaluate_detector,
    load_corpus,
    promote_pending_case,
)
from contig.detect import get_detector
from contig.eval_history import (
    append_snapshot,
    default_history_path,
    load_history,
    snapshot_from_report,
)
from contig.bundle import compute_output_checksums
from contig.cost import cost_report
from contig.signing import generate_keypair, signing_available, verify_signature
from contig.estimate import estimate_run
from contig.methods import render_methods
from contig.provenance import to_rocrate
from contig.models import ExecutionTarget, LaunchManifest, RunRecord, RunSummary, sha256_file
from contig.nfconfig import ConfigGenerationError, preflight_aws_batch, preflight_slurm
from contig.planner import PlanningError
from contig.planner import plan as build_plan
from contig.progress import read_progress, render_progress
from contig.reference import ReferenceError, resolve_reference
from contig.registry import assay_for_pipeline
from contig.report import render_explain, render_run_report, render_run_report_html
from contig.runner import PipelineExecutionError, default_executor
from contig.samplesheet import fastq_paths, parse_samplesheet, validate_samplesheet
from contig.lifecycle import (
    CancelError,
    ResumeError,
    cancel_run,
    resumable_state,
    write_approval,
)
from contig.self_heal import self_heal_run
from contig.workspace import RunNotFoundError, list_run_ids, load_run

app = typer.Typer(help="Contig: agentic bioinformatics analyst.")


_SAFE_RUN_ID = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _is_safe_run_id(run_id: str) -> bool:
    """A run id must be filesystem-safe and never read as a CLI option (no leading dash)."""
    return bool(_SAFE_RUN_ID.match(run_id))


_SAFE_PIPELINE = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _is_safe_pipeline(pipeline: str) -> bool:
    """A pipeline name must be a plain nf-core-style ref and never read as an option.

    No leading dash (so it cannot be mistaken for a flag) and a conservative
    charset (letters, digits, dot, slash, underscore, dash) that covers
    "nf-core/rnaseq" without admitting shell-or-path surprises.
    """
    return bool(_SAFE_PIPELINE.match(pipeline))


def _is_safe_webhook(url: str) -> bool:
    """A notify webhook must be an http(s) URL and never read as a CLI option.

    No leading dash (so it cannot be mistaken for a flag) and an http/https scheme
    only (so a stray file:// or other scheme can never be POSTed to).
    """
    if not url or url.startswith("-"):
        return False
    return url.startswith("http://") or url.startswith("https://")


# A backend-option value is rendered verbatim into the generated nextflow.config
# (e.g. as an sbatch --account flag), so it must be a conservative token: no
# leading dash (could be read as a flag), no whitespace or shell metacharacters.
_SAFE_OPT_VALUE = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+=-]*$")
_SAFE_OPT_KEY = _re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _parse_backend_opts(opts: list[str] | None) -> dict[str, str]:
    """Parse repeated `--opt key=value` into a validated backend_options dict.

    Each entry must be `key=value` with a safe key and a safe value (the value
    reaches the generated config); a malformed entry raises ValueError with a
    message the CLI surfaces, never silently dropping a knob the user asked for.
    """
    parsed: dict[str, str] = {}
    for raw in opts or []:
        if "=" not in raw:
            raise ValueError(f"malformed --opt {raw!r}: expected key=value")
        key, value = raw.split("=", 1)
        if not _SAFE_OPT_KEY.match(key):
            raise ValueError(f"invalid --opt key {key!r}")
        if not _SAFE_OPT_VALUE.match(value):
            raise ValueError(f"invalid --opt value for {key!r}: {value!r}")
        parsed[key] = value
    return parsed


def _generate_run_id() -> str:
    """A fresh, sortable run id from the current UTC instant (PRD: run-<iso>)."""
    return "run-" + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")


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
    pipeline: str = typer.Option("nf-core/rnaseq", "--pipeline", help="Pipeline to run (Nextflow engine)."),
    revision: str = typer.Option("3.26.0", "--revision", help="Pipeline revision."),
    engine: str = typer.Option("nextflow", "--engine", help="Workflow engine (nextflow, snakemake)."),
    snakefile: str = typer.Option(None, "--snakefile", help="Snakefile path (required for --engine snakemake)."),
    profiles: str = typer.Option(None, "--profiles", help="Comma-separated Nextflow profiles."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    backend: str = typer.Option("local", "--backend", help="Execution backend (local, aws_batch, ...)."),
    container_runtime: str = typer.Option("docker", "--container-runtime", help="Container runtime."),
    work_dir: str = typer.Option(None, "--work-dir", help="Nextflow work dir (e.g. s3://bucket/work for aws_batch)."),
    queue: str = typer.Option(None, "--queue", help="Batch/HPC job queue, the SLURM partition for --backend slurm (aws_batch/slurm)."),
    region: str = typer.Option(None, "--region", help="Cloud region (aws_batch)."),
    opt: list[str] = typer.Option(None, "--opt", help="Extra backend option as key=value (e.g. account=lab, qos=high); repeatable."),
    input: str = typer.Option(None, "--input", help="Sample sheet CSV (real-data run)."),
    genome: str = typer.Option(None, "--genome", help="iGenomes reference key (e.g. GRCh38)."),
    fasta: str = typer.Option(None, "--fasta", help="Reference FASTA (with --gtf)."),
    gtf: str = typer.Option(None, "--gtf", help="Reference GTF annotation (with --fasta)."),
    outdir: str = typer.Option(None, "--outdir", help="Pipeline output directory (pipeline --outdir)."),
    max_memory: str = typer.Option(None, "--max-memory", help="Cap per-process memory (e.g. '6.GB'), needed to fit nf-core on a laptop."),
    max_cpus: int = typer.Option(None, "--max-cpus", help="Cap per-process CPUs."),
    max_attempts: int = typer.Option(3, "--max-attempts", help="Max self-heal attempts."),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Apply gated patches without waiting (non-interactive/CI)."),
    approval_timeout: float = typer.Option(1800, "--approval-timeout", help="Seconds to wait for a human approval before stopping."),
    notify: str = typer.Option(None, "--notify", help="Webhook URL to POST run lifecycle events to (http/https)."),
) -> None:
    """Run a pipeline, self-heal recoverable failures, verify it, and report the verdict.

    With --input (a sample sheet) Contig runs on your real data: it pre-flight
    validates the sheet, requires a reference (--genome OR --fasta/--gtf), and
    checksums every input into the provenance. Without --input it runs nf-core's
    bundled test profile.
    """
    _dispatch_run(
        run_id=run_id,
        pipeline=pipeline,
        revision=revision,
        profiles=profiles,
        runs_dir=runs_dir,
        backend=backend,
        container_runtime=container_runtime,
        work_dir=work_dir,
        queue=queue,
        region=region,
        opt=opt,
        engine=engine,
        snakefile=snakefile,
        input=input,
        genome=genome,
        fasta=fasta,
        gtf=gtf,
        outdir=outdir,
        max_memory=max_memory,
        max_cpus=max_cpus,
        max_attempts=max_attempts,
        auto_approve=auto_approve,
        approval_timeout=approval_timeout,
        notify=notify,
    )


def _dispatch_run(
    *,
    run_id: str,
    pipeline: str,
    revision: str,
    profiles: str | None,
    runs_dir: str,
    backend: str,
    container_runtime: str,
    work_dir: str | None,
    queue: str | None,
    region: str | None,
    input: str | None,
    genome: str | None,
    fasta: str | None,
    gtf: str | None,
    outdir: str | None,
    max_memory: str | None,
    max_cpus: int | None,
    max_attempts: int,
    opt: list[str] | None = None,
    engine: str = "nextflow",
    snakefile: str | None = None,
    resume: bool = False,
    auto_approve: bool = False,
    approval_timeout: float = 1800,
    notify: str | None = None,
) -> None:
    """Validate, write the reproduce sidecar, run through self-heal, and report.

    Shared by `run` (fresh invocation) and `rerun` (replayed from a manifest), so
    both paths apply the same validation and write the same launch.json.
    """
    if notify is not None and not _is_safe_webhook(notify):
        typer.echo(f"Invalid notify webhook URL: {notify!r} (must be an http/https URL)", err=True)
        raise typer.Exit(code=1)
    if engine not in ("nextflow", "snakemake"):
        typer.echo(f"Unsupported engine: {engine!r} (use nextflow or snakemake)", err=True)
        raise typer.Exit(code=1)
    # The snakemake engine needs a Snakefile, not an nf-core pipeline ref. Validate
    # it up front (present, safe, on disk) and make it the effective pipeline so the
    # runner builds a snakemake command from it.
    effective_pipeline = pipeline
    if engine == "snakemake":
        if not snakefile:
            typer.echo("The snakemake engine requires --snakefile.", err=True)
            raise typer.Exit(code=1)
        snakefile_path = Path(snakefile)
        if not snakefile_path.is_file():
            typer.echo(f"Snakefile not found: {snakefile}", err=True)
            raise typer.Exit(code=1)
        effective_pipeline = str(snakefile_path.resolve())
    try:
        extra_opts = _parse_backend_opts(opt)
    except ValueError as exc:
        typer.echo(f"Invalid --opt: {exc}", err=True)
        raise typer.Exit(code=1)
    # The SLURM executor reads the partition from process.queue, so --queue maps to
    # the 'partition' knob there; for cloud Batch it stays 'queue'. Extra --opt
    # knobs (account, qos, time) layer on, never overriding the mapped queue.
    if backend == "slurm":
        backend_options = {k: v for k, v in (("partition", queue), ("region", region)) if v}
    else:
        backend_options = {k: v for k, v in (("queue", queue), ("region", region)) if v}
    backend_options.update(extra_opts)
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
            engine=engine,
            backend_options=backend_options,
            resource_limits=resource_limits,
        )
    except ValidationError as exc:
        typer.echo(f"Invalid execution target: {exc}", err=True)
        raise typer.Exit(code=1)

    # AWS Batch refuses a misconfigured launch up front (PRD contract E): a missing
    # queue/region, a non-s3 work dir, or absent credentials would otherwise only
    # surface deep in Nextflow submission. Refuse before launching anything.
    if backend == "aws_batch":
        problems = preflight_aws_batch(target)
        if problems:
            typer.echo("Cannot launch on AWS Batch:", err=True)
            for problem in problems:
                typer.echo(f"  - {problem}", err=True)
            raise typer.Exit(code=1)

    # SLURM refuses a misconfigured launch up front (PRD contract A): a missing
    # partition/account, or sbatch/sinfo absent from PATH, would otherwise only
    # surface deep in Nextflow submission. Refuse before launching anything.
    if backend == "slurm":
        problems = preflight_slurm(target)
        if problems:
            typer.echo("Cannot launch on SLURM:", err=True)
            for problem in problems:
                typer.echo(f"  - {problem}", err=True)
            raise typer.Exit(code=1)

    params: dict[str, object] = {}
    input_paths: list = []
    # The --input/reference/--outdir plumbing is nf-core specific (a samplesheet, a
    # reference, the pipeline --outdir flag). The snakemake foundation pass drives
    # its inputs and outputs from the Snakefile itself, so it skips this block.
    if engine == "nextflow":
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
        # nf-core always requires --outdir; default it under the run dir. Absolute
        # so Nextflow (which runs in the run dir) writes to the right place.
        outdir_path = Path(outdir) if outdir else Path(runs_dir) / run_id / "results"
        params["outdir"] = str(outdir_path.resolve())
    selected_profiles = profiles or ("docker" if input else "test,docker")

    # Write the reproduce sidecar BEFORE the run, so it exists during the run and
    # on early failure. outdir/work_dir are deliberately not captured: reproduce
    # re-defaults them under the new run dir (PRD contract A).
    manifest = LaunchManifest(
        run_id=run_id,
        pipeline=pipeline,
        revision=revision,
        profiles=selected_profiles.split(","),
        backend=backend,
        container_runtime=container_runtime,
        input=params.get("input") if input else None,
        genome=genome,
        fasta=fasta,
        gtf=gtf,
        max_memory=max_memory,
        max_cpus=max_cpus,
        max_attempts=max_attempts,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    manifest_dir = Path(runs_dir) / run_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "launch.json").write_text(manifest.model_dump_json(indent=2))

    try:
        record = self_heal_run(
            pipeline=effective_pipeline,
            revision=revision,
            profiles=selected_profiles.split(","),
            target=target,
            input_paths=input_paths,
            runs_dir=runs_dir,
            run_id=run_id,
            executor=default_executor,
            params=params or None,
            max_attempts=max_attempts,
            assay=assay_for_pipeline(effective_pipeline) or "rnaseq",
            resume=resume,
            auto_approve=auto_approve,
            approval_timeout=approval_timeout,
            notify_webhook=notify,
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
def rerun(
    run_id: str = typer.Argument(..., help="The run to reproduce (reads its launch.json)."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    new_run_id: str = typer.Option(None, "--new-run-id", help="Identifier for the reproduced run (generated if omitted)."),
) -> None:
    """Reproduce a past run from its launch.json under a fresh run id.

    Reads the reproduce sidecar, re-validates the recorded input path (the
    manifest is never trusted blindly), and dispatches an identical run via the
    same path `run` uses, with a re-defaulted outdir/work_dir. Prints the new id.
    """
    manifest_path = Path(runs_dir) / run_id / "launch.json"
    if not manifest_path.exists():
        typer.echo(f"No launch manifest for run {run_id!r} in {runs_dir}.", err=True)
        raise typer.Exit(code=1)
    try:
        manifest = LaunchManifest.model_validate_json(manifest_path.read_text())
    except ValidationError as exc:
        typer.echo(f"Launch manifest for {run_id!r} is malformed: {exc}", err=True)
        raise typer.Exit(code=1)

    # Do not trust the manifest: a recorded input path may have moved or been
    # deleted since the original run. Refuse rather than launch against nothing.
    if manifest.input is not None and not Path(manifest.input).exists():
        typer.echo(f"Recorded input no longer exists: {manifest.input}", err=True)
        raise typer.Exit(code=1)

    target_run_id = new_run_id or _generate_run_id()
    if not _is_safe_run_id(target_run_id):
        typer.echo(f"Invalid run id: {target_run_id!r}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Reproducing {run_id} as {target_run_id}")
    _dispatch_run(
        run_id=target_run_id,
        pipeline=manifest.pipeline,
        revision=manifest.revision,
        profiles=",".join(manifest.profiles),
        runs_dir=runs_dir,
        backend=manifest.backend,
        container_runtime=manifest.container_runtime,
        work_dir=None,  # re-defaulted under the new run dir
        queue=None,
        region=None,
        input=manifest.input,
        genome=manifest.genome,
        fasta=manifest.fasta,
        gtf=manifest.gtf,
        outdir=None,  # re-defaulted under the new run dir
        max_memory=manifest.max_memory,
        max_cpus=manifest.max_cpus,
        max_attempts=manifest.max_attempts,
    )


@app.command()
def show(
    run_id: str = typer.Argument(..., help="The run to inspect."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    html: bool = typer.Option(False, "--html", help="Render a self-contained HTML report instead of text."),
    explain: bool = typer.Option(False, "--explain", help="Explain the verdict: the deciding checks and a one-line reason."),
    output: str = typer.Option(None, "--output", help="Write the report to this file instead of stdout."),
) -> None:
    """Show the verdict and provenance of a past run.

    With --explain, print just the verdict, the deciding QC checks (value vs
    expected range), and a one-line reason. With --html, render a single
    self-contained HTML file (the shareable report a PI or reviewer can trust:
    verdict, QC, repair chain, pinned provenance). With --output, write the report
    to that path instead of printing it to stdout.
    """
    try:
        record = load_run(runs_dir, run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    if explain:
        rendered = render_explain(record)
    elif html:
        rendered = render_run_report_html(record)
    else:
        rendered = render_run_report(record)
    if output:
        Path(output).write_text(rendered)
        typer.echo(f"Wrote report to {output}")
        return
    typer.echo(rendered)


def _results_dir_for(record: RunRecord, runs_dir: str, run_id: str) -> Path:
    """Where a run's outputs live for re-hashing: recorded outdir, else the default.

    The CLI absolutizes --outdir into record.parameters; verify prefers that path
    when it still exists, and otherwise falls back to runs_dir/<id>/results (a
    moved runs directory, or a test-profile run), matching how finalize hashed.
    """
    outdir = record.parameters.get("outdir")
    if outdir:
        path = Path(str(outdir))
        if path.is_dir():
            return path
    return Path(runs_dir) / run_id / "results"


def verify_outputs(record: RunRecord, results_dir: Path) -> dict:
    """Compare on-disk outputs against the recorded checksums (PRD contract B).

    Returns {ok, changed, missing}: `changed` are recorded files whose current
    hash differs, `missing` are recorded files no longer on disk (both sorted).
    Empty recorded checksums report ok with nothing to verify; new files that
    were never recorded are ignored (only the anchored outputs are guaranteed).
    """
    recorded = record.output_checksums
    if not recorded:
        return {"ok": True, "changed": [], "missing": []}
    current = compute_output_checksums(results_dir)
    changed: list[str] = []
    missing: list[str] = []
    for rel, digest in recorded.items():
        if rel not in current:
            missing.append(rel)
        elif current[rel] != digest:
            changed.append(rel)
    changed.sort()
    missing.sort()
    return {"ok": not (changed or missing), "changed": changed, "missing": missing}


@app.command()
def verify(
    run_id: str = typer.Argument(..., help="The run whose outputs to re-verify."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    json_out: bool = typer.Option(False, "--json", help="Emit the result as JSON (for the dashboard)."),
) -> None:
    """Re-hash a finished run's outputs and report any drift from the record.

    Reads the recorded output checksums and re-hashes the files on disk: an
    output that changed or disappeared is drift and exits non-zero. A run whose
    record captured no outputs reports "nothing to verify" (PRD contract B).
    """
    if not _is_safe_run_id(run_id):
        typer.echo(f"Invalid run id: {run_id!r}", err=True)
        raise typer.Exit(code=1)
    try:
        record = load_run(runs_dir, run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    # A signed run carries a signature.json sidecar; a mismatch is a verification
    # failure (the record was tampered with), so it fails the verify just like drift.
    sig = _signature_status(runs_dir, run_id, record)
    sig_bad = sig.get("signed") and sig.get("signature_ok") is False

    if not record.output_checksums:
        result = {"ok": True, "changed": [], "missing": [], **sig}
        if json_out:
            typer.echo(_json.dumps(result))
            if sig_bad:
                raise typer.Exit(code=1)
            return
        if sig_bad:
            typer.echo(f"Signature mismatch for run {run_id}: the record was modified.", err=True)
            raise typer.Exit(code=1)
        signed_note = " (signature verified)" if sig.get("signature_ok") else ""
        typer.echo(f"Nothing to verify for run {run_id}: no outputs were captured.{signed_note}")
        return

    result = verify_outputs(record, _results_dir_for(record, runs_dir, run_id))
    result.update(sig)
    if json_out:
        typer.echo(_json.dumps(result))
        if not result["ok"] or sig_bad:
            raise typer.Exit(code=1)
        return

    if result["ok"] and not sig_bad:
        signed_note = " Signature verified." if sig.get("signature_ok") else ""
        typer.echo(f"Outputs verified for run {run_id}: all recorded outputs match.{signed_note}")
        return
    if sig_bad:
        typer.echo(f"Signature mismatch for run {run_id}: the record was modified.", err=True)
    if not result["ok"]:
        typer.echo(f"Drift detected for run {run_id}:", err=True)
        for rel in result["changed"]:
            typer.echo(f"  changed: {rel}", err=True)
        for rel in result["missing"]:
            typer.echo(f"  missing: {rel}", err=True)
    raise typer.Exit(code=1)


def _signature_status(runs_dir: str, run_id: str, record: RunRecord) -> dict:
    """Read runs/<id>/signature.json and report whether the record is signed and intact.

    Returns {} when there is no signature sidecar. When signing is unavailable
    (the cryptography package is absent) the signature cannot be checked, so we
    report signed without a signature_ok claim rather than a false mismatch.
    """
    sidecar = Path(runs_dir) / run_id / "signature.json"
    if not sidecar.exists():
        return {}
    try:
        payload = _json.loads(sidecar.read_text())
    except (OSError, ValueError):
        return {"signed": True, "signature_ok": False}
    if not signing_available():
        return {"signed": True}
    ok = verify_signature(record, payload.get("signature", ""), payload.get("public_key", ""))
    return {"signed": True, "signature_ok": bool(ok)}


@app.command()
def keygen(
    out: str = typer.Option(None, "--out", help="Write the keypair to this file instead of stdout."),
) -> None:
    """Generate an Ed25519 signing keypair for tamper-evident run records.

    Set CONTIG_SIGNING_KEY to the private key before a run to sign its record; a
    signed run writes a signature.json that `contig verify` checks. Keep the
    private key secret; share only the public key.
    """
    if not signing_available():
        typer.echo("Signing is unavailable: install the cryptography package.", err=True)
        raise typer.Exit(code=1)
    private_key, public_key = generate_keypair()
    if out:
        Path(out).write_text(f"private_key={private_key}\npublic_key={public_key}\n")
        typer.echo(f"Wrote keypair to {out}. Set CONTIG_SIGNING_KEY to the private key to sign runs.")
        return
    typer.echo(f"private_key={private_key}")
    typer.echo(f"public_key={public_key}")
    typer.echo("Set CONTIG_SIGNING_KEY to the private key to sign runs; keep it secret.")


@app.command()
def cost(
    run_id: str = typer.Argument(..., help="The run to price."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    rate_cpu_hour: float = typer.Option(0.0, "--rate-cpu-hour", help="Price per cpu-hour of realtime (default 0: local is free)."),
    rate_mem_gb_hour: float = typer.Option(0.0, "--rate-mem-gb-hour", help="Price per GB-hour of peak memory (default 0: local is free)."),
    currency: str = typer.Option("USD", "--currency", help="Currency label for the report."),
    json_out: bool = typer.Option(False, "--json", help="Emit the cost report as JSON (for the dashboard)."),
) -> None:
    """Price a finished run's recorded resource usage against configurable rates.

    Reads the per-task actuals captured in the record (realtime, peak memory) and
    applies the cpu-hour and GB-hour rates. Rates default to zero, so a local run
    is free; a run that captured no resource usage reports a zero total.
    """
    if not _is_safe_run_id(run_id):
        typer.echo(f"Invalid run id: {run_id!r}", err=True)
        raise typer.Exit(code=1)
    try:
        record = load_run(runs_dir, run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    report = cost_report(
        record.resource_usage,
        rate_cpu_hour=rate_cpu_hour,
        rate_mem_gb_hour=rate_mem_gb_hour,
        currency=currency,
    )
    if json_out:
        typer.echo(_json.dumps(report))
        return

    typer.echo(
        f"Cost for run {run_id}: {report['total']:.4f} {currency} "
        f"(cpu {rate_cpu_hour}/h, mem {rate_mem_gb_hour}/GB-h)"
    )
    for row in report["by_task"]:
        typer.echo(
            f"  {row['name']}: {row['realtime_sec']:.0f}s, "
            f"{row['peak_rss_mb']:.0f} MB -> {row['cost']:.4f} {currency}"
        )


@app.command()
def export(
    run_id: str = typer.Argument(..., help="The run to export."),
    rocrate: bool = typer.Option(False, "--rocrate", help="Export an RO-Crate ro-crate-metadata.json (JSON-LD)."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    output: str = typer.Option(None, "--output", help="Write the export to this file instead of stdout."),
) -> None:
    """Export a finished run's provenance as a portable RO-Crate.

    With --rocrate, build the ro-crate-metadata.json JSON-LD subset (the run as a
    Dataset, the pipeline as a SoftwareApplication, inputs and outputs as File
    entities with checksums, the verdict and QC as properties). The export is
    deterministic and offline (PRD contract C).
    """
    if not _is_safe_run_id(run_id):
        typer.echo(f"Invalid run id: {run_id!r}", err=True)
        raise typer.Exit(code=1)
    if not rocrate:
        typer.echo("Nothing to export: pass --rocrate for the RO-Crate JSON.", err=True)
        raise typer.Exit(code=1)
    try:
        record = load_run(runs_dir, run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    rendered = _json.dumps(to_rocrate(record), indent=2)
    if output:
        Path(output).write_text(rendered)
        typer.echo(f"Wrote RO-Crate to {output}")
        return
    typer.echo(rendered)


@app.command()
def methods(
    run_id: str = typer.Argument(..., help="The run to describe."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    output: str = typer.Option(None, "--output", help="Write the paragraph to this file instead of stdout."),
) -> None:
    """Render a citation-ready methods paragraph for a finished run.

    Templates the pipeline plus revision, the assay, key params, container
    digests, and the verdict plus QC summary into a deterministic paragraph a
    researcher can paste into a manuscript. Offline and rule based (PRD contract C).
    """
    if not _is_safe_run_id(run_id):
        typer.echo(f"Invalid run id: {run_id!r}", err=True)
        raise typer.Exit(code=1)
    try:
        record = load_run(runs_dir, run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    paragraph = render_methods(record)
    if output:
        Path(output).write_text(paragraph)
        typer.echo(f"Wrote methods to {output}")
        return
    typer.echo(paragraph)


@app.command()
def estimate(
    pipeline: str = typer.Option(..., "--pipeline", help="Pipeline to estimate (e.g. nf-core/rnaseq)."),
    input: str = typer.Option(..., "--input", help="Sample sheet CSV (its row count is the sample count)."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory of prior run bundles to learn from."),
    rate_cpu_hour: float = typer.Option(0.0, "--rate-cpu-hour", help="Price per cpu-hour of realtime (default 0: local is free)."),
    rate_mem_gb_hour: float = typer.Option(0.0, "--rate-mem-gb-hour", help="Price per GB-hour of peak memory (default 0: local is free)."),
    currency: str = typer.Option("USD", "--currency", help="Currency label for the estimate."),
    json_out: bool = typer.Option(False, "--json", help="Emit the estimate as JSON (for the dashboard)."),
) -> None:
    """Estimate a run's runtime, peak memory, and cost before launching it.

    Data-driven from prior FINISHED runs of the same pipeline (their recorded
    resource_usage scaled per sample to the sheet's sample count); falls back to a
    transparent per-sample heuristic when there is no history. The sample count
    comes from the sheet's rows (PRD contract B).
    """
    if not _is_safe_pipeline(pipeline):
        typer.echo(f"Invalid pipeline name: {pipeline!r}", err=True)
        raise typer.Exit(code=1)
    if not Path(input).exists():
        typer.echo(f"Sample sheet not found: {input}", err=True)
        raise typer.Exit(code=1)
    try:
        n_samples = len(parse_samplesheet(input))
    except (ValueError, OSError) as exc:
        typer.echo(f"Cannot read sample sheet: {exc}", err=True)
        raise typer.Exit(code=1)
    if n_samples <= 0:
        typer.echo("Sample sheet has no samples to estimate.", err=True)
        raise typer.Exit(code=1)

    report = estimate_run(
        pipeline,
        n_samples,
        runs_dir,
        rate_cpu_hour=rate_cpu_hour,
        rate_mem_gb_hour=rate_mem_gb_hour,
        currency=currency,
    )
    if json_out:
        typer.echo(report.model_dump_json())
        return

    typer.echo(
        f"Estimate for {pipeline} on {n_samples} sample(s) [{report.basis}]: "
        f"{report.est_runtime_sec:.0f}s, peak {report.est_peak_mem_mb:.0f} MB, "
        f"{report.est_total_cpu_hours:.2f} cpu-hours -> {report.est_cost:.4f} {currency}"
    )
    typer.echo(f"  {report.note}")


@app.command()
def status(
    run_id: str = typer.Argument(..., help="The run to inspect."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    json_out: bool = typer.Option(False, "--json", help="Emit the snapshot as JSON (for the dashboard)."),
) -> None:
    """Show a one-shot live snapshot of a run: state, elapsed, task progress, last repair."""
    snapshot = read_progress(runs_dir, run_id)
    if snapshot.state == "missing":
        if json_out:
            typer.echo(snapshot.model_dump_json())
            raise typer.Exit(code=1)
        typer.echo(f"No run {run_id!r} found in {runs_dir} (state: missing).", err=True)
        raise typer.Exit(code=1)
    if json_out:
        typer.echo(snapshot.model_dump_json())
        return
    typer.echo(render_progress(snapshot))


@app.command()
def watch(
    run_id: str = typer.Argument(..., help="The run to follow."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    interval: float = typer.Option(2.0, "--interval", help="Seconds between redraws while running."),
) -> None:
    """Redraw a run's live snapshot until it is no longer running.

    Polls the same progress files `status` reads; stops as soon as the state
    leaves "running" (finished, error, interrupted, or missing).
    """
    while True:
        snapshot = read_progress(runs_dir, run_id)
        typer.echo(render_progress(snapshot))
        if snapshot.state != "running":
            if snapshot.state == "missing":
                raise typer.Exit(code=1)
            return
        time.sleep(interval)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="The cancelled or interrupted run to resume."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
) -> None:
    """Resume a cancelled or interrupted run: re-run the same id with Nextflow -resume.

    Reads the run's launch.json, rebuilds the exact invocation, and re-runs the
    SAME run id in the SAME run dir with -resume so cached completed tasks are
    reused. Refuses a finished, errored, or still-running run.
    """
    if not _is_safe_run_id(run_id):
        typer.echo(f"Invalid run id: {run_id!r}", err=True)
        raise typer.Exit(code=1)
    try:
        resumable_state(runs_dir, run_id)
    except ResumeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    manifest_path = Path(runs_dir) / run_id / "launch.json"
    if not manifest_path.exists():
        typer.echo(f"No launch manifest for run {run_id!r} in {runs_dir}.", err=True)
        raise typer.Exit(code=1)
    try:
        manifest = LaunchManifest.model_validate_json(manifest_path.read_text())
    except ValidationError as exc:
        typer.echo(f"Launch manifest for {run_id!r} is malformed: {exc}", err=True)
        raise typer.Exit(code=1)

    # Do not trust the manifest: a recorded input path may have moved since the
    # original run. Refuse rather than resume against nothing.
    if manifest.input is not None and not Path(manifest.input).exists():
        typer.echo(f"Recorded input no longer exists: {manifest.input}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Resuming {run_id}")
    _dispatch_run(
        run_id=run_id,  # the SAME run id, in the SAME run dir
        pipeline=manifest.pipeline,
        revision=manifest.revision,
        profiles=",".join(manifest.profiles),
        runs_dir=runs_dir,
        backend=manifest.backend,
        container_runtime=manifest.container_runtime,
        work_dir=None,  # re-defaulted to the same runs/<id>/work the run cached into
        queue=None,
        region=None,
        input=manifest.input,
        genome=manifest.genome,
        fasta=manifest.fasta,
        gtf=manifest.gtf,
        outdir=None,
        max_memory=manifest.max_memory,
        max_cpus=manifest.max_cpus,
        max_attempts=manifest.max_attempts,
        resume=True,
    )


@app.command()
def cancel(
    run_id: str = typer.Argument(..., help="The run to cancel."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
) -> None:
    """Cancel an active run: reap its process group and write a cancelled verdict.

    Only a `running` or `awaiting_approval` run can be cancelled; anything already
    finished, errored, or cancelled has nothing to stop and exits non-zero.
    """
    if not _is_safe_run_id(run_id):
        typer.echo(f"Invalid run id: {run_id!r}", err=True)
        raise typer.Exit(code=1)
    try:
        cancel_run(runs_dir, run_id)
    except CancelError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Cancelled run {run_id}.")


@app.command()
def approve(
    run_id: str = typer.Argument(..., help="The awaiting-approval run to decide on."),
    reject: bool = typer.Option(False, "--reject", help="Reject the gated patch instead of approving it."),
    choose: int = typer.Option(None, "--choose", help="On a choice gate, the index of the ranked fix to apply."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
) -> None:
    """Approve (or with --reject, reject) the gated patch a paused run is waiting on.

    Writes runs/<id>/approval.json; the self-heal loop's poll picks it up and
    either applies the patch and retries, or stops. On a choice gate (an ambiguous
    decision with ranked options), pass --choose N to apply option N (PRD contract D).
    """
    if not _is_safe_run_id(run_id):
        typer.echo(f"Invalid run id: {run_id!r}", err=True)
        raise typer.Exit(code=1)
    write_approval(runs_dir, run_id, approve=not reject, choice=choose)
    if reject:
        typer.echo(f"Rejected the pending patch for run {run_id}.")
        return
    if choose is not None:
        typer.echo(f"Approved option {choose} for run {run_id}.")
        return
    typer.echo(f"Approved the pending patch for run {run_id}.")


def _benchmark_set(run_id: str, runs_dir: str, registry_path: str | None) -> None:
    """Record a run's numeric QC metrics as the reference for its (pipeline, assay).

    Loads the run, derives its assay from the registry, and writes (or replaces)
    the reference entry for that (pipeline, assay) in the registry, deduped so
    there is exactly one baseline per pair (PRD contract A).
    """
    if not _is_safe_run_id(run_id):
        typer.echo(f"Invalid run id: {run_id!r}", err=True)
        raise typer.Exit(code=1)
    try:
        record = load_run(runs_dir, run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    path = Path(registry_path) if registry_path else default_reference_path()
    registry = load_reference_registry(path)
    assay = assay_for_pipeline(record.pipeline) or "rnaseq"
    metrics = metrics_from_run(record)
    registry = record_reference(
        registry,
        pipeline=record.pipeline,
        assay=assay,
        reference_run_id=run_id,
        metrics=metrics,
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    save_reference_registry(registry, path)
    typer.echo(
        f"Recorded run {run_id} as the reference for {record.pipeline} / {assay} "
        f"({len(metrics)} metric(s))."
    )


@app.command()
def benchmark(
    target: str = typer.Argument(..., help="A run id to compare, or 'set' to record a reference (then a run id)."),
    run_id: str = typer.Argument(None, help="With 'set', the run whose QC metrics become the reference."),
    tolerance: float = typer.Option(0.1, "--tolerance", help="Relative tolerance for a metric to count as matching."),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    registry_path: str = typer.Option(None, "--registry", help="Reference registry JSONL (defaults to the shipped one)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the comparison as JSON (for the dashboard)."),
) -> None:
    """Compare a run against its designated reference, or record one with 'set' (PRD contract A).

    `contig benchmark <run-id>` loads the run, finds the reference for its
    (pipeline, assay), and compares each shared numeric QC check within the
    relative tolerance plus a structural shape check (the same check names
    present). No reference for that pipeline/assay reports "no reference" and
    exits zero, not an error. `contig benchmark set <run-id>` records that run's
    numeric QC metrics as the reference for its (pipeline, assay).
    """
    # `benchmark set <run-id>` records a reference; the first positional is the
    # literal keyword and the second is the run id.
    if target == "set":
        if run_id is None:
            typer.echo("Provide a run id: 'benchmark set <run-id>'.", err=True)
            raise typer.Exit(code=1)
        _benchmark_set(run_id, runs_dir, registry_path)
        return

    compare_run_id = target
    if not _is_safe_run_id(compare_run_id):
        typer.echo(f"Invalid run id: {compare_run_id!r}", err=True)
        raise typer.Exit(code=1)
    try:
        record = load_run(runs_dir, compare_run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    path = Path(registry_path) if registry_path else default_reference_path()
    registry = load_reference_registry(path)
    assay = assay_for_pipeline(record.pipeline) or "rnaseq"
    result = benchmark_run(record, registry, assay=assay, tolerance=tolerance)

    if json_out:
        typer.echo(_json.dumps(result))
        return
    if result["status"] == "no_reference":
        typer.echo(result["message"])
        return
    typer.echo(
        f"Benchmark for run {compare_run_id}: {result['status']} vs {result['reference_run_id']} "
        f"({result['matched']} matched, {result['drifted']} drifted, tolerance {tolerance})"
    )
    for check in result["checks"]:
        flag = "ok" if check["within_tolerance"] else "DRIFT"
        typer.echo(
            f"  {check['name']}: run {check['run_value']} vs ref {check['reference_value']} "
            f"(delta {check['delta']:.3f}) {flag}"
        )


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
    history_file: str = typer.Option(None, "--history-file", help="Eval history JSONL (defaults to the shipped one)."),
) -> None:
    """Promote a reviewed pending failure case into the golden corpus (moat #2).

    The human confirms the detector's provisional label or corrects it with
    --label; the case then moves from pending into the golden corpus that the
    eval scores against. This is how the corpus compounds from real runs. After a
    successful promote, a fresh eval of the golden corpus is appended to the
    history so the trend reflects the grown corpus (PRD contract D).
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

    # Auto-snapshot: eval the now-grown golden corpus and append it to the trend.
    golden_path = Path(golden) if golden else default_corpus_path()
    history_path = Path(history_file) if history_file else default_history_path()
    cases = load_corpus(golden_path)
    append_snapshot(
        snapshot_from_report(
            evaluate_detector(cases),
            timestamp=datetime.now(timezone.utc).isoformat(),
            corpus_size=len(cases),
            corpus_sha=sha256_file(golden_path),
            contig_version=_pkg_version("contig"),
        ),
        history_path,
    )
    typer.echo(f"Promoted {promoted.case_id} ({promoted.expected_class}) into the golden corpus.")


@app.command(name="eval-detector")
def eval_detector(
    corpus: str = typer.Option(None, "--corpus", help="Failure-corpus JSONL (defaults to the shipped seed)."),
    detector: str = typer.Option("rules", "--detector", help="Which detector to score (rules, rules-strict)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the report as JSON (for the dashboard)."),
    snapshot: bool = typer.Option(False, "--snapshot", help="Append this eval to the committed history (trend)."),
    show_history: bool = typer.Option(False, "--history", help="Print the recorded accuracy-over-time trend instead of re-evaluating."),
    history_file: str = typer.Option(None, "--history-file", help="Eval history JSONL (defaults to the shipped one)."),
) -> None:
    """Score the failure detector against a labeled corpus (moat #2).

    Replays diagnose_failure over every labeled failure and reports accuracy,
    per-class precision/recall, and each miss. A drop in accuracy means the
    detector regressed or a real case exposed a gap worth a new rule. With
    --snapshot the result is appended to the committed history; with --history the
    recorded trend is printed instead (PRD contract D).
    """
    history_path = Path(history_file) if history_file else default_history_path()

    if show_history:
        history = load_history(history_path)
        if json_out:
            typer.echo("[" + ",".join(s.model_dump_json() for s in history) + "]")
            return
        if not history:
            typer.echo(f"No eval history recorded yet in {history_path}.")
            return
        typer.echo("Detector accuracy over time:")
        for snap in history:
            typer.echo(f"  {snap.timestamp}  accuracy {snap.accuracy:.1%}  (corpus {snap.corpus_size})")
        return

    try:
        detector_fn = get_detector(detector)
    except KeyError as exc:
        # KeyError stringifies with quotes; the message already lists the
        # available detectors, so surface it as the user-facing error.
        typer.echo(str(exc).strip("\"'"), err=True)
        raise typer.Exit(code=1)

    path = Path(corpus) if corpus else default_corpus_path()
    try:
        cases = load_corpus(path)
    except FileNotFoundError:
        typer.echo(f"Corpus not found: {path}", err=True)
        raise typer.Exit(code=1)
    report = evaluate_detector(cases, detector_fn)

    if snapshot:
        append_snapshot(
            snapshot_from_report(
                report,
                timestamp=datetime.now(timezone.utc).isoformat(),
                corpus_size=len(cases),
                corpus_sha=sha256_file(path),
                contig_version=_pkg_version("contig"),
                detector=detector,
            ),
            history_path,
        )

    if json_out:
        typer.echo(report.model_dump_json())
        return
    typer.echo(f"Detector eval: {report.correct}/{report.total} correct (accuracy {report.accuracy:.1%})")
    for cls, s in sorted(report.per_class.items()):
        typer.echo(f"  {cls}: precision {s.precision:.2f}  recall {s.recall:.2f}  (support {s.support})")
    for m in report.mismatches:
        typer.echo(f"  MISS {m.case_id}: expected {m.expected}, predicted {m.predicted}")


@app.command()
def clusters(
    corpus: str = typer.Option(None, "--corpus", help="Failure-corpus JSONL (defaults to the shipped seed)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the clusters as JSON (for the dashboard)."),
) -> None:
    """Group corpus failures into recurring systemic modes, worst-first (PRD contract B).

    Clusters cases by failure class plus a normalized log signature (paths,
    numbers, hashes, and timestamps stripped), so the same systemic failure mode
    is one row no matter how many runs produced it. Printed largest-cluster
    first: the recurring modes worth a new rule or a fix at the top.
    """
    path = Path(corpus) if corpus else default_corpus_path()
    try:
        cases = load_corpus(path)
    except FileNotFoundError:
        typer.echo(f"Corpus not found: {path}", err=True)
        raise typer.Exit(code=1)
    grouped = cluster_failures(cases)

    if json_out:
        typer.echo(_json.dumps(grouped))
        return
    if not grouped:
        typer.echo(f"No failure cases in {path}.")
        return
    typer.echo(f"Failure clusters ({len(grouped)} mode(s), worst-first):")
    for cluster in grouped:
        typer.echo(
            f"  {cluster['failure_class']}  x{cluster['count']}  "
            f"(signature {cluster['signature']})"
        )


@app.command()
def coverage(
    corpus: str = typer.Option(None, "--corpus", help="Failure-corpus JSONL (defaults to the shipped seed)."),
    history_file: str = typer.Option(None, "--history-file", help="Eval history JSONL (defaults to the shipped one)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the coverage report as JSON (for the dashboard)."),
) -> None:
    """Report per-class corpus support, thin-coverage gaps, and the confirmed trend (PRD contract C).

    Counts cases per failure class, flags classes with fewer than three cases as
    thin (the gaps to fill next), breaks the corpus down by provenance kind, and
    draws a confirmed-over-time series from the eval history.
    """
    path = Path(corpus) if corpus else default_corpus_path()
    try:
        cases = load_corpus(path)
    except FileNotFoundError:
        typer.echo(f"Corpus not found: {path}", err=True)
        raise typer.Exit(code=1)
    history_path = Path(history_file) if history_file else default_history_path()
    history = load_history(history_path)
    report = coverage_report(cases, history=history)

    if json_out:
        typer.echo(_json.dumps(report))
        return
    typer.echo(f"Corpus coverage: {report['total']} case(s) across {len(report['per_class'])} class(es).")
    for cls, count in sorted(report["per_class"].items()):
        thin = "  THIN" if cls in report["thin"] else ""
        typer.echo(f"  {cls}: {count}{thin}")
    sources = ", ".join(f"{k}={v}" for k, v in sorted(report["by_source"].items()))
    typer.echo(f"  by source: {sources}")
