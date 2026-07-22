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

from contig.models import Diagnosis, ReproduceRecord
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
