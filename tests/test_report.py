"""Tests for the human-readable run report (TDD, real RunRecord objects)."""

from __future__ import annotations

from contig.models import (
    Diagnosis,
    ExecutionTarget,
    Patch,
    QCResult,
    RepairStep,
    RunRecord,
    TaskEvent,
)
from contig.report import render_run_report, render_run_report_html


def _target() -> ExecutionTarget:
    return ExecutionTarget(backend="local", container_runtime="docker", work_dir="w")


def test_report_contains_uppercase_verdict() -> None:
    # A failed task forces the verdict to "fail".
    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={"reads.fastq": "abc"},
        events=[TaskEvent(process="ALIGN", status="FAILED", exit=1)],
    )
    report = render_run_report(record)
    assert "FAIL" in report


def test_report_contains_pipeline_name_and_revision() -> None:
    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={"reads.fastq": "abc"},
    )
    report = render_run_report(record)
    assert "rnaseq" in report
    assert "3.14.0" in report


def test_report_shows_total_and_failed_task_counts() -> None:
    events = [TaskEvent(process=f"OK_{i}", status="COMPLETED", exit=0) for i in range(3)]
    events += [TaskEvent(process=f"BAD_{i}", status="FAILED", exit=1) for i in range(2)]
    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={"reads.fastq": "abc"},
        events=events,
    )
    report = render_run_report(record)
    assert "5" in report  # total tasks
    assert "2 failed" in report


def test_report_lists_each_qc_result_with_status_and_value() -> None:
    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={"reads.fastq": "abc"},
        events=[TaskEvent(process="ALIGN", status="COMPLETED", exit=0)],
        qc_results=[
            QCResult(
                check="mapping_rate",
                status="pass",
                message="ok",
                value=0.97,
                expected_range=">0.9",
            ),
            QCResult(
                check="duplication",
                status="warn",
                message="elevated",
                value=0.42,
            ),
        ],
    )
    report = render_run_report(record)
    assert "mapping_rate" in report
    assert "PASS" in report
    assert "0.97" in report
    assert "duplication" in report
    assert "WARN" in report
    assert "0.42" in report


def test_report_states_no_qc_when_empty() -> None:
    # A successful run with no QC coverage is "unverified", and the report must
    # explain why: no QC checks ran.
    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={"reads.fastq": "abc"},
        events=[TaskEvent(process="ALIGN", status="COMPLETED", exit=0)],
        qc_results=[],
    )
    report = render_run_report(record)
    assert "UNVERIFIED" in report
    assert "no qc" in report.lower()


def test_report_shows_repair_chain_when_present() -> None:
    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.26.0",
        target=_target(),
        input_checksums={},
        events=[TaskEvent(process="ALIGN", status="COMPLETED", exit=0)],
        repair_history=[
            RepairStep(
                attempt=1,
                diagnosis=Diagnosis(failure_class="oom", root_cause="OOM", evidence=["exit 137"], confidence=0.9),
                patch=Patch(kind="resource", operation={"multiply": {"memory": 2}}, rationale="bump", risk="safe", expected_signal="no OOM"),
                outcome="patched_and_retried",
            )
        ],
    )
    report = render_run_report(record)
    assert "oom" in report.lower()
    assert "patched_and_retried" in report


def test_report_includes_versions_and_input_count_when_set() -> None:
    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={"reads_1.fastq": "abc", "reads_2.fastq": "def"},
        events=[TaskEvent(process="ALIGN", status="COMPLETED", exit=0)],
        contig_version="0.5.2",
        nextflow_version="24.04.1",
    )
    report = render_run_report(record)
    assert "0.5.2" in report
    assert "24.04.1" in report
    assert "2 input" in report.lower()  # two input files checksummed


def _full_record() -> RunRecord:
    return RunRecord(
        run_id="run-2026-001",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=_target(),
        input_checksums={"reads_1.fastq": "abc123", "reads_2.fastq": "def456"},
        parameters={"genome": "GRCh38"},
        container_digests={"star": "sha256:deadbeef"},
        output_checksums={"results/star.bam": "00ff11"},
        nextflow_version="24.04.1",
        contig_version="0.5.2",
        events=[TaskEvent(process="STAR", status="COMPLETED", exit=0)],
        qc_results=[
            QCResult(
                check="mapping_rate",
                status="pass",
                message="ok",
                value=0.97,
                expected_range=">0.9",
            ),
        ],
        repair_history=[
            RepairStep(
                attempt=1,
                diagnosis=Diagnosis(
                    failure_class="oom", root_cause="OOM", evidence=["exit 137"], confidence=0.9
                ),
                patch=Patch(
                    kind="resource",
                    operation={"multiply": {"memory": 2}},
                    rationale="bump",
                    risk="safe",
                    expected_signal="no OOM",
                ),
                outcome="patched_and_retried",
            )
        ],
    )


def test_html_report_is_a_self_contained_document() -> None:
    html = render_run_report_html(_full_record())
    assert html.lower().startswith("<!doctype html")
    assert "<html" in html.lower()
    # no external resources / network calls
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html.lower()


def test_html_report_contains_verdict_pipeline_qc_and_run_id() -> None:
    record = _full_record()
    html = render_run_report_html(record)
    assert "run-2026-001" in html  # run id
    assert "pass" in html.lower()  # verdict (the QC passes -> verdict pass)
    assert "nf-core/rnaseq" in html  # pipeline name
    assert "mapping_rate" in html  # a QC check name


def test_html_report_shows_repair_chain() -> None:
    html = render_run_report_html(_full_record())
    assert "oom" in html.lower()
    assert "patched_and_retried" in html


def test_html_report_notes_when_there_are_no_repairs() -> None:
    record = RunRecord(
        run_id="clean-run",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=_target(),
        input_checksums={"reads.fastq": "abc"},
        events=[TaskEvent(process="STAR", status="COMPLETED", exit=0)],
        qc_results=[QCResult(check="mapping_rate", status="pass", message="ok", value=0.97)],
    )
    html = render_run_report_html(record)
    assert "no repairs" in html.lower()


def test_html_report_is_metadata_only() -> None:
    # Structural: the report carries identifiers and hashes, not raw reads.
    record = _full_record()
    html = render_run_report_html(record)
    assert "run-2026-001" in html
    assert "nf-core/rnaseq" in html
    assert "abc123" in html  # an input checksum is present (hash, not the read)


def test_html_report_escapes_user_text() -> None:
    record = RunRecord(
        run_id="r1",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=_target(),
        input_checksums={},
        events=[TaskEvent(process="STAR", status="COMPLETED", exit=0)],
        qc_results=[
            QCResult(check="mapping_rate", status="pass", message="<script>x</script>", value=0.9),
        ],
    )
    html = render_run_report_html(record)
    # the raw injected markup must not appear verbatim
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html
