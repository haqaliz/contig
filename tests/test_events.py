"""Tests for the Nextflow trace-file ingestion module (contig.events)."""

from contig.events import parse_trace_file, parse_trace_text, summarize_trace_text


def test_completed_row_yields_one_non_failure_event():
    text = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        "1\tab/cd12\t1001\tNFCORE_RNASEQ:RNASEQ:FASTQC (SAMPLE_1)\tCOMPLETED\t0\t2026-01-01\t1s\t1s\n"
    )
    events = parse_trace_text(text)
    assert len(events) == 1
    assert events[0].is_failure is False


def test_failed_row_is_failure_with_int_exit():
    text = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        "2\tef/gh34\t1002\tNFCORE_RNASEQ:RNASEQ:STAR_ALIGN (SAMPLE_1)\tFAILED\t137\t2026-01-01\t9s\t8s\n"
    )
    events = parse_trace_text(text)
    assert events[0].is_failure is True
    assert events[0].exit == 137


def test_dash_exit_parses_to_none():
    text = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        "3\tij/kl56\t1003\tNFCORE_RNASEQ:RNASEQ:CUSTOM_DUMPSOFTWAREVERSIONS\tABORTED\t-\t2026-01-01\t-\t-\n"
    )
    events = parse_trace_text(text)
    assert events[0].exit is None


def test_header_row_is_not_an_event():
    text = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        "1\tab/cd12\t1001\tFASTQC (SAMPLE_1)\tCOMPLETED\t0\t2026-01-01\t1s\t1s\n"
        "2\tef/gh34\t1002\tSTAR_ALIGN (SAMPLE_1)\tFAILED\t137\t2026-01-01\t9s\t8s\n"
    )
    events = parse_trace_text(text)
    assert len(events) == 2


def test_summarize_trace_text_counts_failures():
    text = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        "1\tab/cd12\t1001\tFASTQC (SAMPLE_1)\tCOMPLETED\t0\t2026-01-01\t1s\t1s\n"
        "2\tef/gh34\t1002\tSTAR_ALIGN (SAMPLE_1)\tFAILED\t137\t2026-01-01\t9s\t8s\n"
    )
    summary = summarize_trace_text(text)
    assert summary.total_tasks == 2
    assert summary.failed_tasks == 1
    assert summary.succeeded is False


def test_parse_trace_file_matches_parse_trace_text(tmp_path):
    text = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        "1\tab/cd12\t1001\tFASTQC (SAMPLE_1)\tCOMPLETED\t0\t2026-01-01\t1s\t1s\n"
        "2\tef/gh34\t1002\tSTAR_ALIGN (SAMPLE_1)\tFAILED\t137\t2026-01-01\t9s\t8s\n"
    )
    trace = tmp_path / "trace.txt"
    trace.write_text(text)
    assert parse_trace_file(trace) == parse_trace_text(text)


def test_columns_resolved_by_header_name_not_position():
    # A custom Nextflow trace.fields order must NOT feed garbage to the detector.
    text = (
        "status\tname\texit\ttask_id\n"
        "FAILED\tNFCORE_RNASEQ:RNASEQ:STAR_ALIGN (S1)\t137\t7\n"
    )
    events = parse_trace_text(text)
    assert events[0].status == "FAILED"
    assert events[0].process == "NFCORE_RNASEQ:RNASEQ:STAR_ALIGN (S1)"
    assert events[0].exit == 137
    assert events[0].task_id == "7"


def test_blank_and_trailing_lines_are_ignored():
    text = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        "1\tab/cd12\t1001\tFASTQC (SAMPLE_1)\tCOMPLETED\t0\t2026-01-01\t1s\t1s\n"
        "\n"
        "2\tef/gh34\t1002\tSTAR_ALIGN (SAMPLE_1)\tCOMPLETED\t0\t2026-01-01\t9s\t8s\n"
        "\n"
    )
    events = parse_trace_text(text)
    assert len(events) == 2
