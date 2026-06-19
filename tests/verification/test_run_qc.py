from contig.models import ExecutionTarget, RunRecord, TaskEvent
from contig.verification.run_qc import evaluate_run_qc

GOOD_MQC = '{"report_general_stats_data":[{"S1":{"uniquely_mapped_percent":92.0,"percent_assigned":85.0}}]}'
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
