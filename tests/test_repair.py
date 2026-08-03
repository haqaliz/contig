"""Tests for the repair proposer (ARCHITECTURE §5.3).

Real code, no mocks: each case constructs a real Diagnosis and asserts the
ranked, typed Patch candidates `propose_patches` returns for it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from contig.models import Diagnosis, Patch
from contig.repair import has_safe_patch, propose_patches


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


# --- Gap-pinning guard over the inert repairs (PRD R14) ----------------------

# The five operations `propose_patches` emits that nothing consumes, each with
# the class that proposes it and the repair.py line it is emitted from.
_INERT_OPERATIONS = (
    "clean_work_dir",           # disk_full             (repair.py:145)
    "fix_permissions",          # permission_denied     (repair.py:169)
    "relax_or_pin_env",         # conda_solve_failed    (repair.py:123)
    "use_native_arch_backend",  # platform_unsupported  (repair.py:109)
    "wait_seconds",             # container_unavailable (repair.py:50)
)

# `lifecycle.py` uses the bare name `wait_seconds` for an unrelated SIGTERM
# grace period (verified: it is the only such collision among the five), so for
# that one -- and only that one -- the scan narrows to the string-literal form,
# which is how a real consumer would read it back out of `patch.operation`.
# Narrowing is what keeps this guard from being a permanent false positive;
# dropping the name outright would leave container_unavailable's inertness
# unpinned.
_STRING_LITERAL_ONLY = frozenset({"wait_seconds"})


def _code_references(path: Path) -> tuple[set[str], set[str]]:
    """The (identifiers, string literals) a module's CODE mentions.

    Docstrings, bare prose strings and comments are excluded deliberately:
    `cli.py`'s heal-guard docstring names all five of these operations when it
    explains why their classes are uncovered, and so does the guard below.
    Naming an operation in prose is not consuming it.
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


def test_five_inert_patch_operations_are_still_consumed_by_nothing() -> None:
    """This test exists to FAIL when the gap closes. That is its whole point.

    `propose_patches` emits an operation for disk_full, permission_denied,
    conda_solve_failed, platform_unsupported and container_unavailable -- and
    nothing else in `src/contig/` reads any of them. The four `env` ones are
    string-merged into `ExecutionTarget.backend_options`
    (`self_heal.py:583-586`), out of which `nfconfig.py` reads only
    queue/region/partition/account/qos/time. `wait_seconds` rides on a
    `kind="retry"` patch, for which `apply_patch` is a documented no-op, so the
    "wait briefly and retry" its rationale promises never happens.

    That inertness is why the catalog-coverage slice froze scenarios for 11
    failure classes and not 16: freezing an inert repair's outcome into CI would
    have pinned five suspect expectations as correct.

    RED means the situation changed -- an operation grew a consumer
    (implemented) or left `repair.py` (withdrawn). Either way that is the FIRST
    of the two revisit triggers in
    `docs/planning/heal-scenarios-catalog-coverage/prd.md` ("Revisit trigger,
    both directions"), so do not delete this test to get green. Revisit the
    deferral reason in the same commit, correct the heal-guard honest-scope
    docstring in `cli.py`, and give the now-live class a heal scenario.
    """
    src_root = Path(__file__).resolve().parents[1] / "src" / "contig"
    repair_py = src_root / "repair.py"
    assert repair_py.is_file(), f"src layout moved; this guard needs fixing ({src_root})"

    # A rename would otherwise make the guard silently vacuous, so pin the
    # proposer side first: every operation must still be emitted from repair.py.
    _, repair_strings = _code_references(repair_py)
    assert set(_INERT_OPERATIONS) <= repair_strings, (
        "An inert operation is no longer emitted by repair.py: "
        f"{sorted(set(_INERT_OPERATIONS) - repair_strings)}. If it was withdrawn, "
        "that is revisit trigger #1 -- update this guard and the cli.py docstring."
    )

    consumers: dict[str, list[str]] = {}
    for path in sorted(src_root.rglob("*.py")):
        if path == repair_py:
            continue
        identifiers, strings = _code_references(path)
        for op in _INERT_OPERATIONS:
            if op in strings or (op not in _STRING_LITERAL_ONLY and op in identifiers):
                consumers.setdefault(op, []).append(str(path.relative_to(src_root)))

    assert consumers == {}, (
        "An inert patch operation is now referenced outside repair.py: "
        f"{consumers}. If it was implemented, the class it repairs is no longer "
        "inert -- that is revisit trigger #1 in the catalog-coverage PRD. Revisit "
        "the deferral, correct cli.py's heal-guard honest-scope docstring, and add "
        "a heal scenario for the class before relaxing this guard."
    )
