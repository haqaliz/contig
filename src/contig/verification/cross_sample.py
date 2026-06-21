"""Cross-sample QC consistency checks (ARCHITECTURE §6.4).

Single-sample rule packs catch a sample that barely aligned; these checks catch
problems only visible *across* samples in a run: a library that sequenced far
deeper than its peers, a run with too few samples to trust, an outlier whose
metric is wildly off the cohort. Inputs are the ingested metric table
`{sample: {metric: value}}` (the output of MultiQC ingestion).

The thresholds below are illustrative, tunable engineering defaults -- they are
not clinical or biological claims.
"""

from __future__ import annotations

import re

from contig.models import QCResult

_FASTQC_READ_SUFFIX = re.compile(r"\s+Read\s+\d+$", re.IGNORECASE)


def _biological_samples(metrics: dict[str, dict[str, float]]) -> set[str]:
    """Distinct biological samples, collapsing FastQC per-read rows ('S Read 1' -> 'S')."""
    return {_FASTQC_READ_SUFFIX.sub("", s) for s in metrics}


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def check_library_size_skew(
    metrics: dict[str, dict[str, float]],
    metric: str = "total_reads",
    warn_ratio: float = 3.0,
    fail_ratio: float = 10.0,
) -> QCResult | None:
    values = [m[metric] for m in metrics.values() if metric in m]
    if len(values) < 2:
        return None
    ratio = max(values) / min(values)
    if ratio >= fail_ratio:
        status = "fail"
    elif ratio >= warn_ratio:
        status = "warn"
    else:
        status = "pass"
    return QCResult(
        check=f"library_size_skew:{metric}",
        status=status,
        message=f"{metric} max/min ratio across samples = {ratio} ({status})",
        value=ratio,
        expected_range=f"< {warn_ratio}",
    )


def check_min_sample_count(
    metrics: dict[str, dict[str, float]],
    min_samples: int = 2,
) -> QCResult:
    count = len(_biological_samples(metrics))
    status = "fail" if count < min_samples else "pass"
    return QCResult(
        check="min_sample_count",
        status=status,
        message=f"{count} sample(s) present ({status})",
        value=float(count),
        expected_range=f">= {min_samples}",
    )


def check_metric_outliers(
    metrics: dict[str, dict[str, float]],
    metric: str,
    mad_threshold: float = 3.0,
) -> list[QCResult]:
    samples = {s: m[metric] for s, m in metrics.items() if metric in m}
    if len(samples) < 3:
        return []
    values = list(samples.values())
    median = _median(values)
    mad = _median([abs(v - median) for v in values])
    if mad == 0:
        return []
    results: list[QCResult] = []
    for sample, value in samples.items():
        deviation = abs(value - median) / mad
        if deviation > mad_threshold:
            results.append(
                QCResult(
                    check=f"outlier:{metric}:{sample}",
                    status="warn",
                    message=(
                        f"{sample}: {metric}={value} is {deviation:.1f} MADs "
                        f"from the cohort median {median} (warn)"
                    ),
                    value=value,
                    expected_range=f"within {mad_threshold} MAD of {median}",
                )
            )
    return results


def evaluate_cross_sample(
    metrics: dict[str, dict[str, float]],
    size_metric: str = "total_reads",
    min_samples: int = 2,
) -> list[QCResult]:
    results: list[QCResult] = [check_min_sample_count(metrics, min_samples)]
    skew = check_library_size_skew(metrics, metric=size_metric)
    if skew is not None:
        results.append(skew)
    results.extend(check_metric_outliers(metrics, metric=size_metric))
    return results
