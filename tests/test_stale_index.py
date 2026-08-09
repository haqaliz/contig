"""Stale single-file index self-heal: scratch build + atomic replace.

A stale index (an index OLDER than the data it indexes, htslib hts_idx_load3
family) is detected as `missing_index` with staleness evidence; the repair
rebuilds the sidecar into run-scoped scratch (symlinking the resolved source)
and, on a successful build, atomically replaces the user's stale file, then
retries. Failed builds leave the user's file byte-identical; build-once bounds
the loop; cross-device replaces fall back to a same-dir dot-temp copy.
"""

import errno
import os
from pathlib import Path

from contig.models import Diagnosis, ExecutionTarget, RunSummary
from contig.self_heal import self_heal_run, _is_stale_evidence


def _trace(status, exit_code):
    return (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        f"1\tab/cd\t1\tNFCORE_RNASEQ:STAR_ALIGN (S1)\t{status}\t{exit_code}\t-\t-\t-\n"
    )


TRACE_OK = _trace("COMPLETED", 0)
TRACE_INDEX = _trace("FAILED", 1)


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


# The htslib freshness line naming a RELATIVE index path (resolves against
# run_dir, mirroring the heal-scenario fixture shape).
_STALE_BAI_LOG = (
    "[E::hts_idx_load3] The index file is older than the data file: "
    "fixtures/aln.bam.bai"
)

_STALE_ARTIFACT = b"stale-index-artifact"
_FRESH_ARTIFACT = b"fresh-index"


def _seed_stale_bai(tmp_path):
    """Seed a stale .bai sidecar and its data file under run_dir/fixtures."""
    run_dir = tmp_path / "runs" / "r"
    fixtures = run_dir / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "aln.bam.bai").write_bytes(_STALE_ARTIFACT)
    (fixtures / "aln.bam").write_text("bam-data")
    return run_dir


def _stale_executor(state, *, succeed_on_retry=True):
    """Fail attempt 1 with the stale-.bai log; (optionally) succeed on retry."""

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(trace_path, TRACE_INDEX, _STALE_BAI_LOG)
            return 1
        if not succeed_on_retry:
            _write(trace_path, TRACE_INDEX, _STALE_BAI_LOG)
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    return executor


def _stale_builder(calls, *, rc=0, artifact=True):
    """Fake IndexBuilder: records argv; on success creates argv[-1] + ".bai"
    under cwd (what samtools index actually writes next to its input)."""

    def index_builder(cmd, cwd):
        calls["n"] += 1
        calls["cmd"] = cmd
        if rc == 0 and artifact:
            (Path(cwd) / (cmd[-1] + ".bai")).write_bytes(_FRESH_ARTIFACT)
        return rc

    return index_builder


def _sidecar(tmp_path):
    return tmp_path / "runs" / "r" / "fixtures" / "aln.bam.bai"


def test_self_heal_rebuilds_stale_bai_and_retries(tmp_path):
    # AC1: a stale .bai is rebuilt into scratch (symlinked source) and the
    # user's sidecar is atomically replaced; the run retries to success.
    _seed_stale_bai(tmp_path)
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}
    record = _heal(
        tmp_path,
        _stale_executor(state),
        auto_approve=True,
        index_builder=_stale_builder(calls),
    )
    assert RunSummary.from_events(record.events).succeeded is True
    last = record.repair_history[-1]
    assert last.outcome == "built_index_and_retried"
    assert last.patch_applied is True
    assert state["n"] == 2  # the re-run actually happened
    sidecar = _sidecar(tmp_path)
    assert sidecar.exists()
    assert sidecar.read_bytes() == _FRESH_ARTIFACT  # replaced, not left stale
    assert "older than" in last.detail
    assert " ".join(calls["cmd"]) in last.detail  # the applied build argv
    assert "healed_index" in str(calls["cmd"])  # the symlink was used
    assert calls["n"] == 1  # exactly one build


def test_stale_build_failure_leaves_user_file_byte_identical(tmp_path):
    # AC3: a non-zero build ends in an honest FAIL; the user's sidecar is
    # byte-identical and the executor is NOT re-run.
    _seed_stale_bai(tmp_path)
    state = {"n": 0}
    calls = {"n": 0}
    record = _heal(
        tmp_path,
        _stale_executor(state),
        auto_approve=True,
        index_builder=_stale_builder(calls, rc=1),
    )
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert last.patch_applied is False
    assert "fixtures/aln.bam.bai" in last.detail
    assert _sidecar(tmp_path).read_bytes() == _STALE_ARTIFACT  # untouched
    assert record.verdict == "fail"
    assert calls["n"] == 1  # builder ran once
    assert state["n"] == 1  # no re-run after the failed build


def test_stale_build_success_without_artifact_gives_up(tmp_path):
    # The build exits 0 but produces nothing: honest give-up, never a false
    # pass -- the user's stale sidecar stays byte-identical.
    _seed_stale_bai(tmp_path)
    state = {"n": 0}
    calls = {"n": 0}
    record = _heal(
        tmp_path,
        _stale_executor(state),
        auto_approve=True,
        index_builder=_stale_builder(calls, artifact=False),
    )
    last = record.repair_history[-1]
    assert last.outcome == "index_build_failed"
    assert "produced no index" in last.detail
    assert _sidecar(tmp_path).read_bytes() == _STALE_ARTIFACT
    assert record.verdict == "fail"
    assert state["n"] == 1  # no re-run


def test_stale_rebuild_once_only(tmp_path):
    # Build-once: the second stale failure on the same path gives up honestly
    # ("Already rebuilt") instead of rebuilding again -- bounded loop.
    _seed_stale_bai(tmp_path)
    state = {"n": 0}
    calls = {"n": 0}
    record = _heal(
        tmp_path,
        _stale_executor(state, succeed_on_retry=False),
        auto_approve=True,
        index_builder=_stale_builder(calls),
    )
    outcomes = [step.outcome for step in record.repair_history]
    assert outcomes.count("built_index_and_retried") == 1
    assert outcomes[-1] == "index_build_failed"
    assert "Already rebuilt" in record.repair_history[-1].detail
    assert record.verdict == "fail"
    assert calls["n"] == 1  # exactly one build across both attempts
    assert state["n"] == 2  # one retry, then the honest give-up


def test_stale_unparseable_path_gives_up(tmp_path):
    # Stale evidence carrying no index path token: _parse_missing_index returns
    # None first, so the existing index_unresolvable branch handles it.
    _seed_stale_bai(tmp_path)
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        _write(
            trace_path,
            TRACE_INDEX,
            "[E::hts_idx_load3] The index file is older than the data file",
        )
        return 1

    record = _heal(
        tmp_path,
        executor,
        auto_approve=True,
        index_builder=_stale_builder(calls),
    )
    last = record.repair_history[-1]
    assert last.diagnosis.failure_class == "missing_index"
    assert last.outcome == "index_unresolvable"
    assert record.verdict == "fail"
    assert calls["n"] == 0  # builder never called
    assert state["n"] == 1  # no re-run


def test_stale_missing_flavor_still_builds_in_place(tmp_path):
    # A MISSING (absence-phrased) diagnosis keeps the existing in-place path:
    # argv targets the source next to the user's data, no healed_index scratch.
    _seed_stale_bai(tmp_path)
    state = {"n": 0}
    calls = {"n": 0, "cmd": None}

    def executor(cmd, trace_path):
        state["n"] += 1
        if state["n"] == 1:
            _write(
                trace_path,
                TRACE_INDEX,
                "[E::fai_load] Failed to open the index reference.fasta.fai: "
                "No such file or directory",
            )
            return 1
        _write(trace_path, TRACE_OK, "done")
        return 0

    record = _heal(
        tmp_path,
        executor,
        auto_approve=True,
        index_builder=_stale_builder(calls),
    )
    assert RunSummary.from_events(record.events).succeeded is True
    last = record.repair_history[-1]
    assert last.outcome == "built_index_and_retried"
    assert calls["cmd"] == ["samtools", "faidx", "reference.fasta"]
    assert "healed_index" not in str(calls["cmd"])
    assert not (tmp_path / "runs" / "r" / "healed_index").exists()


def test_stale_replace_exdev_fallback(tmp_path, monkeypatch):
    # Cross-device os.replace (EXDEV): fall back to a same-dir dot-temp copy +
    # rename; the repair still succeeds and the dot-temp is gone afterwards.
    _seed_stale_bai(tmp_path)
    state = {"n": 0}
    calls = {"n": 0}
    real_replace = os.replace
    calls_seen = {"n": 0}

    def flaky_replace(src, dst):
        calls_seen["n"] += 1
        if calls_seen["n"] == 1:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real_replace(src, dst)

    monkeypatch.setattr("contig.self_heal.os.replace", flaky_replace)

    record = _heal(
        tmp_path,
        _stale_executor(state),
        auto_approve=True,
        index_builder=_stale_builder(calls),
    )
    assert RunSummary.from_events(record.events).succeeded is True
    last = record.repair_history[-1]
    assert last.outcome == "built_index_and_retried"
    sidecar = _sidecar(tmp_path)
    assert sidecar.read_bytes() == _FRESH_ARTIFACT
    dot_temp = sidecar.parent / f".{sidecar.name}.contig-heal-{os.getpid()}"
    assert not dot_temp.exists()  # cleaned up
    assert calls_seen["n"] == 2  # the fallback rename really ran


def test_stale_evidence_pure():
    # _is_stale_evidence scans the evidence lines only: the freshness phrase
    # marks a stale diagnosis; absence phrasing does not.
    stale = Diagnosis(
        failure_class="missing_index",
        root_cause="An index file is older than the data it indexes.",
        evidence=["[E::hts_idx_load3] The index file is older than the data file: /ref/aln.bam.bai"],
        confidence=0.85,
    )
    missing = Diagnosis(
        failure_class="missing_index",
        root_cause="A required index file is missing.",
        evidence=['samtools index: failed to open "aln.bam.bai": No such file or directory'],
        confidence=0.85,
    )
    assert _is_stale_evidence(stale) is True
    assert _is_stale_evidence(missing) is False
    assert _is_stale_evidence(Diagnosis(failure_class="oom", root_cause="x", evidence=[], confidence=0.9)) is False
    upper = Diagnosis(failure_class="missing_index", root_cause="x", evidence=["INDEX FILE IS OLDER THAN THE DATA"], confidence=0.8)
    assert _is_stale_evidence(upper) is True


def test_stale_relative_index_resolves_against_run_dir(tmp_path):
    # A relative index path resolves against run_dir: the build argv points at
    # run_dir/healed_index/bai/<data-name> and the replaced sidecar is the
    # run_dir-relative fixtures file.
    from contig.self_heal import _rebuild_stale_index

    run_dir = tmp_path / "runs" / "r"
    fixtures = run_dir / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "aln.bam.bai").write_bytes(_STALE_ARTIFACT)
    (fixtures / "aln.bam").write_text("bam-data")
    calls = {"n": 0, "cmd": None}
    built = set()

    target, _params, outcome, detail, cont = _rebuild_stale_index(
        _target(tmp_path / "w"),
        {},
        index_path="fixtures/aln.bam.bai",
        ext=".bai",
        run_dir=run_dir,
        index_builder=_stale_builder(calls),
        built_paths=built,
    )
    assert outcome == "built_index_and_retried"
    assert cont is True
    assert calls["cmd"][-1] == str(run_dir / "healed_index" / "bai" / "aln.bam")
    assert "healed_index" in str(calls["cmd"])
    assert "fixtures" not in str(calls["cmd"][-1])  # built against scratch, not the user's dir
    assert (fixtures / "aln.bam.bai").read_bytes() == _FRESH_ARTIFACT
