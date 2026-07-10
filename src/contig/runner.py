"""Drives the workflow manager in the data plane (ARCHITECTURE §3, §4.2).

For the P0 spike this is just the command builder: it turns a job spec into the
exact Nextflow argv, wiring `-with-trace` so the run is machine-readable and
captured (feeds contig.events ingestion). Actual subprocess execution + RunRecord
assembly is layered on once the toolchain (Nextflow/Docker) is present.
"""

from __future__ import annotations

import subprocess
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Callable


def _contig_version() -> str | None:
    """Contig's installed version, or None in a non-installed (raw PYTHONPATH) setup."""
    try:
        return _pkg_version("contig")
    except PackageNotFoundError:
        return None

from contig.bundle import compute_input_checksums, write_bundle
from contig.events import parse_trace_file
from contig.models import ExecutionTarget, QCResult, RunRecord, TaskEvent
from contig.nfconfig import generate_nextflow_config
from contig.snakemake import build_snakemake_command, parse_snakemake_stats_file
from contig.verification.qc_ingest import parse_multiqc_general_stats_file
from contig.verification.rnaseq_plausibility import evaluate_rnaseq_plausibility
from contig.verification.rule_pack import SCRNASEQ_RULE_PACK, evaluate, rule_pack_for
from contig.verification.scrnaseq_metrics import (
    parse_cellranger_metrics,
    parse_starsolo_summary,
)
from contig.verification.somatic_concordance import evaluate_somatic_concordance_from_run
from contig.verification.somatic_plausibility import evaluate_somatic_plausibility
from contig.verification.run_qc import evaluate_run_qc
from contig.verification.structural import evaluate_structural, manifest_for
from contig.verification.variant_metrics import evaluate_variant_plausibility


# STARsolo writes a Summary.csv under each metric subdir (Gene/, GeneFull/, ...);
# the enclosing dir named "<sample>.Solo.out" carries the sample id. These are the
# STARsolo internal dir names to skip when falling back to a plain ancestor name.
_STARSOLO_INTERNAL = {
    "Gene",
    "GeneFull",
    "GeneFull_Ex50pAS",
    "GeneFull_ExonOverIntron",
    "Velocyto",
    "Solo.out",
    "raw",
    "filtered",
}


def _sample_from_starsolo(path: Path) -> str:
    """Derive the sample id from a STARsolo Summary.csv path.

    Prefers the `<sample>.Solo.out` ancestor (strip the suffix); otherwise the
    nearest ancestor that is not a STARsolo internal directory.
    """
    for parent in path.parents:
        if parent.name.endswith(".Solo.out"):
            return parent.name[: -len(".Solo.out")]
    for parent in path.parents:
        if parent.name and parent.name not in _STARSOLO_INTERNAL:
            return parent.name
    return path.stem


def _sample_from_cellranger(path: Path) -> str:
    """Derive the sample id from a Cell Ranger metrics_summary.csv path.

    Cell Ranger writes `<sample>/outs/metrics_summary.csv`, so the sample is the
    directory above `outs`.
    """
    parent = path.parent
    if parent.name == "outs":
        return parent.parent.name
    return parent.name


def _locate_scrnaseq_qc(run_dir: Path) -> dict[str, dict[str, float]]:
    """Find single-cell cell-QC artifacts under a run dir → {sample: {slug: value}}.

    Cell Ranger takes deterministic precedence over STARsolo for the same sample
    (no merge of two aligners' numbers). A located-but-unparseable file maps the
    sample to an empty dict so the gate can emit an explicit UNVERIFIED. The
    default simpleaf/alevin-fry path has no machine-readable artifact, so it
    contributes nothing here (→ the sample is simply absent).
    """
    located: dict[str, dict[str, float]] = {}
    for path in sorted(run_dir.rglob("metrics_summary.csv")):
        located[_sample_from_cellranger(path)] = parse_cellranger_metrics(path)
    for path in sorted(run_dir.rglob("Summary.csv")):
        sample = _sample_from_starsolo(path)
        if sample in located:
            continue  # Cell Ranger already won this sample, or an earlier Summary.csv
        located[sample] = parse_starsolo_summary(path)
    return located


def _discover_qc(run_dir: Path, assay: str = "rnaseq") -> list[QCResult]:
    """Verify a finished run: MultiQC metric checks (assay-specific rule pack) +
    structural checks on outputs + VCF plausibility checks (germline ts_tv/het_hom;
    somatic VAF/count/PON), each gated to its own assay."""
    results: list[QCResult] = []
    multiqc = next(run_dir.glob("**/multiqc_data.json"), None)
    if multiqc is not None:
        try:
            pack = rule_pack_for(assay)
        except ValueError:
            pack = None  # no rule pack for this assay -> skip metric QC (stay honest)
        if pack is not None:
            results.extend(
                evaluate_run_qc(multiqc, rule_pack=pack, cross_sample=(assay == "rnaseq"))
            )
    # Check that BAM outputs exist and are non-empty. We do NOT blanket-check for
    # indexes here: many BAMs are intermediates that are never indexed, and a
    # spurious index_present:fail would wrongly drag the verdict to "fail".
    bams = sorted(run_dir.glob("**/*.bam"))
    if bams:
        results.extend(evaluate_structural(bams))
    # Germline biological-plausibility checks (ts_tv, het_hom) computed straight
    # from the VCF. This path is INDEPENDENT of MultiQC: it runs whether or not a
    # report was found, so a germline run is never left without these checks. We
    # locate the primary VCF exactly as concordance does (the variant_calling
    # manifest's first required glob, rglob'd under the run), and skip cleanly when
    # there is none. Gated strictly to germline so other assays are untouched.
    if assay == "variant_calling":
        pattern = manifest_for("variant_calling").required[0]  # "*.vcf.gz"
        vcfs = sorted(p for p in run_dir.rglob(pattern) if p.is_file())
        if vcfs:
            results.extend(evaluate_variant_plausibility(vcfs[0]))
    # Annotation structural verification (capability C7, germline slice). Gated to
    # germline. We look for an annotated VCF (one carrying CSQ/ANN) anywhere under
    # the run and verify the annotation step ran over every record. Absent
    # annotation is handled inside evaluate_annotation_structural as UNVERIFIED, so
    # a plain (un-annotated) germline run is never dragged down — we simply don't
    # find an annotated VCF and skip. Research-use only: no significance claim.
    if assay == "variant_calling":
        from contig.verification.annotation_structural import (
            annotation_metrics,
            evaluate_annotation_structural,
        )

        for vcf in sorted(run_dir.rglob("*.vcf.gz")):
            if annotation_metrics(vcf).info_key is not None:
                results.extend(evaluate_annotation_structural(vcf))
                break
    # Somatic biological-plausibility checks (capability C4 follow-on): VAF
    # distribution, somatic variant count, and panel-of-normals presence, all
    # computed from the tumor column of the Mutect2 VCF. Gated strictly to the
    # somatic assay. We glob the somatic manifest's required *.vcf.gz and pick the
    # Mutect2 candidate by path; if VCFs exist but none is Mutect2 we emit ONE
    # honest UNVERIFIED (never a silent pass), and if there is no VCF at all we
    # skip silently (structural QC already covers a missing required output).
    if assay == "somatic_variant_calling":
        pattern = manifest_for("somatic_variant_calling").required[0]  # "*.vcf.gz"
        vcfs = sorted(p for p in run_dir.rglob(pattern) if p.is_file())
        if vcfs:
            # Match "mutect2" as a path COMPONENT below the run dir (sarek writes the
            # VCF under a `mutect2/` directory), not as a substring of the absolute
            # path — otherwise a "mutect2" in an ancestor workspace/run-id name would
            # false-positively select a Strelka VCF and risk a pass on the wrong data.
            mutect2 = next(
                (
                    p
                    for p in vcfs
                    if "mutect2" in {part.lower() for part in p.relative_to(run_dir).parts}
                ),
                None,
            )
            if mutect2 is not None:
                results.extend(evaluate_somatic_plausibility(mutect2))
            else:
                results.append(
                    QCResult(
                        check="somatic_vaf_plausibility",
                        status="unverified",
                        message=(
                            "no Mutect2 somatic VCF found to assess VAF distribution"
                        ),
                        value=None,
                        kind="metric",
                    )
                )
            # Cross-tool PASS-site-overlap concordance (Strelka2 vs Mutect2):
            # appended after, and independent of, VAF plausibility above — it
            # reuses the same globbed VCF list but self-selects both callers'
            # files and skips cleanly (or reports UNVERIFIED) on its own terms.
            results.extend(evaluate_somatic_concordance_from_run(run_dir, vcfs))
    # RNA-seq biological-plausibility checks (capability C3, RNA-seq slice, Phase 3).
    # Gated: only when the assay is rnaseq AND a MultiQC report was found. One extra
    # parse of the same JSON is intentional — mirrors the germline path independently
    # re-locating the VCF so the two gates stay self-contained.
    if assay == "rnaseq" and multiqc is not None:
        metrics = parse_multiqc_general_stats_file(multiqc)
        results.extend(evaluate_rnaseq_plausibility(metrics))
    # Single-cell cell-QC (capability C3, scrnaseq slice). The base nf-core/scrnaseq
    # pipeline does NOT route cell-level metrics into MultiQC general-stats, so a
    # dedicated gate parses the aligner's own cell-QC artifact (STARsolo Summary.csv
    # / Cell Ranger metrics_summary.csv) and drives SCRNASEQ_RULE_PACK. A located file
    # with no usable metric yields one explicit UNVERIFIED (never a silent no-op or a
    # false pass); no artifact at all skips silently (structural QC owns a missing
    # output, mirroring the germline no-VCF path). Gated strictly to scrnaseq.
    if assay == "scrnaseq":
        for sample, sample_metrics in _locate_scrnaseq_qc(run_dir).items():
            if sample_metrics:
                results.extend(evaluate({sample: sample_metrics}, SCRNASEQ_RULE_PACK))
            else:
                results.append(
                    QCResult(
                        check=f"scrnaseq_cell_qc:{sample}",
                        status="unverified",
                        message=(
                            f"{sample}: cell-QC file found but no usable metric parsed"
                        ),
                        value=None,
                        kind="metric",
                    )
                )
    return results

# An executor runs the Nextflow argv and is responsible for the trace file
# existing at trace_path when it returns. The default shells out; tests inject a
# fake that writes a canned trace, so the parse/assemble/bundle path stays real.
Executor = Callable[[list[str], Path], int]

# An index builder runs an auxiliary build command (e.g. `samtools faidx ref`)
# in the given cwd and returns its exit code. The default shells out; tests
# inject a fake that creates the index file, so no real tool runs in CI.
IndexBuilder = Callable[[list[str], Path], int]


class PipelineExecutionError(RuntimeError):
    """Raised when the workflow manager exits nonzero (DETECT, ARCHITECTURE §5.1).

    Surfacing the return code cleanly is the entry point for diagnosis/self-heal;
    it must not be masked by a downstream missing-trace traceback.
    """

    def __init__(self, returncode: int, record: "RunRecord | None" = None):
        self.returncode = returncode
        self.record = record  # whatever was captured before/at failure, for diagnosis
        super().__init__(f"Nextflow exited with code {returncode}")


def default_executor(cmd: list[str], trace_path: Path) -> int:
    """Run Nextflow in the data plane, teeing stdout+stderr to run.log.

    The log is the detector's primary input (ARCHITECTURE §5.1): it carries the
    failing process, command, and stderr that classification keys off.
    """
    log_path = trace_path.parent / "run.log"
    with open(log_path, "wb") as log:
        proc = subprocess.run(
            cmd, cwd=trace_path.parent, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    return proc.returncode


def default_index_builder(cmd: list[str], cwd: Path) -> int:
    """Run an auxiliary index-build command (e.g. ``samtools faidx ref``) in cwd.

    Tees combined stdout+stderr to run.log (appending), so the build output is
    captured alongside the pipeline log that default_executor wrote. Returns the
    process exit code. Tests inject a fake builder so no real tool runs in CI.
    """
    log_path = Path(cwd) / "run.log"
    with open(log_path, "ab") as log:
        proc = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=False)
    return proc.returncode


def read_run_log(run_dir: str | Path) -> str:
    """Return the captured run.log text for a run, or '' if none was written."""
    log_path = Path(run_dir) / "run.log"
    return log_path.read_text() if log_path.exists() else ""


def read_task_errors(run_dir: str | Path, max_tasks: int = 10, tail_lines: int = 40) -> str:
    """Collect the per-task `.command.err` output from the Nextflow work dirs.

    The main run.log only says which process failed; the real error (a tool's
    stderr, a container/platform warning) lives in the failing task's
    `.command.err`. The detector needs it (ARCHITECTURE §5.2).
    """
    work = Path(run_dir) / "work"
    if not work.is_dir():
        return ""
    chunks: list[str] = []
    for err in sorted(work.glob("**/.command.err"))[:max_tasks]:
        # Only failed/killed tasks: a successful task's stderr is noise that can
        # trigger the wrong diagnosis. exitcode "0" -> skip; non-zero or absent
        # (killed before writing one) -> include.
        exitcode = err.parent / ".exitcode"
        if exitcode.exists() and exitcode.read_text().strip() == "0":
            continue
        text = err.read_text(errors="replace").strip()
        if text:
            tail = "\n".join(text.splitlines()[-tail_lines:])
            chunks.append(f"# {err.parent.name}\n{tail}")
    return "\n".join(chunks)


def build_nextflow_command(
    pipeline: str,
    revision: str,
    profiles: list[str],
    trace_path: str,
    params: dict[str, object] | None = None,
    resume: bool = False,
    config_path: str | None = None,
) -> list[str]:
    """Construct the `nextflow run` argv for a pipeline, with trace capture wired in.

    `config_path`, when given, is injected as the `-c` launcher option (which must
    precede the `run` subcommand) so the generated ExecutionTarget profile selects
    the backend/runtime for this run.
    """
    cmd = ["nextflow"]
    if config_path:
        cmd += ["-c", config_path]
    cmd += [
        "run",
        pipeline,
        "-r",
        revision,
        "-profile",
        ",".join(profiles),
        "-with-trace",
        trace_path,
    ]
    if resume:
        cmd.append("-resume")
    for key, value in (params or {}).items():
        cmd += [f"--{key}", str(value)]
    return cmd


def _build_engine_run(
    target: ExecutionTarget,
    run_dir: Path,
    pipeline: str,
    revision: str,
    profiles: list[str],
    params: dict[str, object] | None,
    resume: bool,
) -> tuple[list[str], Path, Callable[[Path], list[TaskEvent]]]:
    """Build the command, artifact path, and events parser for the target's engine.

    This is the single point where Nextflow and Snakemake diverge. Nextflow gets a
    generated nextflow.config (the compute abstraction: local/cloud/HPC selected by
    the profile) and a trace TSV; Snakemake gets a typed `snakemake` command and a
    stats JSON. Both leave a machine-readable artifact the runner ingests into the
    same TaskEvent shape.
    """
    if target.engine == "snakemake":
        # `pipeline` carries the Snakefile path for the snakemake engine (there is
        # no nf-core pipeline ref). cores ride from the resource_limits cap, else 1.
        artifact_path = run_dir / "stats.json"
        cores = int(_lead_int(target.resource_limits.get("cpus"), 1))
        cmd = build_snakemake_command(
            snakefile=pipeline, cores=cores, run_dir=str(run_dir)
        )
        return cmd, artifact_path, parse_snakemake_stats_file

    # Default engine: Nextflow. Map the ExecutionTarget to a nextflow.config (the
    # compute abstraction: local/cloud/HPC selected by generating the profile, not
    # by branching here), then build the `nextflow run` argv with trace capture.
    artifact_path = run_dir / "trace.txt"
    config_path = run_dir / "nextflow.config"
    config_path.write_text(generate_nextflow_config(target))
    cmd = build_nextflow_command(
        pipeline, revision, profiles, str(artifact_path), params, resume, str(config_path)
    )
    return cmd, artifact_path, parse_trace_file


def _lead_int(value: object, default: int) -> int:
    """Leading integer of a resource literal ('4' or '4.GB' -> 4), else the default."""
    if value is None:
        return default
    text = str(value).strip()
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else default


def run_pipeline(
    *,
    pipeline: str,
    revision: str,
    profiles: list[str],
    target: ExecutionTarget,
    input_paths: list[str | Path],
    runs_dir: str | Path,
    run_id: str,
    executor: Executor = default_executor,
    params: dict[str, object] | None = None,
    nextflow_version: str | None = None,
    resume: bool = False,
    assay: str = "rnaseq",
) -> RunRecord:
    """Run a pipeline and capture it into a reproducible, bundled RunRecord.

    Ties the spike together: build the command, execute it (writing a trace),
    ingest the trace into events, assemble the provenance record, and persist a
    portable reproduce-bundle. The result is a run we can prove and re-run.
    """
    run_dir = (Path(runs_dir) / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    # The Engine seam: build the command for the selected engine and name the
    # machine-readable artifact it must leave behind (a Nextflow trace TSV, or a
    # Snakemake stats JSON). Everything downstream (capture, record, verify,
    # bundle) is engine-agnostic, so the engine is swapped only here.
    cmd, artifact_path, parse_events = _build_engine_run(
        target, run_dir, pipeline, revision, profiles, params, resume
    )
    returncode = executor(cmd, artifact_path)

    # Capture whatever the run produced (success OR failure). The failure data
    # (the detect/diagnose input, and the moat) must not be discarded just
    # because the run exited nonzero. Only when no artifact exists is there
    # nothing to record.
    record: RunRecord | None = None
    if artifact_path.exists():
        record = RunRecord(
            run_id=run_id,
            pipeline=pipeline,
            pipeline_revision=revision,
            target=target,
            input_checksums=compute_input_checksums(input_paths),
            parameters=params or {},
            events=parse_events(artifact_path),
            qc_results=_discover_qc(run_dir, assay),
            assay=assay,
            nextflow_version=nextflow_version,
            contig_version=_contig_version(),
        )
        write_bundle(record, run_dir)

    if returncode != 0:
        raise PipelineExecutionError(returncode, record)
    # A clean exit must have produced an artifact (hence a record); guard the
    # contract so a silent None can never escape as a "successful" run.
    assert record is not None, "successful run produced no artifact to capture"
    return record
