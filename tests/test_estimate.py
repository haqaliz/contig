"""Tests for the pre-run estimate (PRD contract B).

`estimate_run` projects what a run will cost before it launches: data-driven from
prior FINISHED runs of the same pipeline (their recorded resource_usage scaled by
the run's sample count), with a transparent per-sample heuristic when there is no
history. The JSON shape is pinned so the dashboard can render it directly.
"""

from pathlib import Path

import pytest

from contig.bundle import write_bundle
from contig.estimate import EstimateReport, estimate_run
from contig.models import ExecutionTarget, RunRecord, TaskEvent, TaskResource


def _sheet(tmp_path: Path, n: int) -> Path:
    lines = ["sample,fastq_1,fastq_2,strandedness"]
    for i in range(1, n + 1):
        r1 = tmp_path / f"s{i}_R1.fastq.gz"
        r2 = tmp_path / f"s{i}_R2.fastq.gz"
        r1.write_bytes(b"\x1f\x8bR1")
        r2.write_bytes(b"\x1f\x8bR2")
        lines.append(f"S{i},{r1.name},{r2.name},auto")
    sheet = tmp_path / "samplesheet.csv"
    sheet.write_text("\n".join(lines) + "\n")
    return sheet


def _prior_run(
    runs_dir: Path,
    run_id: str,
    *,
    pipeline: str,
    input_sheet: Path | None,
    usage: list[TaskResource],
    succeeded: bool = True,
) -> None:
    status = "COMPLETED" if succeeded else "FAILED"
    exit_code = 0 if succeeded else 1
    params = {}
    if input_sheet is not None:
        params["input"] = str(input_sheet)
    record = RunRecord(
        run_id=run_id,
        pipeline=pipeline,
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        parameters=params,
        events=[TaskEvent(process="STAR", status=status, exit=exit_code)],
        resource_usage=usage,
    )
    write_bundle(record, runs_dir / run_id)


def _task(name: str, realtime_sec: float, peak_rss_mb: float) -> TaskResource:
    return TaskResource(
        process=name, name=name, realtime_sec=realtime_sec,
        peak_rss_mb=peak_rss_mb, pct_cpu=100.0,
    )


def test_no_history_falls_back_to_heuristic(tmp_path):
    report = estimate_run("nf-core/rnaseq", n_samples=3, runs_dir=tmp_path)
    assert report.basis == "heuristic"
    assert report.n_prior_runs == 0
    assert report.est_runtime_sec > 0


def test_history_basis_used_when_a_prior_run_exists(tmp_path):
    sheet = _sheet(tmp_path, 2)
    _prior_run(
        tmp_path, "prior1", pipeline="nf-core/rnaseq", input_sheet=sheet,
        usage=[_task("STAR", 200.0, 1000.0), _task("FASTQC", 100.0, 500.0)],
    )
    report = estimate_run("nf-core/rnaseq", n_samples=4, runs_dir=tmp_path)
    assert report.basis == "history"
    assert report.n_prior_runs == 1


def test_history_scales_runtime_per_sample(tmp_path):
    # 2 samples, total realtime 300s -> 150s/sample; estimating 4 samples -> 600s.
    sheet = _sheet(tmp_path, 2)
    _prior_run(
        tmp_path, "prior1", pipeline="nf-core/rnaseq", input_sheet=sheet,
        usage=[_task("STAR", 200.0, 0.0), _task("FASTQC", 100.0, 0.0)],
    )
    report = estimate_run("nf-core/rnaseq", n_samples=4, runs_dir=tmp_path)
    assert report.est_runtime_sec == pytest.approx(600.0)


def test_history_carries_peak_mem_from_the_heaviest_task(tmp_path):
    sheet = _sheet(tmp_path, 2)
    _prior_run(
        tmp_path, "prior1", pipeline="nf-core/rnaseq", input_sheet=sheet,
        usage=[_task("STAR", 200.0, 4000.0), _task("FASTQC", 100.0, 500.0)],
    )
    report = estimate_run("nf-core/rnaseq", n_samples=2, runs_dir=tmp_path)
    assert report.est_peak_mem_mb == pytest.approx(4000.0)


def test_only_same_pipeline_history_is_used(tmp_path):
    sheet = _sheet(tmp_path, 2)
    _prior_run(
        tmp_path, "other", pipeline="nf-core/sarek", input_sheet=sheet,
        usage=[_task("HAPLOTYPECALLER", 999.0, 9000.0)],
    )
    report = estimate_run("nf-core/rnaseq", n_samples=2, runs_dir=tmp_path)
    assert report.basis == "heuristic"
    assert report.n_prior_runs == 0


def test_failed_prior_runs_are_excluded_from_history(tmp_path):
    sheet = _sheet(tmp_path, 2)
    _prior_run(
        tmp_path, "broken", pipeline="nf-core/rnaseq", input_sheet=sheet,
        usage=[_task("STAR", 200.0, 1000.0)], succeeded=False,
    )
    report = estimate_run("nf-core/rnaseq", n_samples=2, runs_dir=tmp_path)
    assert report.basis == "heuristic"
    assert report.n_prior_runs == 0


def test_cost_is_priced_from_the_estimated_cpu_hours(tmp_path):
    # 2 samples, 3600s total realtime -> 1 cpu-hour/run, 1800s/sample; at 4
    # samples that is 2 cpu-hours; at 1.0/cpu-hour the cost is 2.0.
    sheet = _sheet(tmp_path, 2)
    _prior_run(
        tmp_path, "prior1", pipeline="nf-core/rnaseq", input_sheet=sheet,
        usage=[_task("STAR", 3600.0, 0.0)],
    )
    report = estimate_run(
        "nf-core/rnaseq", n_samples=4, runs_dir=tmp_path, rate_cpu_hour=1.0,
    )
    assert report.est_total_cpu_hours == pytest.approx(2.0)
    assert report.est_cost == pytest.approx(2.0)


def test_zero_rates_yield_zero_cost(tmp_path):
    report = estimate_run("nf-core/rnaseq", n_samples=3, runs_dir=tmp_path)
    assert report.est_cost == 0.0
    assert report.currency == "USD"


def test_currency_label_is_echoed(tmp_path):
    report = estimate_run("nf-core/rnaseq", n_samples=3, runs_dir=tmp_path, currency="EUR")
    assert report.currency == "EUR"


def test_n_samples_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        estimate_run("nf-core/rnaseq", n_samples=0, runs_dir=tmp_path)


def test_json_shape_is_pinned(tmp_path):
    report = estimate_run("nf-core/rnaseq", n_samples=3, runs_dir=tmp_path)
    data = report.model_dump()
    assert set(data) == {
        "basis", "pipeline", "n_samples", "n_prior_runs", "est_runtime_sec",
        "est_peak_mem_mb", "est_total_cpu_hours", "est_cost", "currency",
        "rate_cpu_hour", "rate_mem_gb_hour", "note",
    }
    assert data["basis"] == "heuristic"
    assert data["pipeline"] == "nf-core/rnaseq"
    assert data["n_samples"] == 3


def test_prior_run_without_a_reachable_sheet_is_not_history(tmp_path):
    # A prior run whose recorded sheet has moved cannot yield a per-sample figure.
    _prior_run(
        tmp_path, "prior1", pipeline="nf-core/rnaseq",
        input_sheet=tmp_path / "gone.csv",
        usage=[_task("STAR", 200.0, 1000.0)],
    )
    report = estimate_run("nf-core/rnaseq", n_samples=2, runs_dir=tmp_path)
    assert report.basis == "heuristic"
    assert report.n_prior_runs == 0
