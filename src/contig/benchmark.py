"""Cross-run benchmark: compare a run against a designated reference (PRD contract A).

A run is judged against a designated REFERENCE run for its (pipeline, assay), not
bit-for-bit. We compare each shared numeric QC metric within a RELATIVE tolerance
and add a structural-shape check (the same set of QC check names present), so the
benchmark is robust to the run-to-run non-determinism a real pipeline produces
while still catching a genuine drift in a metric or in the shape of the output.

The reference registry is a committed JSONL, one entry per (pipeline, assay),
carrying the reference run's numeric QC values. It is the accumulated baseline a
researcher trusts: "this run still matches the result we validated".
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path

from pydantic import BaseModel

from contig.models import RunRecord


class ReferenceEntry(BaseModel):
    """One designated reference baseline for a (pipeline, assay).

    `metrics` are the reference run's numeric QC values keyed by check name;
    `recorded_at` is when the baseline was set, for provenance.
    """

    pipeline: str
    assay: str
    reference_run_id: str
    metrics: dict[str, float] = {}
    recorded_at: str


class ReferenceRegistry(BaseModel):
    """The full set of designated references, one per (pipeline, assay)."""

    entries: list[ReferenceEntry] = []


def default_reference_path() -> Path:
    """Path to the committed reference registry shipped with the package."""
    return Path(__file__).parent / "data" / "reference_runs.jsonl"


def load_reference_registry(path: str | PathLike[str]) -> ReferenceRegistry:
    """Read the JSONL registry into a ReferenceRegistry; a missing file is empty."""
    p = Path(path)
    if not p.exists():
        return ReferenceRegistry(entries=[])
    entries = [
        ReferenceEntry.model_validate_json(line)
        for line in p.read_text().splitlines()
        if line.strip()
    ]
    return ReferenceRegistry(entries=entries)


def save_reference_registry(registry: ReferenceRegistry, path: str | PathLike[str]) -> None:
    """Write the registry as JSONL (one ReferenceEntry per line)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(entry.model_dump_json() + "\n" for entry in registry.entries))


def reference_for(
    registry: ReferenceRegistry, pipeline: str, assay: str
) -> ReferenceEntry | None:
    """Return the reference entry for a (pipeline, assay), or None if none is set."""
    for entry in registry.entries:
        if entry.pipeline == pipeline and entry.assay == assay:
            return entry
    return None


def record_reference(
    registry: ReferenceRegistry,
    *,
    pipeline: str,
    assay: str,
    reference_run_id: str,
    metrics: dict[str, float],
    recorded_at: str,
) -> ReferenceRegistry:
    """Return a registry with the reference for (pipeline, assay) set or replaced.

    Deduped by (pipeline, assay): recording a new reference for a pair that
    already has one replaces it, so there is always exactly one baseline per
    pair. The input registry is not mutated.
    """
    new_entry = ReferenceEntry(
        pipeline=pipeline,
        assay=assay,
        reference_run_id=reference_run_id,
        metrics=dict(metrics),
        recorded_at=recorded_at,
    )
    kept = [
        e for e in registry.entries
        if not (e.pipeline == pipeline and e.assay == assay)
    ]
    return ReferenceRegistry(entries=kept + [new_entry])


def metrics_from_run(record: RunRecord) -> dict[str, float]:
    """The run's numeric QC values keyed by check name (the benchmark inputs).

    Only checks that carry a numeric value are kept; a structural check with no
    value cannot be compared on magnitude, so it is excluded from the metrics.
    """
    return {
        result.check: float(result.value)
        for result in record.qc_results
        if result.value is not None
    }


def benchmark_run(
    record: RunRecord,
    registry: ReferenceRegistry,
    *,
    assay: str,
    tolerance: float,
) -> dict:
    """Compare a run's QC metrics against its designated reference (PRD contract A).

    Finds the reference for the run's (pipeline, assay). For each metric the run
    and the reference share, the run value is within tolerance when its relative
    difference from the reference is at most `tolerance` (relative, not absolute).
    A structural-shape mismatch (the run and reference do not carry the same set
    of QC check names) is itself drift, even if every shared value matches.

    Returns the dashboard contract:
    `{reference_run_id, tolerance, matched, drifted, checks, status}` where each
    check is `{name, run_value, reference_value, within_tolerance, delta}` and
    status is "match", "drift", or "no_reference". No reference is not an error:
    status is "no_reference" with a message and no checks.
    """
    entry = reference_for(registry, record.pipeline, assay)
    if entry is None:
        return {
            "reference_run_id": None,
            "tolerance": tolerance,
            "matched": 0,
            "drifted": 0,
            "checks": [],
            "status": "no_reference",
            "message": (
                f"no reference set for pipeline {record.pipeline!r} / assay {assay!r}"
            ),
        }

    run_metrics = metrics_from_run(record)
    shared = sorted(set(run_metrics) & set(entry.metrics))
    same_shape = set(run_metrics) == set(entry.metrics)

    checks: list[dict] = []
    matched = 0
    drifted = 0
    for name in shared:
        run_value = run_metrics[name]
        reference_value = entry.metrics[name]
        delta = _relative_delta(run_value, reference_value)
        within = delta <= tolerance
        if within:
            matched += 1
        else:
            drifted += 1
        checks.append(
            {
                "name": name,
                "run_value": run_value,
                "reference_value": reference_value,
                "within_tolerance": within,
                "delta": delta,
            }
        )

    # A value drift OR a shape mismatch is drift; only all values within
    # tolerance AND the same shape counts as a match.
    status = "match" if drifted == 0 and same_shape else "drift"
    return {
        "reference_run_id": entry.reference_run_id,
        "tolerance": tolerance,
        "matched": matched,
        "drifted": drifted,
        "checks": checks,
        "status": status,
    }


def _relative_delta(run_value: float, reference_value: float) -> float:
    """Relative difference of run from reference: |run - ref| / |ref|.

    A zero reference falls back to the absolute difference (there is no relative
    scale to divide by), so an exact zero-vs-zero is a delta of 0 and any nonzero
    run against a zero reference is the run's own magnitude.
    """
    if reference_value == 0:
        return abs(run_value)
    return abs(run_value - reference_value) / abs(reference_value)
