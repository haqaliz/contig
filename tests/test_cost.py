"""Tests for the resource cost model (contig.cost)."""

from contig.cost import cost_report
from contig.models import TaskResource


def _task(name, realtime_sec, peak_rss_mb):
    return TaskResource(
        process=name, name=name, realtime_sec=realtime_sec,
        peak_rss_mb=peak_rss_mb, pct_cpu=100.0,
    )


def test_zero_rates_yield_zero_cost():
    usage = [_task("STAR_ALIGN", 3600.0, 1024.0)]
    report = cost_report(usage)
    assert report["total"] == 0.0
    assert report["by_task"][0]["cost"] == 0.0


def test_cpu_hour_rate_prices_realtime():
    # One hour of realtime at 1.0/cpu-hour is 1.0; memory rate is zero here.
    usage = [_task("STAR_ALIGN", 3600.0, 0.0)]
    report = cost_report(usage, rate_cpu_hour=1.0, rate_mem_gb_hour=0.0)
    assert report["by_task"][0]["cost"] == 1.0
    assert report["total"] == 1.0


def test_mem_gb_hour_rate_prices_peak_rss():
    # 2 GB for one hour at 0.5/GB-hour is 1.0; cpu rate is zero here.
    usage = [_task("MEM_HOG", 3600.0, 2048.0)]
    report = cost_report(usage, rate_cpu_hour=0.0, rate_mem_gb_hour=0.5)
    assert report["by_task"][0]["cost"] == 1.0


def test_total_sums_per_task_costs():
    usage = [
        _task("A", 3600.0, 0.0),
        _task("B", 7200.0, 0.0),
    ]
    report = cost_report(usage, rate_cpu_hour=1.0)
    assert report["total"] == 3.0


def test_by_task_carries_name_realtime_and_peak():
    usage = [_task("STAR_ALIGN", 1800.0, 512.0)]
    report = cost_report(usage, rate_cpu_hour=2.0)
    row = report["by_task"][0]
    assert row["name"] == "STAR_ALIGN"
    assert row["realtime_sec"] == 1800.0
    assert row["peak_rss_mb"] == 512.0


def test_empty_usage_reports_zero_total_and_empty_by_task():
    report = cost_report([], rate_cpu_hour=5.0, rate_mem_gb_hour=5.0)
    assert report["total"] == 0.0
    assert report["by_task"] == []


def test_report_echoes_rates_and_currency():
    report = cost_report([], rate_cpu_hour=0.1, rate_mem_gb_hour=0.02, currency="EUR")
    assert report["currency"] == "EUR"
    assert report["rate_cpu_hour"] == 0.1
    assert report["rate_mem_gb_hour"] == 0.02
