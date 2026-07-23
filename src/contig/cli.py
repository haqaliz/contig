"""Contig command-line interface.

The on-ramp to the Layer-2 engine: `run` drives a real Nextflow pipeline through
the self-heal loop, verifies it, and reports a verdict; `plan`/`show`/`list`
round out the surface. The backend (local, aws_batch, ...) is selected by
generating a nextflow.config from the ExecutionTarget (ARCHITECTURE §4.1).
"""

from __future__ import annotations

import dataclasses as _dataclasses
import hashlib
import json as _json
import re as _re
import shlex
import shutil
import tempfile
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
from contig.fetch import classify_repo_argument, fetch_repo
from contig.eval_history import (
    append_snapshot,
    default_history_path,
    load_history,
    snapshot_from_report,
)
from contig.holdout import (
    compare_to_baseline,
    default_baseline_path,
    default_holdout_history_path,
    default_holdout_path,
    load_baseline,
    save_baseline,
)
from contig.heal import (
    compare_heal_to_baseline,
    default_heal_baseline_path,
    default_heal_history_path,
    default_heal_scenarios_path,
    evaluate_heal,
    load_heal_baseline,
    load_heal_scenarios,
    save_heal_baseline,
    snapshot_from_heal_report,
)
from contig.snapshot_history import append_jsonl, load_jsonl
from contig.bundle import compute_output_checksums, write_reproduce_bundle
from contig.cost import cost_report
from contig.signing import generate_keypair, signing_available, verify_signature
from contig.estimate import estimate_run
from contig.methods import render_methods
from contig.provenance import to_rocrate
from contig.models import (
    EvalSnapshot,
    ExecutionTarget,
    HealSnapshot,
    LaunchManifest,
    RunRecord,
    RunSummary,
    sha256_file,
)
from contig.nfconfig import ConfigGenerationError, preflight_aws_batch, preflight_slurm
from contig.planner import PlanningError
from contig.planner import plan as build_plan
from contig.progress import read_progress, render_progress
from contig.reference import ReferenceError, resolve_reference
from contig.reference_check import check_reference_consistency, fasta_contigs, gtf_contigs
from contig.reference_harmonize import harmonize_gtf, plan_harmonization
from contig.registry import UnknownAssayError, assay_for_pipeline, select_pipeline
from contig.report import (
    render_explain,
    render_reproduction,
    render_run_report,
    render_run_report_html,
)
from contig.verification.concordance import evaluate_concordance
from contig.verification.count_concordance import (
    _COUNT_MATRIX_GLOB,
    evaluate_count_concordance,
)
from contig.verification.sc_count_concordance import (
    _SC_MATRIX_GLOB,
    evaluate_sc_count_concordance,
)
from contig.verification.second_caller import (
    SecondCallerError,
    run_bcftools_caller,
)
from contig.verification.count_quantifier import (
    SecondQuantifierError,
    run_kallisto_quantifier,
)
from contig.verification.sc_count_quantifier import (
    SecondScQuantifierError,
    run_starsolo_quantifier,
)
from contig.verification.reproduce import ClaimsError, load_claims, run_reproduction
from contig.verification.structural import manifest_for
from contig.runner import (
    PipelineExecutionError,
    default_command_executor,
    default_executor,
    default_fetcher,
    default_index_builder,
    default_installer,
)
from contig.samplesheet import (
    fastq_paths,
    parse_samplesheet,
    validate_samplesheet,
    validate_somatic_samplesheet,
)
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
    assay: str = typer.Option(None, "--assay", help="Assay key override; needed when two assays share a pipeline (e.g. somatic vs germline sarek). Defaults to the pipeline's registered assay."),
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
    allow_reference_mismatch: bool = typer.Option(False, "--allow-reference-mismatch", help="Proceed even if the FASTA and GTF use disjoint contig naming (almost always a mistake)."),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Apply gated patches without waiting (non-interactive/CI)."),
    approval_timeout: float = typer.Option(1800, "--approval-timeout", help="Seconds to wait for a human approval before stopping."),
    notify: str = typer.Option(None, "--notify", help="Webhook URL to POST run lifecycle events to (http/https)."),
    fail_on_verdict: bool = typer.Option(False, "--fail-on-verdict", help="Exit non-zero if the run's verdict is FAIL (opt-in; WARN/UNVERIFIED do not). Default off."),
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
        assay=assay,
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
        allow_reference_mismatch=allow_reference_mismatch,
        auto_approve=auto_approve,
        approval_timeout=approval_timeout,
        notify=notify,
        fail_on_verdict=fail_on_verdict,
    )


def _inject_default_params(params: dict[str, object], assay: str) -> None:
    """Merge the resolved assay's registry `default_params` into `params` in place,
    WITHOUT overriding any user-supplied key (setdefault semantics).

    This is the declarative seam that makes a somatic sarek run genuinely invoke
    the somatic callers: the somatic entry carries `{"tools": "strelka,mutect2"}`,
    which becomes `--tools strelka,mutect2` in the Nextflow argv. All other assays
    default-empty, so germline/RNA-seq command assembly is unchanged.

    R5 (honest scope): this only assembles the command correctly — it does NOT wire
    a panel-of-normals / germline resource that Mutect2 typically needs; that
    reference wiring is deferred (PRD Out-of-Scope / OQ2).

    Defensive: an assay with no registry entry (a non-registry fallback like a bare
    "rnaseq" default) is a no-op rather than a crash.
    """
    try:
        defaults = select_pipeline(assay).default_params
    except UnknownAssayError:
        return
    for key, value in defaults.items():
        params.setdefault(key, value)


def _dispatch_run(
    *,
    run_id: str,
    pipeline: str,
    assay: str | None = None,
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
    allow_reference_mismatch: bool = False,
    opt: list[str] | None = None,
    engine: str = "nextflow",
    snakefile: str | None = None,
    resume: bool = False,
    auto_approve: bool = False,
    approval_timeout: float = 1800,
    notify: str | None = None,
    fail_on_verdict: bool = False,
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

    # Resolve the assay ONCE, BEFORE the sample-sheet gate so it can select the
    # right validator: an explicit --assay wins (needed when two assays share a
    # pipeline, e.g. somatic vs germline sarek); otherwise fall back to the legacy
    # pipeline-derived assay, then "rnaseq". Persisted below on both the manifest
    # (so rerun re-applies it) and the RunRecord (so methods/benchmark read it
    # directly instead of re-deriving from the ambiguous pipeline string).
    resolved_assay = assay or assay_for_pipeline(effective_pipeline) or "rnaseq"

    params: dict[str, object] = {}
    input_paths: list = []
    harmonized_direction: str | None = None
    # The --input/reference/--outdir plumbing is nf-core specific (a samplesheet, a
    # reference, the pipeline --outdir flag). The snakemake foundation pass drives
    # its inputs and outputs from the Snakefile itself, so it skips this block.
    if engine == "nextflow":
        if input:
            # Somatic runs validate the sarek tumor/normal paired shape; every
            # other assay (incl. germline sarek) keeps the generic validator
            # unchanged (M3, somatic-gated).
            if resolved_assay == "somatic_variant_calling":
                issues = validate_somatic_samplesheet(input)
            else:
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
            # Pre-flight the explicit reference: a FASTA/GTF pair whose contig
            # naming is disjoint (e.g. FASTA 'chr1' vs GTF '1') silently yields an
            # empty count matrix. If a safe chr-prefix transform can resolve the
            # mismatch, harmonize the GTF and proceed. Only refuse (or bypass with
            # --allow-reference-mismatch) for a genuinely non-harmonizable pair.
            # iGenomes (--genome) has no fasta/gtf here, so it is skipped.
            if "fasta" in params and "gtf" in params:
                problems = check_reference_consistency(params["fasta"], params["gtf"])
                # Drive harmonization off the PLAN, not off the disjoint-only
                # detector: `problems` is empty whenever FASTA/GTF share ANY
                # contig at all, even when only a residual case (e.g. mito
                # chrM/MT) still needs resolving and the autosomes already
                # overlap. `plan_harmonization` is the one that knows whether
                # applying a rename map would strictly improve the overlap, so
                # it — not `problems` — is what gates the harmonize attempt.
                hplan = plan_harmonization(params["fasta"], params["gtf"])
                if hplan is not None:
                    # Safe chr-prefix / alias-table harmonization: rewrite the
                    # GTF and proceed. Harmonize-first even when
                    # --allow-reference-mismatch is set — harmonizing is
                    # strictly safer than running against a mismatch.
                    harmonized_path = (
                        Path(runs_dir) / run_id / "harmonized" / Path(params["gtf"]).name
                    )
                    harmonized_path.parent.mkdir(parents=True, exist_ok=True)
                    harmonize_gtf(params["gtf"], hplan.rename_map, harmonized_path)
                    # POST-CONDITION GUARD: confirm the rewrite actually improved
                    # the FASTA/GTF name overlap. `check_reference_consistency`
                    # alone cannot detect this — it only flags a fully DISJOINT
                    # pair, so it would pass (no problems) even if harmonization
                    # silently no-op'd on a pair that already shared some
                    # contigs (the residual-mito case). Compare overlap counts
                    # directly instead: never proceed believing harmonization
                    # worked when it actually didn't ("never manufacture a
                    # silent wrong result").
                    orig_overlap = len(
                        fasta_contigs(params["fasta"]) & gtf_contigs(params["gtf"])
                    )
                    post_overlap = len(
                        fasta_contigs(params["fasta"])
                        & gtf_contigs(str(harmonized_path.resolve()))
                    )
                    if post_overlap > orig_overlap:
                        # Overlap improved — proceed with the harmonized file.
                        typer.echo(
                            f"⚙ Reference harmonized: GTF seqnames {hplan.direction} "
                            f"to match the FASTA. Proceeding.",
                            err=True,
                        )
                        harmonized_direction = hplan.direction
                        params["gtf"] = str(harmonized_path.resolve())
                        # DO NOT Exit — proceed with the harmonized file.
                    else:
                        # Guard triggered: harmonization did NOT resolve the mismatch.
                        # Discard the scratch file and fall through to the refuse/allow
                        # path with the ORIGINAL problems and GTF.
                        typer.echo(
                            "⚠ Harmonization was attempted but did not resolve the "
                            "reference mismatch; reverting to the original GTF.",
                            err=True,
                        )
                        hplan = None  # signal fall-through to the refuse/allow path
                if hplan is None and problems:
                    # Genuine wrong-assembly (non-harmonizable, or guard triggered):
                    # keep existing behavior.
                    prefix = (
                        "⚠ Reference mismatch (proceeding, --allow-reference-mismatch):"
                        if allow_reference_mismatch
                        else "Reference mismatch:"
                    )
                    typer.echo(prefix, err=True)
                    for problem in problems:
                        typer.echo(f"  - {problem}", err=True)
                    if not allow_reference_mismatch:
                        typer.echo(
                            "  Pass --allow-reference-mismatch to override if this is intentional.",
                            err=True,
                        )
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

    # Merge the resolved assay's declarative default_params into `params` BEFORE the
    # manifest is written and the run starts, so e.g. somatic sarek picks up
    # `--tools strelka,mutect2`. User-supplied params are never overridden. Reproduce
    # is faithful because the assay persists in launch.json and this re-injects on
    # rerun (rather than storing the derived params). See _inject_default_params (R5).
    _inject_default_params(params, resolved_assay)

    # Write the reproduce sidecar BEFORE the run, so it exists during the run and
    # on early failure. outdir/work_dir are deliberately not captured: reproduce
    # re-defaults them under the new run dir (PRD contract A).
    manifest = LaunchManifest(
        run_id=run_id,
        pipeline=pipeline,
        assay=resolved_assay,
        revision=revision,
        profiles=selected_profiles.split(","),
        backend=backend,
        container_runtime=container_runtime,
        input=params.get("input") if input else None,
        genome=genome,
        fasta=fasta,
        gtf=gtf,  # ORIGINAL path — reproduce re-enters dispatch and re-derives harmonization
        max_memory=max_memory,
        max_cpus=max_cpus,
        max_attempts=max_attempts,
        allow_reference_mismatch=allow_reference_mismatch,
        harmonized_reference=bool(harmonized_direction),
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
            index_builder=default_index_builder,
            params=params or None,
            max_attempts=max_attempts,
            assay=resolved_assay,
            resume=resume,
            auto_approve=auto_approve,
            approval_timeout=approval_timeout,
            notify_webhook=notify,
            harmonized_reference_direction=harmonized_direction,
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
    if fail_on_verdict and record.verdict == "fail":
        typer.echo(f"Run {run_id} verdict is FAIL (--fail-on-verdict).", err=True)
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
        assay=manifest.assay,  # replay the persisted assay (None for legacy manifests -> falls back)
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
        allow_reference_mismatch=manifest.allow_reference_mismatch,
    )


@app.command()
def reproduce(
    repo: str = typer.Argument(
        ..., help="Path to a local repo, or an https:// git URL (with --allow-fetch)"
    ),
    run: str = typer.Option(..., "--run", help="Command to run inside the repo"),
    claims: str = typer.Option(..., "--claims", help="Path to the claims JSON file"),
    results: str = typer.Option(
        "results.json",
        "--results",
        help=(
            "Repo-relative JSON the script writes: {claim_id: value}; the "
            "fallback for claims without a 'from'/'path' locator"
        ),
    ),
    runs_dir: str = typer.Option("runs", "--runs-dir", help="Directory holding run bundles."),
    tolerance: float = typer.Option(
        0.1,
        "--tolerance",
        help="Default relative tolerance when a claim omits one",
    ),
    fail_on_diverged: bool = typer.Option(
        False, "--fail-on-diverged", help="Exit non-zero if any claim diverged"
    ),
    allow_install: bool = typer.Option(
        False,
        "--allow-install/--no-allow-install",
        help=(
            "Install a missing Python dependency and retry the run once when the "
            "first run fails on ModuleNotFoundError. Reaches the network and mutates "
            "the environment; off by default (a missing module stays UNVERIFIED)."
        ),
    ),
    allow_fetch: bool = typer.Option(
        False,
        "--allow-fetch/--no-allow-fetch",
        help=(
            "Clone an https:// git URL passed as the repo argument into the run "
            "bundle and run against that checkout. Reaches the network and writes "
            "a checkout under the runs directory; off by default (a URL is "
            "refused without it)."
        ),
    ),
) -> None:
    """Reproduce a published paper/repo's claims against a fresh run.

    Loads a claims file (one published numeric claim per id), runs `--run`
    inside `repo`, classifies each claim against the observed value, and writes
    a signed, re-runnable bundle under `runs_dir`. Nothing is written when the
    repo is missing or the claims file is malformed -- validation happens
    before any run or record.

    `repo` is either a local path or an https:// git URL. A URL requires
    --allow-fetch (off by default): with it, the repo is cloned into
    `<runs_dir>/<reproduce_id>/source` and the run happens against that
    checkout, with the URL and the resolved HEAD commit recorded on the
    bundle as `source_url`/`source_commit` -- the pin that says which
    revision produced this verdict. The record's `repo` stays the URL; the
    local checkout path never enters the portable manifest. The freshness
    requirement below applies to a fetched checkout exactly as to a local
    repo: a clone writes every file at clone time, and the clone happens
    BEFORE the run's start is stamped, so a repo that commits its outputs
    cannot report a false REPRODUCED off the authors' stored numbers.

    A claim's locator may target a JSON value (`from` + `path`, a JSONPath-lite
    into a JSON file) or a TSV/CSV cell (`from` + `column` + `row`, optionally
    `header`/`delimiter`) -- e.g. `{"id": "log2fc", "value": -2.31, "from":
    "out/de.tsv", "column": "log2FoldChange", "row": {"gene_id": "ENSG1"}}`.

    A locator may instead be a regex `pattern`: on its own it is matched
    against the run's own stdout/stderr, and with `from` it is matched against
    that repo-relative file -- e.g. `{"id": "auc", "value": 0.91, "pattern":
    "Final AUC: ([0-9.]+)"}`. The observed value is capture group 1 when the
    pattern has capturing groups, otherwise the whole match. Matching is
    strict: a pattern that matches 0 times or more than 1 time leaves the
    claim UNVERIFIED rather than guessing which number was meant.

    A locator may target a Jupyter notebook cell's output (`from` + `cell` +
    `pattern`), where `cell` is a code-cell index (or `{"contains": <source
    substring>}`) and `pattern` is applied to that cell's captured stdout/
    result text -- e.g. `{"id": "auc", "value": 0.91, "from": "out.ipynb",
    "cell": 7, "pattern": "AUC: ([0-9.]+)"}`.

    Every value read off disk must come from a file THIS run rewrote. Each
    locator carrying a `from` (JSON, TSV/CSV, text/log, notebook) and the
    `--results` file itself resolve only when the file's mtime is at or after
    the run's start; a file the run did not rewrite stays UNVERIFIED rather
    than binding a committed artifact as a false REPRODUCED. There is no
    opt-out. The single exemption is a `pattern` with no `from`: it matches
    the run's own captured stdout/stderr, touches no file on disk, and so can
    never be stale.
    """
    repo_argument = classify_repo_argument(repo)
    if repo_argument.refusal is not None:
        typer.echo(repo_argument.refusal, err=True)
        raise typer.Exit(code=1)

    if repo_argument.kind == "remote" and not allow_fetch:
        typer.echo(
            f"{repo} is a remote URL; pass --allow-fetch to clone it "
            "(it reaches the network and writes a checkout under --runs-dir)",
            err=True,
        )
        raise typer.Exit(code=1)

    # The run id is generated here, ahead of every validation gate, because a
    # remote run's checkout path is derived from it and the containment guards
    # below must run against that real path. It is only a name at this point;
    # nothing is created on disk until the fetch (or, for a local run, until
    # the bundle is written).
    reproduce_id = _generate_run_id()

    if repo_argument.kind == "local":
        repo_path = Path(repo)
        if not repo_path.is_dir():
            typer.echo(f"No such repo directory: {repo}", err=True)
            raise typer.Exit(code=1)
    else:
        # The PROSPECTIVE checkout path -- not created yet. The containment
        # guards below must never join a user path onto the raw URL string:
        # Path("https://host/org/repo") / "../../etc/passwd" is lexically
        # "inside" Path("https://host/org/repo"), so both guards would become
        # silent no-ops on exactly the untrusted third-party repos they exist
        # for. Path.resolve() on a not-yet-existing path is well-defined and
        # touches no filesystem, so every cheap refusal still runs BEFORE the
        # expensive, disk-touching clone.
        repo_path = Path(runs_dir) / reproduce_id / "source"

    # --results is repo-relative by contract (no raw-data egress outside the
    # repo Contig is asked to run in). Reject an absolute path or one that
    # resolves outside repo_path (e.g. "../secret.json") before anything runs.
    resolved_results = (repo_path / results).resolve()
    try:
        resolved_results.relative_to(repo_path.resolve())
    except ValueError:
        typer.echo(f"--results path escapes the repo: {results}", err=True)
        raise typer.Exit(code=1)

    try:
        claims_list = load_claims(claims)
    except (ClaimsError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    # Validate --run BEFORE running anything: an unbalanced quote makes
    # shlex.split raise ValueError, and an empty/whitespace-only command
    # splits to []. Both would otherwise surface as a raw traceback deep in
    # run_reproduction/subprocess. Pre-validate here and still pass the
    # original string through -- run_reproduction's own shlex.split is then
    # guaranteed not to raise on it.
    try:
        run_argv = shlex.split(run)
    except ValueError as exc:
        typer.echo(f"Malformed --run command: {exc}", err=True)
        raise typer.Exit(code=1)
    if not run_argv:
        typer.echo("--run command must not be empty", err=True)
        raise typer.Exit(code=1)

    # load_claims already defaults a claim's tolerance to 0.1 when the claims
    # file omits it. A claim that explicitly sets a DIFFERENT tolerance always
    # wins; --tolerance only re-defaults the ones still sitting at 0.1 (an
    # explicit 0.1 in the file is indistinguishable from an omitted one, and
    # both are the fallback's to own). --tolerance's own default is 0.1, so a
    # caller who never passes it sees no change.
    claims_list = [
        _dataclasses.replace(claim, tolerance=tolerance) if claim.tolerance == 0.1 else claim
        for claim in claims_list
    ]

    # A located claim's 'from' is repo-relative by the same contract as
    # --results: no raw-data egress outside the repo Contig is asked to run
    # in. Reject an absolute path or one that resolves outside repo_path
    # (e.g. "../secret.json") before anything runs -- the engine also
    # defends against this, but refusing here means no run and no record.
    # A `from`-less pattern locator (source is None) names no file at all --
    # it reads the run's own stdout/stderr -- so there is nothing to contain
    # and nothing to join onto repo_path; skip it like an unlocated claim.
    repo_root = repo_path.resolve()
    for claim in claims_list:
        if claim.locator is None or claim.locator.source is None:
            continue
        resolved_locator = (repo_path / claim.locator.source).resolve()
        try:
            resolved_locator.relative_to(repo_root)
        except ValueError:
            typer.echo(
                f"locator 'from' path escapes the repo: {claim.locator.source}", err=True
            )
            raise typer.Exit(code=1)

    # The clone is the FIRST disk write of this command, and it deliberately
    # happens BEFORE run_started_at is stamped below. A clone writes every file
    # at clone time; stamping first would make every author-committed artifact
    # look freshly written by this run and silently disable the freshness guard
    # for remote repos -- reopening the false-REPRODUCED hole on the very path
    # (real published repos) where it matters most. A failed fetch leaves no
    # directory behind (see fetch_repo).
    source_commit: str | None = None
    if repo_argument.kind == "remote":
        fetched = fetch_repo(repo_argument.url, repo_path, fetcher=default_fetcher)
        if fetched.refusal is not None:
            typer.echo(fetched.refusal, err=True)
            raise typer.Exit(code=1)
        source_commit = fetched.commit

    claims_sha256 = hashlib.sha256(Path(claims).read_bytes()).hexdigest()
    created_at = datetime.now(timezone.utc).isoformat()

    # Stamp run-start once, AFTER all pre-run validation and BEFORE the executor
    # runs. Every artifact read off disk -- the JSON, table, file-mode pattern and
    # notebook locators, plus the flat --results file -- binds only when its mtime
    # is >= this instant (i.e. this run rewrote it); anything older stays
    # UNVERIFIED. Captured here so an --allow-install retry does not re-stamp it.
    run_started_at = time.time()

    record = run_reproduction(
        str(repo_path),
        run,
        claims_list,
        executor=default_command_executor,
        claims_sha256=claims_sha256,
        results_path=results,
        created_at=created_at,
        reproduce_id=reproduce_id,
        allow_install=allow_install,
        installer=default_installer,
        run_started_at=run_started_at,
    )
    if repo_argument.kind == "remote":
        # `repo` on the record is the URL, never the local scratch checkout:
        # the checkout is a per-run path that means nothing to anyone else,
        # while the URL + commit is the pin that makes the bundle portable.
        record = record.model_copy(
            update={
                "repo": repo_argument.url,
                "source_url": repo_argument.url,
                "source_commit": source_commit,
            }
        )

    write_reproduce_bundle(record, Path(runs_dir) / reproduce_id)

    typer.echo(render_reproduction(record))

    if fail_on_diverged and any(c.status == "diverged" for c in record.claim_results):
        raise typer.Exit(code=1)


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
    fail_on_verdict: bool = typer.Option(
        False,
        "--fail-on-verdict",
        help=(
            "Exit non-zero if the run's stored verdict is FAIL (opt-in; WARN/UNVERIFIED do "
            "not). Composes with output-drift/signature checks. Default off."
        ),
    ),
    concordance_vcf: str = typer.Option(
        None,
        "--concordance-vcf",
        help="A second call set (VCF) to corroborate this germline run's variants against.",
    ),
    concordance_auto: bool = typer.Option(
        False,
        "--concordance-auto",
        help="Run a second variant caller (bcftools) on --bam and --ref and corroborate against it.",
    ),
    bam: str = typer.Option(
        None,
        "--bam",
        help="Aligned BAM for --concordance-auto's second caller.",
    ),
    ref: str = typer.Option(
        None,
        "--ref",
        help="Reference FASTA for --concordance-auto's second caller.",
    ),
    concordance_counts: str = typer.Option(
        None,
        "--concordance-counts",
        help="A second gene-count matrix (TSV) to corroborate this RNA-seq run's quantification against.",
    ),
    concordance_counts_auto: bool = typer.Option(
        False,
        "--concordance-counts-auto",
        help="Run a second quantifier (kallisto) on --reads and --index and corroborate this RNA-seq run's counts against it.",
    ),
    reads: str = typer.Option(
        None,
        "--reads",
        help="Sample sheet (FASTQ) for --concordance-counts-auto's second quantifier.",
    ),
    index: str = typer.Option(
        None,
        "--index",
        help=(
            "Prebuilt index for the auto second quantifier: a kallisto index for "
            "--concordance-counts-auto, or a STAR genome directory for "
            "--concordance-sc-counts-auto."
        ),
    ),
    concordance_sc_counts: str = typer.Option(
        None,
        "--concordance-sc-counts",
        help=(
            "Second single-cell count matrix (a matrix.mtx(.gz) with sibling "
            "features.tsv/barcodes.tsv, or a dense pseudobulk gene TSV) to corroborate "
            "an scrnaseq run's own matrix. Corroboration only: at most WARN, never "
            "changes the exit code."
        ),
    ),
    concordance_sc_counts_auto: bool = typer.Option(
        False,
        "--concordance-sc-counts-auto",
        help="Auto-run a second single-cell quantifier (STARsolo) and corroborate the run's own matrix.",
    ),
    whitelist: str = typer.Option(
        None,
        "--whitelist",
        help="Barcode whitelist for --concordance-sc-counts-auto (STARsolo).",
    ),
    chemistry: str = typer.Option(
        "10xv3",
        "--chemistry",
        help="Single-cell chemistry preset for --concordance-sc-counts-auto (default 10xv3).",
    ),
) -> None:
    """Re-hash a finished run's outputs and report any drift from the record.

    Reads the recorded output checksums and re-hashes the files on disk: an
    output that changed or disappeared is drift and exits non-zero. A run whose
    record captured no outputs reports "nothing to verify" (PRD contract B).

    With --fail-on-verdict (opt-in, default off), a loaded record whose reduced
    verdict is FAIL also exits non-zero (code 1), on every path — no-checksums and
    has-checksums, text and --json. It composes with the output-drift and signature
    checks (any one non-zero exits non-zero); WARN/UNVERIFIED/PASS still exit 0, the
    --json payload is unchanged, and concordance still NEVER affects the exit code.

    With --concordance-vcf, also corroborate the run's germline variants against a
    second call set (PRD C1): the concordance checks are printed (and included in
    the JSON payload), but concordance is at-most-WARN and NEVER changes the exit
    code, which only output drift or a signature mismatch can do.

    With --concordance-auto (plus --bam and --ref), Contig produces that second call
    set itself by running a second variant caller (bcftools) and corroborates the run
    against it; the same at-most-WARN, never-changes-exit contract applies.

    With --concordance-counts, corroborate an RNA-seq run's gene-count matrix against a
    second quantifier's matrix (PRD C1, rnaseq): the same at-most-WARN, never-changes-
    exit contract applies.

    With --concordance-counts-auto (plus --reads and --index), Contig produces that
    second gene-count matrix itself by running a second quantifier (kallisto) and
    corroborates the run against it; the same at-most-WARN, never-changes-exit
    contract applies. --reads and --index are ignored unless --concordance-counts-auto
    is set.

    With --concordance-sc-counts, corroborate an scrnaseq run's own count matrix against
    a second single-cell matrix (a matrix.mtx(.gz) triplet or a dense pseudobulk gene
    TSV; PRD C1, scrnaseq): both are collapsed to per-gene pseudobulk totals and fed to
    the same concordance core, under the same at-most-WARN, never-changes-exit contract.

    With --concordance-sc-counts-auto (plus --reads, --index and --whitelist), Contig
    produces that second single-cell matrix itself by running a second quantifier
    (STARsolo) and corroborates the run against it; the same at-most-WARN, never-changes-
    exit contract applies. --index is the STAR genome directory here (a kallisto index
    for --concordance-counts-auto). --reads, --index, --whitelist and --chemistry are
    ignored unless --concordance-sc-counts-auto is set.

    The six concordance flags are mutually exclusive.
    """
    if not _is_safe_run_id(run_id):
        typer.echo(f"Invalid run id: {run_id!r}", err=True)
        raise typer.Exit(code=1)
    if (
        sum(
            bool(x)
            for x in (
                concordance_vcf,
                concordance_auto,
                concordance_counts,
                concordance_counts_auto,
                concordance_sc_counts,
                concordance_sc_counts_auto,
            )
        )
        > 1
    ):
        typer.echo(
            "Choose one of --concordance-vcf, --concordance-auto, --concordance-counts, "
            "--concordance-counts-auto, --concordance-sc-counts or "
            "--concordance-sc-counts-auto, not more than one.",
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        record = load_run(runs_dir, run_id)
    except RunNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)

    # Opt-in verdict gate (PRD M2): a loaded FAIL verdict makes verify exit non-zero
    # on every terminal path below, composing with drift/signature (any one non-zero
    # exits non-zero). Computed once; WARN/UNVERIFIED/PASS never trip it.
    verdict_fail = fail_on_verdict and record.verdict == "fail"

    def _echo_verdict_reason() -> None:
        typer.echo(f"Run {run_id} verdict is FAIL (--fail-on-verdict).", err=True)

    # Concordance is independent of output-drift: compute it (if requested) up front
    # so it is surfaced on BOTH the no-checksums and has-checksums paths, and so it
    # can never influence the `ok`/exit decision below.
    if concordance_vcf:
        concordance = _evaluate_run_concordance(record, runs_dir, run_id, concordance_vcf)
    elif concordance_auto:
        concordance = _evaluate_run_concordance_auto(record, runs_dir, run_id, bam, ref)
    elif concordance_counts:
        concordance = _evaluate_run_counts_concordance(
            record, runs_dir, run_id, concordance_counts
        )
    elif concordance_counts_auto:
        concordance = _evaluate_run_counts_concordance_auto(
            record, runs_dir, run_id, reads, index
        )
    elif concordance_sc_counts:
        concordance = _evaluate_run_sc_counts_concordance(
            record, runs_dir, run_id, concordance_sc_counts
        )
    elif concordance_sc_counts_auto:
        concordance = _evaluate_run_sc_counts_concordance_auto(
            record, runs_dir, run_id, reads, index, whitelist, chemistry
        )
    else:
        concordance = None

    # A signed run carries a signature.json sidecar; a mismatch is a verification
    # failure (the record was tampered with), so it fails the verify just like drift.
    sig = _signature_status(runs_dir, run_id, record)
    sig_bad = sig.get("signed") and sig.get("signature_ok") is False

    if not record.output_checksums:
        result = {"ok": True, "changed": [], "missing": [], **sig}
        if concordance is not None:
            result["concordance"] = [c.model_dump() for c in concordance]
        if json_out:
            typer.echo(_json.dumps(result))
            if verdict_fail:
                _echo_verdict_reason()
            if sig_bad or verdict_fail:
                raise typer.Exit(code=1)
            return
        if sig_bad:
            typer.echo(f"Signature mismatch for run {run_id}: the record was modified.", err=True)
            _echo_concordance(concordance)
            raise typer.Exit(code=1)
        if verdict_fail:
            _echo_verdict_reason()
            _echo_concordance(concordance)
            raise typer.Exit(code=1)
        signed_note = " (signature verified)" if sig.get("signature_ok") else ""
        typer.echo(f"Nothing to verify for run {run_id}: no outputs were captured.{signed_note}")
        _echo_concordance(concordance)
        return

    result = verify_outputs(record, _results_dir_for(record, runs_dir, run_id))
    result.update(sig)
    if concordance is not None:
        result["concordance"] = [c.model_dump() for c in concordance]
    if json_out:
        typer.echo(_json.dumps(result))
        if verdict_fail:
            _echo_verdict_reason()
        if not result["ok"] or sig_bad or verdict_fail:
            raise typer.Exit(code=1)
        return

    if result["ok"] and not sig_bad and not verdict_fail:
        signed_note = " Signature verified." if sig.get("signature_ok") else ""
        typer.echo(f"Outputs verified for run {run_id}: all recorded outputs match.{signed_note}")
        _echo_concordance(concordance)
        return
    if sig_bad:
        typer.echo(f"Signature mismatch for run {run_id}: the record was modified.", err=True)
    if not result["ok"]:
        typer.echo(f"Drift detected for run {run_id}:", err=True)
        for rel in result["changed"]:
            typer.echo(f"  changed: {rel}", err=True)
        for rel in result["missing"]:
            typer.echo(f"  missing: {rel}", err=True)
    if verdict_fail:
        _echo_verdict_reason()
    _echo_concordance(concordance)
    raise typer.Exit(code=1)


def _evaluate_run_concordance(
    record: RunRecord, runs_dir: str, run_id: str, concordance_vcf: str
) -> list:
    """Concordance checks for a germline run vs a second call set, or [] with a note.

    Resolves the run's assay from its pipeline and, for germline variant calling,
    its primary VCF from the results dir (the variant_calling manifest's `*.vcf.gz`
    glob). A non-germline assay or a missing primary VCF prints a clear note and
    yields no checks (never a crash, never a false pass). Returns the QCResult list
    so the caller surfaces it without changing the exit code.
    """
    primary = _resolve_primary_vcf(record, runs_dir, run_id)
    if primary is None:
        return []
    return evaluate_concordance(primary, concordance_vcf, assay="variant_calling")


def _evaluate_run_concordance_auto(
    record: RunRecord,
    runs_dir: str,
    run_id: str,
    bam: str,
    ref: str,
    caller=None,
) -> list:
    """Concordance checks for a germline run vs a freshly produced second call set.

    Like `_evaluate_run_concordance`, but Contig produces the second call set itself:
    it gates to germline variant calling, resolves the same primary VCF, validates
    that --bam and --ref were given and exist, then runs the second caller (bcftools
    by default; injectable via `caller` and monkeypatchable as the module-level
    `run_bcftools_caller`). A missing input, a missing caller binary, or any
    SecondCallerError prints a clear skip note and yields no checks (never a crash,
    never a false pass). Returns the QCResult list so the caller surfaces it without
    changing the exit code.
    """
    primary = _resolve_primary_vcf(record, runs_dir, run_id)
    if primary is None:
        return []

    for label, value in (("--bam", bam), ("--ref", ref)):
        if not value:
            typer.echo(f"Skipping concordance: {label} is required for --concordance-auto.")
            return []
        if not Path(value).is_file():
            typer.echo(f"Skipping concordance: {label} file not found: {value}.")
            return []

    run_caller = caller if caller is not None else run_bcftools_caller
    with tempfile.TemporaryDirectory() as out_dir:
        try:
            second_vcf = run_caller(bam, ref, out_dir)
        except SecondCallerError as exc:
            typer.echo(f"Skipping concordance: the second caller could not run ({exc}).")
            return []
        return evaluate_concordance(primary, second_vcf, assay="variant_calling")


def _resolve_primary_vcf(record: RunRecord, runs_dir: str, run_id: str):
    """Resolve a germline run's primary VCF, or None with a clear skip note.

    Shared by both concordance paths so the assay gate and the primary-VCF glob
    cannot drift apart. Gates the run's assay to germline variant calling and finds
    its primary `*.vcf.gz` from the variant_calling manifest under the results dir. A
    non-germline assay or a missing primary VCF prints a clear note and returns None.
    """
    assay = assay_for_pipeline(record.pipeline)
    if assay != "variant_calling":
        typer.echo(
            "Skipping concordance: it is only defined for germline variants today "
            f"(run {run_id} is {assay or record.pipeline})."
        )
        return None

    results_dir = _results_dir_for(record, runs_dir, run_id)
    manifest = manifest_for("variant_calling")
    pattern = manifest.required[0]  # "*.vcf.gz", the primary germline call set
    primaries = sorted(p for p in results_dir.rglob(pattern) if p.is_file())
    if not primaries:
        typer.echo(
            f"Skipping concordance: no primary VCF ({pattern}) found for run {run_id}."
        )
        return None
    return primaries[0]


def _resolve_primary_counts(record: RunRecord, runs_dir: str, run_id: str):
    """Resolve an rnaseq run's primary gene-count matrix, or None with a skip note.

    Gates the run's assay to rnaseq and finds its primary Salmon gene-count matrix by
    globbing `_COUNT_MATRIX_GLOB` under the results dir (NOT the manifest's `required[0]`,
    which is the `*.bam` alignment, not the count matrix). A non-rnaseq assay or a
    missing matrix prints a clear note and returns None (never a crash, never a false
    pass).
    """
    assay = assay_for_pipeline(record.pipeline)
    if assay != "rnaseq":
        typer.echo(
            "Skipping concordance: count concordance is only defined for RNA-seq today "
            f"(run {run_id} is {assay or record.pipeline})."
        )
        return None

    results_dir = _results_dir_for(record, runs_dir, run_id)
    primaries = sorted(
        p for p in results_dir.rglob(_COUNT_MATRIX_GLOB) if p.is_file()
    )
    if not primaries:
        typer.echo(
            "Skipping concordance: no primary gene-count matrix "
            f"({_COUNT_MATRIX_GLOB}) found for run {run_id}."
        )
        return None
    return primaries[0]


def _evaluate_run_counts_concordance(
    record: RunRecord, runs_dir: str, run_id: str, counts_matrix: str
) -> list:
    """Count-concordance checks for an rnaseq run vs a second matrix, or [] with a note.

    Resolves the run's primary gene-count matrix (gating to rnaseq) and corroborates
    it against the provided second matrix. A non-rnaseq assay or a missing primary
    matrix yields no checks. Returns the QCResult list so the caller surfaces it
    without changing the exit code.
    """
    primary = _resolve_primary_counts(record, runs_dir, run_id)
    if primary is None:
        return []
    return evaluate_count_concordance(primary, counts_matrix, assay="rnaseq")


def _resolve_primary_sc_matrix(record: RunRecord, runs_dir: str, run_id: str):
    """Resolve an scrnaseq run's primary count matrix (.mtx), or None with a skip note.

    Gates the run's assay to scrnaseq and finds its primary single-cell count matrix by
    globbing `_SC_MATRIX_GLOB` under the results dir (a STARsolo/Cell Ranger
    `matrix.mtx`(.gz) triplet). A non-scrnaseq assay or a missing matrix prints a clear
    note and returns None (never a crash, never a false pass). When both `filtered/` and
    `raw/` triplets are present, the filtered matrix is preferred (the analysis-ready
    cell set); ties are broken by the deterministic sorted first.
    """
    assay = assay_for_pipeline(record.pipeline)
    if assay != "scrnaseq":
        typer.echo(
            "Skipping concordance: single-cell count concordance is only defined for "
            f"scrnaseq today (run {run_id} is {assay or record.pipeline})."
        )
        return None

    results_dir = _results_dir_for(record, runs_dir, run_id)
    matches = sorted(p for p in results_dir.rglob(_SC_MATRIX_GLOB) if p.is_file())
    if not matches:
        typer.echo(
            "Skipping concordance: no single-cell count matrix (matrix.mtx) found "
            f"for run {run_id}."
        )
        return None

    filtered = [p for p in matches if "filtered" in p.parts]
    if filtered:
        return filtered[0]
    return matches[0]


def _evaluate_run_sc_counts_concordance(
    record: RunRecord, runs_dir: str, run_id: str, second: str
) -> list:
    """Single-cell count-concordance for an scrnaseq run vs a second matrix, or [].

    Resolves the run's primary single-cell count matrix (gating to scrnaseq) and
    corroborates it against the provided second matrix (a `.mtx`(.gz) triplet or a dense
    pseudobulk TSV, sniffed by the loader). A non-scrnaseq assay or a missing primary
    matrix yields no checks. Returns the QCResult list so the caller surfaces it without
    changing the exit code.
    """
    primary = _resolve_primary_sc_matrix(record, runs_dir, run_id)
    if primary is None:
        return []
    return evaluate_sc_count_concordance(primary, second, assay="scrnaseq")


def _evaluate_run_counts_concordance_auto(
    record: RunRecord,
    runs_dir: str,
    run_id: str,
    reads: str,
    index: str,
    quantifier=None,
) -> list:
    """Count-concordance checks for an rnaseq run vs a freshly produced second matrix.

    Like `_evaluate_run_counts_concordance`, but Contig produces the second gene-count
    matrix itself: it gates to rnaseq, resolves the same primary matrix, validates
    that --reads and --index were given and exist, then runs the second quantifier
    (kallisto by default; injectable via `quantifier` and monkeypatchable as the
    module-level `run_kallisto_quantifier`). A missing input or any
    SecondQuantifierError prints a clear skip note and yields no checks (never a
    crash, never a false pass). Returns the QCResult list so the caller surfaces it
    without changing the exit code.
    """
    primary = _resolve_primary_counts(record, runs_dir, run_id)
    if primary is None:
        return []

    for label, value in (("--reads", reads), ("--index", index)):
        if not value:
            typer.echo(f"Skipping concordance: {label} is required for --concordance-counts-auto.")
            return []
        if not Path(value).exists():
            typer.echo(f"Skipping concordance: {label} path not found: {value}.")
            return []

    run_q = quantifier if quantifier is not None else run_kallisto_quantifier
    with tempfile.TemporaryDirectory() as out_dir:
        try:
            second = run_q(reads, index, out_dir)
        except SecondQuantifierError as exc:
            typer.echo(f"Skipping concordance: the second quantifier could not run ({exc}).")
            return []
        return evaluate_count_concordance(primary, second, assay="rnaseq")


def _evaluate_run_sc_counts_concordance_auto(
    record: RunRecord,
    runs_dir: str,
    run_id: str,
    reads: str,
    index: str,
    whitelist: str,
    chemistry: str,
    quantifier=None,
) -> list:
    """Single-cell concordance for an scrnaseq run vs a freshly produced second matrix.

    Like `_evaluate_run_sc_counts_concordance`, but Contig produces the second
    single-cell matrix itself: it gates to scrnaseq, resolves the same primary matrix,
    validates that --reads, --index (STAR genome dir) and --whitelist were given and
    exist, then runs the second quantifier (STARsolo by default; injectable via
    `quantifier` and monkeypatchable as the module-level `run_starsolo_quantifier`). A
    missing primary matrix skips BEFORE any spawn; a missing input or any
    SecondScQuantifierError prints a clear skip note and yields no checks (never a
    crash, never a false pass). Returns the QCResult list so the caller surfaces it
    without changing the exit code.
    """
    primary = _resolve_primary_sc_matrix(record, runs_dir, run_id)
    if primary is None:
        return []

    for label, value in (("--reads", reads), ("--index", index), ("--whitelist", whitelist)):
        if not value:
            typer.echo(
                f"Skipping concordance: {label} is required for --concordance-sc-counts-auto."
            )
            return []
        if not Path(value).exists():
            typer.echo(f"Skipping concordance: {label} path not found: {value}.")
            return []

    run_q = quantifier if quantifier is not None else run_starsolo_quantifier
    with tempfile.TemporaryDirectory() as out_dir:
        try:
            second = run_q(reads, index, whitelist, chemistry, out_dir)
        except SecondScQuantifierError as exc:
            typer.echo(
                f"Skipping concordance: the second quantifier could not run ({exc})."
            )
            return []
        return evaluate_sc_count_concordance(
            str(primary), second, assay="scrnaseq", second_name="STARsolo"
        )


def _echo_concordance(concordance: list | None) -> None:
    """Print the concordance checks in the text path; a no-op when none were run."""
    if not concordance:
        return
    typer.echo("Concordance (cross-tool corroboration):")
    for qc in concordance:
        value = "" if qc.value is None else f" value={qc.value}"
        typer.echo(f"  {qc.check}: {qc.status.upper()}{value} ({qc.message})")


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
        allow_reference_mismatch=manifest.allow_reference_mismatch,
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


def _print_trend(rows, *, title):
    """Render a metric trend oldest->newest with a per-version delta column.

    rows: list of (timestamp, value_float, detail_str, version_str). The delta is
    value vs the previous row's value, in percentage points; the first row shows a
    dash and the last row is tagged so the current standing is obvious.
    """
    typer.echo(title)
    prev = None
    for i, (ts, value, detail, version) in enumerate(rows):
        delta = "   —   " if prev is None else f"{(value - prev) * 100:+.1f}pp"
        latest = "  ←latest" if i == len(rows) - 1 else ""
        typer.echo(f"  {ts}  {detail}  Δ {delta}  [{version}]{latest}")
        prev = value


@app.command(name="eval-detector")
def eval_detector(
    corpus: str = typer.Option(None, "--corpus", help="Failure-corpus JSONL (defaults to the shipped seed)."),
    detector: str = typer.Option("rules", "--detector", help="Which detector to score (rules, rules-strict, or llm when a provider/key is configured)."),
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


@app.command(name="eval-guard")
def eval_guard(
    holdout: str = typer.Option(None, "--holdout", help="Held-out corpus JSONL (defaults to the shipped frozen set)."),
    baseline: str = typer.Option(None, "--baseline", help="Baseline JSON (defaults to the shipped one)."),
    detector: str = typer.Option("rules", "--detector", help="Which detector to guard (rules, rules-strict, ...)."),
    tolerance: float = typer.Option(1e-9, "--tolerance", help="Float tolerance; accuracy below (baseline - tolerance) is a regression."),
    update_baseline: bool = typer.Option(False, "--update-baseline", help="(Re)freeze the baseline to the current held-out accuracy. Deliberate, reviewed act."),
    json_out: bool = typer.Option(False, "--json", help="Emit the guard result as JSON."),
    snapshot: bool = typer.Option(False, "--snapshot", help="Append this guard run to the held-out accuracy trend (moat #2)."),
    show_history: bool = typer.Option(False, "--history", help="Print the recorded held-out accuracy trend instead of guarding. Ignores --snapshot."),
    history_file: str = typer.Option(None, "--history-file", help="Held-out accuracy history JSONL (defaults to the shipped one)."),
) -> None:
    """Guard detector accuracy against a frozen held-out set (moat #2, C6 slice 1).

    Scores `detector` against a held-out corpus it was never tuned against and
    compares the accuracy to a committed baseline, exiting non-zero on a real
    regression so a detector or corpus change never regresses diagnosis
    silently. `--update-baseline` deliberately (re)freezes the baseline instead
    of guarding; that always exits 0. With --snapshot the result is also
    appended to the committed held-out trend; with --history the recorded
    trend is printed instead.
    """
    holdout_path = Path(holdout) if holdout else default_holdout_path()
    baseline_path = Path(baseline) if baseline else default_baseline_path()
    history_path = Path(history_file) if history_file else default_holdout_history_path()

    if show_history:
        history = load_jsonl(EvalSnapshot, history_path)
        if json_out:
            typer.echo("[" + ",".join(s.model_dump_json() for s in history) + "]")
            return
        if not history:
            typer.echo(f"No held-out accuracy snapshots recorded yet in {history_path}.")
            return
        _print_trend(
            [(s.timestamp, s.accuracy,
              f"accuracy {s.accuracy:.1%}  (held-out {s.corpus_size})",
              s.detector) for s in history],
            title="Held-out detector accuracy over time:",
        )
        return

    try:
        detector_fn = get_detector(detector)
    except KeyError as exc:
        typer.echo(str(exc).strip("\"'"), err=True)
        raise typer.Exit(code=1)

    try:
        cases = load_corpus(holdout_path)
    except FileNotFoundError:
        typer.echo(f"Held-out corpus not found: {holdout_path}", err=True)
        raise typer.Exit(code=1)

    report = evaluate_detector(cases, detector_fn)
    holdout_sha = sha256_file(holdout_path)

    if update_baseline:
        snap = snapshot_from_report(
            report,
            timestamp=datetime.now(timezone.utc).isoformat(),
            corpus_size=len(cases),
            corpus_sha=holdout_sha,
            contig_version=_pkg_version("contig"),
            detector=detector,
        )
        save_baseline(snap, baseline_path)
        append_jsonl(snap, history_path)
        typer.echo(
            f"Baseline updated: accuracy {report.accuracy:.1%} over {len(cases)} held-out "
            f"cases (detector={detector}, sha {holdout_sha[:12]}...)"
        )
        return

    if snapshot:
        append_jsonl(
            snapshot_from_report(
                report,
                timestamp=datetime.now(timezone.utc).isoformat(),
                corpus_size=len(cases),
                corpus_sha=holdout_sha,
                contig_version=_pkg_version("contig"),
                detector=detector,
            ),
            history_path,
        )

    baseline_snapshot = load_baseline(baseline_path)
    result = compare_to_baseline(
        report,
        baseline=baseline_snapshot,
        holdout_sha=holdout_sha,
        holdout_size=len(cases),
        detector=detector,
        tolerance=tolerance,
    )

    if json_out:
        typer.echo(result.model_dump_json())

    if not result.has_baseline:
        typer.echo(
            f"No held-out baseline at {baseline_path}; run 'contig eval-guard "
            "--update-baseline' to freeze one.",
            err=True,
        )
        raise typer.Exit(code=1)

    if result.sha_mismatch:
        typer.echo(
            f"Held-out set changed (sha {holdout_sha[:12]} != baseline "
            f"{(result.baseline_sha or '')[:12]}); the delta crosses different sets — "
            "refreeze with --update-baseline.",
            err=True,
        )
    if result.detector_mismatch:
        typer.echo(
            f"Baseline was measured with detector '{baseline_snapshot.detector}', guarding "
            f"'{detector}' — comparison crosses detectors.",
            err=True,
        )

    if not json_out:
        delta_pp = (result.delta or 0.0) * 100
        typer.echo(
            f"Guard: accuracy {result.accuracy:.1%} vs baseline {result.baseline_accuracy:.1%} "
            f"(delta {delta_pp:+.1f}pp) over {result.holdout_size} held-out cases [{detector}]"
        )
        for m in result.mismatches:
            typer.echo(f"  MISS {m.case_id}: expected {m.expected}, predicted {m.predicted}")

    if result.regressed:
        delta_pp = (result.delta or 0.0) * 100
        typer.echo(
            f"REGRESSION: accuracy {result.accuracy:.1%} below baseline "
            f"{result.baseline_accuracy:.1%} (delta {delta_pp:+.1f}pp).",
            err=True,
        )
        raise typer.Exit(code=1)

    if result.improved:
        if not json_out:
            typer.echo(
                f"Held-out accuracy improved ({result.accuracy:.1%} > baseline "
                f"{result.baseline_accuracy:.1%}); consider --update-baseline to lock it in."
            )
        return

    if not json_out:
        typer.echo(f"Guard PASS: accuracy {result.accuracy:.1%} ≥ baseline {result.baseline_accuracy:.1%}.")


@app.command(name="heal-guard")
def heal_guard(
    scenarios: str = typer.Option(None, "--scenarios", help="Self-heal scenario JSONL (defaults to the shipped synthetic set)."),
    baseline: str = typer.Option(None, "--baseline", help="Baseline JSON (defaults to the shipped one)."),
    tolerance: float = typer.Option(1e-9, "--tolerance", help="Float tolerance; outcome-match rate below (baseline - tolerance) is a regression."),
    update_baseline: bool = typer.Option(False, "--update-baseline", help="(Re)freeze the baseline to the current outcome-match rate. Deliberate, reviewed act."),
    json_out: bool = typer.Option(False, "--json", help="Emit the guard result as JSON."),
    snapshot: bool = typer.Option(False, "--snapshot", help="Append this guard run to the self-heal outcome-match trend (moat #2)."),
    show_history: bool = typer.Option(False, "--history", help="Print the recorded self-heal outcome-match trend instead of guarding. Ignores --snapshot."),
    history_file: str = typer.Option(None, "--history-file", help="Self-heal outcome-match history JSONL (defaults to the shipped one)."),
) -> None:
    """Guard the self-heal loop's outcome-match rate against a frozen synthetic scenario set (C6 slice 2).

    Replays `evaluate_heal` -- the REAL detect->diagnose->patch->retry loop,
    never a mock of it -- over a frozen scenario corpus and compares the
    outcome-match rate to a committed baseline, exiting non-zero on a real
    regression so a change to the loop, a detector, or a patch never silently
    starts diverging from a scenario's declared outcome. `--update-baseline`
    deliberately (re)freezes the baseline instead of guarding; that always
    exits 0. With --snapshot the result is also appended to the committed
    self-heal trend; with --history the recorded trend is printed instead.

    Honest scope: the number is over **7 SYNTHETIC scenarios**, not a field
    recovery rate. Covered failure classes: bad_param, missing_index, oom,
    time_limit, tool_crash. Not covered: qc_anomaly and no_progress are
    currently structurally unreachable (no diagnose_failure rule branch emits
    them yet); container_pull_failed, container_unavailable, conda_solve_failed,
    platform_unsupported, disk_full, download_failed, permission_denied, and
    missing_reference have no scenario yet and are deferred follow-on slices.
    """
    scenarios_path = Path(scenarios) if scenarios else default_heal_scenarios_path()
    baseline_path = Path(baseline) if baseline else default_heal_baseline_path()
    history_path = Path(history_file) if history_file else default_heal_history_path()

    if show_history:
        history = load_jsonl(HealSnapshot, history_path)
        if json_out:
            typer.echo("[" + ",".join(s.model_dump_json() for s in history) + "]")
            return
        if not history:
            typer.echo(f"No self-heal outcome-match snapshots recorded yet in {history_path}.")
            return
        _print_trend(
            [(s.timestamp, s.outcome_match_rate,
              f"outcome-match {s.outcome_match_rate:.0%}  ({s.scenario_count} scenarios)  "
              f"recovery {round(s.recovery_rate * s.scenario_count)}/{s.scenario_count}",
              s.contig_version or "unknown") for s in history],
            title="Self-heal outcome-match over time:",
        )
        return

    try:
        cases = load_heal_scenarios(scenarios_path)
    except FileNotFoundError:
        typer.echo(f"Heal scenarios not found: {scenarios_path}", err=True)
        raise typer.Exit(code=1)

    report = evaluate_heal(cases)
    corpus_sha = sha256_file(scenarios_path)
    covered_classes = sorted({s.expected_class for s in cases})

    if update_baseline:
        snap = snapshot_from_heal_report(
            report,
            corpus_sha=corpus_sha,
            covered_classes=covered_classes,
            contig_version=_pkg_version("contig"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        save_heal_baseline(snap, baseline_path)
        append_jsonl(snap, history_path)
        typer.echo(
            f"Baseline updated: outcome-match {report.outcome_match_rate:.0%} over "
            f"{report.total} synthetic scenarios; recovery {report.healed}/{report.total}; "
            f"covered: {', '.join(covered_classes)}"
        )
        return

    if snapshot:
        append_jsonl(
            snapshot_from_heal_report(
                report,
                corpus_sha=corpus_sha,
                covered_classes=covered_classes,
                contig_version=_pkg_version("contig"),
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            history_path,
        )

    baseline_snapshot = load_heal_baseline(baseline_path)
    result = compare_heal_to_baseline(
        report,
        baseline=baseline_snapshot,
        corpus_sha=corpus_sha,
        tolerance=tolerance,
    )

    if json_out:
        typer.echo(result.model_dump_json())

    if not result.has_baseline:
        typer.echo(
            f"No heal-guard baseline at {baseline_path}; run 'contig heal-guard "
            "--update-baseline' to freeze one.",
            err=True,
        )
        raise typer.Exit(code=1)

    if result.sha_mismatch:
        typer.echo(
            f"Scenario set changed (sha {corpus_sha[:12]} != baseline "
            f"{(result.baseline_sha or '')[:12]}); the delta crosses different sets — "
            "refreeze with --update-baseline.",
            err=True,
        )

    if not json_out:
        delta_pp = (result.delta or 0.0) * 100
        typer.echo(
            f"Heal-guard: outcome-match {result.outcome_match_rate:.0%} vs baseline "
            f"{result.baseline_match_rate:.0%} (delta {delta_pp:+.1f}pp) over "
            f"{result.scenario_count} synthetic scenarios; recovery {report.healed}/{report.total}; "
            f"covered: {', '.join(covered_classes)}"
        )
        for m in result.mismatches:
            typer.echo(f"  MISS {m.scenario_id}: {'; '.join(m.divergence)}")

    if result.regressed:
        delta_pp = (result.delta or 0.0) * 100
        mismatch_ids = ", ".join(m.scenario_id for m in result.mismatches)
        typer.echo(
            f"REGRESSION: outcome-match {result.outcome_match_rate:.0%} below baseline "
            f"{result.baseline_match_rate:.0%} (delta {delta_pp:+.1f}pp): {mismatch_ids}",
            err=True,
        )
        raise typer.Exit(code=1)

    if result.improved:
        if not json_out:
            typer.echo(
                f"Heal-guard improved (outcome-match {result.outcome_match_rate:.0%} > baseline "
                f"{result.baseline_match_rate:.0%}); consider --update-baseline to lock it in."
            )
        return

    if not json_out:
        typer.echo(
            f"Heal-guard PASS: outcome-match {result.outcome_match_rate:.0%} "
            f"≥ baseline {result.baseline_match_rate:.0%}."
        )


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
