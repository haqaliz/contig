"""Corpus capture for a QC-FAIL run, plus the contract this slice must not move.

Until now the pending-corpus capture in `self_heal_run` sat on the exception
path only, so a run that finished green and failed QC could not enter the
corpus at all -- the one class of failure with no crash to catch. These tests
pin the capture (A11) and then pin, by assertion rather than assumption, the
four things the slice deliberately leaves alone: the lifecycle event (A7), the
verdict (A8), `propose_patches` (A13), and the held-out detector baseline (A16).
"""

import gzip
import json
from pathlib import Path

from contig.corpus import load_corpus
from contig.holdout import default_baseline_path, load_baseline
from contig.models import Diagnosis, ExecutionTarget, RunSummary
from contig.repair import propose_patches
from contig.self_heal import QC_VERDICT_FLAGGED_OUTCOME, self_heal_run

TRACE_OK = (
    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
    "1\tab/cd\t1\tNFCORE_SAREK:HAPLOTYPECALLER (S1)\tCOMPLETED\t0\t-\t-\t-\n"
)


def _green_qc_fail_executor(cmd, trace_path):
    """One green run leaving a call set with zero sites -- a real QC FAIL.

    `parse_vcf` reads a `.gz` name with stdlib gzip, so a header-only file
    yields `variant_count=0`, which VARIANT_RULE_PACK's `fail_below: 1` makes a
    FAIL. Nothing is mocked: the real `_discover_qc` produces the verdict.
    """
    run_dir = Path(trace_path).parent
    Path(trace_path).write_text(TRACE_OK)
    (run_dir / "run.log").write_text("ok")
    with gzip.open(run_dir / "calls.vcf.gz", "wt") as fh:
        fh.write("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
    return 0


def _heal(tmp_path, **over):
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
        executor=_green_qc_fail_executor,
        assay="variant_calling",
        max_attempts=3,
    )
    kwargs.update(over)
    return self_heal_run(**kwargs)


# --- A11: the QC-FAIL run becomes corpus data ---------------------------------


def test_qc_fail_run_writes_one_pending_case_labelled_qc_anomaly(tmp_path):
    # A11: this is the moat-#2 half of the slice. A diagnosed failure that never
    # reaches the pending corpus is a failure the corpus can never learn from,
    # and this class had no path in at all -- capture only ever ran after an
    # exception, and nothing here raises.
    record = _heal(tmp_path)

    assert record.repair_history[0].outcome == QC_VERDICT_FLAGGED_OUTCOME
    cases = load_corpus(tmp_path / "runs" / "pending_corpus.jsonl")
    assert len(cases) == 1
    assert cases[0].expected_class == "qc_anomaly"


def test_pending_case_lands_in_the_path_the_loop_already_uses(tmp_path):
    # The capture must reuse the loop's own pending path -- including an
    # explicitly passed one -- so a QC anomaly is reviewed and promoted through
    # the same `contig corpus promote` flow as every other captured failure,
    # not out of a second file only this branch knows about.
    elsewhere = tmp_path / "review" / "pending.jsonl"
    _heal(tmp_path, pending_corpus=elsewhere)

    assert not (tmp_path / "runs" / "pending_corpus.jsonl").exists()
    assert len(load_corpus(elsewhere)) == 1


def test_pending_case_carries_the_run_and_attempt_identity(tmp_path):
    # Same case_id/source scheme as the exception path: the reviewer sees one
    # namespace of pending cases, and a QC anomaly is addressable by the run and
    # attempt that produced it like any other.
    _heal(tmp_path)

    case = load_corpus(tmp_path / "runs" / "pending_corpus.jsonl")[0]
    assert case.case_id == "r-attempt1"
    assert case.source == "pending:r"


def test_pending_case_carries_the_qc_evidence_and_no_failing_events(tmp_path):
    # The `log_text` slot has no honest natural value here: nothing crashed, so
    # there is no stderr and no task error file. An empty string would file a
    # case with no evidence at all, and log-shaped prose would put words in
    # Nextflow's mouth. The QC summary is the actual evidence, so that is what
    # goes in -- and `events` is legitimately empty, because a green run has no
    # failing event for a detector to key on. That emptiness is the point: it is
    # exactly why R9 keeps this class out of the committed detector corpora.
    _heal(tmp_path)

    case = load_corpus(tmp_path / "runs" / "pending_corpus.jsonl")[0]
    assert case.events == []
    assert "variant_count" in case.log_text
    assert case.log_text.strip() != ""


# --- A7 / A8: the two contract fields this slice must not move ----------------


def test_lifecycle_event_stays_finished_on_a_qc_only_fail(tmp_path):
    # A7: a QC-only FAIL is a finished run with an untrustworthy result, not a
    # failed run. Recording a give-up-shaped step must not flip the terminal
    # notification -- a `failed` event here would page an on-call for a pipeline
    # that did exactly what it was asked to do.
    _heal(tmp_path)

    feed = (tmp_path / "runs" / "notifications.jsonl").read_text().splitlines()
    kinds = [json.loads(line)["kind"] for line in feed]
    assert kinds[-1] == "finished"
    assert "failed" not in kinds


def test_verdict_is_computed_without_reference_to_the_repair_history(tmp_path):
    # A8: the verdict is the product's honesty contract, and this slice adds no
    # check, band, or threshold. Pinned structurally rather than by eyeballing
    # the string: the same record with its history stripped must reduce to the
    # same verdict, so no future revision can quietly let a recorded repair
    # step (ours or anyone's) feed the number a user trusts.
    record = _heal(tmp_path)

    assert record.verdict == "fail"
    assert RunSummary.from_events(record.events).succeeded is True
    without_history = record.model_copy(update={"repair_history": []})
    assert without_history.verdict == record.verdict


# --- A13 / A16: the two deliberate non-moves ----------------------------------


def test_propose_patches_offers_nothing_for_a_qc_anomaly():
    # A13 pins R4. Every task exited 0, so a `-resume` retry is a 100% cache hit
    # that re-derives an identical verdict: there is no patch that can work, and
    # a plausible-looking one would burn a user's compute to reprint the same
    # FAIL. Adding a branch here must mean revisiting that reasoning, not
    # slipping past a silent default.
    diagnosis = Diagnosis(
        failure_class="qc_anomaly",
        root_cause="2 QC check(s) FAILed on a run whose tasks all succeeded.",
        evidence=["variant_count:S1: fail (S1: 0 sites)"],
        confidence=1.0,
    )

    assert propose_patches(diagnosis) == []


def test_committed_holdout_baseline_still_reads_0_923():
    # A16: the non-goal, asserted rather than assumed. Making `qc_anomaly`
    # reachable at runtime deliberately does NOT touch the detector corpora --
    # a zero-exit structural failure cannot be represented as (events, log_text),
    # so a case added while `detect.py` is untouched would misclassify and
    # LOWER this number. Any movement here means someone traded that away
    # without saying so.
    baseline = load_baseline(default_baseline_path())

    assert baseline is not None
    assert round(baseline.accuracy, 3) == 0.923
    assert baseline.detector == "rules"
