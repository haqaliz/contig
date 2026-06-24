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


def test_html_report_carries_print_styles_for_save_as_pdf() -> None:
    html = render_run_report_html(_full_record())
    assert "@media print" in html


def test_html_report_groups_structural_qc_checks() -> None:
    record = RunRecord(
        run_id="r-struct",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.26.0",
        target=_target(),
        input_checksums={},
        events=[TaskEvent(process="STAR", status="COMPLETED", exit=0)],
        qc_results=[
            QCResult(check="mapping_rate", status="pass", message="ok", value=0.97, kind="metric"),
            QCResult(
                check="output_present:aligned.bam",
                status="pass",
                message="present",
                value=1234.0,
                kind="structural",
            ),
        ],
    )
    html = render_run_report_html(record)
    assert "output_present:aligned.bam" in html
    assert "structural" in html.lower()


def test_html_report_groups_concordance() -> None:
    # A concordance result is grouped under its own heading, apart from the
    # metric and structural tables.
    record = RunRecord(
        run_id="r-concordance",
        pipeline="nf-core/sarek",
        pipeline_revision="3.4.0",
        target=_target(),
        input_checksums={},
        events=[TaskEvent(process="HAPLOTYPECALLER", status="COMPLETED", exit=0)],
        qc_results=[
            QCResult(
                check="mapping_rate",
                status="pass",
                message="ok",
                value=0.97,
                kind="metric",
            ),
            QCResult(
                check="output_present:calls.vcf.gz",
                status="pass",
                message="present",
                value=4096.0,
                kind="structural",
            ),
            QCResult(
                check="genotype_concordance",
                status="warn",
                message="corroborated by second_caller.vcf.gz",
                value=0.84,
                expected_range=">= 0.90",
                kind="concordance",
            ),
        ],
    )
    html = render_run_report_html(record)
    # the distinct concordance heading is present
    assert "Concordance (cross-tool corroboration)" in html
    # the concordance check row renders
    assert "genotype_concordance" in html
    # the concordance result is grouped after (not inside) the metric/structural
    # tables: its heading comes after both of those headings.
    concordance_heading = html.index("Concordance (cross-tool corroboration)")
    metric_heading = html.index("Metric checks")
    structural_heading = html.index("Structural and integrity checks")
    assert concordance_heading > metric_heading
    assert concordance_heading > structural_heading
    # and the concordance check name appears only after the concordance heading,
    # so it is not inside the metric or structural tables.
    assert html.index("genotype_concordance") > concordance_heading


def test_html_report_renders_unverified_status() -> None:
    # A concordance check that corroborated nothing carries status "unverified".
    # It must render without error and show the UNVERIFIED label.
    record = RunRecord(
        run_id="r-unverified",
        pipeline="nf-core/sarek",
        pipeline_revision="3.4.0",
        target=_target(),
        input_checksums={},
        events=[TaskEvent(process="HAPLOTYPECALLER", status="COMPLETED", exit=0)],
        qc_results=[
            QCResult(
                check="genotype_concordance",
                status="unverified",
                message="no shared sites between the two call sets",
                kind="concordance",
            ),
        ],
    )
    html = render_run_report_html(record)
    assert "UNVERIFIED" in html
    assert "genotype_concordance" in html
    # the status carries a CSS class consistent with the others
    assert "status-unverified" in html


def test_text_report_shows_concordance_line() -> None:
    record = RunRecord(
        run_id="r-concordance",
        pipeline="nf-core/sarek",
        pipeline_revision="3.4.0",
        target=_target(),
        input_checksums={},
        events=[TaskEvent(process="HAPLOTYPECALLER", status="COMPLETED", exit=0)],
        qc_results=[
            QCResult(
                check="mapping_rate",
                status="pass",
                message="ok",
                value=0.97,
                kind="metric",
            ),
            QCResult(
                check="genotype_concordance",
                status="warn",
                message="corroborated by second_caller.vcf.gz",
                value=0.84,
                expected_range=">= 0.90",
                kind="concordance",
            ),
        ],
    )
    report = render_run_report(record)
    assert "genotype_concordance" in report
    assert "Concordance" in report or "corroborated by" in report


def test_html_report_shows_signature_status_when_present() -> None:
    record = _full_record()
    signature_status = {
        "signed": True,
        "signature_ok": True,
        "public_key": "ab" * 32,
        "algo": "ed25519",
    }
    html = render_run_report_html(record, signature_status=signature_status)
    assert "signature" in html.lower()
    assert "ab" * 32 in html  # the public key the report was signed with
    assert "verified" in html.lower()


def test_html_report_omits_signature_section_when_not_signed() -> None:
    html = render_run_report_html(_full_record())
    # With no signature passed, the report does not claim a signature status.
    assert "signature verified" not in html.lower()


def test_html_report_shows_provenance_input_and_output_checksums() -> None:
    html = render_run_report_html(_full_record())
    assert "abc123" in html  # an input checksum
    assert "00ff11" in html  # an output checksum


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


def _completed_events(n=1):
    return [TaskEvent(process=f"OK_{i}", status="COMPLETED", exit=0) for i in range(n)]


def test_explain_verdict_fail_when_a_task_failed():
    from contig.report import explain_verdict

    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={},
        events=[TaskEvent(process="ALIGN", status="FAILED", exit=1)],
        qc_results=[QCResult(check="mapping_rate", status="pass", message="ok", value=0.95)],
    )
    explanation = explain_verdict(record)
    assert explanation.verdict == "fail"
    assert "did not complete" in explanation.reason.lower()
    assert explanation.deciding_checks == []


def test_explain_verdict_unverified_when_no_qc():
    from contig.report import explain_verdict

    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={},
        events=_completed_events(),
    )
    explanation = explain_verdict(record)
    assert explanation.verdict == "unverified"
    assert "no qc" in explanation.reason.lower()


def test_explain_verdict_warn_names_the_deciding_warn_checks():
    from contig.report import explain_verdict

    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={},
        events=_completed_events(),
        qc_results=[
            QCResult(check="a", status="pass", message="ok", value=99.0),
            QCResult(check="salmon_mapping_rate", status="warn", message="low",
                     value=58.1, expected_range=">= 60.0"),
            QCResult(check="c", status="warn", message="low", value=70.0, expected_range=">= 80.0"),
        ],
    )
    explanation = explain_verdict(record)
    assert explanation.verdict == "warn"
    deciding = {c.check for c in explanation.deciding_checks}
    assert deciding == {"salmon_mapping_rate", "c"}
    # the lowest deciding check drives the headline reason
    assert "salmon_mapping_rate" in explanation.reason
    assert "58.1" in explanation.reason
    assert ">= 60.0" in explanation.reason
    assert "2 of 3" in explanation.reason


def test_explain_verdict_fail_lists_only_failing_checks_when_run_completed():
    from contig.report import explain_verdict

    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={},
        events=_completed_events(),
        qc_results=[
            QCResult(check="ok_check", status="pass", message="ok", value=99.0),
            QCResult(check="dup_rate", status="fail", message="too high",
                     value=80.0, expected_range="<= 50.0"),
            QCResult(check="ok_check_2", status="warn", message="meh", value=70.0),
        ],
    )
    explanation = explain_verdict(record)
    assert explanation.verdict == "fail"
    deciding = {c.check for c in explanation.deciding_checks}
    assert deciding == {"dup_rate"}


def test_render_explain_includes_verdict_reason_and_deciding_checks():
    from contig.report import render_explain

    record = RunRecord(
        run_id="r1",
        pipeline="rnaseq",
        pipeline_revision="3.14.0",
        target=_target(),
        input_checksums={},
        events=_completed_events(),
        qc_results=[
            QCResult(check="salmon_mapping_rate", status="warn", message="low",
                     value=58.1, expected_range=">= 60.0"),
        ],
    )
    text = render_explain(record)
    assert "WARN" in text
    assert "salmon_mapping_rate" in text
    assert "58.1" in text
    assert ">= 60.0" in text
