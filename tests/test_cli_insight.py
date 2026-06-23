"""CLI tests for `contig clusters` and `contig coverage` (PRD contracts B + C)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contig.cli import app
from contig.corpus import save_corpus
from contig.models import FailureCase, TaskEvent

runner = CliRunner()


def _case(case_id, expected_class, log_text, source="synthetic"):
    return FailureCase(
        case_id=case_id,
        description="d",
        source=source,
        events=[TaskEvent(process="X", status="FAILED", exit=1)],
        log_text=log_text,
        expected_class=expected_class,
    )


def _corpus(tmp_path):
    path = tmp_path / "corpus.jsonl"
    save_corpus(
        [
            _case("a", "oom", "Process killed out of memory exit 137"),
            _case("b", "oom", "Process killed out of memory exit 137"),
            _case("c", "tool_crash", "segmentation fault"),
        ],
        path,
    )
    return path


def test_clusters_json_lists_clusters_worst_first(tmp_path):
    path = _corpus(tmp_path)
    result = runner.invoke(app, ["clusters", "--corpus", str(path), "--json"])
    assert result.exit_code == 0
    clusters = json.loads(result.output)
    assert clusters[0]["failure_class"] == "oom"
    assert clusters[0]["count"] == 2
    assert clusters[1]["count"] == 1


def test_clusters_text_names_the_failure_class(tmp_path):
    path = _corpus(tmp_path)
    result = runner.invoke(app, ["clusters", "--corpus", str(path)])
    assert result.exit_code == 0
    assert "oom" in result.output


def test_clusters_errors_on_missing_corpus(tmp_path):
    result = runner.invoke(app, ["clusters", "--corpus", str(tmp_path / "absent.jsonl")])
    assert result.exit_code != 0


def test_coverage_json_reports_totals_and_thin(tmp_path):
    path = _corpus(tmp_path)
    result = runner.invoke(app, ["coverage", "--corpus", str(path), "--json"])
    assert result.exit_code == 0
    report = json.loads(result.output)
    assert report["total"] == 3
    assert report["per_class"]["oom"] == 2
    assert "tool_crash" in report["thin"]


def test_coverage_text_reports_total(tmp_path):
    path = _corpus(tmp_path)
    result = runner.invoke(app, ["coverage", "--corpus", str(path)])
    assert result.exit_code == 0
    assert "3" in result.output


def test_coverage_errors_on_missing_corpus(tmp_path):
    result = runner.invoke(app, ["coverage", "--corpus", str(tmp_path / "absent.jsonl")])
    assert result.exit_code != 0
