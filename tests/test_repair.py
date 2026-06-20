"""Tests for the repair proposer (ARCHITECTURE §5.3).

Real code, no mocks: each case constructs a real Diagnosis and asserts the
ranked, typed Patch candidates `propose_patches` returns for it.
"""

from __future__ import annotations

from contig.models import Diagnosis
from contig.repair import has_safe_patch, propose_patches


def diag(failure_class: str) -> Diagnosis:
    """A minimal real Diagnosis for the given failure class."""
    return Diagnosis(failure_class=failure_class, root_cause="test", confidence=0.9)


def test_oom_proposes_safe_memory_increase() -> None:
    patches = propose_patches(diag("oom"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "resource"
    assert p.risk == "safe"
    assert p.operation == {"multiply": {"memory": 2}}


def test_time_limit_proposes_safe_time_increase() -> None:
    patches = propose_patches(diag("time_limit"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "resource"
    assert p.risk == "safe"
    assert p.operation == {"multiply": {"time": 2}}


def test_container_pull_failed_proposes_safe_retry() -> None:
    patches = propose_patches(diag("container_pull_failed"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "retry"
    assert p.risk == "safe"
    assert p.operation == {"retry": True}


def test_container_unavailable_proposes_safe_retry_with_wait() -> None:
    patches = propose_patches(diag("container_unavailable"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "retry"
    assert p.risk == "safe"
    assert p.operation == {"retry": True, "wait_seconds": 15}


def test_missing_index_needs_confirmation_build() -> None:
    patches = propose_patches(diag("missing_index"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "reference"
    assert p.risk == "needs_confirmation"
    assert p.operation == {"build_index": True}


def test_missing_reference_needs_confirmation_resolve() -> None:
    patches = propose_patches(diag("missing_reference"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "reference"
    assert p.risk == "needs_confirmation"
    assert p.operation == {"resolve_reference": True}


def test_bad_param_needs_confirmation_review() -> None:
    patches = propose_patches(diag("bad_param"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "param"
    assert p.risk == "needs_confirmation"
    assert p.operation == {"review_param": True}


def test_conda_solve_failed_needs_confirmation_env() -> None:
    patches = propose_patches(diag("conda_solve_failed"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "env"
    assert p.risk == "needs_confirmation"
    assert p.operation == {"relax_or_pin_env": True}


def test_tool_crash_has_no_safe_automatic_patch() -> None:
    assert propose_patches(diag("tool_crash")) == []


def test_unknown_has_no_safe_automatic_patch() -> None:
    assert propose_patches(diag("unknown")) == []


def test_has_safe_patch_distinguishes_auto_apply_classes() -> None:
    assert has_safe_patch(diag("oom")) is True
    assert has_safe_patch(diag("missing_index")) is False
    assert has_safe_patch(diag("unknown")) is False


def test_platform_unsupported_proposes_needs_confirmation_not_safe() -> None:
    d = diag("platform_unsupported")
    patches = propose_patches(d)
    assert patches and patches[0].risk == "needs_confirmation"
    # retrying on the same machine won't help, so it must NOT auto-apply
    assert has_safe_patch(d) is False
