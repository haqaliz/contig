import pytest
from pydantic import ValidationError

from contig.models import (
    ExecutionTarget,
    QCResult,
    RunRecord,
    RunSummary,
    TaskEvent,
    overall_verdict,
    sha256_file,
)


def _qc(status):
    return QCResult(check="alignment_rate", status=status, message="x")


def test_execution_target_defaults_engine_to_nextflow():
    target = ExecutionTarget(backend="local", container_runtime="docker", work_dir="/tmp/run")
    assert target.engine == "nextflow"


def test_execution_target_rejects_unknown_backend():
    with pytest.raises(ValidationError):
        ExecutionTarget(backend="mainframe", container_runtime="docker", work_dir="/tmp/run")


def test_overall_verdict_fail_dominates_warn_and_pass():
    assert overall_verdict([_qc("pass"), _qc("warn"), _qc("fail")]) == "fail"


def test_overall_verdict_warn_when_no_fail_present():
    assert overall_verdict([_qc("pass"), _qc("warn"), _qc("pass")]) == "warn"


def test_overall_verdict_pass_when_all_pass():
    assert overall_verdict([_qc("pass"), _qc("pass")]) == "pass"


def test_overall_verdict_rejects_empty_list_to_prevent_false_pass():
    with pytest.raises(ValueError):
        overall_verdict([])


def test_task_event_is_failure_on_failed_status():
    assert TaskEvent(process="STAR_ALIGN", status="FAILED").is_failure is True


def test_task_event_is_failure_on_nonzero_exit():
    assert TaskEvent(process="STAR_ALIGN", status="COMPLETED", exit=137).is_failure is True


def test_task_event_not_failure_when_completed_exit_zero():
    assert TaskEvent(process="STAR_ALIGN", status="COMPLETED", exit=0).is_failure is False


def test_run_summary_from_events_counts_and_flags_failure():
    events = [
        TaskEvent(process="FASTQC", status="COMPLETED", exit=0),
        TaskEvent(process="STAR_ALIGN", status="FAILED", exit=137),
    ]
    summary = RunSummary.from_events(events)
    assert summary.total_tasks == 2
    assert summary.failed_tasks == 1
    assert summary.succeeded is False


def test_run_summary_from_events_succeeds_when_all_pass():
    events = [TaskEvent(process="FASTQC", status="COMPLETED", exit=0)]
    assert RunSummary.from_events(events).succeeded is True


def test_sha256_file_matches_known_digest(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_bytes(b"hello")
    assert sha256_file(f) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def _minimal_record(qc_results, events=None):
    return RunRecord(
        run_id="run-001",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.14.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="/tmp/run"),
        input_checksums={"reads_R1.fastq.gz": "abc123"},
        parameters={"aligner": "star_salmon"},
        qc_results=qc_results,
        events=events or [],
    )


_OK_TASK = TaskEvent(process="FASTQC", status="COMPLETED", exit=0)
_BAD_TASK = TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)


def test_run_record_verdict_is_fail_when_any_qc_fails():
    record = _minimal_record([_qc("pass"), _qc("fail")], events=[_OK_TASK])
    assert record.verdict == "fail"


def test_run_record_verdict_is_pass_when_run_ok_and_all_qc_pass():
    record = _minimal_record([_qc("pass"), _qc("pass")], events=[_OK_TASK])
    assert record.verdict == "pass"


def test_run_record_verdict_is_fail_when_a_task_failed_even_if_qc_passes():
    record = _minimal_record([_qc("pass")], events=[_OK_TASK, _BAD_TASK])
    assert record.verdict == "fail"


def test_run_record_verdict_is_unverified_when_run_ok_but_no_qc():
    record = _minimal_record([], events=[_OK_TASK])
    assert record.verdict == "unverified"


def test_run_record_verdict_is_warn_when_run_ok_and_qc_warns():
    record = _minimal_record([_qc("pass"), _qc("warn")], events=[_OK_TASK])
    assert record.verdict == "warn"


def test_diagnosis_rejects_confidence_above_one():
    from contig.models import Diagnosis

    with pytest.raises(ValidationError):
        Diagnosis(failure_class="oom", root_cause="x", evidence=["e"], confidence=1.5)


def test_patch_rejects_unknown_kind():
    from contig.models import Patch

    with pytest.raises(ValidationError):
        Patch(kind="teleport", operation={}, rationale="x", risk="safe", expected_signal="y")


def test_repair_step_composes_diagnosis_and_patch():
    from contig.models import Diagnosis, Patch, RepairStep

    step = RepairStep(
        attempt=1,
        diagnosis=Diagnosis(failure_class="oom", root_cause="OOM", evidence=["exit 137"], confidence=0.9),
        patch=Patch(
            kind="resource",
            operation={"set": {"memory": "8.GB"}},
            rationale="bump memory",
            risk="safe",
            expected_signal="no OOM",
        ),
        outcome="patched_and_retried",
    )
    assert step.diagnosis.failure_class == "oom"
    assert step.patch.risk == "safe"


def test_run_record_repair_history_defaults_empty_and_accepts_steps():
    from contig.models import RepairStep

    rec = _minimal_record([], events=[_OK_TASK])
    assert rec.repair_history == []
    step = RepairStep(
        attempt=1,
        diagnosis=__import__("contig.models", fromlist=["Diagnosis"]).Diagnosis(
            failure_class="unknown", root_cause="?", evidence=[], confidence=0.1
        ),
        patch=None,
        outcome="gave_up",
    )
    rec2 = _minimal_record([], events=[_OK_TASK])
    rec2.repair_history.append(step)
    assert rec2.repair_history[0].outcome == "gave_up"
