"""Reproduce-eval guard (C6 fold-in, aspect guard-core: reproduce-guard).

A frozen `ReproduceScenario` set replayed through the REAL `run_reproduction`
loop -- real `load_claims`, real `classify`, real locators, real freshness
guard -- with only the executor/installer seams scripted, guarding the
per-scenario outcome-match rate against a committed baseline, the fourth guard
sibling of eval-guard / heal-guard / verify-guard.

Phase A: models + the three default data paths only; the driver, scorer, and
comparator land in later phases, mirroring verify_corpus.py's shape.
"""

from __future__ import annotations

from pathlib import Path


def default_reproduce_scenarios_path() -> Path:
    """Path to the frozen reproduce scenario set shipped with the package."""
    return Path(__file__).parent / "data" / "reproduce_scenarios.jsonl"


def default_reproduce_baseline_path() -> Path:
    """Path to the committed reproduce baseline shipped with the package.

    A single `ReproduceSnapshot` serialized as one pretty-printed JSON object
    (NOT JSONL) -- there is exactly one frozen baseline to compare against, not
    a trend.
    """
    return Path(__file__).parent / "data" / "reproduce_baseline.json"


def default_reproduce_history_path() -> Path:
    """Committed reproduce outcome-match trend (JSONL, one ReproduceSnapshot per line)."""
    return Path(__file__).parent / "data" / "reproduce_history.jsonl"
