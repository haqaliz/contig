"""Tie MultiQC ingestion to the rule pack: a run's metrics -> typed QC verdicts.

This is the seam the orchestrator calls to turn a finished run's MultiQC output
into the `qc_results` that drive `RunRecord.verdict` (ARCHITECTURE §6).
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path

from contig.models import QCResult
from contig.verification.cross_sample import evaluate_cross_sample
from contig.verification.qc_ingest import parse_multiqc_general_stats_file
from contig.verification.rule_pack import RNASEQ_RULE_PACK, evaluate
from contig.verification.structural import ExpectedOutputs, evaluate_against_manifest


def evaluate_run_qc(
    multiqc_json_path: str | PathLike[str],
    rule_pack: list[dict] = RNASEQ_RULE_PACK,
    cross_sample: bool = True,
) -> list[QCResult]:
    """Evaluate a run's MultiQC metrics: per-sample rule pack + cross-sample checks.

    `cross_sample` runs the replicate/library-size checks, which are RNA-seq-DE
    assumptions (a single-sample germline variant run, say, is valid and must not
    be failed for "needing replicates"). Callers disable it for assays where it
    doesn't apply.
    """
    metrics = parse_multiqc_general_stats_file(multiqc_json_path)
    if not metrics:
        return []  # no samples to verify -> caller reports "unverified", not "fail"
    results = evaluate(metrics, rule_pack)
    if cross_sample:
        results.extend(evaluate_cross_sample(metrics))
    return results


def run_qc(
    run_dir: str | PathLike[str],
    results_dir: str | PathLike[str] | None = None,
    manifest: ExpectedOutputs | None = None,
    rule_pack: list[dict] = RNASEQ_RULE_PACK,
    cross_sample: bool = True,
) -> list[QCResult]:
    """Verify a finished run: MultiQC metric checks plus manifest structural checks.

    Discovers the run's MultiQC report under `run_dir` and runs the metric rule
    pack over it, then applies the per-assay output `manifest` to the run's
    `results_dir` (defaulting to `run_dir/results`). The combined list lands in
    `RunRecord.qc_results`, where a structural fail (a missing/empty required
    output or a corrupt file) drives the computed verdict to FAIL exactly like a
    metric fail. With no MultiQC and no manifest, an empty list means the caller
    honestly reports "unverified".
    """
    run_path = Path(run_dir)
    results: list[QCResult] = []

    multiqc = next(run_path.rglob("multiqc_data.json"), None)
    if multiqc is not None:
        results.extend(
            evaluate_run_qc(multiqc, rule_pack=rule_pack, cross_sample=cross_sample)
        )

    if manifest is not None:
        outputs = Path(results_dir) if results_dir is not None else run_path / "results"
        results.extend(evaluate_against_manifest(outputs, manifest))

    return results
