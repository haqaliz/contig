"""Tie MultiQC ingestion to the rule pack: a run's metrics -> typed QC verdicts.

This is the seam the orchestrator calls to turn a finished run's MultiQC output
into the `qc_results` that drive `RunRecord.verdict` (ARCHITECTURE §6).
"""

from __future__ import annotations

from os import PathLike

from contig.models import QCResult
from contig.verification.qc_ingest import parse_multiqc_general_stats_file
from contig.verification.rule_pack import RNASEQ_RULE_PACK, evaluate


def evaluate_run_qc(
    multiqc_json_path: str | PathLike[str],
    rule_pack: list[dict] = RNASEQ_RULE_PACK,
) -> list[QCResult]:
    """Ingest a run's MultiQC general stats and evaluate them against a rule pack."""
    metrics = parse_multiqc_general_stats_file(multiqc_json_path)
    return evaluate(metrics, rule_pack)
