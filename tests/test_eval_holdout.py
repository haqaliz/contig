"""Tests for the held-out regression guard (moat #2, C6 slice 1).

A frozen, non-leaking held-out corpus lets us catch a detector or corpus
change that regresses diagnosis before it ships: score the `rules` detector
against cases it has never trained/tuned against, compare to a committed
baseline, and fail loud on a real drop. This file covers Phase A (the
held-out corpus + loader), Phase B (the baseline record + pure comparator),
and Phase C (the `eval-guard` CLI command).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.corpus import (
    _source_kind,
    default_corpus_path,
    evaluate_detector,
    load_corpus,
    save_corpus,
)
from contig.holdout import (
    compare_to_baseline,
    default_baseline_path,
    default_holdout_path,
    load_baseline,
    save_baseline,
)
from contig.models import (
    Diagnosis,
    DetectorEvalReport,
    DetectorMismatch,
    EvalSnapshot,
    TaskEvent,
)

runner = CliRunner()

# --- Phase A: held-out corpus + loader ------------------------------------


def test_holdout_loads_and_is_nonempty():
    cases = load_corpus(default_holdout_path())
    assert len(cases) >= 10


def test_holdout_disjoint_from_training():
    holdout_ids = {c.case_id for c in load_corpus(default_holdout_path())}
    training_ids = {c.case_id for c in load_corpus(default_corpus_path())}
    assert holdout_ids.isdisjoint(training_ids)


def test_holdout_source_kind():
    for case in load_corpus(default_holdout_path()):
        assert case.source.startswith("holdout:")
        assert _source_kind(case.source) == "holdout"


def test_holdout_not_a_default_of_other_commands():
    # The held-out path must never be what eval-detector/coverage/clusters fall
    # back to (AC1 leakage guard) -- they all default to default_corpus_path().
    assert default_holdout_path() != default_corpus_path()


def test_holdout_case_ids_prefixed():
    for case in load_corpus(default_holdout_path()):
        assert case.case_id.startswith("holdout-")


def test_rules_detector_scores_high_on_holdout():
    # Not a hardcoded number: just a sanity floor so an obviously-broken
    # authoring pass (e.g. copy-paste wording that never matches a rule) is
    # caught. The committed baseline (Phase D) pins the exact figure.
    report = evaluate_detector(load_corpus(default_holdout_path()))
    assert report.accuracy >= 0.7


# --- Phase B: baseline record + pure comparator ----------------------------


def _report(accuracy: float, mismatches: list[DetectorMismatch] | None = None) -> DetectorEvalReport:
    return DetectorEvalReport(
        total=10,
        correct=round(accuracy * 10),
        accuracy=accuracy,
        mismatches=mismatches or [],
        per_class={},
    )


def _baseline(
    accuracy: float, *, corpus_sha: str = "sha-a", detector: str = "rules"
) -> EvalSnapshot:
    return EvalSnapshot(
        timestamp="2026-07-01T00:00:00+00:00",
        corpus_size=10,
        corpus_sha=corpus_sha,
        accuracy=accuracy,
        per_class={},
        contig_version="0.16.0",
        detector=detector,
    )


def test_default_baseline_path_differs_from_holdout_and_history():
    assert default_baseline_path() != default_holdout_path()
    assert default_baseline_path().name == "holdout_baseline.json"


def test_compare_pass():
    baseline = _baseline(0.9)
    result = compare_to_baseline(
        _report(0.9),
        baseline=baseline,
        holdout_sha="sha-a",
        holdout_size=10,
        detector="rules",
        tolerance=1e-9,
    )
    assert result.regressed is False
    assert result.improved is False
    assert result.has_baseline is True
    assert result.baseline_accuracy == pytest.approx(0.9)
    assert result.delta == pytest.approx(0.0)
    assert result.sha_mismatch is False
    assert result.detector_mismatch is False


def test_compare_regression():
    baseline = _baseline(0.9)
    result = compare_to_baseline(
        _report(0.5),
        baseline=baseline,
        holdout_sha="sha-a",
        holdout_size=10,
        detector="rules",
        tolerance=1e-9,
    )
    assert result.regressed is True
    assert result.improved is False
    assert result.delta < 0


def test_compare_improvement():
    baseline = _baseline(0.5)
    result = compare_to_baseline(
        _report(0.9),
        baseline=baseline,
        holdout_sha="sha-a",
        holdout_size=10,
        detector="rules",
        tolerance=1e-9,
    )
    assert result.improved is True
    assert result.regressed is False
    assert result.delta > 0


def test_compare_tolerance_absorbs_float_noise():
    baseline = _baseline(0.9)
    # Exactly half the tolerance below baseline: must not count as a regression.
    result = compare_to_baseline(
        _report(0.9 - 0.05),
        baseline=baseline,
        holdout_sha="sha-a",
        holdout_size=10,
        detector="rules",
        tolerance=0.1,
    )
    assert result.regressed is False


def test_compare_no_baseline():
    result = compare_to_baseline(
        _report(0.5),
        baseline=None,
        holdout_sha="sha-a",
        holdout_size=10,
        detector="rules",
        tolerance=1e-9,
    )
    assert result.has_baseline is False
    assert result.regressed is False
    assert result.improved is False
    assert result.baseline_accuracy is None
    assert result.delta is None


def test_compare_sha_and_detector_mismatch():
    baseline = _baseline(0.9, corpus_sha="sha-old", detector="rules")
    result = compare_to_baseline(
        _report(0.9),
        baseline=baseline,
        holdout_sha="sha-new",
        holdout_size=10,
        detector="rules-strict",
        tolerance=1e-9,
    )
    assert result.sha_mismatch is True
    assert result.detector_mismatch is True


def test_compare_carries_mismatches_through():
    mismatches = [DetectorMismatch(case_id="holdout-x", expected="oom", predicted="unknown")]
    baseline = _baseline(0.9)
    result = compare_to_baseline(
        _report(0.9, mismatches=mismatches),
        baseline=baseline,
        holdout_sha="sha-a",
        holdout_size=10,
        detector="rules",
        tolerance=1e-9,
    )
    assert result.mismatches == mismatches


def test_baseline_roundtrip(tmp_path):
    path = tmp_path / "baseline.json"
    assert load_baseline(path) is None  # missing file -> None, not an error

    snapshot = _baseline(0.9)
    save_baseline(snapshot, path)
    loaded = load_baseline(path)

    assert loaded == snapshot


def test_worse_detector_scores_lower_than_rules_on_holdout():
    # The "deliberately worse detector" the roadmap acceptance names (AC3),
    # exercised at the eval level without touching the detector registry.
    def _worse(events: list[TaskEvent], log_text: str) -> Diagnosis:
        return Diagnosis(failure_class="unknown", root_cause="stub", confidence=0.1)

    cases = load_corpus(default_holdout_path())
    worse_report = evaluate_detector(cases, _worse)
    rules_report = evaluate_detector(cases)

    assert worse_report.accuracy < rules_report.accuracy


# --- Phase C: `eval-guard` CLI command --------------------------------------


def test_guard_update_then_pass(tmp_path):
    baseline_path = tmp_path / "baseline.json"

    freeze = runner.invoke(app, ["eval-guard", "--update-baseline", "--baseline", str(baseline_path)])
    assert freeze.exit_code == 0
    assert "Baseline updated" in freeze.output
    assert baseline_path.exists()

    guard = runner.invoke(app, ["eval-guard", "--baseline", str(baseline_path)])
    assert guard.exit_code == 0
    assert "Guard PASS" in guard.output


def test_guard_regression_worse_detector(tmp_path, monkeypatch):
    import contig.detect

    def _worse(events: list[TaskEvent], log_text: str) -> Diagnosis:
        return Diagnosis(failure_class="unknown", root_cause="stub", confidence=0.1)

    monkeypatch.setitem(contig.detect.DETECTORS, "worse", _worse)

    baseline_path = tmp_path / "baseline.json"
    freeze = runner.invoke(
        app, ["eval-guard", "--update-baseline", "--detector", "rules", "--baseline", str(baseline_path)]
    )
    assert freeze.exit_code == 0

    guard = runner.invoke(app, ["eval-guard", "--detector", "worse", "--baseline", str(baseline_path)])
    assert guard.exit_code == 1
    assert "REGRESSION" in guard.output


def test_guard_no_baseline(tmp_path):
    baseline_path = tmp_path / "does_not_exist.json"

    guard = runner.invoke(app, ["eval-guard", "--baseline", str(baseline_path)])
    assert guard.exit_code == 1
    assert "No held-out baseline" in guard.stderr


def test_guard_sha_mismatch_warns(tmp_path):
    holdout_a = tmp_path / "holdout_a.jsonl"
    shutil.copy(default_holdout_path(), holdout_a)
    baseline_path = tmp_path / "baseline.json"

    freeze = runner.invoke(
        app,
        ["eval-guard", "--update-baseline", "--holdout", str(holdout_a), "--baseline", str(baseline_path)],
    )
    assert freeze.exit_code == 0

    cases = load_corpus(holdout_a)
    extra = cases[0].model_copy(update={"case_id": "holdout-extra"})
    holdout_b = tmp_path / "holdout_b.jsonl"
    save_corpus(cases + [extra], holdout_b)

    guard = runner.invoke(
        app,
        ["eval-guard", "--holdout", str(holdout_b), "--baseline", str(baseline_path)],
    )
    assert guard.exit_code == 0
    assert "changed" in guard.stderr.lower()
    assert "sha" in guard.stderr.lower()


def test_guard_json(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    freeze = runner.invoke(app, ["eval-guard", "--update-baseline", "--baseline", str(baseline_path)])
    assert freeze.exit_code == 0

    import json

    guard = runner.invoke(app, ["eval-guard", "--baseline", str(baseline_path), "--json"])
    assert guard.exit_code == 0
    data = json.loads(guard.output)
    assert "regressed" in data
    assert data["has_baseline"] is True
