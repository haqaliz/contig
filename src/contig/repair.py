"""Repair proposer: Diagnosis -> ranked candidate Patches (ARCHITECTURE §5.3).

Given a structured Diagnosis from the failure detector, emit the typed,
machine-applicable fixes worth trying, best first. Each Patch carries an
`expected_signal` so DETECT can confirm whether it worked, and a `risk` that
gates auto-application: only "safe" patches are applied without a human.
"""

from __future__ import annotations

from contig.models import Diagnosis, Patch


def propose_patches(diagnosis: Diagnosis) -> list[Patch]:
    """Ranked (best first) candidate fixes for a diagnosis."""
    if diagnosis.failure_class == "oom":
        return [
            Patch(
                kind="resource",
                operation={"multiply": {"memory": 2}},
                rationale="Out of memory; double the memory request and retry.",
                risk="safe",
                expected_signal="no OOM / exit 0",
            )
        ]
    if diagnosis.failure_class == "time_limit":
        return [
            Patch(
                kind="resource",
                operation={"multiply": {"time": 2}},
                rationale="Hit the time limit; double the time request and retry.",
                risk="safe",
                expected_signal="completes within time limit",
            )
        ]
    if diagnosis.failure_class == "container_pull_failed":
        return [
            Patch(
                kind="retry",
                operation={"retry": True},
                rationale="Image pull failed (often transient); retry the pull.",
                risk="safe",
                expected_signal="image pulled successfully",
            )
        ]
    if diagnosis.failure_class == "container_unavailable":
        return [
            Patch(
                kind="retry",
                operation={"retry": True, "wait_seconds": 15},
                rationale="Container runtime unreachable; wait briefly and retry.",
                risk="safe",
                expected_signal="container runtime reachable",
            )
        ]
    if diagnosis.failure_class == "missing_index":
        return [
            Patch(
                kind="reference",
                operation={"build_index": True},
                rationale="Index missing; build it before re-running.",
                risk="needs_confirmation",
                expected_signal="index present",
            )
        ]
    if diagnosis.failure_class == "missing_reference":
        return [
            Patch(
                kind="reference",
                operation={"resolve_reference": True},
                rationale="Reference genome missing; resolve and stage it.",
                risk="needs_confirmation",
                expected_signal="reference resolved",
            )
        ]
    if diagnosis.failure_class == "bad_param":
        return [
            Patch(
                kind="param",
                operation={"review_param": True},
                rationale="A parameter was rejected; review and correct it.",
                risk="needs_confirmation",
                expected_signal="parameter accepted",
            )
        ]
    if diagnosis.failure_class == "conda_solve_failed":
        return [
            Patch(
                kind="env",
                operation={"relax_or_pin_env": True},
                rationale="Conda solve failed; relax or pin the environment spec.",
                risk="needs_confirmation",
                expected_signal="env solved",
            )
        ]
    return []


def has_safe_patch(diagnosis: Diagnosis) -> bool:
    """True iff a proposed patch can be auto-applied without confirmation.

    The self-heal loop uses this to decide whether to apply a fix automatically
    or pause for a human.
    """
    return any(p.risk == "safe" for p in propose_patches(diagnosis))
