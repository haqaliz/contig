"""Wiring tests for the injectable triage seam (aspect `wiring` of
`jev-calibrated-triage`, C9 slice 1).

Plans: docs/planning/jev-calibrated-triage/wiring/plan_20261010.md +
wiring/spec.md. Phase 1: the `--triage-active` / `--triage-threshold` flags
with the companion refusals, the env-derived `triage_for` helper, and the
`triage` kwarg threading into `self_heal_run` / `run_heal_scenario`. Phase 2:
`is_skippable_check` (R4 predicate + enumeration), `append_ledger_row`, and
the two wrap sites (qc_anomaly ledger-only, verify-time skip surface).
Phase 3: the S1 triage footer note in `contig show`.

No network is ever touched: real Jev responses are canned via the module's
`_post_json` seam, and injected fakes stand in for `default_jev_triage` at the
sites. No real `CONTIG_JEV_KEY` in CI.
"""

from __future__ import annotations

import gzip
import inspect
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import contig.triage as triage
from contig.cli import app
from contig.heal import (
    default_heal_scenarios_path,
    load_heal_scenarios,
    run_heal_scenario,
)
from contig.models import (
    ExecutionTarget,
    QCResult,
    RunRecord,
    TaskEvent,
)
from contig.self_heal import self_heal_run
from contig.triage import (
    JEV_KEY_ENV,
    NullTriage,
    TriageRequest,
    TriageResult,
    build_triage_payload,
    default_jev_triage,
    triage_for,
)
from contig.verification.rule_pack import (
    ANNOTATION_PLAUSIBILITY_PACK,
    RNASEQ_PLAUSIBILITY_PACK,
    SOMATIC_PLAUSIBILITY_PACK,
    _RULE_PACKS,
)

runner = CliRunner()

TRACE_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tSTAR (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)
GOOD_MQC = (
    '{"report_general_stats_data":[{'
    '"S1":{"uniquely_mapped_percent":92.0,"percent_assigned":85.0,"total_reads":1000000.0},'
    '"S2":{"uniquely_mapped_percent":90.0,"percent_assigned":84.0,"total_reads":1100000.0}}]}'
)


def _fake_run_executor(trace_text, mqc_json=None):
    def execute(cmd, trace_path):
        Path(trace_path).write_text(trace_text)
        if mqc_json is not None:
            d = Path(trace_path).parent / "results" / "multiqc"
            d.mkdir(parents=True, exist_ok=True)
            (d / "multiqc_data.json").write_text(mqc_json)
        return 0 if mqc_json is not None else 1

    return execute


# ---------------------------------------------------------------------------
# Phase 1: triage_for — the env-derived seam + mode string helper
# ---------------------------------------------------------------------------


def test_triage_for_absent_key_returns_null_triage_and_null_mode(monkeypatch):
    monkeypatch.delenv(JEV_KEY_ENV, raising=False)
    seam, mode = triage_for(mode_requested=True, threshold=0.5)
    assert seam is NullTriage
    assert mode == "null"


def test_triage_for_key_present_defaults_to_shadow(monkeypatch):
    monkeypatch.setenv(JEV_KEY_ENV, "super-secret-key-value")
    seam, mode = triage_for(mode_requested=False, threshold=None)
    assert seam is default_jev_triage
    assert mode == "shadow"


def test_triage_for_key_present_with_active_flag_returns_active(monkeypatch):
    monkeypatch.setenv(JEV_KEY_ENV, "super-secret-key-value")
    seam, mode = triage_for(mode_requested=True, threshold=0.5)
    assert seam is default_jev_triage
    assert mode == "active"
    # An empty key is the same as an absent one: no triage, mode "null".
    monkeypatch.setenv(JEV_KEY_ENV, "")
    seam, mode = triage_for(mode_requested=True, threshold=0.5)
    assert seam is NullTriage
    assert mode == "null"


# ---------------------------------------------------------------------------
# Phase 1: the flags register on `run` and `verify` with their defaults
# ---------------------------------------------------------------------------


def test_run_registers_triage_flags_with_defaults():
    import typer

    cmd = typer.main.get_command(app).commands["run"]
    by_name = {p.name: p for p in cmd.params}
    assert "--triage-active" in by_name["triage_active"].opts
    assert by_name["triage_active"].default is False
    assert "--triage-threshold" in by_name["triage_threshold"].opts
    assert by_name["triage_threshold"].default == 0.5


def test_verify_registers_triage_flags_with_defaults():
    import typer

    cmd = typer.main.get_command(app).commands["verify"]
    by_name = {p.name: p for p in cmd.params}
    assert "--triage-active" in by_name["triage_active"].opts
    assert by_name["triage_active"].default is False
    assert "--triage-threshold" in by_name["triage_threshold"].opts
    assert by_name["triage_threshold"].default == 0.5


# ---------------------------------------------------------------------------
# Phase 1: companion refusals — before any filesystem/run work
# ---------------------------------------------------------------------------


def test_run_triage_threshold_without_active_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(JEV_KEY_ENV, raising=False)
    result = runner.invoke(
        app,
        ["run", "--run-id", "r", "--runs-dir", str(tmp_path / "runs"),
         "--triage-threshold", "0.3"],
    )
    assert result.exit_code != 0
    assert "--triage-active" in result.output


def test_run_triage_threshold_at_its_own_default_without_active_is_still_refused(
    tmp_path, monkeypatch
):
    # Discriminates get_parameter_source from a value-comparison shortcut: the
    # default (0.5) passed explicitly must still be refused.
    monkeypatch.delenv(JEV_KEY_ENV, raising=False)
    result = runner.invoke(
        app,
        ["run", "--run-id", "r", "--runs-dir", str(tmp_path / "runs"),
         "--triage-threshold", "0.5"],
    )
    assert result.exit_code != 0
    assert "--triage-active" in result.output


def test_run_triage_active_without_key_is_refused_before_any_filesystem_work(
    tmp_path, monkeypatch
):
    # R3: active mode is refused when CONTIG_JEV_KEY is absent, naming the env
    # var, BEFORE any run/verify work: the runs dir must not even be created.
    monkeypatch.delenv(JEV_KEY_ENV, raising=False)
    result = runner.invoke(
        app,
        ["run", "--run-id", "r", "--runs-dir", str(tmp_path / "runs"), "--triage-active"],
    )
    assert result.exit_code != 0
    assert JEV_KEY_ENV in result.output
    assert not (tmp_path / "runs").exists()


def test_run_triage_threshold_out_of_bounds_is_refused(tmp_path, monkeypatch):
    # The bounds refusal must fire with a key present so the key gate does not
    # short-circuit it.
    monkeypatch.setenv(JEV_KEY_ENV, "super-secret-key-value")
    for bad in ("-0.1", "1.1", "2"):
        result = runner.invoke(
            app,
            ["run", "--run-id", "r", "--runs-dir", str(tmp_path / "runs"),
             "--triage-active", "--triage-threshold", bad],
        )
        assert result.exit_code != 0, bad
        assert "between 0 and 1" in result.output


def test_verify_triage_threshold_without_active_is_refused_before_run_id_lookup(
    tmp_path, monkeypatch
):
    # The refusal precedes even the run-id sanity check, mirroring the
    # stall-flag precedent: a flag mistake is reported as a flag mistake.
    monkeypatch.delenv(JEV_KEY_ENV, raising=False)
    result = runner.invoke(
        app,
        ["verify", "ghost", "--runs-dir", str(tmp_path), "--triage-threshold", "0.3"],
    )
    assert result.exit_code != 0
    assert "--triage-active" in result.output
    assert "Invalid run id" not in result.output


def test_verify_triage_active_without_key_is_refused_naming_env(tmp_path, monkeypatch):
    monkeypatch.delenv(JEV_KEY_ENV, raising=False)
    result = runner.invoke(
        app,
        ["verify", "ghost", "--runs-dir", str(tmp_path), "--triage-active"],
    )
    assert result.exit_code != 0
    assert JEV_KEY_ENV in result.output


def test_run_triage_active_with_key_passes_validation_and_runs(tmp_path, monkeypatch):
    # The coherent pairing (key + active + threshold in bounds) must proceed:
    # the validation is a refusal gate, never a blocker.
    monkeypatch.setenv(JEV_KEY_ENV, "super-secret-key-value")
    monkeypatch.setattr(
        "contig.cli.default_executor", _fake_run_executor(TRACE_OK, GOOD_MQC)
    )
    result = runner.invoke(
        app,
        ["run", "--run-id", "tr", "--runs-dir", str(tmp_path / "runs"),
         "--triage-active", "--triage-threshold", "0.5"],
    )
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Phase 1: seam threading — self_heal_run kwarg and run_heal_scenario passthrough
# ---------------------------------------------------------------------------


def test_self_heal_run_gains_kw_only_triage_defaulting_to_null_triage():
    sig = inspect.signature(self_heal_run)
    param = sig.parameters["triage"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is NullTriage


def test_run_heal_scenario_accepts_triage_and_passes_it_through(monkeypatch, tmp_path):
    scenarios = load_heal_scenarios(default_heal_scenarios_path())
    assert scenarios, "the shipped heal scenario corpus must not be empty"
    seen = {}

    def fake_self_heal_run(**kwargs):
        seen["triage"] = kwargs.get("triage")
        return RunRecord(
            run_id=kwargs.get("run_id", "heal-x"),
            pipeline=kwargs.get("pipeline", "nf-core/rnaseq"),
            pipeline_revision=kwargs.get("revision", "3.26.0"),
            target=kwargs["target"],
            input_checksums={},
            events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        )

    monkeypatch.setattr("contig.heal.self_heal_run", fake_self_heal_run)
    fake_seam = lambda req: None  # never consulted in null mode
    run_heal_scenario(scenarios[0], tmp_path, triage=fake_seam)
    assert seen.get("triage") is fake_seam