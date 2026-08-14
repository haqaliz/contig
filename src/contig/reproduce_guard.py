"""Reproduce-eval guard (C6 fold-in, aspect guard-core: reproduce-guard).

A frozen `ReproduceScenario` set replayed through the REAL `run_reproduction`
loop -- real `load_claims`, real `classify`, real locators, real freshness
guard -- with only the executor/installer seams scripted, guarding the
per-scenario outcome-match rate against a committed baseline, the fourth guard
sibling of eval-guard / heal-guard / verify-guard.

Phase A: models + the three default data paths. Phase B: the scenario driver
(`run_reproduce_scenario`) and the per-claim locator-family helper
(`claim_family`); the scorer and comparator land in later phases, mirroring
verify_corpus.py's shape.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from contig.models import ExecStep, ReproduceRecord, ReproduceScenario
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
    install outcome can never silently heal. An unexpected extra executor call
    raises `AssertionError` (loud scenario bug). `installer` is accepted for
    signature parity with `run_reproduction`'s seam; the driver always scripts
    the scenario's own steps and never runs a real pip.
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

    def scripted_installer(cmd: list[str], cwd: Path) -> int:
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
