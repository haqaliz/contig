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


# ---------------------------------------------------------------------------
# Phase 2: the R4 predicate — is_skippable_check
# ---------------------------------------------------------------------------

_BOUND_KEYS = ("warn_below", "warn_above", "fail_below", "fail_above")


def test_is_skippable_check_concordance_kind_always_skippable():
    # kind == "concordance" short-circuits regardless of bands: a concordance
    # check is at-most-WARN corroboration, so it can never fail a verdict.
    assert triage.is_skippable_check("concordance", None) is True
    assert triage.is_skippable_check("concordance", {"fail_below": 0.5}) is True
    assert triage.is_skippable_check("concordance", {"warn_above": 0.9}) is True


def test_is_skippable_check_bandless_non_concordance_not_skippable():
    # No bands at all (structural/did-it-run checks) => skip decision never
    # applies (R4: "bands present" is a precondition).
    assert triage.is_skippable_check("metric", None) is False
    assert triage.is_skippable_check("structural", None) is False


def test_is_skippable_check_fail_band_blocks_skip():
    for bands in (
        {"fail_below": 40.0},
        {"fail_above": 3.6},
        {"warn_below": 60.0, "fail_below": 40.0},
        {"warn_above": 2.4, "fail_above": 3.6, "warn_below": 1.8},
    ):
        assert triage.is_skippable_check("metric", bands) is False, bands


def test_is_skippable_check_warn_only_bands_are_skippable():
    for bands in ({"warn_below": 60.0}, {"warn_above": 10.0}, {}):
        assert triage.is_skippable_check("metric", bands) is True, bands


def test_skippable_enumeration_walks_the_shipped_rule_packs():
    # The R4 predicate is pinned against the SHIPPED packs by name: a future
    # FAIL band joining a skippable rule (or a newly cloned pack) reddens this
    # test and forces a deliberate act.
    packs = (
        list(_RULE_PACKS.values())
        + [RNASEQ_PLAUSIBILITY_PACK, SOMATIC_PLAUSIBILITY_PACK, ANNOTATION_PLAUSIBILITY_PACK]
    )
    by_check: dict[str, bool] = {}
    by_metric: dict[str, bool] = {}
    for rule in (r for pack in packs for r in pack):
        bands = {k: rule[k] for k in _BOUND_KEYS if k in rule}
        verdict = triage.is_skippable_check("metric", bands)
        by_check[rule["check"]] = verdict
        by_metric[rule.get("metric", rule["check"])] = verdict

    # FAIL-capable rules are pinned never-skippable, by rule name AND by
    # metric key (PRD R4 names them ts_tv/het_hom/variant_count/
    # somatic_variant_count).
    for name in (
        "ts_tv_ratio", "het_hom_ratio", "variant_count", "mean_coverage",
        "somatic_variant_count",
    ):
        assert name in by_check, name
        assert by_check[name] is False, f"FAIL-capable rule became skippable: {name}"
    for metric in (
        "ts_tv", "het_hom", "variant_count", "mean_coverage", "somatic_variant_count",
        "uniquely_mapped_percent", "percent_assigned", "percent_mapped",
        "estimated_cells", "median_genes_per_cell", "fraction_reads_in_cells",
        "percent_bs_conversion", "percent_aligned", "percent_duplication",
        "percent_retained", "asv_count", "input_reads",
        "n50", "completeness", "contamination",
    ):
        assert metric in by_metric, metric
        assert by_metric[metric] is False, f"FAIL-capable rule became skippable: {metric}"

    # WARN-capped / band-less plausibility rules pass the predicate (by their
    # metric keys; two packs share the check name "duplication_rate", so the
    # metric key is the unambiguous handle).
    for metric in (
        "percent_rRNA", "PERCENT_DUPLICATION", "median_vaf",
        "strelka_median_vaf", "normal_median_vaf",
        "real_consequence_fraction", "intergenic_fraction",
    ):
        assert metric in by_metric, metric
        assert by_metric[metric] is True, f"warn-capped rule became unskippable: {metric}"

    # The concordance family (verify-time dispatch) is always skippable.
    for name in (
        "genotype_concordance", "site_overlap", "spearman_concordance",
        "gene_overlap", "somatic_site_overlap", "consequence_concordance",
        "sc_count_concordance",
    ):
        assert triage.is_skippable_check("concordance", None) is True


# ---------------------------------------------------------------------------
# Phase 2: append_ledger_row — the calibration sidecar writer
# ---------------------------------------------------------------------------


def test_append_ledger_row_writes_one_json_line_and_is_append_only(tmp_path):
    runs_dir = tmp_path / "runs"
    rows = []
    triage.append_ledger_row(
        runs_dir,
        {"run_id": "r1", "attempt": 1, "surface": "qc_anomaly", "mode": "shadow",
         "confidence": 0.42, "reason": None, "checks": ["r1:qc_anomaly:variant_count"],
         "actual": "QC-FAIL: variant_count"},
    )
    for line in (runs_dir / "triage-ledger.jsonl").read_text().splitlines():
        rows.append(json.loads(line))
    assert len(rows) == 1
    assert rows[0]["run_id"] == "r1"
    assert rows[0]["actual"] == "QC-FAIL: variant_count"

    triage.append_ledger_row(
        runs_dir,
        {"run_id": "r2", "attempt": 1, "surface": "verify_concordance",
         "mode": "active", "confidence": 0.9, "reason": None, "checks": [],
         "actual": "skipped"},
    )
    lines = (runs_dir / "triage-ledger.jsonl").read_text().splitlines()
    assert len(lines) == 2  # append-only, never a rewrite
    assert json.loads(lines[1])["actual"] == "skipped"


def test_append_ledger_row_unwritable_path_degrades_silently(tmp_path):
    # A runs_dir that is a FILE (not a directory) must never raise and must
    # not create anything: a calibration ledger never fails a run/verify.
    blocker = tmp_path / "runs"
    blocker.write_text("i am a file, not a directory")
    triage.append_ledger_row(blocker, {"run_id": "r1", "mode": "shadow"})
    triage.append_ledger_row(tmp_path / "missing" / "nested", {"run_id": "r2"})


def test_append_ledger_row_tolerates_unencodable_row(tmp_path):
    # errors="replace": a row carrying a lone surrogate is written (replaced),
    # never an exception, and the file still holds one line.
    runs_dir = tmp_path / "runs"
    triage.append_ledger_row(
        runs_dir, {"run_id": "r1", "mode": "shadow", "reason": "bad \ud800 char"}
    )
    line = (runs_dir / "triage-ledger.jsonl").read_text(encoding="utf-8", errors="replace")
    assert line.strip()


# ---------------------------------------------------------------------------
# Phase 2: qc_anomaly site (self_heal.py) — seam consulted AFTER the trigger
# ---------------------------------------------------------------------------


def _qc_trace(status, exit_code):
    return (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        f"1\tab/cd\t1\tNFCORE_SAREK:HAPLOTYPECALLER (S1)\t{status}\t{exit_code}\t-\t-\t-\n"
    )


QC_TRACE_OK = _qc_trace("COMPLETED", 0)


def _write_empty_vcf(run_dir):
    with gzip.open(Path(run_dir) / "calls.vcf.gz", "wt") as fh:
        fh.write("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")


def _qc_green_fail_executor():
    """An executor whose run exits 0 and leaves a call set that FAILs QC."""
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        Path(trace_path).write_text(QC_TRACE_OK)
        (Path(trace_path).parent / "run.log").write_text("ok")
        _write_empty_vcf(Path(trace_path).parent)
        return 0

    return executor


def _qc_heal(tmp_path, executor, **over):
    kwargs = dict(
        pipeline="nf-core/sarek",
        revision="3.5.1",
        profiles=["test", "docker"],
        target=ExecutionTarget(
            backend="local", container_runtime="docker", work_dir=str(tmp_path / "w")
        ),
        input_paths=[],
        runs_dir=tmp_path / "runs",
        run_id="r",
        executor=executor,
        assay="variant_calling",
        max_attempts=3,
    )
    kwargs.update(over)
    return self_heal_run(**kwargs)


def test_qc_anomaly_consults_seam_after_trigger_and_writes_ledger_row(tmp_path):
    requests = []
    result = TriageResult(mode="shadow", confidence=0.42, items={}, reason=None)

    def recording_seam(req):
        requests.append(req)
        return result

    record = _qc_heal(
        tmp_path, _qc_green_fail_executor(), triage=recording_seam, triage_mode="shadow"
    )
    assert len(requests) == 1
    req = requests[0]
    assert req.run_id == "r"
    assert req.surface == "qc_anomaly"
    assert req.mode == "shadow"
    assert req.payload["run"]["run_id"] == "r"
    assert req.payload["run"]["assay"] == "variant_calling"
    assert req.payload["run"]["verdict"] == "fail"

    rows = [
        json.loads(line)
        for line in (tmp_path / "runs" / "triage-ledger.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "r"
    assert row["attempt"] == 1
    assert row["surface"] == "qc_anomaly"
    assert row["mode"] == "shadow"
    assert row["confidence"] == 0.42
    assert row["reason"] is None
    assert row["actual"] == "QC-FAIL: variant_count:sample"
    assert row["checks"] == ["r:qc_anomaly:variant_count:sample"]


def test_qc_anomaly_trigger_output_byte_identical_with_null_and_shadow_seam(
    tmp_path,
):
    record_null = _qc_heal(tmp_path, _qc_green_fail_executor())
    record_shadow = _qc_heal(
        tmp_path,
        _qc_green_fail_executor(),
        triage=lambda req: TriageResult(mode="shadow", confidence=0.42, items={}, reason=None),
        triage_mode="shadow",
    )
    # The seam consultation happens AFTER the trigger block and must never
    # alter it: the recorded RepairStep (and the whole record) is identical.
    assert record_null.model_dump() == record_shadow.model_dump()
    assert record_null.repair_history == record_shadow.repair_history


def test_qc_anomaly_default_null_mode_consults_nothing_and_writes_no_ledger(
    tmp_path,
):
    calls = []

    def spying_seam(req):
        calls.append(req)
        return NullTriage(req)

    record = _qc_heal(tmp_path, _qc_green_fail_executor(), triage=spying_seam)
    assert record.repair_history, "the trigger itself must still fire"
    assert calls == []
    assert not (tmp_path / "runs" / "triage-ledger.jsonl").exists()


def test_qc_anomaly_seam_degrade_keeps_ledger_row_with_reason(tmp_path):
    # Seam failure mid-call degrades to Null behavior; the ledger row still
    # records the reason and confidence=None (plan section 6).
    degraded = TriageResult(mode="null", confidence=None, items={}, reason="triage request failed")
    record = _qc_heal(
        tmp_path,
        _qc_green_fail_executor(),
        triage=lambda req: degraded,
        triage_mode="shadow",
    )
    assert record.repair_history
    row = json.loads(
        (tmp_path / "runs" / "triage-ledger.jsonl").read_text().splitlines()[0]
    )
    assert row["mode"] == "shadow"
    assert row["confidence"] is None
    assert row["reason"] == "triage request failed"


# ---------------------------------------------------------------------------
# Phase 2: verify-time dispatch — the one active-mode skip surface
# ---------------------------------------------------------------------------

_VCF_HEADER = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
)
_VCF_SITES_A = (
    "chr1\t100\t.\tA\tT\t50\tPASS\t.\tGT\t0/1\n"
    "chr1\t200\t.\tC\tG\t50\tPASS\t.\tGT\t1/1\n"
    "chr2\t300\t.\tG\tA\t50\tPASS\t.\tGT\t0/1\n"
)
_VCF_SITES_CONCORDANT = (
    "chr1\t100\t.\tA\tT\t50\tPASS\t.\tGT\t0|1\n"
    "chr1\t200\t.\tC\tG\t50\tPASS\t.\tGT\t1/1\n"
    "chr2\t300\t.\tG\tA\t50\tPASS\t.\tGT\t1/0\n"
)


def _write_germline_run_with_vcf(runs_dir, run_id):
    """A variant_calling run with a primary VCF and stored QC results.

    The stored QC results make the whitelisted payload non-empty, so a canned
    Jev reply resolves item ids to real checks and yields an overall
    confidence.
    """
    from contig.bundle import compute_output_checksums

    run_dir = Path(runs_dir) / run_id
    results = run_dir / "results"
    results.mkdir(parents=True, exist_ok=True)
    primary = results / "S1.vcf.gz"
    primary.write_bytes(gzip.compress((_VCF_HEADER + _VCF_SITES_A).encode()))
    record = RunRecord(
        run_id=run_id,
        pipeline="nf-core/sarek",  # variant_calling assay
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[TaskEvent(process="X", status="COMPLETED", exit=0)],
        qc_results=[
            QCResult(check="ts_tv_ratio", kind="metric", status="warn",
                     message="low", value=1.7, expected_range="[1.8, 2.4]"),
            QCResult(check="mean_coverage", kind="metric", status="pass",
                     message="ok", value=31.2),
        ],
        output_checksums=compute_output_checksums(results),
    )
    from contig.bundle import write_bundle

    write_bundle(record, run_dir)
    return run_dir


def _write_second_vcf(tmp_path, name, vcf_body):
    path = tmp_path / name
    path.write_bytes(gzip.compress((_VCF_HEADER + vcf_body).encode()))
    return path


def _canned_jev(post_json_calls, *, confidence):
    """A `contig.triage._post_json` stand-in returning one canned item."""

    def fake_post_json(url, payload, **kwargs):
        post_json_calls.append((url, payload))
        run_id = payload.get("run", {}).get("run_id", "run")
        checks = payload.get("checks", [])
        check = checks[0]["check"] if checks else "none"
        return json.dumps(
            {"items": [{"id": f"{run_id}:verify_concordance:{check}", "confidence": confidence}]}
        )

    return fake_post_json


def _setup_verified_jenv(monkeypatch, post_json_calls, *, confidence):
    """A keyed + URLed environment with a canned transport (never network)."""
    monkeypatch.setenv(JEV_KEY_ENV, "super-secret-key-value")
    monkeypatch.setenv("CONTIG_JEV_URL", "https://triage.example.com/v1")
    monkeypatch.delenv("CONTIG_JEV_ALLOW_HTTP", raising=False)
    monkeypatch.setattr(
        triage, "_post_json", _canned_jev(post_json_calls, confidence=confidence)
    )


def test_verify_shadow_mode_runs_evaluator_and_writes_ledger_row(tmp_path, monkeypatch):
    _write_germline_run_with_vcf(tmp_path, "g1")
    second = _write_second_vcf(tmp_path, "second_ok.vcf.gz", _VCF_SITES_CONCORDANT)
    calls: list = []
    _setup_verified_jenv(monkeypatch, calls, confidence=0.9)

    result = runner.invoke(
        app, ["verify", "g1", "--runs-dir", str(tmp_path),
              "--concordance-vcf", str(second)]
    )
    assert result.exit_code == 0, result.output
    out = result.output.lower()
    assert "genotype_concordance" in out  # the evaluator ran, nothing skipped
    assert calls, "the seam transport must have been consulted"
    row = json.loads(
        (tmp_path / "triage-ledger.jsonl").read_text().splitlines()[0]
    )
    assert row["run_id"] == "g1"
    assert row["surface"] == "verify_concordance"
    assert row["mode"] == "shadow"
    assert row["confidence"] == 0.9
    assert row["actual"] == "pass"


def test_verify_off_vs_shadow_byte_identical(tmp_path, monkeypatch):
    # The PRD's core invariant: triage off vs shadow produces byte-identical
    # verify output on the checks that ran (only the ledger sidecar differs).
    _write_germline_run_with_vcf(tmp_path, "g2")
    second = _write_second_vcf(tmp_path, "second_ok.vcf.gz", _VCF_SITES_CONCORDANT)

    monkeypatch.delenv(JEV_KEY_ENV, raising=False)
    off = runner.invoke(
        app, ["verify", "g2", "--runs-dir", str(tmp_path),
              "--concordance-vcf", str(second)]
    )
    assert off.exit_code == 0, off.output
    assert not (tmp_path / "triage-ledger.jsonl").exists()

    calls: list = []
    _setup_verified_jenv(monkeypatch, calls, confidence=0.9)
    shadow = runner.invoke(
        app, ["verify", "g2", "--runs-dir", str(tmp_path),
              "--concordance-vcf", str(second)]
    )
    assert shadow.exit_code == 0, shadow.output
    assert shadow.output == off.output
    assert (tmp_path / "triage-ledger.jsonl").exists()


def test_verify_active_at_or_above_threshold_runs_identically(tmp_path, monkeypatch):
    _write_germline_run_with_vcf(tmp_path, "g3")
    second = _write_second_vcf(tmp_path, "second_ok.vcf.gz", _VCF_SITES_CONCORDANT)
    calls: list = []
    _setup_verified_jenv(monkeypatch, calls, confidence=0.9)

    result = runner.invoke(
        app, ["verify", "g3", "--runs-dir", str(tmp_path),
              "--concordance-vcf", str(second),
              "--triage-active", "--triage-threshold", "0.5"]
    )
    assert result.exit_code == 0, result.output
    assert "genotype_concordance" in result.output.lower()
    assert "UNVERIFIED" not in result.output
    row = json.loads(
        (tmp_path / "triage-ledger.jsonl").read_text().splitlines()[0]
    )
    assert row["mode"] == "active"
    assert row["actual"] == "pass"


def test_verify_active_low_confidence_skips_evaluator_with_honest_unverified(
    tmp_path, monkeypatch
):
    _write_germline_run_with_vcf(tmp_path, "g4")
    second = _write_second_vcf(tmp_path, "second_ok.vcf.gz", _VCF_SITES_CONCORDANT)
    calls: list = []
    _setup_verified_jenv(monkeypatch, calls, confidence=0.2)
    evaluator_calls = []

    def spying_evaluate_concordance(*args, **kwargs):
        evaluator_calls.append(args)
        return []

    monkeypatch.setattr("contig.cli.evaluate_concordance", spying_evaluate_concordance)

    result = runner.invoke(
        app, ["verify", "g4", "--runs-dir", str(tmp_path),
              "--concordance-vcf", str(second),
              "--triage-active", "--triage-threshold", "0.5"]
    )
    assert result.exit_code == 0, result.output
    assert evaluator_calls == [], "the concordance evaluator must be skipped"
    out = result.output
    assert "UNVERIFIED" in out
    assert "Skipping concordance" in out
    assert "0.5" in out  # the threshold is named
    row = json.loads(
        (tmp_path / "triage-ledger.jsonl").read_text().splitlines()[0]
    )
    assert row["mode"] == "active"
    assert row["confidence"] == 0.2
    assert row["actual"] == "skipped"


def test_verify_active_low_confidence_json_shape_is_unverified(tmp_path, monkeypatch):
    _write_germline_run_with_vcf(tmp_path, "g5")
    second = _write_second_vcf(tmp_path, "second_ok.vcf.gz", _VCF_SITES_CONCORDANT)
    calls: list = []
    _setup_verified_jenv(monkeypatch, calls, confidence=0.2)
    monkeypatch.setattr(
        "contig.cli.evaluate_concordance", lambda *a, **k: []
    )

    result = runner.invoke(
        app, ["verify", "g5", "--runs-dir", str(tmp_path),
              "--concordance-vcf", str(second), "--json",
              "--triage-active", "--triage-threshold", "0.5"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    concordance = data["concordance"]
    assert len(concordance) == 1
    entry = concordance[0]
    assert entry["status"] == "unverified"
    assert entry["kind"] == "concordance"
    assert "0.5" in entry["message"]