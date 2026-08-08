"""Tests for the generic append-only JSONL snapshot store (C6 trend, moat #2)."""

from __future__ import annotations

from pathlib import Path

from contig.heal import default_heal_baseline_path, load_heal_baseline
from contig.holdout import default_baseline_path, load_baseline
from contig.models import EvalSnapshot, HealSnapshot, VerifySnapshot
from contig.snapshot_history import append_jsonl, load_jsonl

EVAL_SNAPSHOT_A = EvalSnapshot(
    timestamp="2026-01-01T00:00:00Z",
    corpus_size=10,
    corpus_sha="sha-a",
    accuracy=0.9,
    per_class={},
    contig_version="0.30.0",
    detector="rules",
)
EVAL_SNAPSHOT_B = EvalSnapshot(
    timestamp="2026-01-02T00:00:00Z",
    corpus_size=10,
    corpus_sha="sha-a",
    accuracy=0.92,
    per_class={},
    contig_version="0.31.0",
    detector="rules",
)

HEAL_SNAPSHOT_A = HealSnapshot(
    timestamp="2026-01-01T00:00:00Z",
    scenario_count=5,
    corpus_sha="sha-h",
    outcome_match_rate=0.8,
    recovery_rate=0.6,
    per_class={},
    covered_classes=[],
    contig_version="0.30.0",
)
HEAL_SNAPSHOT_B = HealSnapshot(
    timestamp="2026-01-02T00:00:00Z",
    scenario_count=5,
    corpus_sha="sha-h",
    outcome_match_rate=0.82,
    recovery_rate=0.62,
    per_class={},
    covered_classes=[],
    contig_version="0.31.0",
)


def test_append_creates_file_and_one_line_per_call(tmp_path: Path) -> None:
    p = tmp_path / "history.jsonl"
    append_jsonl(EVAL_SNAPSHOT_A, p)
    append_jsonl(EVAL_SNAPSHOT_B, p)
    lines = [line for line in p.read_text().splitlines() if line.strip()]
    assert len(lines) == 2


def test_load_round_trips_eval_and_heal(tmp_path: Path) -> None:
    eval_path = tmp_path / "eval_history.jsonl"
    append_jsonl(EVAL_SNAPSHOT_A, eval_path)
    append_jsonl(EVAL_SNAPSHOT_B, eval_path)
    assert load_jsonl(EvalSnapshot, eval_path) == [EVAL_SNAPSHOT_A, EVAL_SNAPSHOT_B]

    heal_path = tmp_path / "heal_history.jsonl"
    append_jsonl(HEAL_SNAPSHOT_A, heal_path)
    append_jsonl(HEAL_SNAPSHOT_B, heal_path)
    assert load_jsonl(HealSnapshot, heal_path) == [HEAL_SNAPSHOT_A, HEAL_SNAPSHOT_B]


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_jsonl(EvalSnapshot, tmp_path / "nope.jsonl") == []


def test_load_skips_blank_and_malformed(tmp_path: Path) -> None:
    p = tmp_path / "mixed.jsonl"
    p.write_text(
        EVAL_SNAPSHOT_A.model_dump_json()
        + "\n\n  \nnot json\n"
        + EVAL_SNAPSHOT_B.model_dump_json()
        + "\n"
    )
    assert load_jsonl(EvalSnapshot, p) == [EVAL_SNAPSHOT_A, EVAL_SNAPSHOT_B]


def test_append_creates_parent_dirs(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "dir" / "history.jsonl"
    append_jsonl(EVAL_SNAPSHOT_A, p)
    assert load_jsonl(EvalSnapshot, p) == [EVAL_SNAPSHOT_A]


def test_default_holdout_history_path_under_package_data() -> None:
    from contig.holdout import default_holdout_history_path

    p = default_holdout_history_path()
    assert str(p).endswith("data/holdout_history.jsonl")
    assert p.parent.name == "data"


def test_default_heal_history_path_under_package_data() -> None:
    from contig.heal import default_heal_history_path

    p = default_heal_history_path()
    assert str(p).endswith("data/heal_history.jsonl")
    assert p.parent.name == "data"


def test_holdout_baseline_matches_a_recorded_trend_point() -> None:
    from contig.holdout import default_holdout_history_path

    # The committed baseline must correspond to an actually-measured point in
    # the trend, not a number nobody ever ran eval-guard to produce. History is
    # append-only (RELEASING.md step 2 grows it every release via
    # `eval-guard --snapshot`) and is NEVER rewritten in place, so the baseline
    # is not required to be any particular line -- least of all line 0, the
    # original 0.22.0 seed: an earlier version of this test pinned exactly that
    # and broke the instant a refreeze actually moved accuracy (this one did,
    # 84.6% -> 92.3%, the first refreeze that ever changed the number). A trend
    # whose first point is required to equal the current baseline forever is
    # not a trend. What actually matters -- and is worth guarding -- is that
    # *some* recorded point backs the baseline's number on both metrics that
    # were measured together: accuracy and the held-out corpus's sha. That
    # catches a baseline hand-edited to a value nothing ever measured.
    #
    # contig_version is deliberately NOT part of this cross-check: `--snapshot`
    # stamps a new history point with the CURRENT contig version without
    # touching the baseline, so right after a release the newest history point
    # already carries a newer version than the baseline. Tying the two
    # together here would turn master red at the very next release -- the same
    # failure mode that made this test's line-count check `>= 1` instead of
    # `== 1` at v0.44.0.
    snapshots = load_jsonl(EvalSnapshot, default_holdout_history_path())
    assert len(snapshots) >= 1
    baseline = load_baseline(default_baseline_path())
    assert baseline is not None
    assert any(
        s.accuracy == baseline.accuracy and s.corpus_sha == baseline.corpus_sha
        for s in snapshots
    )


def test_heal_baseline_matches_a_recorded_trend_point() -> None:
    from contig.heal import default_heal_history_path

    # Same reasoning as the holdout sibling above: the baseline must be backed
    # by some actually-measured trend point (on outcome_match_rate + corpus_sha),
    # not pinned to line 0 or to a version -- both traps that only stay hidden
    # until a refreeze (Task 7's heal-baseline refreeze) actually moves the
    # number or a release appends a newer-versioned point.
    snapshots = load_jsonl(HealSnapshot, default_heal_history_path())
    assert len(snapshots) >= 1
    baseline = load_heal_baseline(default_heal_baseline_path())
    assert baseline is not None
    assert any(
        s.outcome_match_rate == baseline.outcome_match_rate
        and s.corpus_sha == baseline.corpus_sha
        for s in snapshots
    )


def test_verify_baseline_matches_a_recorded_trend_point() -> None:
    from contig.verify_corpus import (
        default_verify_baseline_path,
        default_verify_history_path,
        load_verify_baseline,
    )

    # Same reasoning as the two siblings above: the verification baseline must
    # be backed by an actually-measured trend point (on verdict_match_rate +
    # corpus_sha), not pinned to line 0 or to a version -- the aspect-2
    # deliberate freeze appended that point via the real --update-baseline
    # command, and --snapshot grows the trend at every release.
    snapshots = load_jsonl(VerifySnapshot, default_verify_history_path())
    assert len(snapshots) >= 1
    baseline = load_verify_baseline(default_verify_baseline_path())
    assert baseline is not None
    assert any(
        s.verdict_match_rate == baseline.verdict_match_rate
        and s.corpus_sha == baseline.corpus_sha
        for s in snapshots
    )
