"""Injectable triage seam for `contig` (C9 slice 1: `jev-calibrated-triage`).

A `Triage` turns a `TriageRequest` (run id, surface, mode, and the
whitelisted egress payload) into a Contig-owned `TriageResult`. The default
seam is `NullTriage` -- the "no triage" result -- and `default_jev_triage`
is the real, env-gated, https-only transport. Every failure mode degrades
to the Null behavior: never raise, never change caller behavior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Literal


@dataclass(frozen=True)
class TriageRequest:
    """One triage decision: a run's whitelisted payload on one surface.

    `surface` names the decision site (`qc_anomaly` for the self-heal QC
    verdict-trigger branch, `verify_concordance` for the verify-time
    concordance dispatch); `mode` is `shadow` (default when a key is present:
    everything runs, Jev is logged alongside) or `active` (below-threshold
    checks are skipped and recorded UNVERIFIED). `payload` is the R6
    whitelisted egress payload built by `build_triage_payload`.
    """

    run_id: str
    surface: Literal["qc_anomaly", "verify_concordance"]
    mode: Literal["shadow", "active"]
    payload: dict


@dataclass(frozen=True)
class TriageResult:
    """The seam's answer, always a Contig-owned shape.

    `mode` is `"null"` for the no-triage degrade (with `reason` set) or the
    request's mode (`"shadow"`/`"active"`) on a usable response. `confidence`
    is `None` when there was no triage; otherwise the overall 0-1 signal
    (mean of the check-level `items` confidences). `items` maps item ids --
    `{run_id}:{surface}:{check}`, always addressing a real check in the
    payload -- to their 0-1 confidence. `reason` is `None` on success and
    names the degrade cause (unset key, refused URL, transport failure,
    oversized/malformed response) otherwise.
    """

    mode: str
    confidence: float | None
    items: dict[str, float]
    reason: str | None


# An injectable triage callable: a TriageRequest in, a Contig-owned
# TriageResult out. The default is `NullTriage`; tests inject fakes, and the
# wiring aspect threads this seam through run/verify sites (mirrors the
# Executor/Fetcher/Sleeper injectable pattern in runner.py).
Triage = Callable[[TriageRequest], TriageResult]


def NullTriage(req: TriageRequest) -> TriageResult:
    """The default seam: "no triage", touching nothing (no env, no network)."""
    return TriageResult(mode="null", confidence=None, items={}, reason=None)


# ---------------------------------------------------------------------------
# R6: the single whitelist declaration for the egress payload
# ---------------------------------------------------------------------------

# The only keys allowed to leave the machine, in one declaration (R6). The
# run section carries numeric QC metadata (task counts, failures, repair
# attempts), the verdict string rendered, and file metadata -- sizes and
# sha256 hashes only, never paths. The check section carries each check's
# numeric `value` and shape metadata, never its `message`.
PAYLOAD_WHITELIST: dict[str, frozenset[str]] = {
    "run": frozenset(
        {
            "run_id",  # opaque per-run id, never a sample identifier
            "assay",
            "pipeline",
            "task_counts",
            "failed_tasks",
            "repair_attempts",
            "verdict",  # only the rendered string
            "files",  # container, filtered to "file" keys below
        }
    ),
    "file": frozenset({"size", "sha256"}),  # never a path, never read bytes
    "check": frozenset(
        {"check", "kind", "status", "value", "expected_range"}
    ),
}

# Run metadata keys that are strictly numeric QC metrics; everything else in
# the whitelist is a verbatim string (or the "files" container).
_NUMERIC_RUN_KEYS: frozenset[str] = frozenset(
    {"task_counts", "failed_tasks", "repair_attempts"}
)


def _is_numeric(value: object) -> bool:
    """True for a finite int/float (booleans and NaN/inf are not metrics)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _filter_file(file_meta: object) -> dict | None:
    """Reduce one file metadata entry to sizes/hashes only, or None.

    A path-only file entry is not egressable (R6: never paths) and is
    dropped entirely; an entry whose `size`/`sha256` values are not usable
    is reduced to the usable subset.
    """
    if not isinstance(file_meta, dict):
        return None
    out: dict = {}
    size = file_meta.get("size")
    if _is_numeric(size):
        out["size"] = size
    sha256 = file_meta.get("sha256")
    if isinstance(sha256, str) and len(sha256) == 64:
        out["sha256"] = sha256
    return out or None


def _filter_expected_range(entry: object) -> dict | None:
    """Keep only the numeric part of an expected-range band, or None.

    Bands like {"min": 250, "max": 500} or {"fail_below": 0.9} are numeric
    metadata; any non-numeric leaf (labels, text, paths) is dropped. An
    empty band is dropped entirely so free-text can never ride along.
    """
    if not isinstance(entry, dict):
        return None
    out = {k: v for k, v in entry.items() if _is_numeric(v)}
    return out or None


def _filter_check(check: object) -> dict | None:
    """Reduce one check dict to the whitelisted shape metadata, or None."""
    if not isinstance(check, dict):
        return None
    out: dict = {}
    for key in ("check", "kind", "status"):
        value = check.get(key)
        if isinstance(value, str):
            out[key] = value
    value = check.get("value")
    if _is_numeric(value):
        out["value"] = value
    expected_range = _filter_expected_range(check.get("expected_range"))
    if expected_range is not None:
        out["expected_range"] = expected_range
    return out or None


def build_triage_payload(run_meta: dict, checks: list[dict]) -> dict:
    """Build the whitelisted egress payload from run metadata and checks.

    Only keys named in `PAYLOAD_WHITELIST` survive; every other key (paths,
    raw-read markers, sample identifiers, messages, keys) is dropped. Values
    are type-filtered: numeric keys hold finite numbers only, string keys
    hold the verbatim string (the `verdict` string rendered), file metadata
    is reduced to size/sha256 (never paths), and `expected_range` holds
    numeric leaves only. Returns `{"run": {...}, "checks": [...]}`.
    """
    run: dict = {}
    for key, value in run_meta.items():
        if key not in PAYLOAD_WHITELIST["run"]:
            continue
        if key == "files":
            files = [
                f for f in (_filter_file(f) for f in value) if f is not None
            ] if isinstance(value, list) else []
            if files:
                run["files"] = files
            continue
        if key in _NUMERIC_RUN_KEYS:
            if _is_numeric(value):
                run[key] = value
        elif isinstance(value, str):
            run[key] = value
    checks_out = [c for c in (_filter_check(c) for c in checks) if c is not None]
    return {"run": run, "checks": checks_out}