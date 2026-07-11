import json
from pathlib import Path

import pytest

from contig.corpus import load_corpus
from contig.models import ExecutionTarget, Patch, RunSummary
from contig.runner import PipelineExecutionError
from contig.self_heal import apply_patch, self_heal_run


def _trace(status, exit_code):
    return (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        f"1\tab/cd\t1\tNFCORE_RNASEQ:STAR_ALIGN (S1)\t{status}\t{exit_code}\t-\t-\t-\n"
    )


TRACE_OK = _trace("COMPLETED", 0)
TRACE_OOM = _trace("FAILED", 137)
TRACE_TOOL = _trace("FAILED", 1)


def _write(trace_path, trace_text, log_text):
    Path(trace_path).write_text(trace_text)
    (Path(trace_path).parent / "run.log").write_text(log_text)


def _target(d):
    return ExecutionTarget(backend="local", container_runtime="docker", work_dir=str(d))


def _heal(tmp_path, executor, **over):
    kwargs = dict(
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        profiles=["test", "docker"],
        target=_target(tmp_path / "w"),
        input_paths=[],
        runs_dir=tmp_path / "runs",
        run_id="r",
        executor=executor,
        max_attempts=3,
    )
    kwargs.update(over)
    return self_heal_run(**kwargs)


def test_self_heal_recovers_from_oom_and_logs_repair(tmp_path):
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_OOM, "Process killed: out of memory (exit 137)")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is True
    assert len(record.repair_history) == 1
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "oom"
    assert step.patch.risk == "safe"
    assert step.outcome == "patched_and_retried"


def test_self_heal_oom_bump_emits_bumped_resourcelimits(tmp_path):
    # The OOM fix must ride in the generated config's resourceLimits (what modern
    # nf-core honors), not the ignored --max_memory param. Default 8GB -> 16GB.
    state = {"n": 0, "retry_cfg": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_OOM, "out of memory exit 137")
            return 1
        state["retry_cfg"] = (Path(trace_path).parent / "nextflow.config").read_text()
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is True
    assert "process.resourceLimits = [ memory: 16.GB ]" in state["retry_cfg"]


def test_self_heal_writes_status_running_then_finished(tmp_path):
    # The dashboard reads status.json to know a run is in flight (run_record.json
    # only appears at the end). It must say "running" during, "finished" after.
    seen = {}

    def executor(cmd, trace_path):
        sp = Path(trace_path).parent / "status.json"
        seen["during"] = json.loads(sp.read_text())["state"] if sp.exists() else None
        _write(trace_path, TRACE_OK, "ok")
        return 0

    _heal(tmp_path, executor)
    final = json.loads((tmp_path / "runs" / "r" / "status.json").read_text())
    assert seen["during"] == "running"
    assert final["state"] == "finished"


def test_self_heal_populates_resource_usage_from_trace(tmp_path):
    # The final record carries per-task resource actuals parsed from trace.txt so
    # the dashboard and the cost model can price the run.
    trace = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\t"
        "duration\trealtime\t%cpu\tpeak_rss\n"
        "1\tab/cd\t1\tSTAR_ALIGN (S1)\tCOMPLETED\t0\t2026-01-01\t"
        "2m 5s\t2m 3s\t180.4%\t1.2 GB\n"
    )

    def executor(cmd, trace_path):
        _write(trace_path, trace, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert len(record.resource_usage) == 1
    task = record.resource_usage[0]
    assert task.process == "STAR_ALIGN (S1)"
    assert task.realtime_sec == 123.0
    assert task.peak_rss_mb == 1228.8
    assert task.pct_cpu == 180.4


def test_self_heal_writes_status_error_when_no_record(tmp_path):
    # A run that produced no trace at all (engine could not even start) is "error",
    # not a stuck "running".
    def executor(cmd, trace_path):
        return 1  # nonzero, no trace written -> no record

    with pytest.raises(PipelineExecutionError):
        _heal(tmp_path, executor)
    final = json.loads((tmp_path / "runs" / "r" / "status.json").read_text())
    assert final["state"] == "error"


def test_self_heal_gives_up_on_unrecoverable_tool_crash(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "Segmentation fault in some_tool")
        return 1

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is False
    assert record.verdict == "fail"
    assert record.repair_history[-1].outcome == "gave_up"


def test_self_heal_stashes_failure_as_pending_corpus_case(tmp_path):
    # Every failure is captured for the corpus with a PROVISIONAL label (the
    # detector's own guess) so a human can confirm it before it enters the
    # golden corpus. Stored separately, marked pending, so the eval never grades
    # the detector on its own guesses.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "Segmentation fault in some_tool")
        return 1

    _heal(tmp_path, executor)
    pending = load_corpus(tmp_path / "runs" / "pending_corpus.jsonl")
    assert len(pending) == 1
    assert pending[0].expected_class == "tool_crash"  # provisional = detector guess
    assert pending[0].source.startswith("pending:")
    assert pending[0].log_text  # the captured log travels with the case


def test_self_heal_does_not_stash_on_success(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor)
    assert not (tmp_path / "runs" / "pending_corpus.jsonl").exists()


def test_self_heal_pauses_for_approval_on_needs_confirmation(tmp_path):
    # A needs_confirmation patch no longer stops outright: the loop pauses and
    # awaits a human decision (contract C). With an immediate timeout poll it
    # records approval_timed_out.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "ERROR: genome.fai index not found")
        return 1

    record = _heal(tmp_path, executor, poll=lambda run_dir, timeout_sec: None)
    assert record.repair_history[0].diagnosis.failure_class == "missing_index"
    assert record.repair_history[0].outcome == "approval_timed_out"


def test_self_heal_bwa_missing_index_gives_up_unresolvable(tmp_path):
    # Classic bwa missing-index signature (bwa_idx_load_from_disk) IS detected
    # as missing_index, but its evidence line carries no parseable index path
    # (no .fai/.bai/.tbi/.csi/.dict token, and not a STAR genomeDir signature),
    # so _parse_missing_index returns None. Build support for this signature is
    # deliberately deferred this slice: the loop must give up honestly with
    # index_unresolvable — never fabricate a build, never a false pass.
    calls = {"n": 0}

    def index_builder(cmd, cwd):
        calls["n"] += 1
        return 0

    def executor(cmd, trace_path):
        _write(
            trace_path,
            TRACE_TOOL,
            "[E::bwa_idx_load_from_disk] fail to locate the index files",
        )
        return 1

    record = _heal(tmp_path, executor, auto_approve=True, index_builder=index_builder)
    last = record.repair_history[-1]
    assert last.diagnosis.failure_class == "missing_index"
    assert last.outcome == "index_unresolvable"
    assert record.verdict == "fail"
    assert calls["n"] == 0  # the builder is never invoked for an unparseable path


def test_self_heal_bwamem2_missing_index_gives_up_unresolvable(tmp_path):
    # bwa-mem2's unreadable-index signature (FMI_search's "Unable to open the
    # file" gated on the .bwt.2bit.64 sidecar token) IS detected as
    # missing_index, but its evidence line carries no parseable index path
    # (no .fai/.bai/.tbi/.csi/.dict token, and not a STAR genomeDir signature),
    # so _parse_missing_index returns None. Build support for this signature is
    # deliberately deferred this slice: the loop must give up honestly with
    # index_unresolvable — never fabricate a build, never a false pass.
    calls = {"n": 0}

    def index_builder(cmd, cwd):
        calls["n"] += 1
        return 0

    def executor(cmd, trace_path):
        _write(
            trace_path,
            TRACE_TOOL,
            "ERROR! Unable to open the file: /work/idx/genome.fasta.bwt.2bit.64",
        )
        return 1

    record = _heal(tmp_path, executor, auto_approve=True, index_builder=index_builder)
    last = record.repair_history[-1]
    assert last.diagnosis.failure_class == "missing_index"
    assert last.outcome == "index_unresolvable"
    assert record.verdict == "fail"
    assert calls["n"] == 0  # the builder is never invoked for an unparseable path


def test_self_heal_appends_repair_progress_line_per_attempt(tmp_path):
    # Each resolved self-heal attempt is appended to repair_progress.jsonl the
    # moment it resolves, so a live view can show attempts as they happen.
    from contig.models import RepairStep

    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_OOM, "out of memory exit 137")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    progress = (tmp_path / "runs" / "r" / "repair_progress.jsonl").read_text().splitlines()
    assert len(progress) == 1
    step = RepairStep.model_validate_json(progress[0])
    assert step.attempt == 1
    assert step.diagnosis.failure_class == "oom"
    assert step.outcome == "patched_and_retried"
    # the live lines mirror the final repair_history exactly
    assert [s.model_dump() for s in record.repair_history] == [step.model_dump()]


def test_self_heal_repair_progress_records_each_attempt_in_order(tmp_path):
    from contig.models import RepairStep

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OOM, "out of memory exit 137")
        return 1

    _heal(tmp_path, executor, max_attempts=3)
    lines = (tmp_path / "runs" / "r" / "repair_progress.jsonl").read_text().splitlines()
    attempts = [RepairStep.model_validate_json(line).attempt for line in lines]
    assert attempts == sorted(attempts)
    assert attempts == [1, 2, 3]


def test_self_heal_writes_no_repair_progress_on_clean_run(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor)
    assert not (tmp_path / "runs" / "r" / "repair_progress.jsonl").exists()


def _t():
    return ExecutionTarget(backend="local", container_runtime="docker", work_dir="w")


def test_apply_patch_resource_bump_updates_target_leaves_params(tmp_path):
    patch = Patch(kind="resource", operation={"multiply": {"memory": 2}},
                  rationale="x", risk="safe", expected_signal="s")
    target, params = apply_patch(_t(), patch, {"input": "sheet.csv"})
    assert target.resource_limits["memory"] == "16.GB"
    assert params == {"input": "sheet.csv"}


def test_apply_patch_param_merges_set_param_into_params(tmp_path):
    patch = Patch(kind="param", operation={"set_param": {"aligner": "star_salmon"}},
                  rationale="x", risk="needs_confirmation", expected_signal="s")
    target, params = apply_patch(_t(), patch, {"input": "sheet.csv"})
    assert params["aligner"] == "star_salmon"
    assert params["input"] == "sheet.csv"
    assert target.resource_limits == {}  # target untouched


def test_apply_patch_env_merges_operation_into_backend_options(tmp_path):
    patch = Patch(kind="env", operation={"relax_or_pin_env": True},
                  rationale="x", risk="needs_confirmation", expected_signal="s")
    target, params = apply_patch(_t(), patch, {})
    assert target.backend_options["relax_or_pin_env"] == "True"


def test_apply_patch_reference_build_index_is_rerun_only(tmp_path):
    patch = Patch(kind="reference", operation={"build_index": True},
                  rationale="x", risk="needs_confirmation", expected_signal="s")
    target, params = apply_patch(_t(), patch, {"input": "sheet.csv"})
    assert params == {"input": "sheet.csv"}  # unchanged: re-run is the fix
    assert target.resource_limits == {}


def test_apply_patch_reference_set_param_swaps_the_reference_param(tmp_path):
    # A reference patch carrying set_param swaps the reference into params (e.g.
    # point --genome at a resolved build) so the applied patch changes the re-run.
    patch = Patch(kind="reference", operation={"set_param": {"genome": "GRCh38"}},
                  rationale="x", risk="needs_confirmation", expected_signal="s")
    target, params = apply_patch(_t(), patch, {"input": "sheet.csv"})
    assert params["genome"] == "GRCh38"
    assert params["input"] == "sheet.csv"  # other params preserved
    assert target.resource_limits == {}  # target untouched


def test_self_heal_resume_passes_resume_on_first_execute(tmp_path):
    # With resume=True the FIRST execute must carry -resume (continue a cancelled
    # or interrupted run against its cached work dir), not just retries.
    seen = {}

    def executor(cmd, trace_path):
        seen["cmd"] = cmd
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor, resume=True)
    assert "-resume" in seen["cmd"]


# ---------------------------------------------------------------------------
# _finalize / harmonized_reference_direction breadcrumb tests
# ---------------------------------------------------------------------------

def test_finalize_harmonized_direction_adds_warn_breadcrumb(tmp_path):
    # When harmonized_reference_direction is set, _finalize enriches the record:
    # reference_identity.harmonized=True, a WARN QCResult is appended, and the
    # run verdict is capped at "warn" even when all pipeline tasks succeeded.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(
        tmp_path,
        executor,
        params={"fasta": "/fake/ref.fa", "gtf": "/fake/ref.gtf"},
        harmonized_reference_direction="add_chr",
    )

    assert record.reference_identity is not None
    assert record.reference_identity.harmonized is True
    assert record.reference_identity.harmonized_direction == "add_chr"
    assert record.harmonized_reference_direction == "add_chr"

    warn_checks = [r for r in record.qc_results if r.check == "reference_harmonized"]
    assert len(warn_checks) == 1
    assert warn_checks[0].status == "warn"
    assert warn_checks[0].kind == "structural"
    assert "add_chr" in warn_checks[0].message

    # The WARN check caps the verdict at "warn" — never "pass" for a harmonized run.
    assert record.verdict == "warn"


def test_finalize_no_harmonized_direction_leaves_identity_unchanged(tmp_path):
    # When harmonized_reference_direction is None (default), _finalize must not
    # touch reference_identity.harmonized and must not append a warn check.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(
        tmp_path,
        executor,
        params={"fasta": "/fake/ref.fa", "gtf": "/fake/ref.gtf"},
        # harmonized_reference_direction omitted (defaults to None)
    )

    assert record.reference_identity is not None
    assert record.reference_identity.harmonized is False
    assert record.reference_identity.harmonized_direction is None
    assert record.harmonized_reference_direction is None

    warn_checks = [r for r in record.qc_results if r.check == "reference_harmonized"]
    assert len(warn_checks) == 0


# ---------------------------------------------------------------------------
# sex_inference capture at _finalize (germline-gated, strictly == "variant_calling")
# ---------------------------------------------------------------------------

_SEX_VCF_HEADER = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chr1,length=248956422>\n"
    "##contig=<ID=chrX,length=156040895>\n"
    "##contig=<ID=chrY,length=57227415>\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
)


def _write_male_pattern_vcf(path):
    import gzip

    rows = [("chrX", 3_000_000 + i, "A", "G", "0/1") for i in range(2)]
    rows += [("chrX", 4_000_000 + i, "A", "G", "0/0") for i in range(28)]
    rows += [("chrY", 10_000_000 + i, "A", "G", "0/1") for i in range(6)]
    body = "".join(f"{c}\t{p}\t.\t{r}\t{a}\t.\tPASS\t.\tGT\t{gt}\n" for c, p, r, a, gt in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(_SEX_VCF_HEADER + body)
    return path


def test_finalize_germline_run_captures_sex_inference(tmp_path):
    _write_male_pattern_vcf(tmp_path / "runs" / "r" / "results" / "sample.vcf.gz")

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor, assay="variant_calling")

    assert record.sex_inference is not None
    assert record.sex_inference.inferred_sex == "XY"


def test_finalize_non_germline_run_leaves_sex_inference_none(tmp_path):
    # Gate is strictly `== "variant_calling"`, NOT the two-assay VARIANT_ASSAYS
    # tuple -- somatic and rnaseq must both leave sex_inference untouched, even
    # with a male-pattern VCF sitting under the run dir.
    _write_male_pattern_vcf(tmp_path / "runs" / "r" / "results" / "sample.vcf.gz")

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor, assay="rnaseq")

    assert record.sex_inference is None


# ---------------------------------------------------------------------------
# M8: the reference_harmonized breadcrumb must enumerate still-unmatched GTF
# contigs, mirroring exactly what cli.py's pre-flight block does: swap
# params["gtf"] to the harmonized scratch path BEFORE calling self_heal_run.
# ---------------------------------------------------------------------------

def _write_fasta(path, names):
    path.write_text("".join(f">{n}\ndescribeme\n" for n in names))


def _write_gtf(path, names):
    path.write_text(
        "".join(f"{n}\tsrc\texon\t1\t10\t.\t+\t.\tgene_id \"g\";\n" for n in names)
    )


def test_finalize_receives_the_harmonized_gtf_path_in_parameters(tmp_path):
    # This is the RED/decision test for the CRITICAL correctness question: what
    # does record.parameters["gtf"] hold at _finalize time? cli.py (line ~497)
    # overwrites params["gtf"] with the harmonized scratch path BEFORE calling
    # self_heal_run, so current_params (and thus record.parameters, set by
    # run_pipeline as `parameters=params or {}`) carries the HARMONIZED path,
    # never the original. This licenses recomputing the unmatched set in
    # _finalize from record.parameters directly, rather than threading a new
    # parameter through the whole self_heal_run call chain.
    from contig.reference_harmonize import harmonize_gtf, plan_harmonization

    fasta_path = tmp_path / "ref.fa"
    orig_gtf_path = tmp_path / "orig.gtf"
    _write_fasta(fasta_path, ["chr1", "chr2"])
    _write_gtf(orig_gtf_path, ["1", "2"])

    hplan = plan_harmonization(str(fasta_path), str(orig_gtf_path))
    assert hplan is not None
    harmonized_path = tmp_path / "harmonized.gtf"
    harmonize_gtf(str(orig_gtf_path), hplan.rename_map, harmonized_path)

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(
        tmp_path,
        executor,
        params={"fasta": str(fasta_path), "gtf": str(harmonized_path)},
        harmonized_reference_direction=hplan.direction,
    )

    # The GROUND TRUTH: record.parameters["gtf"] is the harmonized path we
    # passed in as `params["gtf"]`, NOT the original gtf path.
    assert record.parameters["gtf"] == str(harmonized_path)
    assert record.parameters["gtf"] != str(orig_gtf_path)


def test_finalize_harmonized_warn_message_lists_unmatched_contig(tmp_path):
    from contig.reference_harmonize import harmonize_gtf, plan_harmonization

    fasta_path = tmp_path / "ref.fa"
    orig_gtf_path = tmp_path / "orig.gtf"
    _write_fasta(fasta_path, ["chr1", "chr2"])
    # "weirdcontig" has no FASTA candidate at all -> lands in hplan.unmatched.
    _write_gtf(orig_gtf_path, ["1", "2", "weirdcontig"])

    hplan = plan_harmonization(str(fasta_path), str(orig_gtf_path))
    assert hplan is not None
    assert hplan.unmatched == ("weirdcontig",)

    harmonized_path = tmp_path / "harmonized.gtf"
    harmonize_gtf(str(orig_gtf_path), hplan.rename_map, harmonized_path)

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(
        tmp_path,
        executor,
        params={"fasta": str(fasta_path), "gtf": str(harmonized_path)},
        harmonized_reference_direction=hplan.direction,
    )

    warn_checks = [r for r in record.qc_results if r.check == "reference_harmonized"]
    assert len(warn_checks) == 1
    message = warn_checks[0].message
    assert "weirdcontig" in message
    assert "could not be matched" in message
    assert "1" in message  # "1 GTF contig(s)"

    # Existing invariants must still hold.
    assert record.reference_identity.harmonized is True
    assert record.reference_identity.harmonized_direction == hplan.direction
    assert record.verdict == "warn"


def test_finalize_harmonized_warn_message_omits_clause_when_fully_matched(tmp_path):
    from contig.reference_harmonize import harmonize_gtf, plan_harmonization

    fasta_path = tmp_path / "ref.fa"
    orig_gtf_path = tmp_path / "orig.gtf"
    _write_fasta(fasta_path, ["chr1", "chr2"])
    _write_gtf(orig_gtf_path, ["1", "2"])  # every contig matches -> no unmatched

    hplan = plan_harmonization(str(fasta_path), str(orig_gtf_path))
    assert hplan is not None
    assert hplan.unmatched == ()

    harmonized_path = tmp_path / "harmonized.gtf"
    harmonize_gtf(str(orig_gtf_path), hplan.rename_map, harmonized_path)

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(
        tmp_path,
        executor,
        params={"fasta": str(fasta_path), "gtf": str(harmonized_path)},
        harmonized_reference_direction=hplan.direction,
    )

    warn_checks = [r for r in record.qc_results if r.check == "reference_harmonized"]
    assert len(warn_checks) == 1
    message = warn_checks[0].message
    assert "could not be matched" not in message
    assert hplan.direction in message

    assert record.reference_identity.harmonized is True
    assert record.verdict == "warn"


# ---------------------------------------------------------------------------
# Ceiling-clamp + never-shrink tests (Task 1: resource-aware-retry)
# ---------------------------------------------------------------------------


def test_apply_patch_clamps_memory_to_ceiling():
    # 96 GB * 2 = 192 GB, but ceiling is 128 GB -> clamped to 128 GB
    patch = Patch(
        kind="resource",
        operation={"multiply": {"memory": 2}},
        rationale="OOM retry",
        risk="safe",
        expected_signal="no OOM exit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"memory": "96.GB"},
    )
    result, _ = apply_patch(target, patch, ceiling={"memory": 128, "time": 72})
    assert result.resource_limits["memory"] == "128.GB"


def test_apply_patch_clamps_time_to_ceiling():
    # 48 h * 2 = 96 h, but ceiling is 72 h -> clamped to 72 h
    patch = Patch(
        kind="resource",
        operation={"multiply": {"time": 2}},
        rationale="timeout retry",
        risk="safe",
        expected_signal="pipeline completes within time limit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"time": "48.h"},
    )
    result, _ = apply_patch(target, patch, ceiling={"memory": 128, "time": 72})
    assert result.resource_limits["time"] == "72.h"


def test_apply_patch_does_not_shrink_oversized_request():
    # Current allocation (256 GB) already exceeds the ceiling (128 GB).
    # The never-shrink rule must keep it at 256 GB, not reduce it to 128 GB.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"memory": 2}},
        rationale="OOM retry",
        risk="safe",
        expected_signal="no OOM exit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"memory": "256.GB"},
    )
    result, _ = apply_patch(target, patch, ceiling={"memory": 128, "time": 72})
    assert result.resource_limits["memory"] == "256.GB"


def test_apply_patch_scales_normally_below_ceiling():
    # 8 GB * 2 = 16 GB, well below ceiling of 128 GB -> normal scale, no clamp.
    # Uses the default ceiling=None path to prove built-in defaults (128/72) apply.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"memory": 2}},
        rationale="OOM retry",
        risk="safe",
        expected_signal="no OOM exit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"memory": "8.GB"},
    )
    result, _ = apply_patch(target, patch)  # ceiling=None -> uses CEILING_MEMORY_GB=128
    assert result.resource_limits["memory"] == "16.GB"


# ---------------------------------------------------------------------------
# observed_target_gb override (Task C2: peak-RSS resource scaling, Phase 2)
# ---------------------------------------------------------------------------


def test_apply_patch_observed_target_overrides_blind_multiplier():
    # A supplied observed target replaces the blind ×2 as the pre-clamp target.
    # 8 GB current, observed 12 GB, ceiling 128 -> 12 GB (not 16 from ×2).
    patch = Patch(
        kind="resource",
        operation={"multiply": {"memory": 2}},
        rationale="OOM retry",
        risk="safe",
        expected_signal="no OOM exit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"memory": "8.GB"},
    )
    result, _ = apply_patch(
        target, patch, ceiling={"memory": 128, "time": 72}, observed_target_gb=12
    )
    assert result.resource_limits["memory"] == "12.GB"


def test_apply_patch_observed_target_none_preserves_blind_behavior():
    # Default observed_target_gb=None -> unchanged blind ×2: 8 GB -> 16 GB.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"memory": 2}},
        rationale="OOM retry",
        risk="safe",
        expected_signal="no OOM exit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"memory": "8.GB"},
    )
    result, _ = apply_patch(
        target, patch, ceiling={"memory": 128, "time": 72}, observed_target_gb=None
    )
    assert result.resource_limits["memory"] == "16.GB"


def test_apply_patch_observed_target_never_shrinks_below_current():
    # Observed 2 GB is below the current 8 GB request; never-shrink holds 8 GB.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"memory": 2}},
        rationale="OOM retry",
        risk="safe",
        expected_signal="no OOM exit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"memory": "8.GB"},
    )
    result, _ = apply_patch(
        target, patch, ceiling={"memory": 128, "time": 72}, observed_target_gb=2
    )
    assert result.resource_limits["memory"] == "8.GB"


def test_apply_patch_observed_target_clamped_to_ceiling():
    # Observed 999 GB exceeds the 128 GB ceiling -> clamped to 128 GB.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"memory": 2}},
        rationale="OOM retry",
        risk="safe",
        expected_signal="no OOM exit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"memory": "8.GB"},
    )
    result, _ = apply_patch(
        target, patch, ceiling={"memory": 128, "time": 72}, observed_target_gb=999
    )
    assert result.resource_limits["memory"] == "128.GB"


def test_apply_patch_observed_target_leaves_time_branch_unaffected():
    # observed_target_gb only affects memory; a time multiply still scales ×2.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"time": 2}},
        rationale="timeout retry",
        risk="safe",
        expected_signal="pipeline completes within time limit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"time": "4.h"},
    )
    result, _ = apply_patch(
        target, patch, ceiling={"memory": 128, "time": 72}, observed_target_gb=12
    )
    assert result.resource_limits["time"] == "8.h"


# ---------------------------------------------------------------------------
# observed_target_h override (walltime scaling; realtime is a censored lower
# bound so the time override is FLOORED at the blind ×2 bump, unlike memory)
# ---------------------------------------------------------------------------


def test_apply_patch_observed_target_h_overrides_blind_multiplier_when_higher():
    # observed 15 h beats the blind ×2 (4 -> 8) -> pre-clamp target 15 h.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"time": 2}},
        rationale="timeout retry",
        risk="safe",
        expected_signal="pipeline completes within time limit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"time": "4.h"},
    )
    result, _ = apply_patch(
        target, patch, ceiling={"memory": 128, "time": 72}, observed_target_h=15
    )
    assert result.resource_limits["time"] == "15.h"


def test_apply_patch_observed_target_h_floored_at_blind_bump():
    # observed 6 h is BELOW the blind ×2 (4 -> 8); realtime is a censored lower
    # bound, so the blind floor wins -> 8 h (the walltime-specific behavior).
    patch = Patch(
        kind="resource",
        operation={"multiply": {"time": 2}},
        rationale="timeout retry",
        risk="safe",
        expected_signal="pipeline completes within time limit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"time": "4.h"},
    )
    result, _ = apply_patch(
        target, patch, ceiling={"memory": 128, "time": 72}, observed_target_h=6
    )
    assert result.resource_limits["time"] == "8.h"


def test_apply_patch_observed_target_h_none_preserves_blind_behavior():
    # Default observed_target_h=None -> unchanged blind ×2: 4 h -> 8 h.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"time": 2}},
        rationale="timeout retry",
        risk="safe",
        expected_signal="pipeline completes within time limit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"time": "4.h"},
    )
    result, _ = apply_patch(
        target, patch, ceiling={"memory": 128, "time": 72}, observed_target_h=None
    )
    assert result.resource_limits["time"] == "8.h"


def test_apply_patch_observed_target_h_clamped_to_ceiling():
    # observed 200 h exceeds the default 72 h ceiling -> clamped to 72 h.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"time": 2}},
        rationale="timeout retry",
        risk="safe",
        expected_signal="pipeline completes within time limit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"time": "40.h"},
    )
    result, _ = apply_patch(target, patch, observed_target_h=200)
    assert result.resource_limits["time"] == "72.h"


def test_apply_patch_observed_target_h_never_shrinks_below_current():
    # current 10 h, blind ×2 -> 20 h, observed 5 h; max(max(5,20),10)=20 h.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"time": 2}},
        rationale="timeout retry",
        risk="safe",
        expected_signal="pipeline completes within time limit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"time": "10.h"},
    )
    result, _ = apply_patch(
        target, patch, ceiling={"memory": 128, "time": 72}, observed_target_h=5
    )
    assert result.resource_limits["time"] == "20.h"


def test_apply_patch_observed_target_h_leaves_memory_branch_unaffected():
    # observed_target_h only affects time; memory scales via the blind ×2.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"memory": 2, "time": 2}},
        rationale="OOM + timeout retry",
        risk="safe",
        expected_signal="no OOM and completes within time limit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"memory": "8.GB", "time": "4.h"},
    )
    result, _ = apply_patch(
        target,
        patch,
        ceiling={"memory": 128, "time": 72},
        observed_target_gb=None,
        observed_target_h=15,
    )
    assert result.resource_limits["memory"] == "16.GB"
    assert result.resource_limits["time"] == "15.h"


def test_apply_patch_both_observed_overrides_honored_independently():
    # Memory override 90 GB and time override 15 h both applied on one patch.
    patch = Patch(
        kind="resource",
        operation={"multiply": {"memory": 2, "time": 2}},
        rationale="OOM + timeout retry",
        risk="safe",
        expected_signal="no OOM and completes within time limit",
    )
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir="w",
        resource_limits={"memory": "8.GB", "time": "4.h"},
    )
    result, _ = apply_patch(
        target,
        patch,
        ceiling={"memory": 128, "time": 72},
        observed_target_gb=90,
        observed_target_h=15,
    )
    assert result.resource_limits["memory"] == "90.GB"
    assert result.resource_limits["time"] == "15.h"


def test_self_heal_first_execute_has_no_resume_by_default(tmp_path):
    seen = {}

    def executor(cmd, trace_path):
        seen["cmd"] = cmd
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor)
    assert "-resume" not in seen["cmd"]


TRACE_INDEX = _trace("FAILED", 1)  # paired with a missing-index log -> gated patch


def _index_executor():
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_INDEX, "ERROR: genome.fai index not found")
        return 1
    return executor


def test_self_heal_writes_pending_approval_when_gated_patch_needed(tmp_path):
    # No safe patch, but a needs_confirmation patch exists: the loop pauses and
    # writes the approval request (read here from inside the poll, while paused,
    # since the file is cleared once a decision lands).
    captured = {}

    def poll(run_dir, timeout_sec):
        captured["pending"] = json.loads((Path(run_dir) / "pending_approval.json").read_text())
        return None  # time out

    _heal(tmp_path, _index_executor(), poll=poll)
    pending = captured["pending"]
    assert pending["run_id"] == "r"
    assert pending["attempt"] == 1
    assert pending["diagnosis"]["failure_class"] == "missing_index"
    assert pending["patch"]["kind"] == "reference"
    assert pending["patch"]["risk"] == "needs_confirmation"
    assert "requested_at" in pending and "timeout_sec" in pending


def test_self_heal_sets_awaiting_approval_state_while_paused(tmp_path):
    seen = {}

    def poll(run_dir, timeout_sec):
        seen["state"] = json.loads((Path(run_dir) / "status.json").read_text())["state"]
        return None

    _heal(tmp_path, _index_executor(), poll=poll)
    assert seen["state"] == "awaiting_approval"


def test_self_heal_approve_applies_patch_and_records_approved_outcome(tmp_path):
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, "ERROR: genome.fai index not found")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    def poll(run_dir, timeout_sec):
        return {"decision": "approve", "decided_at": "2026-06-22T00:00:00+00:00"}

    # The gated patch here is a build_index reference patch, so approving it now
    # builds the index (fake builder) before the retry: the recorded outcome is
    # built_index_and_retried.
    record = _heal(tmp_path, executor, poll=poll, index_builder=lambda cmd, cwd: 0)
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.repair_history[0].outcome == "built_index_and_retried"
    # the pending file is cleared once decided
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()
    final = json.loads((tmp_path / "runs" / "r" / "status.json").read_text())
    assert final["state"] == "finished"


def test_self_heal_reject_records_rejected_and_stops(tmp_path):
    def poll(run_dir, timeout_sec):
        return {"decision": "reject", "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, _index_executor(), poll=poll)
    assert record.repair_history[-1].outcome == "rejected_by_user"
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_timeout_records_timed_out_and_stops(tmp_path):
    def poll(run_dir, timeout_sec):
        return None  # no decision arrived within the window

    record = _heal(tmp_path, _index_executor(), poll=poll)
    assert record.repair_history[-1].outcome == "approval_timed_out"
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_auto_approve_applies_gated_patch_without_pending(tmp_path):
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, "ERROR: genome.fai index not found")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor, auto_approve=True, index_builder=lambda cmd, cwd: 0)
    # The build_index gated patch is built then retried under --auto-approve.
    assert record.repair_history[0].outcome == "built_index_and_retried"
    # auto-approve never writes a pending request (non-interactive path)
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_gives_up_when_no_patch_at_all(tmp_path):
    # An unrecoverable tool crash has no patch (safe or gated): still gave_up, no
    # pending request written.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "Segmentation fault in some_tool")
        return 1

    record = _heal(tmp_path, executor)
    assert record.repair_history[-1].outcome == "gave_up"
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_finalize_populates_output_checksums(tmp_path):
    # On a successful finalize, the produced outputs under results/ are hashed
    # into the record so a later `contig verify` can detect drift (contract B).
    from contig.bundle import compute_output_checksums

    def executor(cmd, trace_path):
        run_dir = Path(trace_path).parent
        results = run_dir / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / "summary.txt").write_bytes(b"produced")
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    run_dir = tmp_path / "runs" / "r"
    assert record.output_checksums == compute_output_checksums(run_dir / "results")
    assert record.output_checksums["summary.txt"]


def test_self_heal_output_checksums_empty_when_no_results(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert record.output_checksums == {}


def _notifications(tmp_path):
    path = tmp_path / "runs" / "notifications.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_self_heal_emits_finished_notification_on_success(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor)
    kinds = [n["kind"] for n in _notifications(tmp_path)]
    assert kinds == ["finished"]
    assert _notifications(tmp_path)[0]["run_id"] == "r"


def test_self_heal_emits_failed_notification_on_give_up(tmp_path):
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TOOL, "Segmentation fault in some_tool")
        return 1

    _heal(tmp_path, executor)
    kinds = [n["kind"] for n in _notifications(tmp_path)]
    assert kinds[-1] == "failed"


def test_self_heal_emits_awaiting_approval_notification_when_paused(tmp_path):
    _heal(tmp_path, _index_executor(), poll=lambda run_dir, timeout_sec: None)
    kinds = [n["kind"] for n in _notifications(tmp_path)]
    assert "awaiting_approval" in kinds


def test_self_heal_forwards_webhook_to_emit(tmp_path, monkeypatch):
    from contig import notify

    captured = []
    monkeypatch.setattr(notify, "_post_webhook", lambda url, payload: captured.append(url))

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    _heal(tmp_path, executor, notify_webhook="https://hook.example/x")
    assert captured == ["https://hook.example/x"]


# --- applied patch reaches the re-run (deeper self-heal, contract D) -----------
# Proven through the injected executor on the REAL proposer path: it captures
# the retry command (params ride there as --key value) and the generated config
# (env/resource ride there), so an applied param/env/reference patch
# demonstrably changes the next run. Each test triggers a real failure class,
# the matching gated patch is auto-approved, and the retry is inspected.


def _failing_then_capturing(state, log_text, on_retry):
    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_TOOL, log_text)
            return 1
        on_retry(cmd, trace_path)
        _write(trace_path, TRACE_OK, "done")
        return 0
    return executor


def test_self_heal_applied_param_patch_reaches_the_rerun_command(tmp_path):
    # A bad_param failure proposes a param patch carrying a corrected value; once
    # approved, the corrected parameter must appear in the retry's command.
    state = {"n": 0}
    seen = {}
    log = (
        "ERROR ~ Validation of pipeline parameters failed!\n"
        "The following invalid input values have been detected:\n"
        "* --aligner is not a valid parameter"
    )
    executor = _failing_then_capturing(
        state, log, lambda cmd, tp: seen.__setitem__("cmd", cmd)
    )
    record = _heal(tmp_path, executor, auto_approve=True, params={"input": "sheet.csv"})
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.repair_history[0].diagnosis.failure_class == "bad_param"
    assert record.repair_history[0].patch.kind == "param"
    assert record.repair_history[0].outcome == "approved_and_retried"
    # the param patch reached the retry command (a real --key value pair)
    assert "--validate_params" in seen["cmd"]
    assert "False" in seen["cmd"]


def test_self_heal_applied_reference_patch_reaches_the_rerun_command(tmp_path):
    # A missing_reference failure proposes a reference patch that disables igenomes
    # so a local reference is used; the swapped param must reach the retry command.
    state = {"n": 0}
    seen = {}
    log = "Error: No such file or directory: /data/genome.fasta"
    executor = _failing_then_capturing(
        state, log, lambda cmd, tp: seen.__setitem__("cmd", cmd)
    )
    record = _heal(tmp_path, executor, auto_approve=True, params={"input": "sheet.csv"})
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.repair_history[0].diagnosis.failure_class == "missing_reference"
    assert record.repair_history[0].patch.kind == "reference"
    assert "--igenomes_ignore" in seen["cmd"]
    assert "True" in seen["cmd"]


def test_self_heal_applied_env_patch_reaches_the_rerun_target(tmp_path):
    # A conda_solve_failed failure proposes an env patch; the env knob must land
    # on the target that the retry runs against (it rides backend_options into the
    # generated config). The final record carries the patched target, proving the
    # applied env change reached the re-run.
    state = {"n": 0}
    log = "ResolvePackageNotFound:\n  - bioconductor-dupradar=1.38"
    executor = _failing_then_capturing(state, log, lambda cmd, tp: None)
    record = _heal(tmp_path, executor, auto_approve=True, params={"input": "sheet.csv"})
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.repair_history[0].diagnosis.failure_class == "conda_solve_failed"
    assert record.repair_history[0].patch.kind == "env"
    assert record.target.backend_options.get("relax_or_pin_env") == "True"


def test_self_heal_respects_max_attempts(tmp_path):
    attempts = {"n": 0}

    def executor(cmd, trace_path):
        attempts["n"] += 1
        _write(trace_path, TRACE_OOM, "out of memory exit 137")
        return 1

    record = _heal(tmp_path, executor, max_attempts=2)
    assert RunSummary.from_events(record.events).succeeded is False
    assert attempts["n"] <= 2
    assert len(record.repair_history) <= 2


# --- guided escalation (PRD contract D) ----------------------------------------
# When a self-heal decision is AMBIGUOUS (low-confidence diagnosis, or several
# viable non-safe fixes and no single safe one), the gate becomes a CHOICE: the
# pending request carries a ranked `options` array (decision_kind "choice"), and
# the human picks one via approval.json's `choice` index. The existing single
# gated-patch path (decision_kind "single") is unchanged.


from contig.models import Diagnosis  # noqa: E402
from contig.self_heal import _is_ambiguous  # noqa: E402


def _gated(kind, op, rationale, signal):
    return Patch(
        kind=kind, operation=op, rationale=rationale,
        risk="needs_confirmation", expected_signal=signal,
    )


def _two_candidates(diagnosis):
    # Two viable non-safe fixes and no safe one: an ambiguous choice.
    return [
        _gated("reference", {"set_param": {"igenomes_ignore": True}},
               "Ignore igenomes and use the local reference.", "reference resolved"),
        _gated("reference", {"build_index": True},
               "Build the missing index before re-running.", "index present"),
    ]


def test_is_ambiguous_flags_low_confidence_single_gated_patch():
    # A single gated patch is normally the single path, but a low-confidence
    # diagnosis makes even that ambiguous: present it as a choice.
    diagnosis = Diagnosis(failure_class="missing_index", root_cause="guess", confidence=0.3)
    one = [_gated("reference", {"build_index": True}, "build it", "index present")]
    assert _is_ambiguous(diagnosis, one) is True


def test_is_ambiguous_flags_multiple_viable_non_safe_patches():
    diagnosis = Diagnosis(failure_class="missing_index", root_cause="sure", confidence=0.9)
    assert _is_ambiguous(diagnosis, _two_candidates(diagnosis)) is True


def test_is_ambiguous_clears_single_confident_gated_patch():
    diagnosis = Diagnosis(failure_class="missing_index", root_cause="sure", confidence=0.9)
    one = [_gated("reference", {"build_index": True}, "build it", "index present")]
    assert _is_ambiguous(diagnosis, one) is False


def test_self_heal_ambiguous_decision_writes_options_with_choice_kind(tmp_path):
    captured = {}

    def poll(run_dir, timeout_sec):
        captured["pending"] = json.loads((Path(run_dir) / "pending_approval.json").read_text())
        return None  # time out so the run stops after we inspect the request

    _heal(tmp_path, _index_executor(), poll=poll, propose=_two_candidates)
    pending = captured["pending"]
    assert pending["decision_kind"] == "choice"
    options = pending["options"]
    assert [o["index"] for o in options] == [0, 1]
    first = options[0]
    assert set(first) == {"index", "kind", "risk", "rationale", "expected_signal"}
    assert first["kind"] == "reference"
    assert first["risk"] == "needs_confirmation"
    # back-compat: the single-patch fields still describe the best option
    assert pending["patch"]["kind"] == options[0]["kind"]


def test_self_heal_single_gated_patch_keeps_single_decision_kind(tmp_path):
    captured = {}

    def poll(run_dir, timeout_sec):
        captured["pending"] = json.loads((Path(run_dir) / "pending_approval.json").read_text())
        return None

    _heal(tmp_path, _index_executor(), poll=poll)
    pending = captured["pending"]
    assert pending["decision_kind"] == "single"
    assert "options" not in pending


def test_self_heal_chosen_option_is_applied_and_reaches_the_rerun(tmp_path):
    # Pick option index 1 (build_index). The chosen option is applied and the loop
    # re-runs to success, recording the chose_and_retried outcome.
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, "ERROR: genome.fai index not found")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    def poll(run_dir, timeout_sec):
        return {"decision": "approve", "choice": 1, "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(
        tmp_path, executor, poll=poll, propose=_two_candidates,
        index_builder=lambda cmd, cwd: 0,
    )
    assert RunSummary.from_events(record.events).succeeded is True
    step = record.repair_history[0]
    # Choice 1 is the build_index option: it builds (fake builder) then retries.
    assert step.outcome == "built_index_and_retried"
    # the applied patch is the chosen option, not the best-ranked default
    assert step.patch.operation == {"build_index": True}
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_out_of_range_choice_is_refused_not_applied(tmp_path):
    def poll(run_dir, timeout_sec):
        return {"decision": "approve", "choice": 9, "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, _index_executor(), poll=poll, propose=_two_candidates)
    assert RunSummary.from_events(record.events).succeeded is False
    assert record.repair_history[-1].outcome == "invalid_choice_rejected"
    assert not (tmp_path / "runs" / "r" / "pending_approval.json").exists()


def test_self_heal_choice_reject_stops_without_applying(tmp_path):
    def poll(run_dir, timeout_sec):
        return {"decision": "reject", "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, _index_executor(), poll=poll, propose=_two_candidates)
    assert record.repair_history[-1].outcome == "rejected_by_user"


def test_self_heal_choice_timeout_stops_without_applying(tmp_path):
    record = _heal(
        tmp_path, _index_executor(),
        poll=lambda run_dir, timeout_sec: None, propose=_two_candidates,
    )
    assert record.repair_history[-1].outcome == "approval_timed_out"


def test_self_heal_choice_missing_index_defaults_to_rejected(tmp_path):
    # Approve with no choice on a choice gate is not actionable: refuse it rather
    # than silently apply the best-ranked option.
    def poll(run_dir, timeout_sec):
        return {"decision": "approve", "decided_at": "2026-06-22T00:00:00+00:00"}

    record = _heal(tmp_path, _index_executor(), poll=poll, propose=_two_candidates)
    assert record.repair_history[-1].outcome == "invalid_choice_rejected"
    assert RunSummary.from_events(record.events).succeeded is False


# --- Task 2: at-ceiling give-up (resource-aware-retry) --------------------------

TRACE_TIME_LIMIT = _trace("FAILED", 1)  # time limit detected from log text, not exit code


def test_gives_up_at_memory_ceiling(tmp_path):
    # Start with memory already at the ceiling; OOM on every attempt.
    # The loop must give up IMMEDIATELY (before scaling) with gave_up_at_ceiling.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OOM, "out of memory exit 137")
        return 1

    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir=str(tmp_path / "w"),
        resource_limits={"memory": "128.GB"},
    )
    record = _heal(tmp_path, executor, target=target)
    last = record.repair_history[-1]
    assert last.outcome == "gave_up_at_ceiling"
    assert last.detail is not None
    assert "memory" in last.detail
    assert "128" in last.detail
    assert record.verdict == "fail"


def test_gives_up_at_time_ceiling(tmp_path):
    # Start with time already at the ceiling; time limit on every attempt.
    # The loop must give up IMMEDIATELY with gave_up_at_ceiling.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_TIME_LIMIT, "Pipeline terminated due to time limit")
        return 1

    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir=str(tmp_path / "w"),
        resource_limits={"time": "72.h"},
    )
    record = _heal(tmp_path, executor, target=target)
    last = record.repair_history[-1]
    assert last.outcome == "gave_up_at_ceiling"
    assert last.detail is not None
    assert "time" in last.detail.lower()
    assert "72" in last.detail
    assert record.verdict == "fail"


def test_persistent_oom_terminates(tmp_path):
    # Persistent OOM with a low ceiling (16 GB). After the first retry bumps
    # memory to 16 GB, the loop must give up via the ceiling — not max_attempts.
    attempts_made = {"n": 0}

    def executor(cmd, trace_path):
        attempts_made["n"] += 1
        _write(trace_path, TRACE_OOM, "out of memory exit 137")
        return 1

    record = _heal(
        tmp_path,
        executor,
        max_attempts=10,
        resource_ceiling={"memory": 16, "time": 72},
    )
    # Must terminate (no infinite loop) and the ceiling must be the stop reason.
    last = record.repair_history[-1]
    assert last.outcome == "gave_up_at_ceiling"
    # Well short of max_attempts=10: default 8 GB -> 16 GB on first retry -> ceiling
    assert attempts_made["n"] < 10


def test_oom_recovers_below_ceiling_unchanged(tmp_path):
    # OOM once (low starting memory, well below the 128 GB cap), then succeeds.
    # Task 2 must not break normal recovery below the ceiling.
    state = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_OOM, "out of memory exit 137")
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)  # default 8 GB << 128 GB ceiling
    assert record.verdict != "fail"  # recovered (unverified or pass, not fail)
    patched = [s for s in record.repair_history if s.outcome == "patched_and_retried"]
    assert len(patched) >= 1


def test_ceiling_giveup_is_captured_in_pending_corpus(tmp_path):
    # When the loop gives up at the ceiling, the failure must still be captured
    # to the pending corpus (the existing append_case path runs before the patch
    # decision, so give-up-at-ceiling is included automatically).
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OOM, "out of memory exit 137")
        return 1

    pending_path = tmp_path / "my_corpus.jsonl"
    target = ExecutionTarget(
        backend="local",
        container_runtime="docker",
        work_dir=str(tmp_path / "w"),
        resource_limits={"memory": "128.GB"},
    )
    _heal(tmp_path, executor, target=target, pending_corpus=pending_path)
    pending = load_corpus(pending_path)
    assert len(pending) >= 1


# ---------------------------------------------------------------------------
# Pure parse helpers: _parse_missing_index and _index_build_command
# ---------------------------------------------------------------------------

def test_parse_missing_index_returns_relative_token():
    # The canonical fai_load evidence line → relative filename token with ext tuple.
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="fai not found",
        evidence=[
            "[E::fai_load] Failed to open the index reference.fasta.fai: No such file or directory"
        ],
        confidence=0.95,
    )
    assert _parse_missing_index(d) == ("reference.fasta.fai", ".fai")


def test_parse_missing_index_returns_absolute_token():
    # An absolute-path token must be returned verbatim.
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="fai not found",
        evidence=["Could not open /data/ref.fa.fai: No such file or directory"],
        confidence=0.9,
    )
    assert _parse_missing_index(d) == ("/data/ref.fa.fai", ".fai")


def test_parse_missing_index_returns_none_when_no_fai_token():
    # Evidence with no whitespace-free token ending in a supported extension → None.
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="some index issue",
        evidence=["Error: index file is missing"],
        confidence=0.7,
    )
    assert _parse_missing_index(d) is None


def test_index_build_command_strips_fai_suffix(tmp_path):
    # _index_build_command("reference.fasta.fai", ".fai", run_dir) → ["samtools", "faidx", "reference.fasta"]
    from contig.self_heal import _index_build_command

    assert _index_build_command("reference.fasta.fai", ".fai", tmp_path) == [
        "samtools",
        "faidx",
        "reference.fasta",
    ]


def test_index_build_command_strips_fai_suffix_absolute(tmp_path):
    # Works with absolute paths too.
    from contig.self_heal import _index_build_command

    assert _index_build_command("/data/ref.fa.fai", ".fai", tmp_path) == [
        "samtools",
        "faidx",
        "/data/ref.fa",
    ]


def test_parse_missing_index_ignores_trailing_suffix_token():
    # A token that merely *starts* with "<...>.fai" but continues (e.g. a backup
    # name) must NOT be truncated to a bogus ".fai" path — the boundary regex
    # rejects it, so with no real .fai token present we get None.
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="x",
        evidence=["staging touched ref.fasta.fai_backup before the failure"],
        confidence=0.5,
    )
    assert _parse_missing_index(d) is None


def test_parse_missing_index_canonical_colon_line_still_yields_fai():
    # The canonical "...fai:" evidence line must still parse cleanly to the path
    # (the colon is a token boundary, not part of the path).
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="fai not found",
        evidence=[
            "[E::fai_load] Failed to open the index reference.fasta.fai: No such file or directory"
        ],
        confidence=0.95,
    )
    assert _parse_missing_index(d) == ("reference.fasta.fai", ".fai")


# ---------------------------------------------------------------------------
# Phase 2: build a missing .fai and retry (spec AC1–AC6)
# ---------------------------------------------------------------------------

# The canonical samtools fai_load failure: names the missing reference.fasta.fai.
_FAI_LOG = (
    "[E::fai_load] Failed to open the index reference.fasta.fai: "
    "No such file or directory"
)


def _fai_executor(state, *, succeed_on_retry=True):
    """Fail attempt 1 with a missing-.fai log; (optionally) succeed on retry."""

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, _FAI_LOG)
            return 1
        if not succeed_on_retry:
            _write(trace_path, TRACE_INDEX, _FAI_LOG)
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0
    return executor


def _building_builder(calls, *, rc=0):
    """Fake IndexBuilder: records argv, creates the .fai in cwd, returns rc."""

    def index_builder(cmd, cwd):
        calls["n"] += 1
        calls["cmd"] = cmd
        if rc == 0:
            # mirror samtools faidx writing <fasta>.fai next to the fasta
            (Path(cwd) / "reference.fasta.fai").write_text("idx")
        return rc
    return index_builder


def test_self_heal_builds_missing_fai_and_retries(tmp_path):
    # AC1/AC5: a missing .fai is built and the pipeline re-runs to success.
    state = {"n": 0}
    calls = {"n": 0}
    record = _heal(
        tmp_path,
        _fai_executor(state),
        auto_approve=True,
        index_builder=_building_builder(calls),
    )
    assert RunSummary.from_events(record.events).succeeded is True
    last = record.repair_history[-1]
    assert last.outcome == "built_index_and_retried"
    assert last.patch.operation == {"build_index": True}
    assert state["n"] == 2  # the re-run actually happened
    assert calls["n"] == 1  # exactly one build


def test_self_heal_builder_invoked_with_samtools_faidx(tmp_path):
    # AC2: the builder is called with the exact samtools argv derived from evidence.
    state = {"n": 0}
    calls = {"n": 0}
    _heal(
        tmp_path,
        _fai_executor(state),
        auto_approve=True,
        index_builder=_building_builder(calls),
    )
    assert calls["cmd"] == ["samtools", "faidx", "reference.fasta"]


def test_self_heal_failed_index_build_fails_honestly(tmp_path):
    # AC3: a non-zero build ends in an honest FAIL with no extra retry.
    state = {"n": 0}
    calls = {"n": 0}
    record = _heal(
        tmp_path,
        _fai_executor(state),
        auto_approve=True,
        index_builder=_building_builder(calls, rc=1),
    )
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert last.detail is not None and "reference.fasta.fai" in last.detail
    assert record.verdict == "fail"
    assert calls["n"] == 1  # builder ran once
    assert state["n"] == 1  # executor was NOT re-run after the failed build


def test_self_heal_unparseable_index_path_fails_honestly(tmp_path):
    # AC4: a missing_index diagnosis with no parseable .fai token gives up honestly.
    # "index" + "not found" triggers missing_index in detect.py with no path token.
    state = {"n": 0}
    calls = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        _write(trace_path, TRACE_INDEX, "ERROR: index file not found")
        return 1

    record = _heal(
        tmp_path,
        executor,
        auto_approve=True,
        index_builder=_building_builder(calls),
    )
    last = record.repair_history[-1]
    assert last.diagnosis.failure_class == "missing_index"
    assert last.outcome == "index_unresolvable"
    assert record.verdict == "fail"
    assert calls["n"] == 0  # builder never called
    assert state["n"] == 1  # no re-run


# ---------------------------------------------------------------------------
# recompress-reference: a plain-gzip'd reference is decompressed and retried
# (self-heal-bgzip-reference, Phase 4 — the loop wiring for _recompress_reference)
# ---------------------------------------------------------------------------

_BGZF_FAI_LOG = (
    "[E::fai_build3_core] Cannot index files compressed with gzip, please use bgzip\n"
    "[faidx] Could not build fai index /work/ref.fa.gz.fai"
)

# The canonical 28-byte BGZF EOF block: magic 1f8b, FEXTRA set, "BC" subfield.
_BGZF_REF_BYTES = bytes.fromhex(
    "1f8b08040000000000ff0600424302001b0003000000000000000000"
)

_PLAIN_REF_FASTA = b">chr1\nACGT\n"


def _bgzip_ref_executor(state, *, succeed_on_retry=True):
    """Fail attempt 1 with the faidx not-BGZF log; (optionally) succeed on retry."""

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, _BGZF_FAI_LOG)
            return 1
        if not succeed_on_retry:
            _write(trace_path, TRACE_INDEX, _BGZF_FAI_LOG)
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0
    return executor


def test_self_heal_recompresses_reference_and_retries(tmp_path):
    # AC4: a plain-gzip reference is decompressed to scratch and the pipeline
    # re-runs, redirected at the scratch copy, to success.
    import gzip

    state = {"n": 0}
    fasta = tmp_path / "ref.fa.gz"
    fasta.write_bytes(gzip.compress(_PLAIN_REF_FASTA))

    record = _heal(
        tmp_path,
        _bgzip_ref_executor(state),
        auto_approve=True,
        params={"fasta": str(fasta)},
    )

    assert RunSummary.from_events(record.events).succeeded is True
    last = record.repair_history[-1]
    assert last.outcome == "recompressed_reference_and_retried"
    assert last.patch.operation == {"recompress_reference": True}
    scratch = tmp_path / "runs" / "r" / "healed_reference" / "ref.fa"
    assert scratch.is_file()
    assert scratch.read_bytes() == _PLAIN_REF_FASTA
    assert record.parameters["fasta"] == str(scratch)
    assert state["n"] == 2  # the re-run actually happened


def test_self_heal_recompress_persisting_failure_gives_up_once(tmp_path):
    # AC5: one-per-run guard. The same faidx failure on both attempts means the
    # scratch copy is already in built_paths on the retry -- give up honestly
    # instead of looping, bounded by max_attempts.
    import gzip

    state = {"n": 0}
    fasta = tmp_path / "ref.fa.gz"
    fasta.write_bytes(gzip.compress(_PLAIN_REF_FASTA))

    record = _heal(
        tmp_path,
        _bgzip_ref_executor(state, succeed_on_retry=False),
        auto_approve=True,
        params={"fasta": str(fasta)},
    )

    outcomes = [step.outcome for step in record.repair_history]
    assert outcomes.count("recompressed_reference_and_retried") == 1
    assert outcomes[-1] == "reference_recompress_unresolvable"
    assert record.verdict == "fail"
    assert state["n"] == 2  # exactly one retry attempted, then an honest give-up


def test_self_heal_recompress_no_fasta_gives_up(tmp_path):
    # give-up: no params["fasta"] at all (e.g. an iGenomes --genome KEY path).
    state = {"n": 0}

    record = _heal(
        tmp_path,
        _bgzip_ref_executor(state),
        auto_approve=True,
    )

    last = record.repair_history[-1]
    assert last.outcome == "reference_recompress_unresolvable"
    assert record.verdict == "fail"
    assert not RunSummary.from_events(record.events).succeeded


def test_self_heal_recompress_bgzf_reference_left_untouched(tmp_path):
    # give-up: a valid BGZF reference misfiled as the failure is left untouched.
    state = {"n": 0}
    fasta = tmp_path / "ref.fa.gz"
    fasta.write_bytes(_BGZF_REF_BYTES)

    record = _heal(
        tmp_path,
        _bgzip_ref_executor(state),
        auto_approve=True,
        params={"fasta": str(fasta)},
    )

    last = record.repair_history[-1]
    assert last.outcome == "reference_recompress_unresolvable"
    assert record.verdict == "fail"
    assert not (tmp_path / "runs" / "r" / "healed_reference").exists()


def test_self_heal_recompress_decompress_failure_gives_up(tmp_path):
    # give-up: a corrupt gzip fails to decompress -- honest FAIL, never a false pass.
    state = {"n": 0}
    fasta = tmp_path / "ref.fa.gz"
    fasta.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff" + b"\x00" * 4)

    record = _heal(
        tmp_path,
        _bgzip_ref_executor(state),
        auto_approve=True,
        params={"fasta": str(fasta)},
    )

    last = record.repair_history[-1]
    assert last.outcome == "reference_recompress_failed"
    assert record.verdict == "fail"
    assert not RunSummary.from_events(record.events).succeeded


# ---------------------------------------------------------------------------
# Phase 4: build a missing GATK .dict and retry (G1–G3)
# ---------------------------------------------------------------------------


def _dict_log_for(tmp_path):
    """A GATK missing-sequence-dictionary line naming paths under tmp_path, so
    the filesystem-probing deriver can resolve a FASTA the test actually creates.
    The /work/ref/... canonical path would NOT resolve here on purpose.
    """
    return (
        f"A USER ERROR has occurred: Fasta dict file {tmp_path}/genome.dict for "
        f"reference {tmp_path}/genome.fasta does not exist. Please build it using "
        f"e.g. picard CreateSequenceDictionary or samtools dict."
    )


def _dict_executor(state, dict_log, *, succeed_on_retry=True):
    """Fail attempt 1 with a missing-.dict log; (optionally) succeed on retry."""

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, dict_log)
            return 1
        if not succeed_on_retry:
            _write(trace_path, TRACE_INDEX, dict_log)
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    return executor


def _dict_building_builder(calls, *, rc=0):
    """Fake IndexBuilder for .dict: records argv, writes the .dict at the -o
    target (cmd[3]), returns rc. cmd is None only when the source is unresolvable
    — in which case the orchestration must never call us."""

    def index_builder(cmd, cwd):
        calls["n"] += 1
        calls["cmd"] = cmd
        if rc == 0 and cmd is not None:
            Path(cmd[3]).write_text("dict")
        return rc

    return index_builder


def test_self_heal_builds_missing_dict_and_retries(tmp_path):
    # G1: a missing .dict is built (samtools dict) and the pipeline re-runs to success.
    (tmp_path / "genome.fasta").write_text("ref")
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _dict_executor(state, _dict_log_for(tmp_path)),
        auto_approve=True,
        index_builder=_dict_building_builder(calls),
    )
    assert RunSummary.from_events(record.events).succeeded is True
    last = record.repair_history[-1]
    assert last.outcome == "built_index_and_retried"
    assert last.patch.operation == {"build_index": True}
    assert state["n"] == 2  # the re-run actually happened
    assert calls["n"] == 1  # exactly one build


def test_self_heal_dict_builder_invoked_with_samtools_dict(tmp_path):
    # G3: the builder is called with the exact samtools dict argv — output is the
    # missing .dict path, input is the resolved FASTA.
    (tmp_path / "genome.fasta").write_text("ref")
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    _heal(
        tmp_path,
        _dict_executor(state, _dict_log_for(tmp_path)),
        auto_approve=True,
        index_builder=_dict_building_builder(calls),
    )
    assert calls["cmd"] == [
        "samtools",
        "dict",
        "-o",
        f"{tmp_path}/genome.dict",
        f"{tmp_path}/genome.fasta",
    ]


def test_self_heal_dict_unresolvable_source_fails_honestly(tmp_path):
    # G2: a missing-.dict failure with NO FASTA companion on disk → the deriver
    # returns None → index_unresolvable, verdict FAIL, builder never called.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _dict_executor(state, _dict_log_for(tmp_path)),
        auto_approve=True,
        index_builder=_dict_building_builder(calls),
    )
    last = record.repair_history[-1]
    assert last.diagnosis.failure_class == "missing_index"
    assert last.outcome == "index_unresolvable"
    assert last.detail is not None and f"{tmp_path}/genome.dict" in last.detail
    assert record.verdict == "fail"
    assert calls["n"] == 0  # builder never called
    assert state["n"] == 1  # no re-run


def test_self_heal_failed_dict_build_fails_honestly(tmp_path):
    # G2: a resolvable source but a non-zero build → index_build_failed, the
    # .dict path in detail, verdict FAIL, no re-run.
    (tmp_path / "genome.fasta").write_text("ref")
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _dict_executor(state, _dict_log_for(tmp_path)),
        auto_approve=True,
        index_builder=_dict_building_builder(calls, rc=1),
    )
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert last.detail is not None and f"{tmp_path}/genome.dict" in last.detail
    assert record.verdict == "fail"
    assert calls["n"] == 1  # builder ran once
    assert state["n"] == 1  # no re-run after the failed build


# ---------------------------------------------------------------------------
# Phase 5: build each missing index at most once per run (termination guard)
# ---------------------------------------------------------------------------


def test_self_heal_dict_build_once_then_honest_give_up(tmp_path):
    # A wrong-reference masquerading as a missing dict: the build succeeds (rc 0)
    # but the re-run keeps failing the same way. We must build ONCE and give up
    # honestly, NOT rebuild on every attempt up to max_attempts.
    (tmp_path / "genome.fasta").write_text("ref")
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _dict_executor(state, _dict_log_for(tmp_path), succeed_on_retry=False),
        auto_approve=True,
        index_builder=_dict_building_builder(calls),
        max_attempts=3,
    )
    assert calls["n"] == 1  # built exactly once, not once per attempt
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert last.detail is not None
    assert "already rebuilt" in last.detail.lower()
    assert "failure persists" in last.detail.lower()
    assert record.verdict == "fail"


def test_self_heal_fai_happy_path_unaffected_by_build_once_guard(tmp_path):
    # Non-regression: the guard must not perturb a single-build success.
    state = {"n": 0}
    calls = {"n": 0}
    record = _heal(
        tmp_path,
        _fai_executor(state),
        auto_approve=True,
        index_builder=_building_builder(calls),
    )
    assert RunSummary.from_events(record.events).succeeded is True
    assert calls["n"] == 1  # one build, then success — unchanged
    assert record.repair_history[-1].outcome == "built_index_and_retried"


# ---------------------------------------------------------------------------
# New index-family unit tests: parse per kind + build command per kind
# ---------------------------------------------------------------------------

_BAI_LOG = 'samtools index: failed to open "aln.bam.bai": No such file or directory'
_TBI_LOG = "[E::idx_load] Could not load the index calls.vcf.gz.tbi: No such file or directory"
_CSI_LOG = "Failed to open calls.vcf.gz.csi: No such file or directory"
_DETERMINISM_LOG = "samtools index: aln.bam.bai missing for aln.bam: No such file or directory"
# The canonical GATK4 missing-sequence-dictionary USER ERROR, as emitted under
# nf-core/sarek. Names BOTH the missing .dict and the source .fasta; the parser
# must extract the .dict token (the path GATK looked for and could not find).
_DICT_LOG = (
    "A USER ERROR has occurred: Fasta dict file /work/ref/genome.dict for "
    "reference /work/ref/genome.fasta does not exist. Please build it using "
    "e.g. picard CreateSequenceDictionary or samtools dict."
)
# Some GATK builds print the path as a file:// URI; the parser captures it
# verbatim (URI form) and the deriver strips the scheme later (Phase 3).
_DICT_LOG_FILE_URI = (
    "A USER ERROR has occurred: Fasta dict file file:///work/ref/genome.dict "
    "does not exist."
)


def test_parse_missing_index_returns_bai_token():
    # .bai token: samtools index failure line.
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="bai not found",
        evidence=[_BAI_LOG],
        confidence=0.95,
    )
    assert _parse_missing_index(d) == ("aln.bam.bai", ".bai")


def test_parse_missing_index_returns_tbi_token():
    # .tbi token: tabix index load failure line.
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="tbi not found",
        evidence=[_TBI_LOG],
        confidence=0.95,
    )
    assert _parse_missing_index(d) == ("calls.vcf.gz.tbi", ".tbi")


def test_parse_missing_index_returns_csi_token():
    # .csi token: generic open failure line.
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="csi not found",
        evidence=[_CSI_LOG],
        confidence=0.95,
    )
    assert _parse_missing_index(d) == ("calls.vcf.gz.csi", ".csi")


def test_parse_missing_index_returns_dict_token():
    # .dict token: GATK missing-sequence-dictionary USER ERROR. The line also
    # names genome.fasta, but the .dict path is the one to extract.
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="sequence dictionary missing",
        evidence=[_DICT_LOG],
        confidence=0.85,
    )
    assert _parse_missing_index(d) == ("/work/ref/genome.dict", ".dict")


def test_parse_missing_index_returns_dict_token_file_uri():
    # file:// wrinkle: the captured token keeps the URI scheme; the deriver
    # strips it in Phase 3.
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="sequence dictionary missing",
        evidence=[_DICT_LOG_FILE_URI],
        confidence=0.85,
    )
    assert _parse_missing_index(d) == ("file:///work/ref/genome.dict", ".dict")


def test_parse_missing_index_determinism_picks_bai_token():
    # AC5: evidence line naming both aln.bam.bai and aln.bam → .bai token wins
    # (aln.bam ends in .bam which is not a supported extension, so .bai is selected).
    from contig.models import Diagnosis
    from contig.self_heal import _parse_missing_index

    d = Diagnosis(
        failure_class="missing_index",
        root_cause="bai missing",
        evidence=[_DETERMINISM_LOG],
        confidence=0.95,
    )
    assert _parse_missing_index(d) == ("aln.bam.bai", ".bai")


def test_index_build_command_bai(tmp_path):
    # AC2: .bai → samtools index <source>. Regression guard across the
    # (index_path, ext, run_dir) signature: suffix-strip kinds ignore run_dir.
    from contig.self_heal import _index_build_command

    assert _index_build_command("aln.bam.bai", ".bai", tmp_path) == [
        "samtools",
        "index",
        "aln.bam",
    ]


def test_index_build_command_tbi(tmp_path):
    # AC2: .tbi → tabix -p vcf <source>
    from contig.self_heal import _index_build_command

    assert _index_build_command("calls.vcf.gz.tbi", ".tbi", tmp_path) == [
        "tabix",
        "-p",
        "vcf",
        "calls.vcf.gz",
    ]


def test_index_build_command_csi(tmp_path):
    # AC2: .csi → bcftools index <source>
    from contig.self_heal import _index_build_command

    assert _index_build_command("calls.vcf.gz.csi", ".csi", tmp_path) == [
        "bcftools",
        "index",
        "calls.vcf.gz",
    ]


def test_index_build_command_bai_absolute(tmp_path):
    # AC2: absolute .bai path strips suffix correctly.
    from contig.self_heal import _index_build_command

    assert _index_build_command("/data/aln.bam.bai", ".bai", tmp_path) == [
        "samtools",
        "index",
        "/data/aln.bam",
    ]


# --- .dict source-deriver unit tests (filesystem-probing) ---


def test_resolve_dict_source_finds_fasta(tmp_path):
    # /dir/genome.dict with /dir/genome.fasta on disk → resolves the fasta.
    # run_dir is irrelevant for an absolute .dict path.
    from contig.self_heal import _resolve_dict_source

    (tmp_path / "genome.fasta").write_text("ref")
    dict_path = str(tmp_path / "genome.dict")
    assert _resolve_dict_source(dict_path, ".dict", tmp_path / "elsewhere") == str(
        tmp_path / "genome.fasta"
    )


def test_resolve_dict_source_priority_prefers_fasta(tmp_path):
    # All four companions present → .fasta wins (fixed priority order).
    from contig.self_heal import _resolve_dict_source

    for ext in (".fasta", ".fa", ".fasta.gz", ".fa.gz"):
        (tmp_path / f"genome{ext}").write_text("ref")
    dict_path = str(tmp_path / "genome.dict")
    assert _resolve_dict_source(dict_path, ".dict", tmp_path) == str(
        tmp_path / "genome.fasta"
    )


def test_resolve_dict_source_priority_falls_through_to_fa(tmp_path):
    # .fasta absent → next in priority (.fa) is chosen over .fasta.gz.
    from contig.self_heal import _resolve_dict_source

    (tmp_path / "genome.fa").write_text("ref")
    (tmp_path / "genome.fasta.gz").write_text("ref")
    dict_path = str(tmp_path / "genome.dict")
    assert _resolve_dict_source(dict_path, ".dict", tmp_path) == str(
        tmp_path / "genome.fa"
    )


def test_resolve_dict_source_absolute_probes_own_parent(tmp_path):
    # Absolute-safe: the fasta sits beside the .dict, NOT in run_dir.
    from contig.self_heal import _resolve_dict_source

    refdir = tmp_path / "ref"
    refdir.mkdir()
    (refdir / "genome.fasta").write_text("ref")
    rundir = tmp_path / "run"
    rundir.mkdir()
    dict_path = str(refdir / "genome.dict")
    assert _resolve_dict_source(dict_path, ".dict", rundir) == str(
        refdir / "genome.fasta"
    )


def test_resolve_dict_source_relative_probes_run_dir(tmp_path):
    # A relative .dict path probes run_dir for the companion fasta.
    from contig.self_heal import _resolve_dict_source

    (tmp_path / "genome.fa").write_text("ref")
    assert _resolve_dict_source("genome.dict", ".dict", tmp_path) == "genome.fa"


def test_resolve_dict_source_strips_file_uri(tmp_path):
    # A leading file:// scheme is stripped before Path math.
    from contig.self_heal import _resolve_dict_source

    refdir = tmp_path / "ref"
    refdir.mkdir()
    (refdir / "genome.fasta").write_text("ref")
    dict_uri = "file://" + str(refdir / "genome.dict")
    assert _resolve_dict_source(dict_uri, ".dict", tmp_path) == str(
        refdir / "genome.fasta"
    )


def test_resolve_dict_source_none_when_no_fasta(tmp_path):
    # No companion on disk → None (signals unresolvable to the orchestration).
    from contig.self_heal import _resolve_dict_source

    assert (
        _resolve_dict_source(str(tmp_path / "genome.dict"), ".dict", tmp_path) is None
    )


def test_index_build_command_dict(tmp_path):
    # AC: .dict → samtools dict -o <dict> <resolved-fasta>; output is the missing
    # .dict path itself, input is the resolved FASTA.
    from contig.self_heal import _index_build_command

    (tmp_path / "genome.fasta").write_text("ref")
    dict_path = str(tmp_path / "genome.dict")
    assert _index_build_command(dict_path, ".dict", tmp_path) == [
        "samtools",
        "dict",
        "-o",
        dict_path,
        str(tmp_path / "genome.fasta"),
    ]


def test_index_build_command_dict_unresolvable(tmp_path):
    # No FASTA companion → None (the orchestration turns this into
    # index_unresolvable).
    from contig.self_heal import _index_build_command

    assert _index_build_command(str(tmp_path / "genome.dict"), ".dict", tmp_path) is None


# --- End-to-end heal tests parameterized over .bai / .tbi / .csi ---


@pytest.mark.parametrize(
    "log_line, index_filename, expected_argv",
    [
        (
            _BAI_LOG,
            "aln.bam.bai",
            ["samtools", "index", "aln.bam"],
        ),
        (
            _TBI_LOG,
            "calls.vcf.gz.tbi",
            ["tabix", "-p", "vcf", "calls.vcf.gz"],
        ),
        (
            _CSI_LOG,
            "calls.vcf.gz.csi",
            ["bcftools", "index", "calls.vcf.gz"],
        ),
    ],
)
def test_self_heal_builds_missing_index_and_retries_per_kind(
    tmp_path, log_line, index_filename, expected_argv
):
    # AC1: fail-then-succeed for each of .bai/.tbi/.csi; outcome, argv, counts all correct.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, log_line)
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    def index_builder(cmd, cwd):
        calls["n"] += 1
        calls["cmd"] = cmd
        (Path(cwd) / index_filename).write_text("idx")
        return 0

    record = _heal(tmp_path, executor, auto_approve=True, index_builder=index_builder)
    assert RunSummary.from_events(record.events).succeeded is True
    last = record.repair_history[-1]
    assert last.outcome == "built_index_and_retried"
    assert last.patch.operation == {"build_index": True}
    assert state["n"] == 2  # re-run happened
    assert calls["n"] == 1  # exactly one build
    assert calls["cmd"] == expected_argv


@pytest.mark.parametrize(
    "log_line, index_filename",
    [
        (_BAI_LOG, "aln.bam.bai"),
        (_TBI_LOG, "calls.vcf.gz.tbi"),
        (_CSI_LOG, "calls.vcf.gz.csi"),
    ],
)
def test_self_heal_failed_index_build_fails_honestly_per_kind(
    tmp_path, log_line, index_filename
):
    # AC3: a non-zero build → index_build_failed, index path in detail, no retry.
    state = {"n": 0}
    calls = {"n": 0}

    def executor(cmd, trace_path):
        state["n"] += 1
        _write(trace_path, TRACE_INDEX, log_line)
        return 1

    def index_builder(cmd, cwd):
        calls["n"] += 1
        return 1

    record = _heal(tmp_path, executor, auto_approve=True, index_builder=index_builder)
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert last.detail is not None and index_filename in last.detail
    assert record.verdict == "fail"
    assert calls["n"] == 1
    assert state["n"] == 1  # no re-run after failed build


# ---------------------------------------------------------------------------
# STAR directory-index self-heal: build into scratch from params + redirect
# ---------------------------------------------------------------------------

# STAR opens genomeParameters.txt first; a missing/partial index surfaces here,
# naming the failing genomeDir. The version-incompatible line carries NO path.
_STAR_MISSING_LOG = (
    "EXITING because of FATAL ERROR: could not open genome file "
    "/user/idx/genomeParameters.txt"
)
_STAR_VERSION_LOG = (
    "EXITING because of FATAL ERROR: Genome version: 20201 is INCOMPATIBLE "
    "with running STAR version: 2.7.5a_2020-06-29\n"
    "SOLUTION: please re-generate genome from scratch with STAR >= 2.5"
)


def _star_executor(state, log, *, succeed_on_retry=True):
    """Fail attempt 1 with a STAR index log; (optionally) succeed on retry."""

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, log)
            return 1
        if not succeed_on_retry:
            _write(trace_path, TRACE_INDEX, log)
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    return executor


def _star_building_builder(calls, *, rc=0, empty=False):
    """Fake STAR IndexBuilder: records argv, creates the --genomeDir scratch dir
    and (unless ``empty``) a fake core file inside it, returns rc."""

    def index_builder(cmd, cwd):
        calls["n"] += 1
        calls["cmd"] = cmd
        genome_dir = Path(cmd[cmd.index("--genomeDir") + 1])
        genome_dir.mkdir(parents=True, exist_ok=True)
        if rc == 0 and not empty:
            (genome_dir / "Genome").write_text("idx")
        return rc

    return index_builder


def _star_scratch(tmp_path):
    return str((tmp_path / "runs" / "r").resolve() / "healed_index" / "star")


def test_self_heal_builds_missing_star_index_and_redirects(tmp_path):
    # STAR missing: rebuild into run-scoped scratch, redirect star_index, retry.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_MISSING_LOG),
        auto_approve=True,
        index_builder=_star_building_builder(calls),
        params={
            "star_index": "/user/idx",
            "fasta": "/ref/genome.fa",
            "gtf": "/ref/genes.gtf",
        },
    )
    assert RunSummary.from_events(record.events).succeeded is True
    last = record.repair_history[-1]
    assert last.outcome == "built_index_and_retried"
    assert state["n"] == 2  # the re-run actually happened
    assert calls["n"] == 1  # exactly one build
    scratch = _star_scratch(tmp_path)
    cmd = calls["cmd"]
    assert cmd[0] == "STAR"
    for tok in (
        "--runMode",
        "genomeGenerate",
        "--genomeDir",
        scratch,
        "--genomeFastaFiles",
        "/ref/genome.fa",
        "--sjdbGTFfile",
        "/ref/genes.gtf",
    ):
        assert tok in cmd
    # the retried run was redirected at the freshly built scratch index
    assert record.parameters.get("star_index") == scratch


def test_self_heal_star_version_incompatible_redirects_without_touching_user_index(tmp_path):
    # The version-incompatible line has NO path: the failing genomeDir must come
    # from params["star_index"], and the user's intact index is never overwritten.
    user_idx = tmp_path / "user_idx"
    user_idx.mkdir()
    (user_idx / "SAindex").write_text("original")
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_VERSION_LOG),
        auto_approve=True,
        index_builder=_star_building_builder(calls),
        params={"star_index": str(user_idx), "fasta": "/ref/genome.fa"},
    )
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.repair_history[-1].outcome == "built_index_and_retried"
    scratch = _star_scratch(tmp_path)
    assert record.parameters.get("star_index") == scratch
    assert calls["cmd"][calls["cmd"].index("--genomeDir") + 1] == scratch
    # the user's supplied index dir is untouched
    assert (user_idx / "SAindex").read_text() == "original"


def test_self_heal_star_build_without_gtf_omits_sjdb(tmp_path):
    # No gtf in params → argv omits --sjdbGTFfile and the build still heals.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_MISSING_LOG),
        auto_approve=True,
        index_builder=_star_building_builder(calls),
        params={"star_index": "/user/idx", "fasta": "/ref/genome.fa"},
    )
    assert record.repair_history[-1].outcome == "built_index_and_retried"
    assert "--sjdbGTFfile" not in calls["cmd"]
    assert "--genomeFastaFiles" in calls["cmd"]


def test_self_heal_star_missing_fasta_is_unresolvable(tmp_path):
    # No fasta to build from → index_unresolvable, builder never called, no re-run.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_MISSING_LOG),
        auto_approve=True,
        index_builder=_star_building_builder(calls),
        params={"star_index": "/user/idx"},
    )
    last = record.repair_history[-1]
    assert last.outcome == "index_unresolvable"
    assert record.verdict == "fail"
    assert calls["n"] == 0
    assert state["n"] == 1


def test_self_heal_star_unresolvable_dir_is_unresolvable(tmp_path):
    # Version log (no path) AND no star_index param → the genomeDir can't be
    # resolved at all → index_unresolvable, builder never called.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_VERSION_LOG),
        auto_approve=True,
        index_builder=_star_building_builder(calls),
        params={"fasta": "/ref/genome.fa"},
    )
    last = record.repair_history[-1]
    assert last.outcome == "index_unresolvable"
    assert record.verdict == "fail"
    assert calls["n"] == 0
    assert state["n"] == 1


def test_self_heal_star_build_nonzero_fails_honestly(tmp_path):
    # A non-zero STAR build → index_build_failed, no re-run.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_MISSING_LOG),
        auto_approve=True,
        index_builder=_star_building_builder(calls, rc=2),
        params={"star_index": "/user/idx", "fasta": "/ref/genome.fa"},
    )
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert record.verdict == "fail"
    assert calls["n"] == 1
    assert state["n"] == 1


def test_self_heal_star_build_empty_dir_fails_honestly(tmp_path):
    # rc 0 but the scratch dir is empty (no index produced) → index_build_failed.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_MISSING_LOG),
        auto_approve=True,
        index_builder=_star_building_builder(calls, empty=True),
        params={"star_index": "/user/idx", "fasta": "/ref/genome.fa"},
    )
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert record.verdict == "fail"
    assert calls["n"] == 1
    assert state["n"] == 1


def test_self_heal_star_build_once_then_honest_give_up(tmp_path):
    # Build succeeds (rc 0) but the re-run keeps failing the same way: build the
    # genomeDir ONCE, then give up honestly rather than rebuild every attempt.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_MISSING_LOG, succeed_on_retry=False),
        auto_approve=True,
        index_builder=_star_building_builder(calls),
        params={"star_index": "/user/idx", "fasta": "/ref/genome.fa"},
        max_attempts=3,
    )
    assert calls["n"] == 1  # built exactly once, not once per attempt
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert last.detail is not None
    assert "already rebuilt" in last.detail.lower()
    assert "failure persists" in last.detail.lower()
    assert record.verdict == "fail"


# ---------------------------------------------------------------------------
# Task 3 (R1): bound the STAR rebuild to exactly ONE per run, even when the
# redirect makes the second failure's failing_dir the scratch path itself.
# ---------------------------------------------------------------------------


def test_self_heal_star_version_incompatible_second_failure_recognizes_scratch_as_built(
    tmp_path,
):
    # The version-incompatible line carries NO path, so the failing genomeDir is
    # resolved from params["star_index"] each time. After a successful build the
    # redirect rewrites params["star_index"] to the scratch path, so a SECOND
    # version-incompatible failure resolves failing_dir == scratch. That must be
    # recognized as already-built (not a fresh path to rebuild): give up
    # honestly, and never rebuild into the same scratch dir a second time.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_VERSION_LOG, succeed_on_retry=False),
        auto_approve=True,
        index_builder=_star_building_builder(calls),
        params={"star_index": "/user/idx", "fasta": "/ref/genome.fa"},
        max_attempts=3,
    )
    assert calls["n"] == 1  # built exactly once, never rebuilt the scratch dir
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert last.detail is not None and "already rebuilt" in last.detail.lower()
    assert record.verdict == "fail"


def test_self_heal_star_build_uses_fresh_scratch_dir_not_residue(tmp_path):
    # The scratch dir must be wiped before each build so a build that produces NO
    # output can't be masked as a "success" by residue already sitting in the
    # scratch dir (e.g. left over from outside this run).
    scratch = _star_scratch(tmp_path)
    Path(scratch).mkdir(parents=True)
    (Path(scratch) / "stale_from_before").write_text("leftover")
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_MISSING_LOG),
        auto_approve=True,
        index_builder=_star_building_builder(calls, empty=True),
        params={"star_index": "/user/idx", "fasta": "/ref/genome.fa"},
    )
    last = record.repair_history[-1]
    # the (empty) build produced nothing; residue must not fake a "success"
    assert last.outcome == "index_build_failed"
    assert not (Path(scratch) / "stale_from_before").exists()  # residue was wiped


# ---------------------------------------------------------------------------
# Task 3 (R2): a NEW-reason retry failure after a successful STAR build must
# surface honestly — no re-entry into the STAR builder, no false pass.
# ---------------------------------------------------------------------------


def test_self_heal_star_new_reason_after_build_gives_up_honestly_no_second_build(tmp_path):
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, _STAR_MISSING_LOG)
            return 1
        # A different, unrecoverable failure on the retry: not an index failure.
        _write(trace_path, TRACE_TOOL, "Segmentation fault in some_tool")
        return 1

    record = _heal(
        tmp_path,
        executor,
        auto_approve=True,
        index_builder=_star_building_builder(calls),
        params={"star_index": "/user/idx", "fasta": "/ref/genome.fa"},
        max_attempts=3,
    )
    assert calls["n"] == 1  # exactly one STAR build — the loop did not re-enter it
    assert state["n"] == 2  # the retry actually happened once
    last = record.repair_history[-1]
    assert last.outcome != "built_index_and_retried"
    assert last.outcome == "gave_up"  # tool_crash proposes no patches: honest give-up
    assert RunSummary.from_events(record.events).succeeded is False
    assert record.verdict == "fail"


# ---------------------------------------------------------------------------
# Task 3 (R3/S1): record the STAR genome version used, read from the freshly
# built genomeParameters.txt. Tolerant of a missing file/line.
# ---------------------------------------------------------------------------


def _star_building_builder_with_version(calls, version_line):
    """Fake STAR IndexBuilder that also writes a genomeParameters.txt carrying
    the given raw ``versionGenome`` line (caller controls tab vs space)."""

    def index_builder(cmd, cwd):
        calls["n"] += 1
        calls["cmd"] = cmd
        genome_dir = Path(cmd[cmd.index("--genomeDir") + 1])
        genome_dir.mkdir(parents=True, exist_ok=True)
        (genome_dir / "Genome").write_text("idx")
        (genome_dir / "genomeParameters.txt").write_text(version_line)
        return 0

    return index_builder


@pytest.mark.parametrize(
    "version_line",
    [
        "versionGenome\t2.7.4a\nother\tvalue\n",  # tab-separated (real STAR format)
        "versionGenome 2.7.9a\n",  # space-separated — be tolerant
    ],
)
def test_self_heal_star_build_records_genome_version_in_detail(tmp_path, version_line):
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_MISSING_LOG),
        auto_approve=True,
        index_builder=_star_building_builder_with_version(calls, version_line),
        params={"star_index": "/user/idx", "fasta": "/ref/genome.fa"},
    )
    last = record.repair_history[-1]
    assert last.outcome == "built_index_and_retried"
    version = version_line.split(None, 2)[1].strip()
    assert last.detail is not None and version in last.detail


def test_self_heal_star_build_detail_graceful_without_version_line(tmp_path):
    # No genomeParameters.txt written at all -> a graceful detail, never a
    # failed heal over a missing version.
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _star_executor(state, _STAR_MISSING_LOG),
        auto_approve=True,
        index_builder=_star_building_builder(calls),  # writes no genomeParameters.txt
        params={"star_index": "/user/idx", "fasta": "/ref/genome.fa"},
    )
    last = record.repair_history[-1]
    scratch = _star_scratch(tmp_path)
    assert last.outcome == "built_index_and_retried"
    assert last.detail == f"Built STAR index into {scratch}."


# ---------------------------------------------------------------------------
# Task 3: reference identity captured on every finalized record
# ---------------------------------------------------------------------------


def test_self_heal_finalize_populates_reference_identity_explicit(tmp_path):
    # A successful run whose params carry fasta+gtf (pointing at real tmp_path
    # files) must finalize with reference_identity populated in "explicit" mode.
    fasta = tmp_path / "ref.fa"
    gtf = tmp_path / "ref.gtf"
    fasta.write_bytes(b">chr1\nACGT\n")
    gtf.write_bytes(b"# gtf\n")

    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(
        tmp_path,
        executor,
        params={"fasta": str(fasta), "gtf": str(gtf)},
    )
    assert record.reference_identity is not None
    assert record.reference_identity.mode == "explicit"
    assert record.reference_identity.fasta_sha256 is not None
    assert record.reference_identity.gtf_sha256 is not None


def test_self_heal_finalize_reference_identity_none_when_no_reference_keys(tmp_path):
    # A successful run whose params carry NO reference keys (no genome, fasta, gtf)
    # must leave reference_identity as None.
    def executor(cmd, trace_path):
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor, params={"input": "sheet.csv"})
    assert record.reference_identity is None


# --- Phase 3: peak-RSS-informed OOM retry sizing (C2) -----------------------
#
# These drive the real self_heal loop through a fake executor that writes a
# partial trace, exercising the OOM safe-path wiring that sizes the memory
# retry from the run's observed peak RSS (helper: peak_informed_memory_gb) and
# records the observed peak + fallback tier into RepairStep.detail.

_TRACE_HEADER = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\t"
    "duration\trealtime\t%cpu\tpeak_rss\n"
)


def _peak_trace(status, exit_code, peak_rss, name="NFCORE_RNASEQ:STAR_ALIGN (S1)"):
    # A trace row carrying the resource columns (incl. peak_rss) the sizer reads.
    return _TRACE_HEADER + (
        f"1\tab/cd\t1\t{name}\t{status}\t{exit_code}\t2026-01-01\t"
        f"10m\t9m\t180.0%\t{peak_rss}\n"
    )


def test_self_heal_sizes_oom_retry_from_observed_peak(tmp_path):
    # The killed STAR_ALIGN row carries a real 60 GB peak. The retry must be
    # sized to ceil(60 GB * 1.5) = 90 GB (clamped to the 128 GB ceiling, never
    # below the 8 GB current) -- NOT the blind x2 (16 GB) -- and the retained
    # RepairStep.detail must name the observed peak and the "oom_task" tier.
    oom_trace = _peak_trace("FAILED", 137, "60 GB")
    ok_trace = _peak_trace("COMPLETED", 0, "20 GB")
    state = {"n": 0, "retry_cfg": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, oom_trace, "out of memory exit 137")
            return 1
        state["retry_cfg"] = (Path(trace_path).parent / "nextflow.config").read_text()
        _write(trace_path, ok_trace, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is True
    assert "process.resourceLimits = [ memory: 90.GB ]" in state["retry_cfg"]
    assert record.target.resource_limits["memory"] == "90.GB"
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "oom"
    assert step.outcome == "patched_and_retried"
    assert "observed peak" in step.detail
    assert "oom_task" in step.detail


def test_self_heal_oom_falls_back_to_blind_bump_without_usable_peak(tmp_path):
    # No usable observed peak in the trace (the killed row has no peak_rss) ->
    # the retry must scale the OLD blind x2 way (8 GB -> 16 GB) and the detail
    # must say the observed peak was unavailable. This is the regression guard:
    # a peakless OOM heal must behave exactly as it did before sizing existed.
    state = {"n": 0, "retry_cfg": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_OOM, "out of memory exit 137")
            return 1
        state["retry_cfg"] = (Path(trace_path).parent / "nextflow.config").read_text()
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is True
    assert "process.resourceLimits = [ memory: 16.GB ]" in state["retry_cfg"]
    assert record.target.resource_limits["memory"] == "16.GB"
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "oom"
    assert step.outcome == "patched_and_retried"
    assert "unavailable" in step.detail


# --- Phase 3: realtime-informed time_limit retry sizing ---------------------
#
# Supersedes the old "time_limit is untouched by sizing" test: a time_limit heal
# now sizes the walltime retry from the run's observed realtime (helper:
# realtime_informed_time_h), floored at the blind x2 bump (a walltime kill's
# realtime is a censored lower bound), and records the observed realtime + tier
# into RepairStep.detail.


def _realtime_trace(status, exit_code, realtime, name="NFCORE_RNASEQ:STAR_ALIGN (S1)"):
    # A trace row whose realtime column drives the walltime sizer.
    return _TRACE_HEADER + (
        f"1\tab/cd\t1\t{name}\t{status}\t{exit_code}\t2026-01-01\t"
        f"{realtime}\t{realtime}\t180.0%\t-\n"
    )


def test_self_heal_sizes_time_limit_retry_from_observed_realtime(tmp_path):
    # attempt-1's trace shows a max realtime of ~10h. A walltime kill must size the
    # retry to ceil(10h * 1.5) = 15h, which BEATS the blind x2 (8h) off the 4h
    # default -- and the retained detail must name the observed realtime seconds,
    # the applied 15h, and that it beat blind.
    time_trace = _realtime_trace("FAILED", 140, "10h")
    state = {"n": 0, "retry_cfg": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, time_trace, "Terminated due to time limit")
            return 1
        state["retry_cfg"] = (Path(trace_path).parent / "nextflow.config").read_text()
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.target.resource_limits["time"] == "15.h"
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "time_limit"
    assert step.outcome == "patched_and_retried"
    assert "36000" in step.detail  # observed realtime seconds
    assert "15h" in step.detail  # the APPLIED (post-floor/clamp) walltime
    assert "beat" in step.detail  # beat the blind x2


def test_self_heal_time_limit_sizing_floors_at_blind_bump(tmp_path):
    # A censored realtime of ~4h scales to ceil(4h * 1.5) = 6h, which is BELOW the
    # blind x2 (8h). apply_patch floors the observed override at blind, so the
    # applied time is 8h (ties blind) and the detail records the observed realtime
    # and that it tied/floored blind rather than beating it.
    time_trace = _realtime_trace("FAILED", 140, "4h")
    state = {"n": 0, "retry_cfg": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, time_trace, "Terminated due to time limit")
            return 1
        state["retry_cfg"] = (Path(trace_path).parent / "nextflow.config").read_text()
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.target.resource_limits["time"] == "8.h"
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "time_limit"
    assert step.outcome == "patched_and_retried"
    assert "14400" in step.detail  # observed realtime seconds
    assert "8h" in step.detail  # applied walltime (floored at blind)
    assert "tied" in step.detail  # tied/floored the blind x2


def test_self_heal_time_limit_falls_back_to_blind_bump_without_realtime(tmp_path):
    # No usable observed realtime in the trace (the killed row's realtime is a
    # dash) -> the retry must scale the OLD blind x2 way (4h -> 8h) and the detail
    # must say the observed realtime was unavailable. Regression guard: a
    # realtime-less time_limit heal must behave exactly as it did before sizing.
    time_trace = _realtime_trace("FAILED", 140, "-")
    state = {"n": 0, "retry_cfg": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, time_trace, "Terminated due to time limit")
            return 1
        state["retry_cfg"] = (Path(trace_path).parent / "nextflow.config").read_text()
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(tmp_path, executor)
    assert RunSummary.from_events(record.events).succeeded is True
    assert record.target.resource_limits["time"] == "8.h"
    step = record.repair_history[0]
    assert step.diagnosis.failure_class == "time_limit"
    assert step.outcome == "patched_and_retried"
    assert step.detail == "no usable observed realtime; blind x2 fallback (unavailable)"


# ---------------------------------------------------------------------------
# _gzip_kind / _recompress_reference (recompress-reference, Phase 3)
# ---------------------------------------------------------------------------

# The canonical 28-byte BGZF EOF block: magic 1f8b, FEXTRA set, "BC" subfield.
_BGZF_EOF_BLOCK = bytes.fromhex(
    "1f8b08040000000000ff0600424302001b0003000000000000000000"
)

_PLAIN_FASTA = b">chr1\nACGT\n"


def test_gzip_kind_plain_gzip(tmp_path):
    import gzip

    from contig.self_heal import _gzip_kind

    path = tmp_path / "ref.fa.gz"
    path.write_bytes(gzip.compress(_PLAIN_FASTA))
    assert _gzip_kind(path) == "plain_gzip"


def test_gzip_kind_not_gzip(tmp_path):
    from contig.self_heal import _gzip_kind

    path = tmp_path / "ref.fa"
    path.write_bytes(_PLAIN_FASTA)
    assert _gzip_kind(path) == "not_gzip"


def test_gzip_kind_bgzf(tmp_path):
    from contig.self_heal import _gzip_kind

    path = tmp_path / "ref.fa.gz"
    path.write_bytes(_BGZF_EOF_BLOCK)
    assert _gzip_kind(path) == "bgzf"


def test_recompress_reference_success(tmp_path):
    import gzip

    from contig.models import ExecutionTarget
    from contig.self_heal import _recompress_reference

    fasta = tmp_path / "ref.fa.gz"
    fasta.write_bytes(gzip.compress(_PLAIN_FASTA))
    target = ExecutionTarget(backend="local", container_runtime="docker", work_dir="w")
    params = {"fasta": str(fasta)}
    built_paths = set()

    result_target, result_params, outcome, detail, continue_ = _recompress_reference(
        target, params, run_dir=tmp_path, built_paths=built_paths
    )

    assert outcome == "recompressed_reference_and_retried"
    assert continue_ is True
    scratch = tmp_path / "healed_reference" / "ref.fa"
    assert scratch.is_file()
    assert scratch.read_bytes() == _PLAIN_FASTA
    assert result_params["fasta"] == str(scratch)
    assert str(fasta) in built_paths
    assert str(scratch) in built_paths
    assert detail is not None and str(fasta) in detail


def test_recompress_reference_no_fasta_gives_up(tmp_path):
    from contig.models import ExecutionTarget
    from contig.self_heal import _recompress_reference

    target = ExecutionTarget(backend="local", container_runtime="docker", work_dir="w")
    params: dict[str, object] = {}
    built_paths: set[str] = set()

    result_target, result_params, outcome, detail, continue_ = _recompress_reference(
        target, params, run_dir=tmp_path, built_paths=built_paths
    )

    assert outcome == "reference_recompress_unresolvable"
    assert continue_ is False
    assert "fasta" not in result_params
    assert not (tmp_path / "healed_reference").exists()


def test_recompress_reference_bgzf_input_left_untouched(tmp_path):
    from contig.models import ExecutionTarget
    from contig.self_heal import _recompress_reference

    fasta = tmp_path / "ref.fa.gz"
    fasta.write_bytes(_BGZF_EOF_BLOCK)
    target = ExecutionTarget(backend="local", container_runtime="docker", work_dir="w")
    params = {"fasta": str(fasta)}
    built_paths: set[str] = set()

    result_target, result_params, outcome, detail, continue_ = _recompress_reference(
        target, params, run_dir=tmp_path, built_paths=built_paths
    )

    assert outcome == "reference_recompress_unresolvable"
    assert continue_ is False
    assert result_params["fasta"] == str(fasta)
    assert not (tmp_path / "healed_reference").exists()


def test_recompress_reference_already_built_gives_up(tmp_path):
    from contig.models import ExecutionTarget
    from contig.self_heal import _recompress_reference

    fasta = tmp_path / "ref.fa.gz"
    fasta.write_bytes(b"not gzip at all")
    target = ExecutionTarget(backend="local", container_runtime="docker", work_dir="w")
    params = {"fasta": str(fasta)}
    built_paths = {str(fasta)}

    result_target, result_params, outcome, detail, continue_ = _recompress_reference(
        target, params, run_dir=tmp_path, built_paths=built_paths
    )

    assert outcome == "reference_recompress_unresolvable"
    assert continue_ is False
    assert result_params["fasta"] == str(fasta)
    assert not (tmp_path / "healed_reference").exists()


def test_recompress_reference_decompress_failure(tmp_path):
    from contig.models import ExecutionTarget
    from contig.self_heal import _recompress_reference

    # Gzip magic present (so _gzip_kind sees "plain_gzip") but truncated body
    # that fails to decompress.
    fasta = tmp_path / "ref.fa.gz"
    fasta.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff" + b"\x00" * 4)
    target = ExecutionTarget(backend="local", container_runtime="docker", work_dir="w")
    params = {"fasta": str(fasta)}
    built_paths: set[str] = set()

    result_target, result_params, outcome, detail, continue_ = _recompress_reference(
        target, params, run_dir=tmp_path, built_paths=built_paths
    )

    assert outcome == "reference_recompress_failed"
    assert continue_ is False
    assert result_params["fasta"] == str(fasta)
