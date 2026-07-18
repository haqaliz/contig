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
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from contig.benchmark import _relative_delta
from contig.models import (
    ClaimResult,
    ClaimStatus,
    Diagnosis,
    Patch,
    RepairStep,
    ReproduceRecord,
)
from contig.runner import Installer, _pip_install_argv, default_installer

_STATUSES: tuple[ClaimStatus, ...] = ("reproduced", "within_tolerance", "diverged", "unverified")

_DEFAULT_TOLERANCE = 0.1

_MISSING_MODULE_RE = re.compile(r"No module named ['\"]([^'\"]+)['\"]", re.IGNORECASE)
_SAFE_PACKAGE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def detect_missing_module(output: str) -> str | None:
    """Extract the missing top-level package from a run's captured error text.

    Scans for a `No module named 'X'` message (as emitted by ModuleNotFoundError /
    ImportError) and returns X's top-level package (`sklearn.utils` -> `sklearn`).
    Returns None when nothing matches or the token is not a safe package name.
    Pure, no I/O.
    """
    match = _MISSING_MODULE_RE.search(output)
    if match is None:
        return None
    module = match.group(1).split(".")[0]
    if not _SAFE_PACKAGE_TOKEN_RE.match(module):
        return None
    return module


def _parse_path(expr: str) -> list[str | int] | None:
    """Tokenize a dotted+[n] path into keys (str) and indices (int).

    Leading '$' and one leading '.' are stripped. Returns None on any
    malformed expression -- the caller treats None as "unresolved".
    """
    s = expr.strip()
    if s.startswith("$"):
        s = s[1:]
    if s.startswith("."):
        s = s[1:]
    if not s:
        return None
    tokens: list[str | int] = []
    i, n = 0, len(s)
    first = True
    while i < n:
        c = s[i]
        if c == "[":
            j = s.find("]", i)
            if j == -1:
                return None
            inner = s[i + 1 : j]
            if not inner.isdecimal():  # rejects empty, sign, spaces, non-digit;
                # isdecimal() (not isdigit()) so every accepted char is one
                # int() actually parses -- e.g. "²".isdigit() is True but
                # int("²") raises ValueError
                return None
            tokens.append(int(inner))
            i = j + 1
        elif c == ".":
            if first:
                return None
            i += 1
            if i >= n or s[i] in ".[":
                return None
            start = i
            while i < n and s[i] not in ".[":
                i += 1
            tokens.append(s[start:i])
        else:  # a bare key -- only valid as the very first accessor
            if not first:
                return None
            start = i
            while i < n and s[i] not in ".[":
                i += 1
            tokens.append(s[start:i])
        first = False
    return tokens or None


def resolve_pointer(data: object, expr: str) -> object | None:
    """Walk `data` (nested dict/list from parsed JSON) by `expr`.

    Any unresolved step -> None. Never raises. Never guesses.
    """
    tokens = _parse_path(expr)
    if tokens is None:
        return None
    cur = data
    for tok in tokens:
        if isinstance(tok, int):
            if isinstance(cur, list) and 0 <= tok < len(cur):
                cur = cur[tok]
            else:
                return None
        else:
            if isinstance(cur, dict) and tok in cur:
                cur = cur[tok]
            else:
                return None
    return cur


class ClaimsError(ValueError):
    """Raised when a claims file is malformed or one of its claims is invalid."""


@dataclass(frozen=True)
class Locator:
    """Where to find a located claim's observed value: `source` is the
    claims file's `"from"` field (a repo-relative JSON file path -- named
    `source` internally because `from` is a Python keyword), `path` is the
    dotted+`[n]` pointer into that file's parsed JSON, resolved via
    `resolve_pointer`.
    """

    source: str
    path: str


@dataclass(frozen=True)
class Claim:
    """One published numeric claim to reproduce: `id` names the metric,
    `value` is the claimed reference number, `tolerance` is the relative
    band (see `classify`) within which an observed value still counts as
    reproducing it. `locator`, when set, means this claim's observed value
    is bound from its own repo-relative JSON file at a path rather than
    from the flat `--results` map (slice-1 behavior, `locator=None`).
    """

    id: str
    value: float
    tolerance: float = _DEFAULT_TOLERANCE
    locator: Locator | None = None


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

        has_from, has_path = "from" in item, "path" in item
        if has_from != has_path:
            raise ClaimsError(
                f"claim {claim_id!r} must set both 'from' and 'path', or neither"
            )
        locator: Locator | None = None
        if has_from:
            raw_from, raw_path = item["from"], item["path"]
            if not isinstance(raw_from, str) or not raw_from.strip():
                raise ClaimsError(f"claim {claim_id!r} has an invalid 'from': {raw_from!r}")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ClaimsError(f"claim {claim_id!r} has an invalid 'path': {raw_path!r}")
            locator = Locator(source=raw_from, path=raw_path)

        claims.append(
            Claim(
                id=claim_id,
                value=float(value),
                tolerance=float(tolerance),
                locator=locator,
            )
        )

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
    executor: Callable[[list[str], Path], tuple[int, str]],
    claims_sha256: str,
    results_path: str = "results.json",
    created_at: str,
    reproduce_id: str,
    allow_install: bool = False,
    installer: Installer = default_installer,
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

    When the first run fails (nonzero exit) and `allow_install` is True, this
    makes one bounded env-resurrection attempt: detect a missing Python
    module in the run's output (`detect_missing_module`), install it via
    `installer`, and retry the run exactly once. There is no loop -- at most
    one install and one retry, ever, even if the retried run names a
    different missing module. `repair_history` records what happened (empty
    when `allow_install` is False, or when no installable module was
    detected). The final `exit_code` on the record is always the LAST run's
    exit code (the retried one, if a retry happened).
    """
    repo_path = Path(repo)
    repo_root = repo_path.resolve()
    _json_cache: dict[str, object | None] = {}

    def _observe_located(loc: Locator) -> tuple[float | None, str]:
        """Bind one located claim's observed value from its own repo-relative
        JSON file at `loc.path`. Never reads outside the repo (containment
        guard below); every resolution failure returns `(None, message)`
        rather than raising -- the caller always maps that to `unverified`.
        """
        resolved = (repo_path / loc.source).resolve()
        try:
            resolved.relative_to(repo_root)  # defense-in-depth: never read outside repo
        except ValueError:
            return None, f"locator 'from' {loc.source!r} escapes the repo"

        key = str(resolved)
        if key not in _json_cache:
            parsed: object | None = None
            if resolved.exists():
                try:
                    parsed = json.loads(resolved.read_text())
                except (ValueError, OSError):
                    # ValueError covers json.JSONDecodeError (already a
                    # ValueError subclass) and UnicodeDecodeError raised by
                    # read_text() on a non-UTF-8 file (also a ValueError
                    # subclass, NOT an OSError) -- both are "unparseable".
                    parsed = None
            _json_cache[key] = parsed

        if not resolved.exists():
            return None, f"locator file {loc.source!r} is missing"

        parsed = _json_cache[key]
        if parsed is None:
            return None, f"locator file {loc.source!r} is not valid JSON"

        target = resolve_pointer(parsed, loc.path)
        if target is None:
            return None, f"locator path {loc.path!r} did not resolve in {loc.source!r}"

        if isinstance(target, bool) or not isinstance(target, (int, float)):
            return None, (
                f"locator value at {loc.path!r} in {loc.source!r} is not a number: {target!r}"
            )

        if math.isnan(target) or math.isinf(target):
            return None, (
                f"locator value at {loc.path!r} in {loc.source!r} is not finite: {target!r}"
            )

        return float(target), ""

    exit_code, run_output = executor(shlex.split(run_command), repo_path)
    repair_history: list[RepairStep] = []

    if exit_code != 0 and allow_install:
        module = detect_missing_module(run_output)
        if module is not None:
            diagnosis = Diagnosis(
                failure_class="missing_dependency",
                root_cause=f"missing Python module {module!r}",
                evidence=[run_output[:500]],
                confidence=0.8,
            )
            patch = Patch(
                kind="env",
                operation={"install": module},
                rationale=f"install {module} and retry",
                risk="needs_confirmation",
                expected_signal="run exits 0 after install",
            )
            install_rc = installer(_pip_install_argv(module), repo_path)
            if install_rc != 0:
                repair_history.append(
                    RepairStep(
                        attempt=1,
                        diagnosis=diagnosis,
                        patch=patch,
                        outcome="install_failed",
                        detail=f"pip install {module} exited {install_rc}",
                    )
                )
            else:
                # Bounded: exactly one retry, no re-detection afterwards -- even
                # if the retried output names a different missing module, we do
                # not install again.
                exit_code, run_output = executor(shlex.split(run_command), repo_path)
                if exit_code != 0:
                    repair_history.append(
                        RepairStep(
                            attempt=1,
                            diagnosis=diagnosis,
                            patch=patch,
                            outcome="retry_failed",
                            detail=f"installed {module}; retry exited {exit_code}",
                        )
                    )
                else:
                    repair_history.append(
                        RepairStep(
                            attempt=1,
                            diagnosis=diagnosis,
                            patch=patch,
                            outcome="installed_and_retried",
                            detail=f"installed {module}; retry exited 0",
                        )
                    )
        # module is None: no installable module detected -- nothing to record,
        # honest UNVERIFIED via the short-circuit below.

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
            repair_history=repair_history,
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
        if claim.locator is not None:
            observed, fail_msg = _observe_located(claim.locator)
            if observed is None:
                claim_results.append(
                    ClaimResult(
                        id=claim.id,
                        status="unverified",
                        claimed=claim.value,
                        observed=None,
                        tolerance=claim.tolerance,
                        delta=None,
                        message=fail_msg,
                    )
                )
                continue

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
            continue

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
        repair_history=repair_history,
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
