"""Reproduce engine for C8 slice 1: claims loader, tolerance classifier, run
engine, and the pure reduction over claim results.

A "claim" is one published numeric result (e.g. an AUC or accuracy) that a
paper/repo states. `load_claims` reads a small JSON claims file; `classify`
decides, for one claim, whether a freshly observed value reproduces it within
tolerance; `run_reproduction` drives an injected executor over the repo, reads
its results file, and classifies every claim into a `ReproduceRecord`.
"""

from __future__ import annotations

import json
import math
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from contig.benchmark import _relative_delta
from contig.models import ClaimResult, ClaimStatus, ReproduceRecord

_STATUSES: tuple[ClaimStatus, ...] = ("reproduced", "within_tolerance", "diverged", "unverified")

_DEFAULT_TOLERANCE = 0.1


class ClaimsError(ValueError):
    """Raised when a claims file is malformed or one of its claims is invalid."""


@dataclass(frozen=True)
class Claim:
    """One published numeric claim to reproduce: `id` names the metric,
    `value` is the claimed reference number, `tolerance` is the relative
    band (see `classify`) within which an observed value still counts as
    reproducing it.
    """

    id: str
    value: float
    tolerance: float = _DEFAULT_TOLERANCE


def load_claims(path: str | Path) -> list[Claim]:
    """Read a JSON claims file: a list of `{"id", "value", "tolerance"?}` objects.

    Raises `ClaimsError` on anything invalid: malformed JSON, a non-list top
    level, a claim missing `id`/`value`, a non-numeric `value` (a Python
    `bool` does not count, even though `bool` is an `int` subclass), a
    duplicate `id`, or a `tolerance <= 0`.
    """
    text = Path(path).read_text()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaimsError(f"claims file is not valid JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise ClaimsError("claims file must contain a JSON list of claim objects")

    claims: list[Claim] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ClaimsError(f"claim at index {index} must be a JSON object")
        if "id" not in item:
            raise ClaimsError(f"claim at index {index} is missing required field 'id'")
        if "value" not in item:
            raise ClaimsError(f"claim at index {index} is missing required field 'value'")

        claim_id = item["id"]
        if claim_id in seen_ids:
            raise ClaimsError(f"duplicate claim id: {claim_id!r}")
        seen_ids.add(claim_id)

        value = item["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ClaimsError(f"claim {claim_id!r} has a non-numeric 'value': {value!r}")

        tolerance = item.get("tolerance", _DEFAULT_TOLERANCE)
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
            raise ClaimsError(f"claim {claim_id!r} has a non-numeric 'tolerance': {tolerance!r}")
        if tolerance <= 0:
            raise ClaimsError(f"claim {claim_id!r} has a non-positive 'tolerance': {tolerance!r}")

        claims.append(Claim(id=claim_id, value=float(value), tolerance=float(tolerance)))

    return claims


def classify(
    claimed: float, observed: float | None, tolerance: float
) -> tuple[ClaimStatus, float | None, str]:
    """Classify one observed value against a claimed reference within tolerance.

    `delta` is the RELATIVE delta (`_relative_delta(observed, claimed)`, i.e.
    consistent with the tolerance band it is compared against, not a plain
    `observed - claimed`). `None` observed, or either value being NaN/inf,
    is always `unverified` with `delta=None` -- never `diverged`.
    """
    if observed is None:
        return "unverified", None, "claim not verified: no observed value"

    if any(math.isnan(x) or math.isinf(x) for x in (observed, claimed)):
        return (
            "unverified",
            None,
            f"claim not verified: observed={observed} or claimed={claimed} is not finite",
        )

    delta = _relative_delta(observed, claimed)

    if abs(observed - claimed) <= 1e-9:
        return "reproduced", delta, f"observed {observed} matches claimed {claimed} exactly"

    if delta <= tolerance:
        return (
            "within_tolerance",
            delta,
            f"observed {observed} is within tolerance {tolerance} of claimed {claimed} "
            f"(delta={delta})",
        )

    return (
        "diverged",
        delta,
        f"observed {observed} diverged from claimed {claimed} (delta={delta}, "
        f"tolerance={tolerance})",
    )


def run_reproduction(
    repo: str,
    run_command: str,
    claims: list[Claim],
    *,
    executor: Callable[[list[str], Path], int],
    claims_sha256: str,
    results_path: str = "results.json",
    created_at: str,
    reproduce_id: str,
) -> ReproduceRecord:
    """Drive `executor` over `repo`, then classify every claim.

    A nonzero exit code short-circuits: every claim is `unverified` and the
    results file is never read. On a zero exit, a missing or unparseable
    results file also marks every claim `unverified`; otherwise each claim's
    id is looked up in the flat `{id: number}` results map (a missing key or
    a non-numeric value, including `bool`, is `unverified`; everything else
    goes through `classify`). Extra keys in the results map that no claim
    names are ignored. `created_at`/`reproduce_id` are passed in, never
    generated here, so the record stays deterministic.
    """
    repo_path = Path(repo)
    exit_code = executor(shlex.split(run_command), repo_path)

    if exit_code != 0:
        claim_results = [
            ClaimResult(
                id=claim.id,
                status="unverified",
                claimed=claim.value,
                observed=None,
                tolerance=claim.tolerance,
                delta=None,
                message=f"run did not complete (exit {exit_code})",
            )
            for claim in claims
        ]
        return ReproduceRecord(
            reproduce_id=reproduce_id,
            repo=repo,
            run_command=run_command,
            claims_sha256=claims_sha256,
            claim_results=claim_results,
            exit_code=exit_code,
            created_at=created_at,
        )

    results_file = repo_path / results_path
    results: dict | None = None
    if results_file.exists():
        try:
            loaded = json.loads(results_file.read_text())
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            results = loaded

    claim_results = []
    for claim in claims:
        if results is None:
            claim_results.append(
                ClaimResult(
                    id=claim.id,
                    status="unverified",
                    claimed=claim.value,
                    observed=None,
                    tolerance=claim.tolerance,
                    delta=None,
                    message=f"results file '{results_path}' is missing or unparseable",
                )
            )
            continue

        if claim.id not in results:
            claim_results.append(
                ClaimResult(
                    id=claim.id,
                    status="unverified",
                    claimed=claim.value,
                    observed=None,
                    tolerance=claim.tolerance,
                    delta=None,
                    message=f"claim {claim.id!r} not found in results",
                )
            )
            continue

        raw_observed = results[claim.id]
        if isinstance(raw_observed, bool) or not isinstance(raw_observed, (int, float)):
            claim_results.append(
                ClaimResult(
                    id=claim.id,
                    status="unverified",
                    claimed=claim.value,
                    observed=None,
                    tolerance=claim.tolerance,
                    delta=None,
                    message=f"claim {claim.id!r} has a non-numeric observed value: "
                    f"{raw_observed!r}",
                )
            )
            continue

        observed = float(raw_observed)
        status, delta, message = classify(claim.value, observed, claim.tolerance)
        claim_results.append(
            ClaimResult(
                id=claim.id,
                status=status,
                claimed=claim.value,
                observed=observed,
                tolerance=claim.tolerance,
                delta=delta,
                message=message,
            )
        )

    return ReproduceRecord(
        reproduce_id=reproduce_id,
        repo=repo,
        run_command=run_command,
        claims_sha256=claims_sha256,
        claim_results=claim_results,
        exit_code=exit_code,
        created_at=created_at,
    )


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
