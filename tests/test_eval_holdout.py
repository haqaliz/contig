"""Tests for the held-out regression guard (moat #2, C6 slice 1).

A frozen, non-leaking held-out corpus lets us catch a detector or corpus
change that regresses diagnosis before it ships: score the `rules` detector
against cases it has never trained/tuned against, compare to a committed
baseline, and fail loud on a real drop. This file covers Phase A (the
held-out corpus + loader) and Phase B (the baseline record + pure
comparator) only; the `eval-guard` CLI command is a later slice.
"""

from __future__ import annotations

from pathlib import Path

from contig.corpus import (
    _source_kind,
    default_corpus_path,
    evaluate_detector,
    load_corpus,
)
from contig.holdout import default_holdout_path
from contig.models import Diagnosis, TaskEvent

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
