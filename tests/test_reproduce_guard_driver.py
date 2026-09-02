"""Tests for the reproduce-guard scenario driver (C6 fold-in, guard-core
aspect, Phase B).

`run_reproduce_scenario` replays one frozen `ReproduceScenario` through the
REAL `run_reproduction` loop -- real `load_claims`, real `classify`, real
locators, real freshness guard -- with only the executor/installer seams
scripted. These tests pin the driver contract: fresh artifacts reproduce,
stale artifacts are UNVERIFIED by the real guard (never a false pass),
stdout-mode patterns bind the run's captured output, env-resurrection heals
record their repair, invalid scenario claims are loud, executor over-calls are
loud, and everything stays deterministic at the repo-wide
`run_started_at=1_000_000.0` convention.
"""

from __future__ import annotations

import sys

import pytest

from contig.models import ExecStep, ReproduceScenario
from contig.reproduce_guard import claim_family, run_reproduce_scenario
from contig.verification.reproduce import (
    Claim,
    ClaimsError,
    Locator,
    NotebookLocator,
    PatternLocator,
    TableLocator,
)

# Repo-wide deterministic identity convention (mirrors
# tests/test_reproduce_env_resurrection.py): a 1970-era epoch so freshness is
# decided purely by mtimes we control, never wall-clock time.
_RUN_START = 1_000_000.0
_CLAIMS_SHA256 = "a" * 64
_CREATED_AT = "2026-07-18T00:00:00Z"
_REPRODUCE_ID = "rp_1"


def _scenario(**overrides) -> ReproduceScenario:
    base = dict(
        scenario_id="s1",
        description="fixture",
        run_command="python run.py",
        claims=[{"id": "auc", "value": 0.9}],
        executor_steps=[ExecStep(exit_code=0, output="")],
        expected_claim_statuses={},
    )
    base.update(overrides)
    return ReproduceScenario(**base)


def test_flat_fresh_artifact_exact_match(tmp_path):
    scenario = _scenario(
        executor_steps=[ExecStep(exit_code=0, output="", write_results={"auc": 0.9})],
    )
    record, claims = run_reproduce_scenario(
        scenario, repo_dir=tmp_path, run_started_at=_RUN_START
    )

    assert record.exit_code == 0
    assert record.reproduce_id == _REPRODUCE_ID
    assert record.claims_sha256 == _CLAIMS_SHA256
    assert record.created_at == _CREATED_AT
    assert record.repair_history == []
    assert [r.status for r in record.claim_results] == ["reproduced"]
    assert record.claim_results[0].observed == 0.9
    assert [c.id for c in claims] == ["auc"]
    assert claims[0].locator is None


def test_stale_artifact_is_unverified_never_false_pass(tmp_path):
    scenario = _scenario(
        executor_steps=[
            ExecStep(
                exit_code=0,
                output="",
                write_results={"auc": 0.9},
                artifact_mtimes={"results.json": _RUN_START - 1},
            )
        ],
    )
    record, _ = run_reproduce_scenario(
        scenario, repo_dir=tmp_path, run_started_at=_RUN_START
    )

    assert record.exit_code == 0
    assert record.claim_results[0].status == "unverified"
    assert "not rewritten by this run" in record.claim_results[0].message


def test_stdout_mode_pattern_claim_binds_run_output(tmp_path):
    scenario = _scenario(
        claims=[{"id": "auc", "value": 0.9, "pattern": r"auc:\s*([0-9.]+)"}],
        executor_steps=[ExecStep(exit_code=0, output="metric auc: 0.9\n")],
    )
    record, _ = run_reproduce_scenario(
        scenario, repo_dir=tmp_path, run_started_at=_RUN_START
    )

    assert record.exit_code == 0
    assert record.claim_results[0].status == "reproduced"
    assert record.claim_results[0].observed == 0.9


def test_env_resurrection_heal_records_installed_and_retried(tmp_path):
    scenario = _scenario(
        allow_install=True,
        installer_steps=[0],
        executor_steps=[
            ExecStep(exit_code=1, output="ModuleNotFoundError: No module named 'x'"),
            ExecStep(exit_code=0, output="", write_results={"auc": 0.9}),
        ],
    )
    record, _ = run_reproduce_scenario(
        scenario, repo_dir=tmp_path, run_started_at=_RUN_START
    )

    assert record.exit_code == 0
    assert record.claim_results[0].status == "reproduced"
    assert len(record.repair_history) == 1
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "missing_dependency"
    assert step.outcome == "installed_and_retried"


def test_install_fail_gives_up_with_install_failed(tmp_path):
    scenario = _scenario(
        allow_install=True,
        installer_steps=[1],
        executor_steps=[ExecStep(exit_code=1, output="No module named 'x'")],
    )
    record, _ = run_reproduce_scenario(
        scenario, repo_dir=tmp_path, run_started_at=_RUN_START
    )

    assert record.exit_code == 1
    assert all(r.status == "unverified" for r in record.claim_results)
    assert len(record.repair_history) == 1
    assert record.repair_history[0].outcome == "install_failed"


def test_nonzero_exit_with_no_install_marks_everything_unverified(tmp_path):
    scenario = _scenario(executor_steps=[ExecStep(exit_code=5, output="")])
    record, _ = run_reproduce_scenario(
        scenario, repo_dir=tmp_path, run_started_at=_RUN_START
    )

    assert record.exit_code == 5
    assert all(r.status == "unverified" for r in record.claim_results)
    assert record.repair_history == []


def test_schema_invalid_inline_claims_propagate_claims_error(tmp_path):
    scenario = _scenario(
        claims=[{"id": "dup", "value": 1.0}, {"id": "dup", "value": 2.0}],
    )
    with pytest.raises(ClaimsError):
        run_reproduce_scenario(scenario, repo_dir=tmp_path, run_started_at=_RUN_START)


def test_extra_executor_call_raises_assertion_error(tmp_path):
    scenario = _scenario(
        allow_install=True,
        installer_steps=[0],
        executor_steps=[ExecStep(exit_code=1, output="No module named 'x'")],
    )
    with pytest.raises(AssertionError):
        run_reproduce_scenario(scenario, repo_dir=tmp_path, run_started_at=_RUN_START)


def test_installer_expected_argv_mismatch_raises_assertion_error(tmp_path):
    # The scripted installer asserts the resolved pip argv when a scenario
    # declares `installer_expected_argv`. A wrong expected argv is a scenario
    # bug and must fail loudly (matching the executor's extra-call posture) --
    # never a silent rc-only replay that would let a stale scenario "pass".
    scenario = _scenario(
        allow_install=True,
        installer_steps=[0],
        installer_expected_argv=[
            ["/usr/bin/python3", "-m", "pip", "install", "opencv-python"]
        ],
        executor_steps=[
            ExecStep(exit_code=1, output="No module named 'cv2'"),
            ExecStep(exit_code=0, output="", write_results={"auc": 0.9}),
        ],
    )
    with pytest.raises(AssertionError, match="argv"):
        run_reproduce_scenario(scenario, repo_dir=tmp_path, run_started_at=_RUN_START)


def test_installer_expected_argv_over_draw_raises_assertion_error(tmp_path):
    # One declared expected argv but two install calls: the second pop over-draws
    # the declared list -- a loud scenario bug, never a fallback to rc-only.
    scenario = _scenario(
        allow_install=True,
        installer_steps=[0, 0],
        installer_expected_argv=[
            [sys.executable, "-m", "pip", "install", "opencv-python"]
        ],
        executor_steps=[
            ExecStep(exit_code=1, output="No module named 'cv2'"),
            ExecStep(exit_code=1, output="No module named 'sklearn'"),
            ExecStep(exit_code=0, output="", write_results={"auc": 0.9}),
        ],
    )
    with pytest.raises(AssertionError, match="argv"):
        run_reproduce_scenario(scenario, repo_dir=tmp_path, run_started_at=_RUN_START)


def test_installer_expected_argv_matching_resolved_pip_argv_heals(tmp_path):
    # cv2 -> opencv-python (the alias map), so the scripted installer must have
    # seen exactly `_pip_install_argv("opencv-python")`. An exact match heals
    # with no assertion noise.
    scenario = _scenario(
        allow_install=True,
        installer_steps=[0],
        installer_expected_argv=[
            [sys.executable, "-m", "pip", "install", "opencv-python"]
        ],
        executor_steps=[
            ExecStep(exit_code=1, output="No module named 'cv2'"),
            ExecStep(exit_code=0, output="", write_results={"auc": 0.9}),
        ],
    )
    record, _ = run_reproduce_scenario(
        scenario, repo_dir=tmp_path, run_started_at=_RUN_START
    )

    assert record.exit_code == 0
    assert record.claim_results[0].status == "reproduced"
    assert record.repair_history[0].outcome == "installed_and_retried"


def test_installer_expected_argv_absent_stays_rc_only(tmp_path):
    # The field defaults to None: a scenario without it replays byte-identically
    # to today (rc-only scripted install, no argv assertion).
    scenario = _scenario(
        allow_install=True,
        installer_steps=[0],
        executor_steps=[
            ExecStep(exit_code=1, output="No module named 'cv2'"),
            ExecStep(exit_code=0, output="", write_results={"auc": 0.9}),
        ],
    )
    assert scenario.installer_expected_argv is None
    record, _ = run_reproduce_scenario(
        scenario, repo_dir=tmp_path, run_started_at=_RUN_START
    )

    assert record.exit_code == 0
    assert record.claim_results[0].status == "reproduced"
    assert record.repair_history[0].outcome == "installed_and_retried"


def test_scenario_replay_is_deterministic(tmp_path):
    scenario = _scenario(
        executor_steps=[ExecStep(exit_code=0, output="", write_results={"auc": 0.9})],
    )
    first, _ = run_reproduce_scenario(
        scenario, repo_dir=tmp_path / "a", run_started_at=_RUN_START
    )
    second, _ = run_reproduce_scenario(
        scenario, repo_dir=tmp_path / "b", run_started_at=_RUN_START
    )

    assert [r.status for r in first.claim_results] == [
        r.status for r in second.claim_results
    ]
    assert first.exit_code == second.exit_code


def test_claim_family_maps_every_locator_kind():
    cases = [
        (Claim(id="flat", value=1.0), "flat"),
        (
            Claim(
                id="json",
                value=1.0,
                locator=Locator(source="results.json", path="auc"),
            ),
            "json",
        ),
        (
            Claim(
                id="table",
                value=1.0,
                locator=TableLocator(
                    source="t.tsv", column="auc", row=0, delimiter="\t", header=True
                ),
            ),
            "table",
        ),
        (
            Claim(
                id="pat-file",
                value=1.0,
                locator=PatternLocator(source="log.txt", pattern=r"auc:\s*([0-9.]+)"),
            ),
            "pattern",
        ),
        (
            Claim(id="pat-stdout", value=1.0, locator=PatternLocator(source=None, pattern=r"x")),
            "pattern",
        ),
        (
            Claim(
                id="nb",
                value=1.0,
                locator=NotebookLocator(source="n.ipynb", cell=0, pattern=r"x"),
            ),
            "notebook",
        ),
    ]
    for claim, expected in cases:
        assert claim_family(claim) == expected
