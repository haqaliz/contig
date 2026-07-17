"""Reduction over reproduce claim results (C8 slice 1).

Phase 2 will add the reproduce engine itself here; this slice is the pure,
side-effect-free counting helper the CLI/dashboard will summarize with.
"""

from __future__ import annotations

from contig.models import ClaimResult, ClaimStatus

_STATUSES: tuple[ClaimStatus, ...] = ("reproduced", "within_tolerance", "diverged", "unverified")


def reduce_reproduction(results: list[ClaimResult]) -> dict:
    """Per-status counts over a list of claim results, plus a one-line summary.

    Pure: never mutates its input, never re-derives or upgrades a claim's status
    -- it only counts what each ClaimResult already says (mirrors the QC verdict
    contract: no silent upgrades to "reproduced").
    """
    counts = {status: 0 for status in _STATUSES}
    for result in results:
        counts[result.status] += 1

    total = len(results)
    if total == 0:
        summary = "no claims to reproduce"
    else:
        other = [f"{counts[status]} {status}" for status in _STATUSES[1:] if counts[status]]
        summary = f"{counts['reproduced']}/{total} reproduced"
        if other:
            summary += f", {', '.join(other)}"

    return {**counts, "summary": summary}
