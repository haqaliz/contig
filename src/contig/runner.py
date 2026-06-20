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
from contig.models import ExecutionTarget, QCResult, RunRecord
from contig.verification.rule_pack import rule_pack_for
from contig.verification.run_qc import evaluate_run_qc
from contig.verification.structural import evaluate_structural


def _discover_qc(run_dir: Path, assay: str = "rnaseq") -> list[QCResult]:
    """Verify a finished run: MultiQC metric checks (assay-specific rule pack) +
    structural checks on outputs."""
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
    return results

# An executor runs the Nextflow argv and is responsible for the trace file
# existing at trace_path when it returns. The default shells out; tests inject a
# fake that writes a canned trace, so the parse/assemble/bundle path stays real.
Executor = Callable[[list[str], Path], int]


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


def read_run_log(run_dir: str | Path) -> str:
    """Return the captured run.log text for a run, or '' if none was written."""
    log_path = Path(run_dir) / "run.log"
    return log_path.read_text() if log_path.exists() else ""


def build_nextflow_command(
    pipeline: str,
    revision: str,
    profiles: list[str],
    trace_path: str,
    params: dict[str, object] | None = None,
    resume: bool = False,
) -> list[str]:
    """Construct the `nextflow run` argv for a pipeline, with trace capture wired in."""
    cmd = [
        "nextflow",
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
    trace_path = run_dir / "trace.txt"

    cmd = build_nextflow_command(pipeline, revision, profiles, str(trace_path), params, resume)
    returncode = executor(cmd, trace_path)

    # Capture whatever the run produced — success OR failure. The failure data
    # (the detect/diagnose input, and the moat) must not be discarded just
    # because the run exited nonzero. Only when no trace exists is there nothing
    # to record.
    record: RunRecord | None = None
    if trace_path.exists():
        record = RunRecord(
            run_id=run_id,
            pipeline=pipeline,
            pipeline_revision=revision,
            target=target,
            input_checksums=compute_input_checksums(input_paths),
            parameters=params or {},
            events=parse_trace_file(trace_path),
            qc_results=_discover_qc(run_dir, assay),
            nextflow_version=nextflow_version,
            contig_version=_contig_version(),
        )
        write_bundle(record, run_dir)

    if returncode != 0:
        raise PipelineExecutionError(returncode, record)
    # A clean exit must have produced a trace (hence a record); guard the contract
    # so a silent None can never escape as a "successful" run.
    assert record is not None, "successful run produced no trace to capture"
    return record
