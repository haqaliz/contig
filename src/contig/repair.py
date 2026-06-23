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
                # Disable the igenomes lookup so the pipeline uses the locally
                # staged reference instead of a remote build it could not find.
                # set_param carries the concrete swap apply_patch merges into params.
                operation={"set_param": {"igenomes_ignore": True}},
                rationale="Reference genome missing; ignore igenomes and use the local reference.",
                risk="needs_confirmation",
                expected_signal="reference resolved",
            )
        ]
    if diagnosis.failure_class == "bad_param":
        return [
            Patch(
                kind="param",
                # Relax nf-core's strict parameter-schema validation so the run
                # proceeds past the rejected value. set_param carries the concrete
                # change apply_patch merges into the run params.
                operation={"set_param": {"validate_params": False}},
                rationale="A parameter was rejected; relax strict schema validation and retry.",
                risk="needs_confirmation",
                expected_signal="parameter accepted",
            )
        ]
    if diagnosis.failure_class == "platform_unsupported":
        return [
            Patch(
                kind="env",
                operation={"use_native_arch_backend": True},
                rationale=(
                    "A step's container has no image for this host's CPU architecture "
                    "(e.g. nf-core amd64 images on Apple Silicon). Re-running here won't "
                    "help: run on an x86_64 host or a cloud backend."
                ),
                risk="needs_confirmation",
                expected_signal="step runs on a native-architecture host",
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
    if diagnosis.failure_class == "download_failed":
        return [
            Patch(
                kind="retry",
                operation={"retry": True},
                rationale="A download failed (often transient); retry the staging step.",
                risk="safe",
                expected_signal="input downloaded successfully",
            )
        ]
    if diagnosis.failure_class == "disk_full":
        return [
            Patch(
                kind="env",
                # Reclaiming space deletes the work dir's intermediates: this
                # destroys data, so it can never auto-apply.
                operation={"clean_work_dir": True},
                rationale="Out of disk; clean the work directory to reclaim space, then retry.",
                risk="needs_confirmation",
                expected_signal="free disk space available",
            )
        ]
    if diagnosis.failure_class == "permission_denied":
        return [
            Patch(
                kind="env",
                # The fix is to correct the path's ownership/permissions; only a
                # human can decide and do that safely.
                operation={"fix_permissions": True},
                rationale="Permission denied; fix the path ownership or permissions, then retry.",
                risk="needs_confirmation",
                expected_signal="path writable",
            )
        ]
    return []


def has_safe_patch(diagnosis: Diagnosis) -> bool:
    """True iff a proposed patch can be auto-applied without confirmation.

    The self-heal loop uses this to decide whether to apply a fix automatically
    or pause for a human.
    """
    return any(p.risk == "safe" for p in propose_patches(diagnosis))
