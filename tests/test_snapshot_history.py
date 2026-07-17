"""Tests for the generic append-only JSONL snapshot store (C6 trend, moat #2)."""

from __future__ import annotations

from pathlib import Path

from contig.models import EvalSnapshot, HealSnapshot
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
