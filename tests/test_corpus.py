"""Tests for the failure-corpus + detector eval harness (moat #2).

The corpus is accumulated, labeled failure data: each case carries exactly what
the detector consumes (events + log text) plus the ground-truth class. The eval
replays `diagnose_failure` over the corpus and scores it, turning "the detector
seems good" into a number that improves as real runs accrue.
"""

from contig.corpus import (
    default_corpus_path,
    evaluate_detector,
    load_corpus,
    save_corpus,
)
from contig.models import FailureCase, TaskEvent


def _oom_case():
    return FailureCase(
        case_id="oom-1",
        description="STAR killed with exit 137",
        source="synthetic",
        events=[TaskEvent(process="STAR_ALIGN", status="FAILED", exit=137)],
        log_text="Process killed: out of memory (exit 137)",
        expected_class="oom",
    )


def test_corpus_round_trips_through_jsonl(tmp_path):
    cases = [
        _oom_case(),
        FailureCase(
            case_id="plat-1",
            description="arm64 emulation kill",
            source="live:livetest",
            events=[TaskEvent(process="MAKE_TRANSCRIPTS_FASTA", status="FAILED", exit=None)],
            log_text="WARNING: The requested image's platform (linux/amd64) does not match the detected host platform",
            expected_class="platform_unsupported",
        ),
    ]
    path = tmp_path / "corpus.jsonl"
    save_corpus(cases, path)
    loaded = load_corpus(path)
    assert loaded == cases


def test_corpus_is_one_json_object_per_line(tmp_path):
    path = tmp_path / "corpus.jsonl"
    save_corpus([_oom_case(), _oom_case()], path)
    lines = path.read_text().splitlines()
    assert len(lines) == 2


def _mislabeled_case():
    # A failed task with no diagnostic signal: the detector can only say
    # "tool_crash", so labeling it "oom" makes it a deliberate miss.
    return FailureCase(
        case_id="miss-1",
        description="failed task, no OOM signal in the log",
        source="synthetic",
        events=[TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)],
        log_text="Segmentation fault",
        expected_class="oom",
    )


def test_evaluate_detector_scores_accuracy():
    report = evaluate_detector([_oom_case(), _mislabeled_case()])
    assert report.total == 2
    assert report.correct == 1
    assert report.accuracy == 0.5


def test_evaluate_detector_lists_mismatches_with_predicted_class():
    report = evaluate_detector([_oom_case(), _mislabeled_case()])
    assert len(report.mismatches) == 1
    miss = report.mismatches[0]
    assert miss.case_id == "miss-1"
    assert miss.expected == "oom"
    assert miss.predicted == "tool_crash"


def test_evaluate_detector_empty_corpus_is_zero_not_a_crash():
    report = evaluate_detector([])
    assert report.total == 0
    assert report.accuracy == 0.0


def test_shipped_seed_corpus_loads_and_detector_scores_it():
    # Regression guard: the detector must classify every case in the shipped
    # corpus. A drop here means either the detector regressed or a newly added
    # real case exposed a gap (the signal this harness exists to give).
    cases = load_corpus(default_corpus_path())
    assert len(cases) >= 10
    report = evaluate_detector(cases)
    assert report.accuracy == 1.0


def test_evaluate_detector_reports_per_class_precision_and_recall():
    # Two cases truly "oom"; detector gets one right (the real OOM) and labels the
    # signal-less one "tool_crash". So for oom: support 2, predicted 1, hit 1.
    report = evaluate_detector([_oom_case(), _mislabeled_case()])
    oom = report.per_class["oom"]
    assert oom.support == 2
    assert oom.predicted == 1
    assert oom.correct == 1
    assert oom.precision == 1.0
    assert oom.recall == 0.5
    # the wrong prediction shows up as a low-precision tool_crash row
    assert report.per_class["tool_crash"].precision == 0.0


def test_failure_case_from_run_keeps_only_failing_events_and_labels_it():
    from contig.corpus import failure_case_from_run, evaluate_detector
    from contig.models import RunRecord, ExecutionTarget, TaskEvent
    record = RunRecord(
        run_id="r1", pipeline="nf-core/rnaseq", pipeline_revision="3.26.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        events=[
            TaskEvent(process="FASTQC", status="COMPLETED", exit=0),
            TaskEvent(process="STAR_ALIGN", status="FAILED", exit=137),
        ],
    )
    case = failure_case_from_run(record, log_text="out of memory exit 137", expected_class="oom")
    # only the failing event is retained
    assert len(case.events) == 1 and case.events[0].process == "STAR_ALIGN"
    assert case.log_text == "out of memory exit 137"
    assert case.expected_class == "oom"
    assert "r1" in case.source and "r1" in case.case_id
    # the captured case is faithful: the detector reproduces the label
    report = evaluate_detector([case])
    assert report.accuracy == 1.0


def test_failure_case_from_run_allows_overriding_id_and_source():
    from contig.corpus import failure_case_from_run
    from contig.models import RunRecord, ExecutionTarget, TaskEvent
    record = RunRecord(
        run_id="r2", pipeline="p", pipeline_revision="1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={}, events=[TaskEvent(process="X", status="FAILED", exit=1)],
    )
    case = failure_case_from_run(record, log_text="boom", expected_class="tool_crash",
                                 case_id="custom-1", source="manual")
    assert case.case_id == "custom-1" and case.source == "manual"


def test_append_case_adds_one_line_to_corpus(tmp_path):
    from contig.corpus import append_case, load_corpus
    from contig.models import FailureCase, TaskEvent
    path = tmp_path / "c.jsonl"
    c1 = FailureCase(case_id="a", description="d", source="s",
                     events=[TaskEvent(process="X", status="FAILED", exit=1)],
                     log_text="boom", expected_class="tool_crash")
    append_case(c1, path)
    append_case(c1, path)
    loaded = load_corpus(path)
    assert len(loaded) == 2
