"""Scenario driver over the REAL self-heal loop, and its scoring (C6 slice 2).

`run_heal_scenario` turns one declarative `HealScenario` into scripted seams
(executor/index_builder/poll) and drives the real `self_heal_run` end to end --
`propose` and the failure detector are never stubbed (PRD R2): this measures
the actual detect->diagnose->patch->retry loop, not a mock of it.

`evaluate_heal` runs a whole scenario corpus through the driver and tallies
outcome-match and recovery rates, mirroring the detector's own eval report
(`DetectorEvalReport`) but scored on the loop's terminal outcome instead of a
single classification.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from contig.models import (
    AttemptSpec,
    ExecutionTarget,
    HealClassScore,
    HealEvalReport,
    HealScenario,
    HealScenarioResult,
    RunSummary,
)
from contig.runner import IndexBuilder, PipelineExecutionError, default_index_builder
from contig.self_heal import _poll_approval_file, self_heal_run


def _write_attempt(trace_path: Path, attempt: AttemptSpec) -> None:
    """Write one AttemptSpec's single-task trace row + sibling run.log.

    Mirrors the `_trace(status, exit)` helper in tests/test_self_heal.py.
    """
    header = "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    row = f"1\tab/cd\t1\tNFCORE_RNASEQ:STAR_ALIGN (S1)\t{attempt.status}\t{attempt.exit}\t-\t-\t-\n"
    Path(trace_path).write_text(header + row)
    (Path(trace_path).parent / "run.log").write_text(attempt.log_text)


def _scripted_executor(scenario: HealScenario) -> Callable[[list[str], Path], int]:
    """A closure over an attempt counter that plays back `scenario.attempts` in
    order, clamped to the last attempt if the loop retries beyond what was
    declared (never IndexError)."""
    state = {"n": 0}

    def executor(cmd: list[str], trace_path: Path) -> int:
        state["n"] += 1
        index = min(state["n"], len(scenario.attempts)) - 1
        attempt = scenario.attempts[index]
        _write_attempt(trace_path, attempt)
        return attempt.exit

    return executor


def _scripted_index_builder(scenario: HealScenario) -> IndexBuilder:
    """Honor `scenario.index_builder_result`; fall back to the real default
    builder when unset (None means "no scripted outcome, use the real one")."""
    if scenario.index_builder_result is None:
        return default_index_builder

    result = scenario.index_builder_result

    def index_builder(cmd: list[str], cwd: Path) -> int:
        return 0 if result == "success" else 1

    return index_builder


def _scripted_poll(scenario: HealScenario):
    """Map `scenario.poll_decision` to the approval-poll dict the loop expects
    (`{"decision": "approve"|"reject"}` or None for a timeout); fall back to the
    real file-based poll when unset."""
    if scenario.poll_decision is None:
        return _poll_approval_file

    decision = scenario.poll_decision

    def poll(run_dir: Path, timeout_sec: float) -> dict | None:
        if decision == "timeout":
            return None
        return {"decision": decision}

    return poll


def run_heal_scenario(scenario: HealScenario, tmp_dir: Path) -> HealScenarioResult:
    """Drive the real `self_heal_run` with `scenario`'s scripted seams and score
    the terminal outcome against the scenario's expectations.

    Only executor/index_builder/poll are synthesized. `propose` and the failure
    detector are left at their real defaults (PRD R2): this measures the actual
    loop, not a mock of it.
    """
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir=str(Path(tmp_dir) / f"w-{scenario.scenario_id}"),
    )
    runs_dir = Path(tmp_dir) / "runs"

    diagnosed_class: str | None = None
    recovered = False
    actual_outcome: str | None = None

    try:
        record = self_heal_run(
            pipeline="nf-core/rnaseq",
            revision="3.26.0",
            profiles=["test", "docker"],
            target=target,
            input_paths=[],
            runs_dir=runs_dir,
            run_id=f"heal-{scenario.scenario_id}",
            executor=_scripted_executor(scenario),
            index_builder=_scripted_index_builder(scenario),
            poll=_scripted_poll(scenario),
            auto_approve=scenario.auto_approve,
            resource_ceiling=scenario.resource_ceiling,
            max_attempts=scenario.max_attempts,
            assay=scenario.assay,
        )
        recovered = RunSummary.from_events(record.events).succeeded
        if record.repair_history:
            last = record.repair_history[-1]
            actual_outcome = last.outcome
            diagnosed_class = last.diagnosis.failure_class
    except PipelineExecutionError:
        recovered = False
        actual_outcome = "no_record"
        diagnosed_class = None

    divergence: list[str] = []
    if diagnosed_class != scenario.expected_class:
        divergence.append(
            f"class: expected {scenario.expected_class!r}, got {diagnosed_class!r}"
        )
    if recovered != scenario.expected_recovered:
        divergence.append(
            f"recovered: expected {scenario.expected_recovered!r}, got {recovered!r}"
        )
    if actual_outcome != scenario.expected_outcome:
        divergence.append(
            f"outcome: expected {scenario.expected_outcome!r}, got {actual_outcome!r}"
        )

    return HealScenarioResult(
        scenario_id=scenario.scenario_id,
        diagnosed_class=diagnosed_class,
        recovered=recovered,
        actual_outcome=actual_outcome,
        matched=not divergence,
        divergence=divergence,
    )


def evaluate_heal(scenarios: list[HealScenario]) -> HealEvalReport:
    """Run the whole scenario corpus through the real self-heal loop and tally
    outcome-match and recovery rates, mirroring the detector's own eval report
    but scored on the loop's terminal outcome.
    """
    results: list[HealScenarioResult] = []
    for scenario in scenarios:
        with tempfile.TemporaryDirectory() as tmp_dir:
            results.append(run_heal_scenario(scenario, Path(tmp_dir)))

    total = len(results)
    matched = sum(1 for r in results if r.matched)
    healed = sum(1 for r in results if r.recovered)
    outcome_match_rate = matched / total if total else 0.0
    recovery_rate = healed / total if total else 0.0

    per_class: dict[str, HealClassScore] = {}
    by_class: dict[str, list[HealScenarioResult]] = {}
    for scenario, result in zip(scenarios, results):
        by_class.setdefault(scenario.expected_class, []).append(result)
    for cls, cls_results in by_class.items():
        cls_matched = sum(1 for r in cls_results if r.matched)
        cls_total = len(cls_results)
        per_class[cls] = HealClassScore(
            matched=cls_matched,
            total=cls_total,
            rate=cls_matched / cls_total if cls_total else 0.0,
        )

    mismatches = [r for r in results if not r.matched]

    return HealEvalReport(
        total=total,
        matched=matched,
        outcome_match_rate=outcome_match_rate,
        healed=healed,
        recovery_rate=recovery_rate,
        per_class=per_class,
        mismatches=mismatches,
    )
