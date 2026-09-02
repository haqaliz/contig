"""Reproduce-eval guard (C6 fold-in, aspect guard-core: reproduce-guard).

A frozen `ReproduceScenario` set replayed through the REAL `run_reproduction`
loop -- real `load_claims`, real `classify`, real locators, real freshness
guard -- with only the executor/installer seams scripted, guarding the
per-scenario outcome-match rate against a committed baseline, the fourth guard
sibling of eval-guard / heal-guard / verify-guard.

Phase A: models + the three default data paths. Phase B: the scenario driver
(`run_reproduce_scenario`) and the per-claim locator-family helper
(`claim_family`). Phase C: the scorer (`evaluate_reproduce`), snapshot builder,
baseline save/load, the pure comparator, and the JSONL scenario loader --
mirroring verify_corpus.py's shape.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from os import PathLike
from pathlib import Path

from pydantic import ValidationError

from contig.models import (
    ExecStep,
    FamilyScore,
    ReproduceRecord,
    ReproduceScenario,
    ReproduceSnapshot,
)
from contig.runner import Installer, default_installer
from contig.verification.reproduce import (
    Claim,
    Locator,
    NotebookLocator,
    PatternLocator,
    TableLocator,
    load_claims,
    run_reproduction,
)

# Deterministic replay identity (repo-wide convention, mirrors the
# env-resurrection fixtures): run_started_at is injected by the caller, and
# the rest of the record identity is pinned so the guard never depends on
# wall-clock time or generated ids.
_CLAIMS_SHA256 = "a" * 64
_CREATED_AT = "2026-07-18T00:00:00Z"
_REPRODUCE_ID = "rp_1"

# Frozen scenarios live in the repo, so they can never embed a machine-specific
# interpreter path. A leading sentinel in `installer_expected_argv` argv[0]
# resolves to the replay-time interpreter; every other element is compared
# verbatim, so the fixed `-m pip install <package>` tail stays byte-exact.
_SYS_EXECUTABLE_SENTINEL = "<sys.executable>"


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


def claim_family(claim: Claim) -> str:
    """The locator family of one claim: `flat` (no locator) or the locator
    class's family (`json`/`table`/`pattern`/`notebook`). Explicit isinstance
    chain, mirroring `run_reproduction`'s observer dispatch -- a `PatternLocator`
    is never confused with a `Locator`. Pure, no I/O.
    """
    if claim.locator is None:
        return "flat"
    if isinstance(claim.locator, NotebookLocator):
        return "notebook"
    if isinstance(claim.locator, TableLocator):
        return "table"
    if isinstance(claim.locator, PatternLocator):
        return "pattern"
    return "json"


def run_reproduce_scenario(
    scenario: ReproduceScenario,
    *,
    repo_dir: Path,
    run_started_at: float,
    installer: Installer = default_installer,
) -> tuple[ReproduceRecord, list[Claim]]:
    """Replay one scenario through the REAL `run_reproduction`.

    The scenario's inline `claims` are written to `<repo_dir>/claims.json` and
    validated through the real `load_claims` -- never constructed by hand, so a
    `ClaimsError` propagates loudly as a scenario bug. A scripted executor pops
    `scenario.executor_steps` in call order, writing each step's
    `write_results` as the scenario's results file and `write_artifacts` as
    repo-relative files, then `os.utime`-stamping every written path to
    `artifact_mtimes.get(path, run_started_at)` (the shipped `>=` boundary:
    mtime == stamp passes the freshness guard, mtime < stamp is UNVERIFIED).
    A scripted installer pops `scenario.installer_steps` (rc per step); when
    the scenario gives no steps the closure returns rc 1 -- an install that
    fails is the honest fallback, so a scenario that does not script an
    install outcome can never silently heal. When `installer_expected_argv` is
    present, each install call also pops one expected argv and asserts
    `cmd == expected` (the resolved pip target must reach the seam verbatim);
    a mismatch or an over-draw is a loud `AssertionError` scenario bug, never
    a silent fallback. A leading `"<sys.executable>"` in an expected argv
    resolves to the replay-time interpreter (frozen scenarios cannot embed a
    machine-specific interpreter path); every other element -- including any
    other argv[0] -- is compared verbatim, so the fixed
    `-m pip install <package>` tail must match byte-for-byte. An unexpected
    extra executor call raises `AssertionError` (loud scenario bug).
    `installer` is accepted for signature parity with `run_reproduction`'s
    seam; the driver always scripts the scenario's own steps and never runs a
    real pip.
    """
    repo_dir = Path(repo_dir)
    repo_dir.mkdir(parents=True, exist_ok=True)

    claims_path = repo_dir / "claims.json"
    claims_path.write_text(json.dumps(scenario.claims))
    claims = load_claims(claims_path)

    steps = list(scenario.executor_steps)

    def scripted_executor(argv: list[str], cwd: Path) -> tuple[int, str]:
        if not steps:
            raise AssertionError(
                "executor called more times than the scenario's "
                f"{len(scenario.executor_steps)} executor_steps"
            )
        step = steps.pop(0)

        written: list[tuple[str, Path]] = []
        if step.write_results is not None:
            target = cwd / scenario.results_path
            target.write_text(json.dumps(step.write_results))
            written.append((scenario.results_path, target))
        if step.write_artifacts:
            for relpath, content in step.write_artifacts.items():
                target = cwd / relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                written.append((relpath, target))

        for relpath, target in written:
            mtimes = step.artifact_mtimes or {}
            mtime = mtimes.get(relpath, run_started_at)
            os.utime(target, (mtime, mtime))

        return step.exit_code, step.output

    install_rcs = list(scenario.installer_steps) if scenario.installer_steps else []
    expected_argv = (
        list(scenario.installer_expected_argv)
        if scenario.installer_expected_argv
        else None
    )

    def scripted_installer(cmd: list[str], cwd: Path) -> int:
        if expected_argv is not None:
            # A scenario that declares expected install argv asserts it: the
            # resolved pip target must arrive at the installer seam verbatim.
            # A mismatch or an over-draw is a scenario bug -- loud, never a
            # silent fallback (mirrors the executor's extra-call posture).
            if not expected_argv:
                raise AssertionError(
                    f"installer called more times than the scenario's "
                    f"{len(scenario.installer_expected_argv)} installer_expected_argv "
                    f"entries (scenario {scenario.scenario_id})"
                )
            expected = expected_argv.pop(0)
            if expected[:1] == [_SYS_EXECUTABLE_SENTINEL]:
                expected = [sys.executable, *expected[1:]]
            if cmd != expected:
                raise AssertionError(
                    f"installer argv mismatch in scenario {scenario.scenario_id}: "
                    f"expected {expected!r}, got {cmd!r}"
                )
        if not install_rcs:
            return 1
        return install_rcs.pop(0)

    record = run_reproduction(
        repo=str(repo_dir),
        run_command=scenario.run_command,
        claims=claims,
        executor=scripted_executor,
        claims_sha256=_CLAIMS_SHA256,
        results_path=scenario.results_path,
        created_at=_CREATED_AT,
        run_started_at=run_started_at,
        reproduce_id=_REPRODUCE_ID,
        allow_install=scenario.allow_install,
        installer=scripted_installer,
    )
    return record, claims


# --- scorer, snapshot, comparator, baseline I/O (Phase C, mirrors ---------------
# --- verify_corpus.py's evaluate_verify/save_verify_baseline/compare) ----------


def evaluate_reproduce(
    scenarios: list[ReproduceScenario],
    *,
    run_started_at: float = 1_000_000.0,
) -> dict:
    """Replay every scenario through the REAL `run_reproduction` loop and score
    each against its expectations (one temp repo dir per scenario).

    A scenario matches only when EVERY expected claim status equals the
    observed status (strict equality: `unverified` never equals `reproduced`,
    and an expected claim id with NO observed result is a mismatch, never a
    pass), AND the expected repair equals `record.repair_history[-1].outcome`
    (`"none"` when there is no repair history), AND the expected exit code
    equals `record.exit_code`. `known_miss` scenarios are scored as ordinary
    matches/mismatches -- metadata only, never special-cased.

    The report carries the guarded `outcome_match_rate` (matched / total),
    an informational `recovery_rate` (scenarios whose observed repair is
    `installed_and_retried` / total), per-claim per-family rates (a claim
    counts as matched when its observed status equals its expected status,
    accumulated across scenarios, via `claim_family` on the replayed claims),
    and the sorted `covered_families`. Deterministic: one `run_started_at` is
    injected into every replay, never wall-clock time.
    """
    scenario_results: list[dict] = []
    per_family: dict[str, FamilyScore] = {}
    matched_count = 0
    healed = 0
    total = len(scenarios)

    for scenario in scenarios:
        with tempfile.TemporaryDirectory() as tmp_dir:
            record, claims = run_reproduce_scenario(
                scenario,
                repo_dir=Path(tmp_dir),
                run_started_at=run_started_at,
            )

        observed_claim_statuses = {r.id: r.status for r in record.claim_results}
        observed_repair = (
            record.repair_history[-1].outcome if record.repair_history else "none"
        )
        observed_exit_code = record.exit_code

        mismatches: dict[str, tuple] = {}
        for claim_id, expected_status in scenario.expected_claim_statuses.items():
            if expected_status != observed_claim_statuses.get(claim_id):
                mismatches[f"claim:{claim_id}"] = (
                    expected_status,
                    observed_claim_statuses.get(claim_id),
                )
        if scenario.expected_repair != observed_repair:
            mismatches["repair"] = (scenario.expected_repair, observed_repair)
        if scenario.expected_exit_code != observed_exit_code:
            mismatches["exit_code"] = (scenario.expected_exit_code, observed_exit_code)

        is_matched = not mismatches
        if is_matched:
            matched_count += 1
        if observed_repair == "installed_and_retried":
            healed += 1

        scenario_results.append(
            {
                "scenario_id": scenario.scenario_id,
                "matched": is_matched,
                "mismatches": mismatches,
            }
        )

        family_by_id = {claim.id: claim_family(claim) for claim in claims}
        for claim_id, expected_status in scenario.expected_claim_statuses.items():
            family = family_by_id.get(claim_id)
            if family is None:
                continue
            score = per_family.get(family)
            if score is None:
                score = per_family[family] = FamilyScore(matched=0, total=0, rate=0.0)
            score.total += 1
            if observed_claim_statuses.get(claim_id) == expected_status:
                score.matched += 1

    for score in per_family.values():
        score.rate = score.matched / score.total if score.total else 0.0

    return {
        "scenario_results": scenario_results,
        "matched_count": matched_count,
        "total_count": total,
        "outcome_match_rate": matched_count / total if total else 0.0,
        "healed_count": healed,
        "recovery_rate": healed / total if total else 0.0,
        "per_family": per_family,
        "covered_families": sorted(per_family),
    }


def snapshot_from_reproduce_report(
    report: dict,
    corpus_sha: str,
    contig_version: str,
    *,
    timestamp: str | None = None,
) -> ReproduceSnapshot:
    """Build a ReproduceSnapshot from a reproduce-eval report plus the corpus
    identity.

    `timestamp` defaults to now(UTC).isoformat() (the sibling CLI convention);
    `corpus_sha` and `contig_version` are computed/passed by the caller so this
    stays a pure projection of the report -- mirrors
    `verify_corpus.py:snapshot_from_verify_report`.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    return ReproduceSnapshot(
        timestamp=timestamp,
        scenario_count=report["total_count"],
        corpus_sha=corpus_sha,
        outcome_match_rate=report["outcome_match_rate"],
        recovery_rate=report["recovery_rate"],
        per_family=report["per_family"],
        covered_families=report["covered_families"],
        contig_version=contig_version,
    )


def save_reproduce_baseline(
    snapshot: ReproduceSnapshot, path: str | PathLike[str]
) -> None:
    """Write the baseline as one pretty-printed JSON object (diffs cleanly)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(snapshot.model_dump_json(indent=2) + "\n")


def load_reproduce_baseline(path: str | PathLike[str]) -> ReproduceSnapshot | None:
    """Read the committed baseline; a missing file means "no baseline yet"."""
    p = Path(path)
    if not p.exists():
        return None
    return ReproduceSnapshot.model_validate_json(p.read_text())


def compare_reproduce_to_baseline(
    snapshot: ReproduceSnapshot,
    baseline: ReproduceSnapshot,
    *,
    tolerance: float = 1e-9,
) -> tuple[str, str]:
    """Compare a reproduce-eval snapshot to the committed baseline (pure, no
    I/O) and return (status, message).

    A real drop below `baseline.outcome_match_rate - tolerance` is
    `regressed`; a real rise above `baseline.outcome_match_rate + tolerance`
    is `improved`; the tolerance band between the two absorbs float noise so
    an unchanged rate is `pass` (the default `1e-9` mirrors verify-guard's
    CLI). `sha_mismatch` (the snapshot's corpus_sha differs from the
    baseline's) and `version_mismatch` (the contig versions differ) are
    informational warnings appended to the message -- the rate comparison
    still decides the status, exactly as `verify_corpus.py:compare_verify_to_baseline`
    keeps sha_mismatch informational.
    """
    if baseline is None:
        return ("pass", "no reproduce baseline recorded; run --update-baseline")

    delta = snapshot.outcome_match_rate - baseline.outcome_match_rate
    delta_pp = delta * 100
    regressed = snapshot.outcome_match_rate < baseline.outcome_match_rate - tolerance
    improved = snapshot.outcome_match_rate > baseline.outcome_match_rate + tolerance

    if regressed:
        message = (
            f"REGRESSION: outcome-match {snapshot.outcome_match_rate:.1%} below "
            f"baseline {baseline.outcome_match_rate:.1%} (delta {delta_pp:+.1f}pp)"
        )
        status = "regressed"
    elif improved:
        message = (
            f"improved: outcome-match {snapshot.outcome_match_rate:.1%} above "
            f"baseline {baseline.outcome_match_rate:.1%} (delta {delta_pp:+.1f}pp)"
        )
        status = "improved"
    else:
        message = (
            f"reproduce-guard PASS: outcome-match {snapshot.outcome_match_rate:.1%} "
            f"\u2265 baseline {baseline.outcome_match_rate:.1%}"
        )
        status = "pass"

    warnings: list[str] = []
    if snapshot.corpus_sha != baseline.corpus_sha:
        warnings.append(
            f"corpus sha mismatch ({snapshot.corpus_sha[:12]}... != "
            f"{baseline.corpus_sha[:12]}...) -- the delta crosses different scenario sets"
        )
    if snapshot.contig_version != baseline.contig_version:
        warnings.append(
            f"contig version mismatch ({snapshot.contig_version} != "
            f"{baseline.contig_version})"
        )
    if warnings:
        message += "; " + "; ".join(warnings)

    return status, message


def load_reproduce_scenarios(path: str | PathLike[str]) -> list[ReproduceScenario]:
    """Read a JSONL reproduce scenario set back into ReproduceScenario objects.

    Blank and malformed lines are skipped (verify_corpus.py precedent), so a
    hand-edited or half-written file never crashes the guard.
    """
    text = Path(path).read_text()
    scenarios: list[ReproduceScenario] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            scenarios.append(ReproduceScenario.model_validate_json(line))
        except ValidationError:
            continue  # skip a malformed/half-written line; rest is valid
    return scenarios
