"""Tests for the heal-guard models (C6 slice 2: self-heal outcome-match guard).

Task 1 only: the 7 new Pydantic models exist, carry the documented defaults,
and round-trip through JSON. No CLI/logic here -- that's later tasks.
"""

from __future__ import annotations

import pytest

from contig.models import (
    AttemptSpec,
    HealClassScore,
    HealEvalReport,
    HealGuardResult,
    HealScenario,
    HealScenarioResult,
    HealSnapshot,
)

# --- HealScenario + AttemptSpec --------------------------------------------


def test_heal_scenario_constructs_from_dict_with_defaults():
    scenario = HealScenario.model_validate(
        {
            "scenario_id": "heal-001",
            "description": "OOM on star_align, retried with bumped memory",
            "source": "synthetic",
            "expected_class": "oom",
            "attempts": [
                {"status": "failed", "exit": 137, "log_text": "Out of memory"},
            ],
            "expected_recovered": True,
            "expected_outcome": "pass",
        }
    )
    assert isinstance(scenario.attempts[0], AttemptSpec)
    assert scenario.attempts[0].status == "failed"
    assert scenario.attempts[0].exit == 137
    assert scenario.attempts[0].log_text == "Out of memory"
    # Documented defaults.
    assert scenario.auto_approve is False
    assert scenario.poll_decision is None
    assert scenario.resource_ceiling is None
    assert scenario.index_builder_result is None
    assert scenario.max_attempts == 3
    assert scenario.assay == "rnaseq"


def test_heal_scenario_json_round_trip():
    scenario = HealScenario(
        scenario_id="heal-002",
        description="missing index triggers index_builder",
        source="run:abc123",
        expected_class="missing_index",
        attempts=[AttemptSpec(status="failed", exit=1)],
        expected_recovered=True,
        expected_outcome="pass",
    )
    round_tripped = HealScenario.model_validate_json(scenario.model_dump_json())
    assert round_tripped == scenario
    assert round_tripped.attempts[0].log_text == ""


# --- HealClassScore / HealScenarioResult / HealEvalReport ------------------


def test_heal_class_score_constructs():
    score = HealClassScore(matched=3, total=4, rate=0.75)
    assert score.matched == 3
    assert score.total == 4
    assert score.rate == 0.75


def test_heal_scenario_result_constructs():
    result = HealScenarioResult(
        scenario_id="heal-001",
        diagnosed_class="oom",
        recovered=True,
        actual_outcome="pass",
        matched=True,
        divergence=[],
    )
    assert result.matched is True
    assert result.divergence == []


def test_heal_eval_report_constructs():
    report = HealEvalReport(
        total=10,
        matched=8,
        outcome_match_rate=0.8,
        healed=7,
        recovery_rate=0.7,
        per_class={"oom": HealClassScore(matched=3, total=4, rate=0.75)},
        mismatches=[],
    )
    assert report.total == 10
    assert report.per_class["oom"].total == 4


# --- HealSnapshot / HealGuardResult ----------------------------------------


def test_heal_snapshot_dump_json():
    snapshot = HealSnapshot(
        timestamp="2026-07-07T00:00:00Z",
        scenario_count=10,
        corpus_sha="deadbeef",
        outcome_match_rate=0.8,
        recovery_rate=0.7,
        per_class={"oom": HealClassScore(matched=3, total=4, rate=0.75)},
        covered_classes=["oom", "missing_index"],
    )
    payload = snapshot.model_dump_json()
    assert '"corpus_sha":"deadbeef"' in payload
    reloaded = HealSnapshot.model_validate_json(payload)
    assert reloaded == snapshot
    assert reloaded.contig_version is None


def test_heal_guard_result_dump_json():
    result = HealGuardResult(
        scenario_count=10,
        outcome_match_rate=0.8,
        baseline_match_rate=0.75,
        delta=0.05,
        tolerance=0.02,
        regressed=False,
        improved=True,
        recovery_rate=0.7,
        corpus_sha="deadbeef",
        baseline_sha="deadbeef",
        sha_mismatch=False,
        has_baseline=True,
        mismatches=[],
    )
    payload = result.model_dump_json()
    assert '"regressed":false' in payload
    reloaded = HealGuardResult.model_validate_json(payload)
    assert reloaded == result


# --- run_heal_scenario / evaluate_heal (Task 2: real self-heal driver) -----

from contig.heal import evaluate_heal, run_heal_scenario  # noqa: E402


def test_run_heal_scenario_oom_recovers(tmp_path):
    # Transcribed from test_self_heal.py:49-66 (test_self_heal_recovers_from_oom_and_logs_repair).
    scn = HealScenario(
        scenario_id="oom-1",
        description="OOM on star_align, retried with bumped memory",
        source="synthetic",
        expected_class="oom",
        attempts=[
            AttemptSpec(status="FAILED", exit=137, log_text="Process killed: out of memory (exit 137)"),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True
    assert result.diagnosed_class == "oom"
    assert result.recovered is True
    assert result.actual_outcome == "patched_and_retried"
    assert result.divergence == []


def test_run_heal_scenario_tool_crash_gives_up(tmp_path):
    # Transcribed from test_self_heal.py:140-148 (test_self_heal_gives_up_on_unrecoverable_tool_crash).
    scn = HealScenario(
        scenario_id="tool-crash-1",
        description="Segfault in some_tool is unrecoverable",
        source="synthetic",
        expected_class="tool_crash",
        attempts=[
            AttemptSpec(status="FAILED", exit=1, log_text="Segmentation fault in some_tool"),
        ],
        expected_recovered=False,
        expected_outcome="gave_up",
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True
    assert result.diagnosed_class == "tool_crash"
    assert result.recovered is False
    assert result.actual_outcome == "gave_up"


def test_run_heal_scenario_bwa_missing_index_unresolvable(tmp_path):
    # Transcribed from test_self_heal.py:190-216
    # (test_self_heal_bwa_missing_index_gives_up_unresolvable). The bwa signature
    # is detected as missing_index but its evidence line carries no parseable
    # index path, so the loop must give up honestly with index_unresolvable.
    scn = HealScenario(
        scenario_id="bwa-missing-index-1",
        description="bwa missing-index signature is unresolvable (no parseable path)",
        source="synthetic",
        expected_class="missing_index",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text="[E::bwa_idx_load_from_disk] fail to locate the index files",
            ),
        ],
        auto_approve=True,
        index_builder_result="success",
        expected_recovered=False,
        expected_outcome="index_unresolvable",
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True
    assert result.diagnosed_class == "missing_index"
    assert result.recovered is False
    assert result.actual_outcome == "index_unresolvable"


def test_run_heal_scenario_qc_anomaly_flags_a_green_run(tmp_path):
    """A14: a green-from-attempt-1 scenario whose run dir carries a header-only
    VCF drives the REAL `_discover_qc` to a FAIL verdict, so the loop's QC-anomaly
    trigger records one `qc_verdict_flagged` step -- no QC mocking anywhere.

    `expected_recovered=False`: nothing was healed here, and since R8 the driver
    says so -- `recovered` now requires event success AND some enacted patch, and
    this scenario's single `qc_verdict_flagged` step applies none.
    """
    scn = HealScenario(
        scenario_id="qc-anomaly-1",
        description="Green sarek run whose empty VCF fails variant QC",
        source="synthetic",
        expected_class="qc_anomaly",
        attempts=[AttemptSpec(status="COMPLETED", exit=0, log_text="done")],
        assay="variant_calling",
        qc_artifact="empty_vcf_gz",
        expected_recovered=False,
        expected_outcome="qc_verdict_flagged",
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True, result.divergence
    assert result.diagnosed_class == "qc_anomaly"
    assert result.actual_outcome == "qc_verdict_flagged"


def test_heal_scenario_qc_artifact_defaults_to_none():
    """The new field is opt-in: every shipped scenario that omits it keeps its
    existing behaviour (no artifact written into the run dir)."""
    scn = HealScenario(
        scenario_id="no-artifact",
        description="unchanged",
        source="synthetic",
        expected_class="oom",
        attempts=[AttemptSpec(status="FAILED", exit=137)],
        expected_recovered=False,
        expected_outcome="gave_up",
    )
    assert scn.qc_artifact is None


def test_heal_scenario_fasta_artifact_defaults_to_none():
    """PRD R3: `fasta_artifact` is additive and default-inert. A scenario built
    without it parses with the field at None, so the nine shipped JSONL lines
    stay byte-identical and take a byte-identical path through the driver."""
    scn = HealScenario(
        scenario_id="no-fasta-artifact",
        description="unchanged",
        source="synthetic",
        expected_class="oom",
        attempts=[AttemptSpec(status="FAILED", exit=137)],
        expected_recovered=False,
        expected_outcome="gave_up",
    )
    assert scn.fasta_artifact is None


def test_heal_scenario_stale_index_artifact_defaults_to_none():
    """PRD M6: `stale_index_artifact` is additive and default-inert. A scenario
    built without it parses with the field at None, so every existing shipped
    line keeps its behaviour (no stale sidecar pre-created into the run dir)."""
    scn = HealScenario(
        scenario_id="no-stale-artifact",
        description="unchanged",
        source="synthetic",
        expected_class="oom",
        attempts=[AttemptSpec(status="FAILED", exit=137)],
        expected_recovered=False,
        expected_outcome="gave_up",
    )
    assert scn.stale_index_artifact is None


def test_heal_scenario_stale_index_artifact_round_trips():
    """PRD M6: the field is fixture schema only (not part of the signed record),
    additive, and survives a JSON round-trip with its value intact."""
    scn = HealScenario(
        scenario_id="stale-roundtrip",
        description="stale sidecar named",
        source="synthetic",
        expected_class="missing_index",
        attempts=[AttemptSpec(status="FAILED", exit=1)],
        expected_recovered=True,
        expected_outcome="built_index_and_retried",
        stale_index_artifact="fixtures/aln.bam.bai",
    )
    round_tripped = HealScenario.model_validate_json(scn.model_dump_json())
    assert round_tripped == scn
    assert round_tripped.stale_index_artifact == "fixtures/aln.bam.bai"


def test_run_heal_scenario_reference_not_bgzf_recompresses_and_retries(tmp_path):
    """PRD R4: `fasta_artifact="plain_gzip"` makes the driver write a REAL
    non-BGZF gzip FASTA and point `params["fasta"]` at it, so the loop reaches
    the real `_recompress_reference` success path instead of stopping at its
    `reference_recompress_unresolvable` "no FASTA in params" guard.

    The log is the shipped detector-corpus wording for `reference-not-bgzf`; the
    trigger needle is `Cannot index files compressed with gzip`. The third line
    carries `index` and `.fai` but none of `missing_index`'s absence needles, so
    it is not stolen -- do not reword it toward "not found"/"missing".
    """
    scn = HealScenario(
        scenario_id="reference-not-bgzf-recompress",
        description="Plain-gzip reference FASTA is decompressed and the run retried",
        source="synthetic",
        expected_class="reference_not_bgzf",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text=(
                    "[E::fai_build_core] File truncated at line 1\n"
                    "[E::fai_build3_core] Cannot index files compressed with gzip, "
                    "please use bgzip\n"
                    "[faidx] Could not build fai index /work/ref.fa.gz.fai"
                ),
            ),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        auto_approve=True,
        fasta_artifact="plain_gzip",
        expected_recovered=True,
        expected_outcome="recompressed_reference_and_retried",
        expected_patch_applied=True,
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True, result.divergence
    assert result.diagnosed_class == "reference_not_bgzf"
    assert result.actual_outcome == "recompressed_reference_and_retried"
    assert result.recovered is True


def test_run_heal_scenario_missing_reference_approved_and_retried(tmp_path):
    """PRD R1/R5: `missing_reference` reaches its real, honest repair -- the
    `igenomes_ignore` param mutation (`repair.py:79-91`), gated on confirmation
    and merged into the retry's params (`self_heal.py:575-582`).

    The log is the shipped detector-corpus wording. It needs the full phrase
    `no such file or directory` PLUS a reference token; it must NOT name an index
    (`index`, `.fai`, `.bai`, `.tbi`, `.csi`, `.dict`, `genomeParameters.txt`) or
    `missing_index` steals it, and must carry no `killed`/`oom` and no exit 137,
    or the `oom` rule at `detect.py:90` steals it.

    `auto_approve` is load-bearing (PRD R6): the patch is `needs_confirmation`,
    so without it the driver falls back to the real file poll and the suite hangs
    for the default 1800 s approval timeout.
    """
    scn = HealScenario(
        scenario_id="missing-reference-approved",
        description="Absent reference FASTA; igenomes_ignore is approved and the run retried",
        source="synthetic",
        expected_class="missing_reference",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text="Error: No such file or directory: /data/genome.fasta",
            ),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        auto_approve=True,
        expected_recovered=True,
        expected_outcome="approved_and_retried",
        expected_patch_applied=True,
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True, result.divergence
    assert result.diagnosed_class == "missing_reference"
    assert result.actual_outcome == "approved_and_retried"
    assert result.recovered is True


def test_run_heal_scenario_container_pull_failed_patched_and_retried(tmp_path):
    """PRD R1/R5: `container_pull_failed` proposes a `safe` `{"retry": True}`
    patch (`repair.py:36-45`), so there is no approval gate and the re-run itself
    is the fix -- `apply_patch` is a documented no-op for a `retry` patch
    (`self_heal.py:549`). `patch_applied` therefore means ENACTED, not effective.

    The log is the shipped detector-corpus wording. It must NOT contain
    `docker.sock`/`cannot connect to the docker daemon` or `permission denied`
    (those rules are checked first), and no `killed`/`oom`/exit 137.
    """
    scn = HealScenario(
        scenario_id="container-pull-retry",
        description="Registry manifest error; the retry carries -resume and succeeds",
        source="synthetic",
        expected_class="container_pull_failed",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text=(
                    "failed to pull image quay.io/biocontainers/fastqc: manifest unknown"
                ),
            ),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
        expected_patch_applied=True,
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True, result.divergence
    assert result.diagnosed_class == "container_pull_failed"
    assert result.actual_outcome == "patched_and_retried"
    assert result.recovered is True


def test_run_heal_scenario_download_failed_patched_and_retried(tmp_path):
    """PRD R1/R5: `download_failed` proposes the same `safe` `{"retry": True}`
    patch (`repair.py:129-138`) -- ungated, and again a documented no-op whose
    fix is the re-run itself (`self_heal.py:549`).

    The log is the shipped detector-corpus wording. It must NOT contain
    `failed to pull` (`container_pull_failed` is checked first) and no
    `killed`/`oom`/exit 137.
    """
    scn = HealScenario(
        scenario_id="download-failed-retry",
        description="Transient foreign-file staging timeout; the retry succeeds",
        source="synthetic",
        expected_class="download_failed",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text=(
                    "Unable to stage foreign file https://example.org/genome.fa.gz: "
                    "connection timed out"
                ),
            ),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
        expected_patch_applied=True,
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True, result.divergence
    assert result.diagnosed_class == "download_failed"
    assert result.actual_outcome == "patched_and_retried"
    assert result.recovered is True


def test_run_heal_scenario_missing_reference_rejected_by_user(tmp_path):
    """PRD R12: the refusal path for a gated `missing_reference` patch. This is
    the exact shape v0.49.0 fixed -- before it, a rejected patch was still
    recorded with a non-null patch and rendered as `Repaired`. `patch_applied`
    must be False here: nothing was enacted.
    """
    scn = HealScenario(
        scenario_id="missing-reference-rejected",
        description="Absent reference FASTA; the user rejects igenomes_ignore",
        source="synthetic",
        expected_class="missing_reference",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text="Error: No such file or directory: /data/genome.fasta",
            ),
        ],
        poll_decision="reject",
        expected_recovered=False,
        expected_outcome="rejected_by_user",
        expected_patch_applied=False,
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True, result.divergence
    assert result.diagnosed_class == "missing_reference"
    assert result.actual_outcome == "rejected_by_user"
    assert result.recovered is False


def test_run_heal_scenario_reference_not_bgzf_unresolvable(tmp_path):
    """PRD R12: with NO `fasta_artifact`, the driver passes no params at all, so
    `_recompress_reference` hits its first guard ("No FASTA in params") and gives
    up honestly rather than claiming a repair (`self_heal.py:783-800`).
    """
    scn = HealScenario(
        scenario_id="reference-not-bgzf-unresolvable",
        description="Plain-gzip reference error with no reference path to act on",
        source="synthetic",
        expected_class="reference_not_bgzf",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text=(
                    "[E::fai_build_core] File truncated at line 1\n"
                    "[E::fai_build3_core] Cannot index files compressed with gzip, "
                    "please use bgzip\n"
                    "[faidx] Could not build fai index /work/ref.fa.gz.fai"
                ),
            ),
        ],
        auto_approve=True,
        expected_recovered=False,
        expected_outcome="reference_recompress_unresolvable",
        expected_patch_applied=False,
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True, result.divergence
    assert result.diagnosed_class == "reference_not_bgzf"
    assert result.actual_outcome == "reference_recompress_unresolvable"
    assert result.recovered is False


def test_run_heal_scenario_download_failed_exhausts_budget(tmp_path):
    """PRD R12: budget exhaustion. `max_attempts=1` means the first failure is
    also the last, so the loop must give up instead of spending a retry."""
    scn = HealScenario(
        scenario_id="download-failed-budget",
        description="Staging timeout with no retry budget left",
        source="synthetic",
        expected_class="download_failed",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text=(
                    "Unable to stage foreign file https://example.org/genome.fa.gz: "
                    "connection timed out"
                ),
            ),
        ],
        max_attempts=1,
        expected_recovered=False,
        expected_outcome="gave_up",
        expected_patch_applied=False,
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is True, result.divergence
    assert result.diagnosed_class == "download_failed"
    assert result.actual_outcome == "gave_up"
    assert result.recovered is False


def test_scenario_without_expected_patch_applied_is_unchanged(tmp_path):
    """R7 back-compat: `expected_patch_applied` is opt-in. A scenario omitting it
    parses with the field at None and scores exactly as it did before -- no new
    divergence entry, matched unchanged."""
    scn = HealScenario(
        scenario_id="oom-no-assertion",
        description="OOM heals; the scenario says nothing about patch_applied",
        source="synthetic",
        expected_class="oom",
        attempts=[
            AttemptSpec(status="FAILED", exit=137, log_text="Process killed: out of memory (exit 137)"),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
    )
    assert scn.expected_patch_applied is None

    result = run_heal_scenario(scn, tmp_path)
    assert result.divergence == []
    assert result.matched is True


def test_patch_applied_mismatch_is_a_divergence(tmp_path):
    """R7 negative: a scenario claiming a patch was applied, driven down a path
    that applies nothing (unrecoverable tool crash), must diverge -- and the
    divergence string must name the field so the failure is readable."""
    scn = HealScenario(
        scenario_id="tool-crash-claims-a-patch",
        description="Segfault gives up, but the scenario wrongly claims a patch was applied",
        source="synthetic",
        expected_class="tool_crash",
        attempts=[
            AttemptSpec(status="FAILED", exit=1, log_text="Segmentation fault in some_tool"),
        ],
        expected_recovered=False,
        expected_outcome="gave_up",
        expected_patch_applied=True,
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.matched is False
    assert any("patch_applied" in d for d in result.divergence), result.divergence


def test_patch_applied_match_is_not_a_divergence(tmp_path):
    """R7 positive control: when the loop agrees with the scenario's claim, the
    check must stay silent. Without this an implementation that appends a
    divergence unconditionally would still pass the negative test."""
    scn = HealScenario(
        scenario_id="oom-claims-a-patch",
        description="OOM heals by applying a resource patch, and says so",
        source="synthetic",
        expected_class="oom",
        attempts=[
            AttemptSpec(status="FAILED", exit=137, log_text="Process killed: out of memory (exit 137)"),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
        expected_patch_applied=True,
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.divergence == []
    assert result.matched is True


def test_a_green_run_that_applied_no_patch_is_not_recovered(tmp_path):
    """R8: `recovered` was event-derived, so a run that was green from attempt 1
    reported recovered=True although nothing was ever repaired -- the artifact the
    qc-anomaly slice disclosed rather than fixed (CAPABILITY_ROADMAP.md:1128-1132).

    The QC-anomaly path is the live instance: one task exits 0, the REAL
    `_discover_qc` reduces a header-only VCF to FAIL, and the loop records a single
    `qc_verdict_flagged` step that proposes and applies nothing.
    """
    scn = HealScenario(
        scenario_id="qc-anomaly-not-recovered",
        description="Green sarek run whose empty VCF fails variant QC; no patch applied",
        source="synthetic",
        expected_class="qc_anomaly",
        attempts=[AttemptSpec(status="COMPLETED", exit=0, log_text="done")],
        assay="variant_calling",
        qc_artifact="empty_vcf_gz",
        expected_recovered=False,
        expected_outcome="qc_verdict_flagged",
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.recovered is False
    assert result.matched is True, result.divergence


def test_a_healed_run_is_still_recovered(tmp_path):
    """R8 positive control: the redefinition must not demote a genuine heal. The
    OOM path fails, applies a resource patch, and retries green."""
    scn = HealScenario(
        scenario_id="oom-still-recovered",
        description="OOM is patched and retried",
        source="synthetic",
        expected_class="oom",
        attempts=[
            AttemptSpec(status="FAILED", exit=137, log_text="Process killed: out of memory (exit 137)"),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
    )
    result = run_heal_scenario(scn, tmp_path)
    assert result.recovered is True
    assert result.matched is True, result.divergence


def test_evaluate_heal_aggregates_rates(tmp_path):
    oom_scn = HealScenario(
        scenario_id="oom-1",
        description="OOM recovers",
        source="synthetic",
        expected_class="oom",
        attempts=[
            AttemptSpec(status="FAILED", exit=137, log_text="Process killed: out of memory (exit 137)"),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
    )
    tool_crash_scn = HealScenario(
        scenario_id="tool-crash-1",
        description="Segfault is unrecoverable",
        source="synthetic",
        expected_class="tool_crash",
        attempts=[
            AttemptSpec(status="FAILED", exit=1, log_text="Segmentation fault in some_tool"),
        ],
        expected_recovered=False,
        expected_outcome="gave_up",
    )
    # A scenario that will NOT match (expects the wrong outcome) so mismatches
    # and the aggregate rate below 1.0 are both exercised.
    mismatched_scn = HealScenario(
        scenario_id="tool-crash-mismatch",
        description="Segfault, but we (incorrectly) expect it to recover",
        source="synthetic",
        expected_class="tool_crash",
        attempts=[
            AttemptSpec(status="FAILED", exit=1, log_text="Segmentation fault in some_tool"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
    )

    report = evaluate_heal([oom_scn, tool_crash_scn, mismatched_scn])

    assert report.total == 3
    assert report.matched == 2
    assert report.outcome_match_rate == pytest.approx(2 / 3)
    assert report.healed == 1
    assert report.recovery_rate == pytest.approx(1 / 3)
    assert set(report.per_class) == {"oom", "tool_crash"}
    assert report.per_class["tool_crash"].total == 2
    assert report.per_class["tool_crash"].matched == 1
    assert len(report.mismatches) == 1
    assert report.mismatches[0].scenario_id == "tool-crash-mismatch"


# --- Shipped Core-mix scenario set (Task 4: the frozen 7 + committed baseline) --

from contig.heal import (  # noqa: E402
    compare_heal_to_baseline,
    default_heal_baseline_path,
    default_heal_scenarios_path,
    load_heal_baseline,
    load_heal_scenarios,
)
from contig.models import sha256_file  # noqa: E402


def test_shipped_heal_scenarios_all_reproduce_their_declared_outcomes():
    """The frozen Core-mix set (PRD R7) must score outcome_match_rate == 1.0
    when driven through the REAL self-heal loop: every shipped scenario behaves
    exactly as it declares."""
    scenarios = load_heal_scenarios(default_heal_scenarios_path())
    report = evaluate_heal(scenarios)

    assert report.total == 22
    assert report.outcome_match_rate == 1.0, [
        (m.scenario_id, m.divergence) for m in report.mismatches
    ]
    # 11 of 22, up from 11 of 21. This is a CORPUS-COMPOSITION change, not a
    # behaviour change: the C2 slice added one by-design give-up scenario
    # (alignment-format-mismatch-give-up, which recovers nothing -- the class
    # has no repair), and the ratio simply follows what was added. No
    # pre-existing scenario changed its outcome. `recovery_rate` is
    # informational-only and is never guarded (heal.py:413-414 compares only
    # outcome_match_rate) -- the guarded number is `outcome_match_rate`, which
    # stayed at 1.0 across the move.
    assert report.healed == 11
    assert report.recovery_rate == pytest.approx(11 / 22)

    covered = {s.expected_class for s in scenarios}
    assert covered >= {
        "oom",
        "time_limit",
        "missing_index",
        "tool_crash",
        "qc_anomaly",
        "missing_reference",
        "reference_not_bgzf",
        "container_pull_failed",
        "download_failed",
        "disk_full",
        "permission_denied",
        "conda_solve_failed",
        "container_unavailable",
        "alignment_format_mismatch",
    }


def test_shipped_heal_baseline_matches_shipped_scenarios():
    """The committed baseline is measured against the shipped scenario file
    (corpus_sha matches) and pins outcome_match_rate == 1.0."""
    scenarios_path = default_heal_scenarios_path()
    baseline = load_heal_baseline(default_heal_baseline_path())

    assert baseline is not None
    assert baseline.scenario_count == 22
    assert baseline.outcome_match_rate == 1.0
    # 11/22 since the C2 alignment-format give-up refreeze; 11/21 before it.
    # Again a CORPUS-COMPOSITION move -- one by-design give-up scenario
    # (alignment-format-mismatch-give-up, which recovers nothing) was added --
    # not a behaviour change, and never a guarded number.
    assert baseline.recovery_rate == pytest.approx(11 / 22)
    assert baseline.corpus_sha == sha256_file(scenarios_path)
    assert set(baseline.covered_classes) >= {
        "oom",
        "time_limit",
        "missing_index",
        "tool_crash",
        "qc_anomaly",
        "missing_reference",
        "reference_not_bgzf",
        "container_pull_failed",
        "download_failed",
        "disk_full",
        "permission_denied",
        "conda_solve_failed",
        "container_unavailable",
        "alignment_format_mismatch",
    }
    # Sixteen covered classes exactly -- the eleven the catalog-coverage slice
    # left, Task 6's four newly-honest classes (disk_full,
    # permission_denied, conda_solve_failed, container_unavailable), and the
    # C2 alignment-format-mismatch give-up. platform_unsupported stays
    # uncovered: detect.py:355 requires a failed
    # event with exit is None, but AttemptSpec.exit is a required int
    # (models.py:543) used both as the trace column (heal.py:82) and the
    # executor return code (:100) -- reaching it needs an additive
    # model/driver change, which is out of scope here. A silent drop here
    # would mean a class lost its scenario.
    assert len(baseline.covered_classes) == 16


def test_shipped_heal_report_does_not_regress_against_baseline():
    """Replaying the frozen set and comparing to the committed baseline shows no
    regression (this is the guard Task 5's CLI wraps)."""
    scenarios_path = default_heal_scenarios_path()
    scenarios = load_heal_scenarios(scenarios_path)
    report = evaluate_heal(scenarios)
    baseline = load_heal_baseline(default_heal_baseline_path())
    result = compare_heal_to_baseline(
        report,
        baseline=baseline,
        corpus_sha=sha256_file(scenarios_path),
        tolerance=0.0,
    )
    assert result.regressed is False
    assert result.sha_mismatch is False
    assert result.outcome_match_rate == 1.0


def test_evaluate_heal_is_deterministic_over_the_shipped_scenarios():
    """PRD R8: the same scenario corpus, run twice through the real self-heal
    loop, must yield identical rates -- proving the scored path has no run-to-
    run nondeterminism (flaky timing, ordering, etc.) that could mask or fake a
    regression."""
    scenarios = load_heal_scenarios(default_heal_scenarios_path())

    first = evaluate_heal(scenarios)
    second = evaluate_heal(scenarios)

    assert first.outcome_match_rate == second.outcome_match_rate
    assert first.recovery_rate == second.recovery_rate
    assert first.matched == second.matched
    assert first.total == second.total


def test_run_heal_scenario_stale_index_rebuilds_and_retries(tmp_path):
    """PRD M6 end-to-end: the shipped `stale-index-heal` scenario replays the
    REAL loop. htslib's freshness line classifies `missing_index`; the stale
    rebuild runs the scripted builder against the scratch symlink, whose
    simulated output (the touched `.bai`) is atomically swapped over the
    pre-created stale sidecar; the retry succeeds with the declared
    `built_index_and_retried` outcome.

    The artifact pre-create is load-bearing: the repair replaces the sidecar
    with the freshly built one, so the file that exists after the run is the
    builder's output, not the stale fixture the driver wrote.
    """
    from pathlib import Path

    scenarios = load_heal_scenarios(default_heal_scenarios_path())
    scn = next(s for s in scenarios if s.scenario_id == "stale-index-heal")

    result = run_heal_scenario(scn, tmp_path)

    assert result.matched is True, result.divergence
    assert result.diagnosed_class == "missing_index"
    assert result.actual_outcome == "built_index_and_retried"
    assert result.recovered is True
    sidecar = (
        Path(tmp_path) / "runs" / "heal-stale-index-heal" / "fixtures" / "aln.bam.bai"
    )
    assert sidecar.read_bytes() != b"stale-index-artifact"


# --- run_heal_scenario's defensive PipelineExecutionError branch -----------


def test_run_heal_scenario_handles_pipeline_execution_error(monkeypatch, tmp_path):
    """Unit-tests the driver's `except PipelineExecutionError` branch (never hit
    by the shipped scenario set) by monkeypatching the `self_heal_run` name
    `contig.heal` imports, so a hard executor/nextflow-launch failure still
    yields an honest 'no_record' result instead of an uncaught exception. This
    only stubs the loop inside this dedicated error-path test -- the shipped
    scored path above still drives the real loop end to end."""
    import contig.heal as heal_module
    from contig.runner import PipelineExecutionError

    def _boom(*args, **kwargs):
        raise PipelineExecutionError(1, None)

    monkeypatch.setattr(heal_module, "self_heal_run", _boom)

    scn = HealScenario(
        scenario_id="pipeline-execution-error-1",
        description="Hard nextflow-launch failure never reaches repair_history",
        source="synthetic",
        expected_class="oom",
        attempts=[
            AttemptSpec(status="FAILED", exit=137, log_text="Process killed: out of memory (exit 137)"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
    )

    result = heal_module.run_heal_scenario(scn, tmp_path)

    assert result.recovered is False
    assert result.actual_outcome == "no_record"
    assert result.diagnosed_class is None
    assert result.matched is False


# --- container_unavailable's wait_seconds is honored (Task 6) --------------


def test_container_unavailable_wait_is_honored_with_a_recording_sleeper(tmp_path):
    """`evaluate_heal` always drives scenarios through the shared no-op sleeper
    (`heal.py:_no_sleep`), so the frozen `container-unavailable-wait-and-retry-heal`
    scenario can only pin the terminal outcome -- it cannot prove the 15s wait
    (repair.py:46-55, self_heal.py:1442-1448) actually happened. This test calls
    `run_heal_scenario` directly with an injected recording sleeper to assert
    that, keeping the two concerns distinct: the frozen scenario pins the
    outcome, this test pins the wait.
    """
    calls: list[float] = []

    def recording_sleeper(seconds: float) -> None:
        calls.append(seconds)

    scn = HealScenario(
        scenario_id="container-unavailable-wait-proof",
        description="Docker daemon unreachable; an injected sleeper proves the 15s wait happened",
        source="synthetic",
        expected_class="container_unavailable",
        attempts=[
            AttemptSpec(
                status="FAILED",
                exit=1,
                log_text=(
                    "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
                    "Is the docker daemon running?"
                ),
            ),
            AttemptSpec(status="COMPLETED", exit=0, log_text="done"),
        ],
        expected_recovered=True,
        expected_outcome="patched_and_retried",
        expected_patch_applied=True,
    )

    result = run_heal_scenario(scn, tmp_path, sleeper=recording_sleeper)

    assert result.matched is True, result.divergence
    assert calls == [15]
