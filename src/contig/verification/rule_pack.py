"""RNA-seq QC rule pack + evaluator (ARCHITECTURE §6).

A rule pack is *data, not code*: a versioned, auditable list of checks the
verifier applies to ingested metrics. Keeping it declarative means a pack can be
diffed, pinned into a RunRecord, and tuned without code changes.

The thresholds below are illustrative, tunable engineering defaults for catching
gross run failures (e.g. a sample that barely aligned) -- they are not clinical
or biological claims.
"""

from __future__ import annotations

from contig.models import QCResult

RNASEQ_RULE_PACK: list[dict] = [
    {
        "check": "alignment_rate",
        "metric": "uniquely_mapped_percent",
        "warn_below": 60.0,
        "fail_below": 40.0,
        "message": "fraction of reads uniquely mapped to the reference",
    },
    {
        "check": "assignment_rate",
        "metric": "percent_assigned",
        "warn_below": 60.0,
        "fail_below": 40.0,
        "message": "fraction of reads assigned to features",
    },
]


def evaluate(
    metrics: dict[str, dict[str, float]], rule_pack: list[dict]
) -> list[QCResult]:
    results: list[QCResult] = []
    for sample, sample_metrics in metrics.items():
        for check in rule_pack:
            if check["metric"] not in sample_metrics:
                continue
            value = sample_metrics[check["metric"]]
            if value < check["fail_below"]:
                status = "fail"
            elif value < check["warn_below"]:
                status = "warn"
            else:
                status = "pass"
            results.append(
                QCResult(
                    check=f"{check['check']}:{sample}",
                    status=status,
                    message=f"{sample}: {check['metric']}={value} ({status})",
                    value=value,
                    expected_range=f">= {check['warn_below']}",
                )
            )
    return results
