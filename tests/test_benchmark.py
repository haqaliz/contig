"""Tests for the cross-run benchmark (PRD contract A).

A run is compared against a designated reference for its (pipeline, assay) by QC
metric values within a relative tolerance plus a structural shape check (the same
QC check names present), so the benchmark is robust to run-to-run
non-determinism instead of demanding bit-for-bit equality.
"""

import pytest

from contig.benchmark import (
    ReferenceRegistry,
    benchmark_run,
    load_reference_registry,
    record_reference,
    reference_for,
    save_reference_registry,
)
from contig.models import ExecutionTarget, QCResult, RunRecord, TaskEvent


def _record(run_id, pipeline, qc):
    return RunRecord(
        run_id=run_id,
        pipeline=pipeline,
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        qc_results=qc,
    )


def _qc(check, value, status="pass"):
    return QCResult(check=check, status=status, message="ok", value=value)


def test_registry_round_trips_through_jsonl(tmp_path):
    path = tmp_path / "ref.jsonl"
    registry = ReferenceRegistry(entries=[])
    registry = record_reference(
        registry,
        pipeline="nf-core/rnaseq",
        assay="rnaseq",
        reference_run_id="run-a",
        metrics={"mapping_rate": 92.0},
        recorded_at="2026-06-20T00:00:00Z",
    )
    save_reference_registry(registry, path)
    loaded = load_reference_registry(path)
    assert loaded == registry


def test_load_missing_registry_is_empty(tmp_path):
    loaded = load_reference_registry(tmp_path / "absent.jsonl")
    assert loaded.entries == []


def test_record_reference_dedupes_by_pipeline_and_assay(tmp_path):
    registry = ReferenceRegistry(entries=[])
    registry = record_reference(
        registry,
        pipeline="nf-core/rnaseq",
        assay="rnaseq",
        reference_run_id="run-old",
        metrics={"mapping_rate": 90.0},
        recorded_at="2026-06-19T00:00:00Z",
    )
    registry = record_reference(
        registry,
        pipeline="nf-core/rnaseq",
        assay="rnaseq",
        reference_run_id="run-new",
        metrics={"mapping_rate": 93.0},
        recorded_at="2026-06-20T00:00:00Z",
    )
    assert len(registry.entries) == 1
    entry = reference_for(registry, "nf-core/rnaseq", "rnaseq")
    assert entry.reference_run_id == "run-new"
    assert entry.metrics == {"mapping_rate": 93.0}


def test_record_reference_keeps_distinct_pipelines(tmp_path):
    registry = ReferenceRegistry(entries=[])
    registry = record_reference(
        registry, pipeline="nf-core/rnaseq", assay="rnaseq",
        reference_run_id="run-a", metrics={"m": 1.0}, recorded_at="t",
    )
    registry = record_reference(
        registry, pipeline="nf-core/sarek", assay="variant_calling",
        reference_run_id="run-b", metrics={"m": 2.0}, recorded_at="t",
    )
    assert len(registry.entries) == 2


def test_reference_for_returns_none_when_absent():
    registry = ReferenceRegistry(entries=[])
    assert reference_for(registry, "nf-core/rnaseq", "rnaseq") is None


def test_benchmark_reports_match_within_tolerance():
    registry = record_reference(
        ReferenceRegistry(entries=[]),
        pipeline="nf-core/rnaseq", assay="rnaseq", reference_run_id="run-ref",
        metrics={"mapping_rate": 90.0}, recorded_at="t",
    )
    run = _record("run-now", "nf-core/rnaseq", [_qc("mapping_rate", 94.0)])
    result = benchmark_run(run, registry, assay="rnaseq", tolerance=0.1)
    assert result["status"] == "match"
    assert result["reference_run_id"] == "run-ref"
    assert result["matched"] == 1
    assert result["drifted"] == 0
    check = result["checks"][0]
    assert check["name"] == "mapping_rate"
    assert check["run_value"] == 94.0
    assert check["reference_value"] == 90.0
    assert check["within_tolerance"] is True


def test_benchmark_reports_drift_outside_tolerance():
    registry = record_reference(
        ReferenceRegistry(entries=[]),
        pipeline="nf-core/rnaseq", assay="rnaseq", reference_run_id="run-ref",
        metrics={"mapping_rate": 90.0}, recorded_at="t",
    )
    run = _record("run-now", "nf-core/rnaseq", [_qc("mapping_rate", 50.0)])
    result = benchmark_run(run, registry, assay="rnaseq", tolerance=0.1)
    assert result["status"] == "drift"
    assert result["drifted"] == 1
    assert result["checks"][0]["within_tolerance"] is False


def test_benchmark_delta_is_relative_difference():
    registry = record_reference(
        ReferenceRegistry(entries=[]),
        pipeline="nf-core/rnaseq", assay="rnaseq", reference_run_id="run-ref",
        metrics={"mapping_rate": 100.0}, recorded_at="t",
    )
    run = _record("run-now", "nf-core/rnaseq", [_qc("mapping_rate", 110.0)])
    result = benchmark_run(run, registry, assay="rnaseq", tolerance=0.2)
    assert result["checks"][0]["delta"] == pytest.approx(0.1)


def test_benchmark_missing_check_name_is_drift_structural_shape():
    # The reference has two metrics; the run only carries one, so the shapes
    # differ. A missing shared check name is structural drift, not a match.
    registry = record_reference(
        ReferenceRegistry(entries=[]),
        pipeline="nf-core/rnaseq", assay="rnaseq", reference_run_id="run-ref",
        metrics={"mapping_rate": 90.0, "duplication": 10.0}, recorded_at="t",
    )
    run = _record("run-now", "nf-core/rnaseq", [_qc("mapping_rate", 91.0)])
    result = benchmark_run(run, registry, assay="rnaseq", tolerance=0.1)
    assert result["status"] == "drift"


def test_benchmark_no_reference_is_status_no_reference_not_an_error():
    registry = ReferenceRegistry(entries=[])
    run = _record("run-now", "nf-core/rnaseq", [_qc("mapping_rate", 91.0)])
    result = benchmark_run(run, registry, assay="rnaseq", tolerance=0.1)
    assert result["status"] == "no_reference"
    assert result["reference_run_id"] is None
    assert result["checks"] == []
    assert "message" in result


def test_benchmark_only_compares_shared_numeric_checks():
    # A reference metric the run does not carry contributes to structural drift,
    # but a run-only metric is ignored for the value comparison.
    registry = record_reference(
        ReferenceRegistry(entries=[]),
        pipeline="nf-core/rnaseq", assay="rnaseq", reference_run_id="run-ref",
        metrics={"mapping_rate": 90.0}, recorded_at="t",
    )
    run = _record(
        "run-now", "nf-core/rnaseq",
        [_qc("mapping_rate", 91.0), _qc("extra_metric", 5.0)],
    )
    result = benchmark_run(run, registry, assay="rnaseq", tolerance=0.1)
    # the extra run-only metric makes the shapes differ, so this is drift
    assert result["status"] == "drift"
    names = {c["name"] for c in result["checks"]}
    assert "mapping_rate" in names


def test_metrics_from_run_keeps_only_numeric_qc_values():
    from contig.benchmark import metrics_from_run

    run = _record(
        "run-now", "nf-core/rnaseq",
        [_qc("mapping_rate", 91.0), QCResult(check="files_present", status="pass", message="ok", value=None)],
    )
    metrics = metrics_from_run(run)
    assert metrics == {"mapping_rate": 91.0}
