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

from os import PathLike
from pathlib import Path

from contig.models import DetectorEvalReport, EvalSnapshot, HoldoutGuardResult


def default_holdout_path() -> Path:
    """Path to the frozen held-out corpus shipped with the package.

    Deliberately never the default of `eval-detector`/`coverage`/`clusters`
    (those all fall back to `default_corpus_path()`), so held-out cases never
    leak into the training-corpus commands.
    """
    return Path(__file__).parent / "data" / "detector_corpus_holdout.jsonl"


def default_holdout_history_path() -> Path:
    """Committed held-out accuracy trend (JSONL, one EvalSnapshot per line)."""
    return Path(__file__).parent / "data" / "holdout_history.jsonl"


def default_baseline_path() -> Path:
    """Path to the committed held-out baseline shipped with the package.

    A single `EvalSnapshot` serialized as one pretty-printed JSON object (NOT
    JSONL, unlike `eval_history.py`'s append-only log) — there is exactly one
    frozen baseline to compare against, not a trend.
    """
    return Path(__file__).parent / "data" / "holdout_baseline.json"


def save_baseline(snapshot: EvalSnapshot, path: str | PathLike[str]) -> None:
    """Write the baseline as one pretty-printed JSON object (diffs cleanly)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(snapshot.model_dump_json(indent=2) + "\n")


def load_baseline(path: str | PathLike[str]) -> EvalSnapshot | None:
    """Read the committed baseline; a missing file means "no baseline yet"."""
    p = Path(path)
    if not p.exists():
        return None
    return EvalSnapshot.model_validate_json(p.read_text())


def compare_to_baseline(
    report: DetectorEvalReport,
    *,
    baseline: EvalSnapshot | None,
    holdout_sha: str,
    holdout_size: int,
    detector: str,
    tolerance: float,
) -> HoldoutGuardResult:
    """Compare a held-out eval report to the committed baseline (pure, no I/O).

    A real drop below `baseline.accuracy - tolerance` is `regressed`; a real
    rise above `baseline.accuracy + tolerance` is `improved`; the tolerance
    band between the two absorbs float noise so an unchanged accuracy is
    neither. `sha_mismatch`/`detector_mismatch` flag when the comparison
    crosses a different held-out set or detector than the baseline was
    measured against — informational, not a failure by themselves (the CLI
    layer decides what to do with a missing baseline or these warnings; this
    function stays pure so it is fast and deterministic to test).
    """
    if baseline is None:
        return HoldoutGuardResult(
            detector=detector,
            holdout_size=holdout_size,
            accuracy=report.accuracy,
            baseline_accuracy=None,
            delta=None,
            tolerance=tolerance,
            regressed=False,
            improved=False,
            holdout_sha=holdout_sha,
            baseline_sha=None,
            sha_mismatch=False,
            detector_mismatch=False,
            has_baseline=False,
            mismatches=report.mismatches,
        )

    delta = report.accuracy - baseline.accuracy
    return HoldoutGuardResult(
        detector=detector,
        holdout_size=holdout_size,
        accuracy=report.accuracy,
        baseline_accuracy=baseline.accuracy,
        delta=delta,
        tolerance=tolerance,
        regressed=report.accuracy < baseline.accuracy - tolerance,
        improved=report.accuracy > baseline.accuracy + tolerance,
        holdout_sha=holdout_sha,
        baseline_sha=baseline.corpus_sha,
        sha_mismatch=holdout_sha != baseline.corpus_sha,
        detector_mismatch=detector != baseline.detector,
        has_baseline=True,
        mismatches=report.mismatches,
    )
