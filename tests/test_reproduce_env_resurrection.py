"""Tests for C8 slice 2 (environment resurrection). Accumulates this
slice's tests across tasks.

Task 1: `detect_missing_module` (pure helper) + `missing_dependency`
FailureClass literal.

Task 3: the opt-in bounded install->retry loop wired into `run_reproduction`,
plus `ReproduceRecord.repair_history`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contig.bundle import load_reproduction, write_reproduce_bundle
from contig.models import Diagnosis, ReproduceRecord
from contig.signing import generate_keypair, signing_available, verify_signature
from contig.verification.reproduce import Claim, detect_missing_module, run_reproduction

# Mirrors the fixed synthetic run-start in tests/test_reproduce.py: a 1970-era
# epoch so freshness is decided purely by mtimes we control, never wall-clock
# time.
_RUN_START = 1_000_000.0


def test_detect_missing_module_simple_top_level_package():
    assert detect_missing_module("ModuleNotFoundError: No module named 'numpy'") == "numpy"


def test_detect_missing_module_returns_top_level_only():
    assert (
        detect_missing_module("ModuleNotFoundError: No module named 'sklearn.utils'")
        == "sklearn"
    )


def test_detect_missing_module_is_case_insensitive():
    assert detect_missing_module("no module named 'Pandas'") == "Pandas"


def test_detect_missing_module_finds_error_mid_stream_in_multiline_output():
    output = """Traceback (most recent call last):
  File "run.py", line 3, in <module>
    import scipy
ModuleNotFoundError: No module named 'scipy'
some trailing log line
"""
    assert detect_missing_module(output) == "scipy"


def test_detect_missing_module_no_match_returns_none():
    assert detect_missing_module("Segmentation fault (core dumped)") is None


def test_detect_missing_module_empty_string_returns_none():
    assert detect_missing_module("") is None


def test_detect_missing_module_rejects_unsafe_token():
    assert detect_missing_module("No module named 'foo;rm -rf'") is None


def test_diagnosis_accepts_missing_dependency_failure_class():
    diagnosis = Diagnosis(failure_class="missing_dependency", root_cause="x", confidence=0.5)
    assert diagnosis.failure_class == "missing_dependency"


# ---------------------------------------------------------------------------
# Task 3: install->retry loop wired into run_reproduction()
# ---------------------------------------------------------------------------


def _claims(*specs: tuple[str, float, float]) -> list[Claim]:
    return [Claim(id=cid, value=value, tolerance=tol) for cid, value, tol in specs]


class _ScriptedExecutor:
    """Returns scripted `(exit_code, output)` tuples in call order. Optionally
    writes `results.json` (or `results_path`) into the repo on chosen 1-based
    call numbers, mirroring the injected `Callable[[list[str], Path],
    tuple[int, str]]` seam but across multiple successive invocations (the
    slice-1 fakes in test_reproduce.py only ever script a single call).
    """

    def __init__(self, script, results_by_call=None, results_path="results.json"):
        self.script = list(script)
        self.results_by_call = results_by_call or {}
        self.results_path = results_path
        self.calls = 0

    def __call__(self, argv: list[str], repo: Path) -> tuple[int, str]:
        self.calls += 1
        if self.calls in self.results_by_call:
            (Path(repo) / self.results_path).write_text(json.dumps(self.results_by_call[self.calls]))
        return self.script[self.calls - 1]


class _ScriptedInstaller:
    """Records every `(argv, cwd)` it was called with and always returns the
    same scripted exit code."""

    def __init__(self, return_code: int):
        self.return_code = return_code
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, cmd: list[str], cwd: Path) -> int:
        self.calls.append((list(cmd), cwd))
        return self.return_code


def _run(tmp_path: Path, claims: list[Claim], executor, **overrides):
    kwargs = dict(
        repo=str(tmp_path),
        run_command="python run.py",
        claims=claims,
        executor=executor,
        claims_sha256="a" * 64,
        created_at="2026-07-18T00:00:00Z",
        reproduce_id="rp_1",
        run_started_at=_RUN_START,
    )
    kwargs.update(overrides)
    return run_reproduction(**kwargs)


def test_run_reproduction_heals_after_install_and_retry(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(
        script=[
            (1, "ModuleNotFoundError: No module named 'numpy'"),
            (0, ""),
        ],
        results_by_call={2: {"auc": 0.9}},
    )
    installer = _ScriptedInstaller(return_code=0)

    record = _run(tmp_path, claims, executor, allow_install=True, installer=installer)

    assert record.claim_results[0].status == "reproduced"
    assert record.exit_code == 0
    assert len(record.repair_history) == 1
    step = record.repair_history[0]
    assert step.outcome == "installed_and_retried"
    assert step.patch is not None
    assert step.patch.operation["install"] == "numpy"
    assert len(installer.calls) == 1
    assert executor.calls == 2


def test_run_reproduction_allow_install_off_never_installs(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(
        script=[
            (1, "ModuleNotFoundError: No module named 'numpy'"),
            (0, ""),
        ],
        results_by_call={2: {"auc": 0.9}},
    )
    installer = _ScriptedInstaller(return_code=0)

    record = _run(tmp_path, claims, executor, allow_install=False, installer=installer)

    assert installer.calls == []
    assert all(r.status == "unverified" for r in record.claim_results)
    assert record.exit_code == 1
    assert record.repair_history == []
    assert executor.calls == 1


def test_run_reproduction_no_installable_module_leaves_repair_history_empty(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(script=[(1, "Segmentation fault (core dumped)")])
    installer = _ScriptedInstaller(return_code=0)

    record = _run(tmp_path, claims, executor, allow_install=True, installer=installer)

    assert installer.calls == []
    assert all(r.status == "unverified" for r in record.claim_results)
    assert record.repair_history == []
    assert executor.calls == 1


def test_run_reproduction_install_failure_short_circuits_without_retry(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(script=[(1, "No module named 'numpy'")])
    installer = _ScriptedInstaller(return_code=1)

    record = _run(tmp_path, claims, executor, allow_install=True, installer=installer)

    assert all(r.status == "unverified" for r in record.claim_results)
    assert record.exit_code == 1
    assert len(record.repair_history) == 1
    assert record.repair_history[0].outcome == "install_failed"
    assert executor.calls == 1
    assert len(installer.calls) == 1


def test_run_reproduction_retry_still_fails_records_retry_failed(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(
        script=[
            (1, "No module named 'numpy'"),
            (1, "some other error"),
        ]
    )
    installer = _ScriptedInstaller(return_code=0)

    record = _run(tmp_path, claims, executor, allow_install=True, installer=installer)

    assert all(r.status == "unverified" for r in record.claim_results)
    assert record.exit_code == 1
    assert len(record.repair_history) == 1
    assert record.repair_history[0].outcome == "retry_failed"
    assert executor.calls == 2
    assert len(installer.calls) == 1


def test_run_reproduction_does_not_chase_a_second_missing_module(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(
        script=[
            (1, "No module named 'numpy'"),
            (1, "No module named 'scipy'"),
        ]
    )
    installer = _ScriptedInstaller(return_code=0)

    record = _run(tmp_path, claims, executor, allow_install=True, installer=installer)

    assert len(installer.calls) == 1
    assert installer.calls[0][0][-1] == "numpy"
    assert all(r.status == "unverified" for r in record.claim_results)
    assert executor.calls == 2


def test_run_reproduction_classifies_against_post_retry_results_not_stale(tmp_path):
    # Stale results.json written BEFORE the run, with wrong values -- must be
    # ignored: classification must happen against the file the retried run
    # writes, not this pre-existing one.
    (tmp_path / "results.json").write_text(json.dumps({"auc": 0.1}))

    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(
        script=[
            (1, "No module named 'numpy'"),
            (0, ""),
        ],
        results_by_call={2: {"auc": 0.9}},
    )
    installer = _ScriptedInstaller(return_code=0)

    record = _run(tmp_path, claims, executor, allow_install=True, installer=installer)

    assert record.claim_results[0].status == "reproduced"
    assert record.claim_results[0].observed == 0.9


# ---------------------------------------------------------------------------
# patch_applied: did the patch's operation actually run? (R3)
#
# Truth here is `install_rc == 0`, NOT "the reproduction succeeded" -- see D2 in
# docs/planning/repair-patch-applied/prd.md. `retry_failed` is the canonical
# demonstration: the install was enacted, the retried run then failed, so the
# step is applied-but-unsuccessful.
# ---------------------------------------------------------------------------


def test_install_failure_records_patch_not_applied(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(script=[(1, "No module named 'numpy'")])
    installer = _ScriptedInstaller(return_code=1)

    record = _run(tmp_path, claims, executor, allow_install=True, installer=installer)

    step = record.repair_history[0]
    assert step.outcome == "install_failed"
    assert step.patch_applied is False
    # The patch was still PROPOSED -- the pair (patch non-null, not applied) is
    # exactly the distinction this field exists to make.
    assert step.patch is not None


def test_retry_failure_records_the_patch_as_applied(tmp_path):
    # The sharp case: pip install exited 0, so the patch WAS enacted; the
    # retried run then failed on its own. applied != successful.
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(
        script=[
            (1, "No module named 'numpy'"),
            (1, "some other error"),
        ]
    )
    installer = _ScriptedInstaller(return_code=0)

    record = _run(tmp_path, claims, executor, allow_install=True, installer=installer)

    step = record.repair_history[0]
    assert step.outcome == "retry_failed"
    assert step.patch_applied is True
    # ...while the reproduction itself is still an honest failure.
    assert record.exit_code == 1
    assert all(r.status == "unverified" for r in record.claim_results)


def test_successful_install_and_retry_records_the_patch_as_applied(tmp_path):
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(
        script=[
            (1, "ModuleNotFoundError: No module named 'numpy'"),
            (0, ""),
        ],
        results_by_call={2: {"auc": 0.9}},
    )
    installer = _ScriptedInstaller(return_code=0)

    record = _run(tmp_path, claims, executor, allow_install=True, installer=installer)

    step = record.repair_history[0]
    assert step.outcome == "installed_and_retried"
    assert step.patch_applied is True


def test_patch_applied_round_trips_through_the_signed_reproduce_bundle(tmp_path, monkeypatch):
    # The applied-but-unsuccessful case is the one worth attesting to, so it is
    # the one driven through the bundle.
    if not signing_available():
        pytest.skip("cryptography not installed")
    private_key, public_key = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)

    repo = tmp_path / "repo"
    repo.mkdir()
    dest = tmp_path / "bundle"
    claims = _claims(("auc", 0.9, 0.05))
    executor = _ScriptedExecutor(
        script=[
            (1, "No module named 'numpy'"),
            (1, "some other error"),
        ]
    )
    record = _run(
        repo,
        claims,
        executor,
        allow_install=True,
        installer=_ScriptedInstaller(return_code=0),
    )
    assert record.repair_history[0].patch_applied is True

    json_path = write_reproduce_bundle(record, dest)

    # (a) it is in the serialized record on disk...
    on_disk = json.loads(json_path.read_text())
    assert on_disk["repair_history"][0]["patch_applied"] is True
    # (b) ...it survives the load...
    loaded = load_reproduction(dest)
    assert loaded.repair_history[0].patch_applied is True
    assert loaded == record
    # (c) ...and it is inside the SIGNED canonical payload: the sidecar verifies
    # over the record as recorded, and flipping the flag breaks verification.
    sidecar = json.loads((dest / "signature.json").read_text())
    assert sidecar["public_key"] == public_key
    assert verify_signature(record, sidecar["signature"], sidecar["public_key"]) is True
    lied = record.model_copy(deep=True)
    lied.repair_history[0].patch_applied = False
    assert verify_signature(lied, sidecar["signature"], sidecar["public_key"]) is False
    # Boundary, pinned so it is not mistaken for an omission: `reproduce.json`
    # is the small re-runnable manifest, not the attested record. It carries no
    # repair data of any kind -- `patch_applied` lives in the SIGNED
    # reproduce_record.json above, which is what load_reproduction() reads.
    manifest = json.loads((dest / "reproduce.json").read_text())
    assert "repair_history" not in manifest


def test_reproduce_record_repair_history_defaults_and_backcompat():
    record = ReproduceRecord(
        reproduce_id="rp_1",
        repo="https://github.com/example/paper",
        run_command="contig reproduce https://github.com/example/paper",
        claims_sha256="a" * 64,
        claim_results=[],
        exit_code=0,
        created_at="2026-07-18T00:00:00Z",
    )
    assert record.repair_history == []

    legacy = ReproduceRecord.model_validate(
        {
            "reproduce_id": "rp_2",
            "repo": "https://github.com/example/paper",
            "run_command": "contig reproduce https://github.com/example/paper",
            "claims_sha256": "b" * 64,
            "claim_results": [],
            "exit_code": 1,
            "created_at": "2026-07-18T00:00:00Z",
        }
    )
    assert legacy.repair_history == []
