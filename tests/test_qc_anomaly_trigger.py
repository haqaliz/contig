"""The qc_anomaly trigger: a green run whose QC reduces to FAIL is diagnosed.

`self_heal_run` only ever diagnosed a non-zero exit, so a run with every task
green and a FAIL verdict returned undiagnosed. These tests pin the trigger's
three conditions (events succeeded, QC present, verdict fail) and the shape of
the step it records.
"""

import gzip
import json
from pathlib import Path

import pytest

from contig.models import ExecutionTarget, QCResult, RunRecord, RunSummary, TaskEvent
from contig.self_heal import QC_VERDICT_FLAGGED_OUTCOME, self_heal_run


def _trace(status, exit_code):
    return (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        f"1\tab/cd\t1\tNFCORE_SAREK:HAPLOTYPECALLER (S1)\t{status}\t{exit_code}\t-\t-\t-\n"
    )


TRACE_OK = _trace("COMPLETED", 0)
TRACE_FAILED = _trace("FAILED", 1)
TRACE_OOM = _trace("FAILED", 137)


def _write_empty_vcf(run_dir):
    """The proven minimal FAIL fixture: a header-only germline VCF.

    `parse_vcf` reads a `.gz` name with stdlib gzip, so this yields zero sites,
    `variant_count=0`, and VARIANT_RULE_PACK's `fail_below: 1` makes that a FAIL
    by design. No mocking anywhere: the real `_discover_qc` produces the verdict.
    """
    with gzip.open(Path(run_dir) / "calls.vcf.gz", "wt") as fh:
        fh.write("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")


def _write(trace_path, trace_text, log_text, *, empty_vcf=False):
    Path(trace_path).write_text(trace_text)
    (Path(trace_path).parent / "run.log").write_text(log_text)
    if empty_vcf:
        _write_empty_vcf(Path(trace_path).parent)


def _target(d):
    return ExecutionTarget(backend="local", container_runtime="docker", work_dir=str(d))


def _heal(tmp_path, executor, **over):
    kwargs = dict(
        pipeline="nf-core/sarek",
        revision="3.5.1",
        profiles=["test", "docker"],
        target=_target(tmp_path / "w"),
        input_paths=[],
        runs_dir=tmp_path / "runs",
        run_id="r",
        executor=executor,
        assay="variant_calling",
        max_attempts=3,
    )
    kwargs.update(over)
    return self_heal_run(**kwargs)


def _green_qc_fail_executor(trace=TRACE_OK):
    """An executor whose run exits 0 and leaves a call set that FAILs QC."""

    def executor(cmd, trace_path):
        _write(trace_path, trace, "ok", empty_vcf=True)
        return 0

    return executor


def _heal_over_record(monkeypatch, tmp_path, *, events, qc_results):
    """Drive the loop over a run whose QC results are stated outright.

    The trigger is a pure function of the record run_pipeline returns, and some
    of the shapes it must survive cannot be produced by the real rule packs at
    all: an `informational` check is band-less by construction, so it can never
    carry a FAIL, and a non-empty all-`unverified` result set is unreachable for
    a germline run (variant_count is always computable). Stating the record here
    tests the predicate directly; the real `_discover_qc` path is exercised by
    the tests above and by the frozen heal scenario.
    """

    def fake_run_pipeline(**kwargs):
        return RunRecord(
            run_id=kwargs["run_id"],
            pipeline=kwargs["pipeline"],
            pipeline_revision=kwargs["revision"],
            target=kwargs["target"],
            input_checksums={},
            events=events,
            qc_results=qc_results,
            assay=kwargs.get("assay"),
        )

    monkeypatch.setattr("contig.self_heal.run_pipeline", fake_run_pipeline)
    return _heal(tmp_path, lambda cmd, trace_path: 0)


GREEN_EVENT = TaskEvent(
    process="NFCORE_SAREK:HAPLOTYPECALLER (S1)", status="COMPLETED", exit=0, task_id="1"
)


def test_green_run_with_fail_verdict_records_one_qc_anomaly_step(tmp_path):
    # A1: every task COMPLETED, the verdict reduces to FAIL -> exactly one
    # diagnosed step, carrying no patch because none can work (R4).
    record = _heal(tmp_path, _green_qc_fail_executor())

    assert RunSummary.from_events(record.events).succeeded is True
    assert record.verdict == "fail"
    assert len(record.repair_history) == 1
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "qc_anomaly"
    assert step.patch is None
    assert step.outcome == QC_VERDICT_FLAGGED_OUTCOME


def test_failed_task_event_with_exit_zero_is_not_a_qc_anomaly(tmp_path):
    # A2: the events guard is load-bearing. RunRecord.verdict is already "fail"
    # for a FAILED task event, before QC is consulted, so an implementation
    # keying on the verdict alone would file a crash as a QC anomaly.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_FAILED, "task failed", empty_vcf=True)
        return 0  # the launcher exited clean; the TASK is what failed

    record = _heal(tmp_path, executor)

    assert RunSummary.from_events(record.events).succeeded is False
    assert record.verdict == "fail"
    assert [s for s in record.repair_history if s.outcome == QC_VERDICT_FLAGGED_OUTCOME] == []


def test_run_with_no_qc_coverage_is_a_silent_skip(tmp_path):
    # A3: no QC artifact means no check covered the run, which reduces to
    # "unverified" and never to "fail". Nothing to diagnose, and asking
    # overall_verdict for a severity over an empty list is not allowed.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "ok")
        return 0

    record = _heal(tmp_path, executor)

    assert record.qc_results == []
    assert record.verdict == "unverified"
    assert record.repair_history == []


@pytest.mark.parametrize(
    "status, verdict", [("warn", "warn"), ("pass", "pass"), ("unverified", "unverified")]
)
def test_non_fail_verdicts_record_nothing(monkeypatch, tmp_path, status, verdict):
    # A4: only a FAIL verdict is a diagnosable anomaly. WARN is the normal
    # corroboration tier and would otherwise fire constantly.
    record = _heal_over_record(
        monkeypatch,
        tmp_path,
        events=[GREEN_EVENT],
        qc_results=[QCResult(check="ts_tv_ratio:S1", status=status, message="S1: ts_tv")],
    )

    assert record.verdict == verdict
    assert record.repair_history == []


def test_informational_fail_alone_does_not_trigger(monkeypatch, tmp_path):
    # A5: an informational check asserts nothing, whatever its status, so it
    # carries no severity into the verdict. The trigger must ride
    # overall_verdict's existing filter rather than scanning raw statuses --
    # otherwise a verdict-neutral check would file a false anomaly.
    record = _heal_over_record(
        monkeypatch,
        tmp_path,
        events=[GREEN_EVENT],
        qc_results=[
            QCResult(
                check="gene_symbol_concordance",
                status="fail",
                message="symbols disagree; informational only",
                informational=True,
            ),
            QCResult(check="variant_count:S1", status="pass", message="S1: 12 sites"),
        ],
    )

    assert record.verdict == "pass"
    assert record.repair_history == []


def test_evidence_and_detail_name_the_failing_checks(monkeypatch, tmp_path):
    # A12: the step has to answer "which checks, how many, on what assay, and
    # why was nothing tried?" -- R12's field instrument, since the detail line is
    # what makes real firings countable later without new telemetry.
    record = _heal_over_record(
        monkeypatch,
        tmp_path,
        events=[GREEN_EVENT],
        qc_results=[
            QCResult(check="variant_count:S1", status="fail", message="S1: 0 sites"),
            QCResult(check="ts_tv_ratio:S1", status="fail", message="S1: ts_tv=4.1"),
            QCResult(check="het_hom_ratio:S1", status="pass", message="S1: het_hom=1.6"),
            QCResult(
                check="x_het_ratio:S1",
                status="fail",
                message="S1: informational",
                informational=True,
            ),
        ],
    )

    step = record.repair_history[0]
    evidence = " ".join(step.diagnosis.evidence)
    assert "variant_count:S1" in evidence
    assert "ts_tv_ratio:S1" in evidence
    # Only severity-bearing failures are the anomaly; a passing check and a
    # verdict-neutral informational one are not evidence of it.
    assert "het_hom_ratio:S1" not in evidence
    assert "x_het_ratio:S1" not in evidence

    assert "2" in step.diagnosis.root_cause
    detail = step.detail
    assert "QC verdict FAIL on a green run" in detail  # the greppable stem
    assert "variant_count:S1" in detail and "ts_tv_ratio:S1" in detail
    assert "variant_calling" in detail
    assert "cache hit" in detail


def test_finalize_runs_once_and_persists_the_flagged_step(monkeypatch, tmp_path):
    # A9: the trigger records into the SAME repair_history that the existing
    # single _finalize persists -- it must not add a second finalize call site,
    # and it must run before finalize, or the step reaches memory but never the
    # bundle a reader (or the dashboard) actually loads.
    import contig.self_heal as sh

    calls = []
    original = sh._finalize

    def counting_finalize(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(sh, "_finalize", counting_finalize)

    record = _heal(tmp_path, _green_qc_fail_executor())

    assert len(calls) == 1
    persisted = json.loads((tmp_path / "runs" / "r" / "run_record.json").read_text())
    assert [s["outcome"] for s in persisted["repair_history"]] == [QC_VERDICT_FLAGGED_OUTCOME]
    assert record.repair_history[0].outcome == QC_VERDICT_FLAGGED_OUTCOME


def test_trigger_fires_once_on_the_attempt_that_finally_succeeded(tmp_path):
    # A10: a run that OOMs, gets patched, and then comes back green with a FAIL
    # verdict flags that verdict exactly once -- on the attempt that produced it,
    # after the repair step, and without re-entering the loop (there is no retry
    # to make: the trigger falls through to finalize).
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_OOM, "Process killed: out of memory (exit 137)")
            return 1
        _write(trace_path, TRACE_OK, "done", empty_vcf=True)
        return 0

    record = _heal(tmp_path, executor)

    assert state["n"] == 2
    outcomes = [s.outcome for s in record.repair_history]
    assert outcomes == ["patched_and_retried", QC_VERDICT_FLAGGED_OUTCOME]
    flagged = record.repair_history[-1]
    assert flagged.attempt == 2


def test_real_variant_bad_bundle_shape_trips_the_trigger(monkeypatch, tmp_path):
    # A17: the regression fixture is a real bundle, not an invented one. The
    # `runs/variant-bad` sarek record is the single recorded run that trips R1's
    # condition: one COMPLETED/exit-0 task, ts_tv_ratio FAILing among two PASSing
    # checks, and repair_history [] -- the gap this slice closes, sitting on disk.
    record = _heal_over_record(
        monkeypatch,
        tmp_path,
        events=[
            TaskEvent(
                process="NFCORE_SAREK:HAPLOTYPECALLER (S1)",
                status="COMPLETED",
                exit=0,
                task_id="1",
                name="NFCORE_SAREK:HAPLOTYPECALLER (S1)",
            )
        ],
        qc_results=[
            QCResult(
                check="ts_tv_ratio:S1",
                status="fail",
                message="S1: ts_tv=3.5 (fail)",
                value=3.5,
                expected_range="[1.8, 2.4]",
            ),
            QCResult(
                check="het_hom_ratio:S1",
                status="pass",
                message="S1: het_hom=1.6 (pass)",
                value=1.6,
                expected_range="[1.4, 2.5]",
            ),
            QCResult(
                check="mean_coverage:S1",
                status="pass",
                message="S1: mean_coverage=35.0 (pass)",
                value=35.0,
                expected_range=">= 20.0",
            ),
        ],
    )

    assert RunSummary.from_events(record.events).succeeded is True
    assert record.verdict == "fail"
    assert len(record.repair_history) == 1
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "qc_anomaly"
    assert step.diagnosis.evidence == ["ts_tv_ratio:S1: fail (S1: ts_tv=3.5 (fail))"]
    # D6: a deterministic read of our own verdict object, not a graded guess.
    assert step.diagnosis.confidence == 1.0
