"""Tests for failure clustering and corpus coverage (PRD contracts B + C).

Clustering groups corpus cases by failure class plus a normalized log signature
so the same systemic failure mode collapses to one cluster even across runs.
Coverage reports per-class support, a thin-coverage flag, a by-source breakdown,
and a confirmed-over-time series drawn from the eval history.
"""

from contig.corpus import cluster_failures, coverage_report
from contig.models import EvalSnapshot, FailureCase, TaskEvent


def _case(case_id, expected_class, log_text, source="synthetic"):
    return FailureCase(
        case_id=case_id,
        description="d",
        source=source,
        events=[TaskEvent(process="X", status="FAILED", exit=1)],
        log_text=log_text,
        expected_class=expected_class,
    )


# --- clustering (contract B) ---------------------------------------------------


def test_cluster_groups_same_class_and_signature_together():
    cases = [
        _case("a", "oom", "Process killed (out of memory), exit 137"),
        _case("b", "oom", "Process killed (out of memory), exit 137"),
    ]
    clusters = cluster_failures(cases)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["failure_class"] == "oom"
    assert cluster["count"] == 2
    assert set(cluster["case_ids"]) == {"a", "b"}


def test_cluster_normalizes_paths_numbers_and_hashes_into_one_signature():
    # The same failure mode differing only in an absolute path, a task hash, and a
    # line number collapses to a single cluster.
    cases = [
        _case("a", "missing_reference", "/work/ab/cd1234 ERROR: reference /data/genome/GRCh38.fa not found at line 42"),
        _case("b", "missing_reference", "/work/ef/9988aa ERROR: reference /other/path/mm10.fa not found at line 7"),
    ]
    clusters = cluster_failures(cases)
    assert len(clusters) == 1
    assert clusters[0]["count"] == 2


def test_cluster_keeps_distinct_failure_classes_apart():
    cases = [
        _case("a", "oom", "killed out of memory"),
        _case("b", "tool_crash", "segmentation fault"),
    ]
    clusters = cluster_failures(cases)
    assert len(clusters) == 2


def test_cluster_orders_worst_first_by_count():
    cases = [
        _case("a", "oom", "out of memory killed"),
        _case("b", "oom", "out of memory killed"),
        _case("c", "tool_crash", "segfault"),
    ]
    clusters = cluster_failures(cases)
    assert clusters[0]["failure_class"] == "oom"
    assert clusters[0]["count"] == 2
    assert clusters[1]["count"] == 1


def test_cluster_signature_is_stable_for_one_case():
    case = _case("a", "oom", "killed out of memory exit 137")
    first = cluster_failures([case])[0]["signature"]
    second = cluster_failures([case])[0]["signature"]
    assert first == second


def test_cluster_empty_corpus_is_no_clusters():
    assert cluster_failures([]) == []


# --- coverage (contract C) -----------------------------------------------------


def test_coverage_counts_total_and_per_class():
    cases = [
        _case("a", "oom", "x"),
        _case("b", "oom", "y"),
        _case("c", "tool_crash", "z"),
    ]
    report = coverage_report(cases)
    assert report["total"] == 3
    assert report["per_class"] == {"oom": 2, "tool_crash": 1}


def test_coverage_flags_classes_with_fewer_than_three_cases_as_thin():
    cases = [
        _case("a", "oom", "x"),
        _case("b", "oom", "y"),
        _case("c", "oom", "z"),
        _case("d", "tool_crash", "w"),
    ]
    report = coverage_report(cases)
    assert "tool_crash" in report["thin"]
    assert "oom" not in report["thin"]


def test_coverage_breaks_down_by_source_kind():
    cases = [
        _case("a", "oom", "x", source="synthetic"),
        _case("b", "oom", "y", source="run:r1"),
        _case("c", "tool_crash", "z", source="confirmed:r2"),
    ]
    report = coverage_report(cases)
    assert report["by_source"]["synthetic"] == 1
    assert report["by_source"]["run"] == 1
    assert report["by_source"]["confirmed"] == 1


def test_coverage_empty_corpus_is_zero_total():
    report = coverage_report([])
    assert report["total"] == 0
    assert report["per_class"] == {}
    assert report["thin"] == []


def test_coverage_includes_confirmed_over_time_from_history():
    cases = [_case("a", "oom", "x")]
    history = [
        EvalSnapshot(timestamp="2026-06-19T00:00:00Z", corpus_size=5, corpus_sha="s1", accuracy=0.8),
        EvalSnapshot(timestamp="2026-06-20T00:00:00Z", corpus_size=8, corpus_sha="s2", accuracy=0.9),
    ]
    report = coverage_report(cases, history=history)
    series = report["confirmed_over_time"]
    assert series == [
        {"timestamp": "2026-06-19T00:00:00Z", "corpus_size": 5},
        {"timestamp": "2026-06-20T00:00:00Z", "corpus_size": 8},
    ]


def test_coverage_without_history_has_an_empty_series():
    report = coverage_report([_case("a", "oom", "x")])
    assert report["confirmed_over_time"] == []
