"""Tests for per-task resource actuals parsed from the Nextflow trace.

The trace's resource columns (realtime, peak_rss, %cpu) are resolved by header
name and parsed from Nextflow's human formats (durations, byte sizes, percents)
into the TaskResource contract the record and the cost model consume.
"""

from contig.events import parse_resource_usage_text
from contig.models import TaskResource


def _trace(rows: str, header: str | None = None) -> str:
    head = header or (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\t"
        "duration\trealtime\t%cpu\tpeak_rss\n"
    )
    return head + rows


def test_parses_one_task_with_minute_second_duration():
    text = _trace(
        "1\tab/cd\t1\tSTAR_ALIGN (S1)\tCOMPLETED\t0\t2026-01-01\t"
        "2m 5s\t2m 3s\t180.4%\t1.2 GB\n"
    )
    usage = parse_resource_usage_text(text)
    assert len(usage) == 1
    task = usage[0]
    assert isinstance(task, TaskResource)
    assert task.process == "STAR_ALIGN (S1)"
    assert task.name == "STAR_ALIGN (S1)"
    assert task.realtime_sec == 123.0
    assert task.peak_rss_mb == 1228.8
    assert task.pct_cpu == 180.4


def test_parses_hour_minute_duration_to_seconds():
    text = _trace(
        "1\tab/cd\t1\tBIG_STEP\tCOMPLETED\t0\t2026-01-01\t"
        "1h 4m\t1h 4m\t99.0%\t512 MB\n"
    )
    usage = parse_resource_usage_text(text)
    assert usage[0].realtime_sec == 3840.0


def test_parses_millisecond_duration_to_seconds():
    text = _trace(
        "1\tab/cd\t1\tTINY\tCOMPLETED\t0\t2026-01-01\t"
        "980ms\t980ms\t12.0%\t8 MB\n"
    )
    usage = parse_resource_usage_text(text)
    assert usage[0].realtime_sec == 0.98


def test_parses_gigabyte_peak_rss_to_megabytes():
    text = _trace(
        "1\tab/cd\t1\tMEM_HOG\tCOMPLETED\t0\t2026-01-01\t"
        "5s\t5s\t100.0%\t1.5 GB\n"
    )
    usage = parse_resource_usage_text(text)
    assert usage[0].peak_rss_mb == 1536.0


def test_parses_kilobyte_peak_rss_to_megabytes():
    text = _trace(
        "1\tab/cd\t1\tLIGHT\tCOMPLETED\t0\t2026-01-01\t"
        "5s\t5s\t100.0%\t2048 KB\n"
    )
    usage = parse_resource_usage_text(text)
    assert usage[0].peak_rss_mb == 2.0


def test_missing_resource_fields_default_to_zero():
    # Tasks that never ran (ABORTED) leave realtime/%cpu/peak_rss as a dash.
    text = _trace(
        "1\tab/cd\t1\tSKIPPED\tABORTED\t-\t2026-01-01\t-\t-\t-\t-\n"
    )
    usage = parse_resource_usage_text(text)
    assert usage[0].realtime_sec == 0.0
    assert usage[0].peak_rss_mb == 0.0
    assert usage[0].pct_cpu == 0.0


def test_columns_resolved_by_header_name_not_position():
    header = "name\tpeak_rss\trealtime\t%cpu\n"
    text = header + "STAR_ALIGN\t1.2 GB\t2m 3s\t180.4%\n"
    usage = parse_resource_usage_text(text)
    assert usage[0].process == "STAR_ALIGN"
    assert usage[0].peak_rss_mb == 1228.8
    assert usage[0].realtime_sec == 123.0
    assert usage[0].pct_cpu == 180.4


def test_empty_trace_yields_no_resource_usage():
    assert parse_resource_usage_text("") == []


def test_name_absent_leaves_name_none_with_empty_process():
    header = "realtime\tpeak_rss\t%cpu\n"
    text = header + "5s\t512 MB\t100.0%\n"
    usage = parse_resource_usage_text(text)
    assert usage[0].name is None
    assert usage[0].process == ""
