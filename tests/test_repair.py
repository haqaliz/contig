"""Tests for the repair proposer (ARCHITECTURE §5.3).

Real code, no mocks: each case constructs a real Diagnosis and asserts the
ranked, typed Patch candidates `propose_patches` returns for it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from contig.models import Diagnosis, ExecutionTarget, Patch
from contig.repair import has_safe_patch, propose_patches
from contig.self_heal import apply_patch


def diag(failure_class: str) -> Diagnosis:
    """A minimal real Diagnosis for the given failure class."""
    return Diagnosis(failure_class=failure_class, root_cause="test", confidence=0.9)


def test_advisory_is_a_valid_patch_kind() -> None:
    # `kind="advisory"` marks human-only advice that carries no machine
    # operation -- `operation` is `{}` by design (R-Open-1): inventing a
    # descriptor key would read as an operation to the next reader, which is
    # the exact bug this kind exists to fix.
    p = Patch(
        kind="advisory",
        operation={},
        rationale="test rationale",
        risk="needs_confirmation",
        expected_signal="a human resolves it",
    )
    assert p.kind == "advisory"
    assert p.operation == {}


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


def test_reference_not_bgzf_needs_confirmation_recompresses() -> None:
    patches = propose_patches(diag("reference_not_bgzf"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "reference"
    assert p.risk == "needs_confirmation"
    assert p.operation == {"recompress_reference": True}
    assert has_safe_patch(diag("reference_not_bgzf")) is False


def test_missing_reference_needs_confirmation_swaps_reference_param() -> None:
    patches = propose_patches(diag("missing_reference"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "reference"
    assert p.risk == "needs_confirmation"
    # carries a concrete reference swap apply_patch merges into params
    assert p.operation == {"set_param": {"igenomes_ignore": True}}


def test_bad_param_needs_confirmation_sets_corrected_param() -> None:
    patches = propose_patches(diag("bad_param"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "param"
    assert p.risk == "needs_confirmation"
    # carries a concrete param change apply_patch merges into params
    assert p.operation == {"set_param": {"validate_params": False}}


def test_conda_solve_failed_is_advisory() -> None:
    # Nothing in the codebase relaxes or pins an env spec: recording this as an
    # enacted `env` patch claimed a fix that never happened. It becomes advice
    # only -- kept verbatim -- with no machine-applicable operation.
    patches = propose_patches(diag("conda_solve_failed"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "advisory"
    assert p.risk == "needs_confirmation"
    assert p.operation == {}
    assert "relax_or_pin_env" not in p.operation
    assert p.rationale == "Conda solve failed; relax or pin the environment spec."
    assert has_safe_patch(diag("conda_solve_failed")) is False


def test_download_failed_proposes_safe_retry() -> None:
    # A staging/network download is often transient: a plain retry is safe.
    patches = propose_patches(diag("download_failed"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "retry"
    assert p.risk == "safe"
    assert p.operation == {"retry": True}


def test_disk_full_is_advisory() -> None:
    # Nothing in the codebase cleans the work dir: recording this as an enacted
    # `env` patch claimed a fix that never happened. It becomes advice only --
    # kept verbatim -- with no machine-applicable operation. (Freeing space is
    # destructive too, which is separately why it could never auto-apply.)
    patches = propose_patches(diag("disk_full"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "advisory"
    assert p.risk == "needs_confirmation"
    assert p.operation == {}
    assert "clean_work_dir" not in p.operation
    assert p.rationale == "Out of disk; clean the work directory to reclaim space, then retry."
    assert has_safe_patch(diag("disk_full")) is False


def test_permission_denied_is_advisory() -> None:
    # Nothing in the codebase fixes path ownership/permissions: recording this
    # as an enacted `env` patch claimed a fix that never happened. It becomes
    # advice only -- kept verbatim -- with no machine-applicable operation.
    patches = propose_patches(diag("permission_denied"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "advisory"
    assert p.risk == "needs_confirmation"
    assert p.operation == {}
    assert "fix_permissions" not in p.operation
    assert p.rationale == "Permission denied; fix the path ownership or permissions, then retry."
    assert has_safe_patch(diag("permission_denied")) is False


def test_tool_crash_has_no_safe_automatic_patch() -> None:
    assert propose_patches(diag("tool_crash")) == []


def test_unknown_has_no_safe_automatic_patch() -> None:
    assert propose_patches(diag("unknown")) == []


def test_has_safe_patch_distinguishes_auto_apply_classes() -> None:
    assert has_safe_patch(diag("oom")) is True
    assert has_safe_patch(diag("missing_index")) is False
    assert has_safe_patch(diag("unknown")) is False


def test_platform_unsupported_is_advisory() -> None:
    # Nothing in the codebase switches to a native-arch backend: recording this
    # as an enacted `env` patch claimed a fix that never happened. It becomes
    # advice only -- kept verbatim -- with no machine-applicable operation.
    # (Retrying on the same machine won't help either, which is separately why
    # it could never auto-apply.)
    d = diag("platform_unsupported")
    patches = propose_patches(d)
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "advisory"
    assert p.risk == "needs_confirmation"
    assert p.operation == {}
    assert "use_native_arch_backend" not in p.operation
    assert p.rationale == (
        "A step's container has no image for this host's CPU architecture "
        "(e.g. nf-core amd64 images on Apple Silicon). Re-running here won't "
        "help: run on an x86_64 host or a cloud backend."
    )
    assert has_safe_patch(d) is False


def test_no_progress_proposes_safe_retry() -> None:
    # Retry is cheap: self_heal.py already passes -resume, so a stalled run
    # resumes from the last completed task rather than starting over.
    patches = propose_patches(diag("no_progress"))
    assert len(patches) == 1
    p = patches[0]
    assert p.kind == "retry"
    assert p.risk == "safe"
    assert p.operation == {"retry": True}
    assert p.rationale == "No forward progress; terminate and retry from the last completed task."
    assert p.expected_signal == "tasks progressing again"
    assert has_safe_patch(diag("no_progress")) is True


# --- Advisory-contract guard, replacing the retired inertness guard (PRD R14, R8) --

# The gap the retired guard existed to pin has closed: `clean_work_dir`,
# `fix_permissions`, `relax_or_pin_env` and `use_native_arch_backend` are no
# longer emitted at all (their classes propose `kind="advisory"` with
# `operation={}` instead), and `wait_seconds` -- the fifth -- now has a real
# consumer in self_heal.py. That tripped BOTH of the old guard's assertions at
# once, which is what a closed gap looks like; deleting the guard to get green
# would have thrown away the thing its own docstring forbade throwing away.
# This replaces it with three assertions pinning the NEW contract, so it is
# this guard's job now to go RED the moment that contract regresses:
#  1. none of the four withdrawn keys reappears in an advisory's operation;
#  2. `wait_seconds` keeps a consumer outside repair.py (the exact inverse of
#     the retired guard's consumer-side check);
#  3. `apply_patch` still refuses an advisory rather than silently no-opping.
_WITHDRAWN_OPERATIONS = (
    "clean_work_dir",           # disk_full             -- withdrawn (repair.py: advisory)
    "fix_permissions",          # permission_denied     -- withdrawn (repair.py: advisory)
    "relax_or_pin_env",         # conda_solve_failed    -- withdrawn (repair.py: advisory)
    "use_native_arch_backend",  # platform_unsupported  -- withdrawn (repair.py: advisory)
)

_ADVISORY_CLASSES = (
    "disk_full",
    "permission_denied",
    "conda_solve_failed",
    "platform_unsupported",
)


def _code_references(path: Path) -> tuple[set[str], set[str]]:
    """The (identifiers, string literals) a module's CODE mentions.

    Docstrings, bare prose strings and comments are excluded deliberately:
    `cli.py`'s heal-guard docstring names `wait_seconds` when it explains
    container_unavailable's history. Naming an operation in prose is not
    consuming it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    prose = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    identifiers: set[str] = set()
    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            identifiers.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in prose:
                strings.add(node.value)
    return identifiers, strings


def test_no_advisory_carries_a_withdrawn_operation_key() -> None:
    """Assertion 1: disk_full, permission_denied, conda_solve_failed and
    platform_unsupported must stay `kind="advisory"` with `operation={}` --
    none of the four operation keys the retired guard pinned as inert may
    reappear. RED here means one of these classes grew a machine operation
    again without a real consumer being verified for it first (which is the
    whole reason the retired guard used to fire on the proposer side).
    """
    for failure_class in _ADVISORY_CLASSES:
        patches = propose_patches(diag(failure_class))
        assert len(patches) == 1
        p = patches[0]
        assert p.kind == "advisory"
        assert p.operation == {}
        for key in _WITHDRAWN_OPERATIONS:
            assert key not in p.operation, (
                f"{failure_class}'s advisory carries withdrawn key {key!r} again -- "
                "verify a real consumer exists before treating this as progress."
            )


def test_wait_seconds_is_consumed_outside_repair_py() -> None:
    """Assertion 2: the exact inverse of the retired guard's consumer-side
    check. container_unavailable's `wait_seconds: 15` (repair.py:50) used to
    be a documented no-op for a `kind="retry"` patch; self_heal.py now sleeps
    on it before the retry (self_heal.py:1442-1448). RED here means
    `wait_seconds` lost its only consumer outside repair.py -- i.e. this
    repair went inert again.
    """
    src_root = Path(__file__).resolve().parents[1] / "src" / "contig"
    repair_py = src_root / "repair.py"
    assert repair_py.is_file(), f"src layout moved; this guard needs fixing ({src_root})"

    consumers = []
    for path in sorted(src_root.rglob("*.py")):
        if path == repair_py:
            continue
        _, strings = _code_references(path)
        if "wait_seconds" in strings:
            consumers.append(str(path.relative_to(src_root)))

    assert consumers, (
        "wait_seconds is no longer referenced as a string literal anywhere "
        "outside repair.py -- container_unavailable's wait is inert again."
    )


def test_apply_patch_raises_for_an_advisory() -> None:
    """Assertion 3: an advisory reaching `apply_patch` is a caller bug, never
    a silent no-op (design-decision.md). Narrower duplicate of
    test_self_heal.py's fuller coverage, kept here because the replaced
    guard's contract names this explicitly as part of what "advisory, not
    inert-and-hidden" means.
    """
    p = Patch(kind="advisory", operation={}, rationale="x",
               risk="needs_confirmation", expected_signal="s")
    target = ExecutionTarget(backend="local", container_runtime="docker", work_dir="w")
    with pytest.raises(ValueError, match="advisories carry no machine operation"):
        apply_patch(target, p, {})
