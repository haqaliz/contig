"""Tests for the detector eval history (moat #2 trend; PRD contract D).

A committed JSONL of EvalSnapshots: one per `eval-detector --snapshot` and one
per successful corpus-promote, so detector accuracy over time is auditable and
the dashboard can render the trend.
"""

import json
from pathlib import Path

from contig.eval_history import (
    append_snapshot,
    default_history_path,
    load_history,
    snapshot_from_report,
)
from contig.models import ClassScore, DetectorEvalReport, EvalSnapshot


def _report():
    return DetectorEvalReport(
        total=4,
        correct=3,
        accuracy=0.75,
        per_class={"oom": ClassScore(support=2, predicted=2, correct=2, precision=1.0, recall=1.0)},
    )


def test_snapshot_from_report_carries_accuracy_and_per_class():
    snap = snapshot_from_report(
        _report(),
        timestamp="2026-06-22T00:00:00+00:00",
        corpus_size=4,
        corpus_sha="abc123",
        contig_version="0.0.1",
    )
    assert snap.accuracy == 0.75
    assert snap.corpus_size == 4
    assert snap.corpus_sha == "abc123"
    assert snap.contig_version == "0.0.1"
    assert snap.per_class["oom"].recall == 1.0


def test_append_and_load_round_trip(tmp_path):
    path = tmp_path / "eval_history.jsonl"
    snap = snapshot_from_report(
        _report(), timestamp="2026-06-22T00:00:00+00:00", corpus_size=4,
        corpus_sha="abc", contig_version="0.0.1",
    )
    append_snapshot(snap, path)
    append_snapshot(snap, path)
    history = load_history(path)
    assert len(history) == 2
    assert history[0].accuracy == 0.75


def test_append_creates_one_json_object_per_line(tmp_path):
    path = tmp_path / "eval_history.jsonl"
    snap = snapshot_from_report(
        _report(), timestamp="t", corpus_size=4, corpus_sha="abc", contig_version="v",
    )
    append_snapshot(snap, path)
    append_snapshot(snap, path)
    assert len(path.read_text().splitlines()) == 2


def test_load_history_missing_file_is_empty(tmp_path):
    assert load_history(tmp_path / "nope.jsonl") == []


def test_default_history_path_lives_under_package_data():
    p = default_history_path()
    assert p.name == "eval_history.jsonl"
    assert p.parent.name == "data"


def test_eval_snapshot_serializes_per_class_nested():
    snap = EvalSnapshot(
        timestamp="t", corpus_size=1, corpus_sha="s", accuracy=1.0,
        per_class={"oom": ClassScore(support=1, predicted=1, correct=1, precision=1.0, recall=1.0)},
        contig_version="v",
    )
    data = json.loads(snap.model_dump_json())
    assert data["per_class"]["oom"]["support"] == 1
