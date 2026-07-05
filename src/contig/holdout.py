"""Held-out regression guard (moat #2, C6 slice 1).

A frozen, non-leaking held-out corpus plus a committed baseline let us catch a
detector or corpus change that regresses diagnosis before it ships: score
`rules` (or any registered detector) against cases it was never tuned
against, then compare the accuracy to a pinned baseline and fail loud on a
real drop. `evaluate_detector`/`load_corpus` (`corpus.py`) do the scoring;
this module only adds the held-out path, the baseline artifact, and a pure
comparator on top.
"""

from __future__ import annotations

from pathlib import Path


def default_holdout_path() -> Path:
    """Path to the frozen held-out corpus shipped with the package.

    Deliberately never the default of `eval-detector`/`coverage`/`clusters`
    (those all fall back to `default_corpus_path()`), so held-out cases never
    leak into the training-corpus commands.
    """
    return Path(__file__).parent / "data" / "detector_corpus_holdout.jsonl"
