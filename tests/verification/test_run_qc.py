from contig.models import ExecutionTarget, RunRecord, TaskEvent
from contig.verification.run_qc import evaluate_run_qc, run_qc
from contig.verification.structural import ExpectedOutputs

GOOD_MQC = (
    '{"report_general_stats_data":[{'
    '"S1":{"uniquely_mapped_percent":92.0,"percent_assigned":85.0,"total_reads":1000000.0},'
    '"S2":{"uniquely_mapped_percent":90.0,"percent_assigned":84.0,"total_reads":1100000.0}}]}'
)
BAD_MQC = '{"report_general_stats_data":[{"S2":{"uniquely_mapped_percent":30.0}}]}'


def test_evaluate_run_qc_passes_good_metrics(tmp_path):
    f = tmp_path / "multiqc_data.json"
    f.write_text(GOOD_MQC)
    results = evaluate_run_qc(f)
    assert results
    assert all(r.status == "pass" for r in results)


def test_evaluate_run_qc_flags_low_alignment(tmp_path):
    f = tmp_path / "multiqc_data.json"
    f.write_text(BAD_MQC)
    results = evaluate_run_qc(f)
    assert any(r.status == "fail" for r in results)


def test_evaluate_run_qc_uses_default_rnaseq_pack(tmp_path):
    f = tmp_path / "multiqc_data.json"
    f.write_text(GOOD_MQC)
    results = evaluate_run_qc(f)
    assert any(r.check.startswith("alignment_rate") for r in results)


TWO_SAMPLE_MQC = (
    '{"report_general_stats_data":[{'
    '"S1":{"uniquely_mapped_percent":90.0,"percent_assigned":85.0,"total_reads":1000000.0},'
    '"S2":{"uniquely_mapped_percent":91.0,"percent_assigned":86.0,"total_reads":1050000.0}}]}'
)


def test_evaluate_run_qc_returns_empty_for_no_metrics(tmp_path):
    # MultiQC present but with no general-stats samples -> no QC ran -> unverified,
    # NOT a spurious min_sample_count fail.
    f = tmp_path / "multiqc_data.json"
    f.write_text('{"report_general_stats_data": []}')
    assert evaluate_run_qc(f) == []


def test_evaluate_run_qc_includes_cross_sample_checks(tmp_path):
    f = tmp_path / "multiqc_data.json"
    f.write_text(TWO_SAMPLE_MQC)
    results = evaluate_run_qc(f)
    checks = [r.check for r in results]
    assert any(c.startswith("min_sample_count") for c in checks)
    assert any(c.startswith("library_size_skew") for c in checks)


def test_run_qc_combines_metric_and_structural_results(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "multiqc_data.json").write_text(GOOD_MQC)
    results_dir = run_dir / "results"
    results_dir.mkdir()
    (results_dir / "sample.bam").write_bytes(b"aligned reads")

    manifest = ExpectedOutputs(required=["*.bam"])
    results = run_qc(run_dir, results_dir=results_dir, manifest=manifest)

    assert any(r.kind == "metric" for r in results)
    assert any(r.kind == "structural" for r in results)
    assert all(r.status == "pass" for r in results)


def test_run_qc_fails_verdict_on_missing_required_output(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "multiqc_data.json").write_text(GOOD_MQC)
    results_dir = run_dir / "results"
    results_dir.mkdir()  # required bam never produced

    manifest = ExpectedOutputs(required=["*.bam"])
    results = run_qc(run_dir, results_dir=results_dir, manifest=manifest)

    record = RunRecord(
        run_id="r",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        qc_results=results,
    )
    assert record.verdict == "fail"


def test_successful_run_with_good_qc_reads_pass(tmp_path):
    # the full loop: a completed run + passing QC attached -> verdict "pass"
    f = tmp_path / "multiqc_data.json"
    f.write_text(GOOD_MQC)
    record = RunRecord(
        run_id="r",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        qc_results=evaluate_run_qc(f),
    )
    assert record.verdict == "pass"
