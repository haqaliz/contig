"""Tests for the pre-band verification-inputs capture (C6 fold-in, aspect 3).

PRD R4/R4a: a real run's verification case must be built from PRE-BAND metric
inputs, never from stored QC statuses -- so `RunRecord.verification_inputs`
captures the same metric dicts `_discover_qc` already computes, keyed by the
aspect-1 scorer's family names. Phase 1 pins the capture seam; Phase 2 pins
the pending-case capture at finalize.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from contig.models import ExecutionTarget, RunRecord, TaskEvent, QCResult
from contig.runner import _discover_qc

GOOD_MQC_JSON = (
    '{"report_general_stats_data":[{'
    '"S1":{"uniquely_mapped_percent":92.0,"percent_assigned":85.0,"total_reads":1000000.0},'
    '"S2":{"uniquely_mapped_percent":90.0,"percent_assigned":84.0,"total_reads":1100000.0}}]}'
)


def _write_multiqc(run_dir: Path, body: str = GOOD_MQC_JSON) -> None:
    mqc_dir = run_dir / "results" / "multiqc"
    mqc_dir.mkdir(parents=True, exist_ok=True)
    (mqc_dir / "multiqc_data.json").write_text(body)


def _write_gz(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(body)


# --- Phase 1: verification_inputs capture inside _discover_qc -----------------


def test_discover_qc_captures_multiqc_and_rnaseq_plausibility_families(tmp_path):
    _write_multiqc(tmp_path)

    capture_inputs: dict[str, dict[str, dict[str, float]]] = {}
    _discover_qc(tmp_path, assay="rnaseq", capture_inputs=capture_inputs)

    # Family names must match the aspect-1 scorer table exactly.
    multiqc = capture_inputs["multiqc"]
    assert multiqc["S1"]["uniquely_mapped_percent"] == 92.0
    assert multiqc["S1"]["percent_assigned"] == 85.0
    assert multiqc["S2"]["uniquely_mapped_percent"] == 90.0
    # The rnaseq plausibility gate sees the same MultiQC metrics dict.
    assert capture_inputs["rnaseq_plausibility"] == multiqc
    # No composition artifact in this run: the family is absent, never empty.
    assert "rnaseq_composition" not in capture_inputs


def test_discover_qc_captures_rnaseq_composition_family(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "rnaseq" / "WT_REP1.read_distribution.txt"
    (tmp_path / "results" / "rnaseq_qc").mkdir(parents=True, exist_ok=True)
    (tmp_path / "results" / "rnaseq_qc" / "WT_REP1.read_distribution.txt").write_text(
        fixture.read_text()
    )

    capture_inputs: dict[str, dict[str, dict[str, float]]] = {}
    _discover_qc(tmp_path, assay="rnaseq", capture_inputs=capture_inputs)

    composition = capture_inputs["rnaseq_composition"]
    assert "WT_REP1" in composition
    assert "exonic_fraction" in composition["WT_REP1"]
    assert "intronic_fraction" in composition["WT_REP1"]
    assert "unassigned_fraction" in composition["WT_REP1"]


def test_discover_qc_captures_germline_family(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\t.\tGT\t0/1\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\t.\tGT\t1/1\n"
        "chr1\t300\t.\tA\tC\t50\tPASS\t.\tGT\t0/1\n"
    )
    _write_gz(tmp_path / "calls.vcf.gz", body)

    capture_inputs: dict[str, dict[str, dict[str, float]]] = {}
    _discover_qc(tmp_path, assay="variant_calling", capture_inputs=capture_inputs)

    # 2 transitions (A>G, C>T) / 1 transversion (A>C) -> ts_tv 2.0;
    # 2 het / 1 hom-alt -> het_hom 2.0; 3 distinct sites.
    germline = capture_inputs["germline"]
    assert germline == {
        "sample": {"ts_tv": 2.0, "het_hom": 2.0, "variant_count": 3.0}
    }


def test_discover_qc_leaves_capture_untouched_when_nothing_parseable(tmp_path):
    # A run dir with no QC artifacts at all: the out-param stays empty.
    capture_inputs: dict[str, dict[str, dict[str, float]]] = {}
    _discover_qc(tmp_path, assay="rnaseq", capture_inputs=capture_inputs)
    assert capture_inputs == {}


def test_run_record_without_verification_inputs_loads_unchanged():
    # Back-compat: bundles written before the field deserialize with None.
    old = (
        '{"run_id": "r1", "pipeline": "nf-core/rnaseq", "pipeline_revision": "3.14.0", '
        '"target": {"backend": "local", "container_runtime": "docker", "work_dir": "w"}, '
        '"input_checksums": {}}'
    )
    record = RunRecord.model_validate_json(old)
    assert record.verification_inputs is None


def test_run_record_verification_inputs_round_trips():
    record = RunRecord(
        run_id="r1",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.14.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        verification_inputs={"multiqc": {"S1": {"percent_assigned": 85.0}}},
    )
    loaded = RunRecord.model_validate_json(record.model_dump_json())
    assert loaded.verification_inputs == {"multiqc": {"S1": {"percent_assigned": 85.0}}}


# --- Phase 2: pending capture at finalize --------------------------------------


def _record(
    *,
    events: list[TaskEvent],
    qc_results: list[QCResult],
    verification_inputs: dict[str, dict[str, dict[str, float]]] | None,
) -> RunRecord:
    return RunRecord(
        run_id="r",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.14.0",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        parameters={},
        events=events,
        qc_results=qc_results,
        assay="rnaseq",
        verification_inputs=verification_inputs,
    )


def _green(verdict: str) -> list[QCResult]:
    return [QCResult(check=f"x:{verdict}", status=verdict, message=verdict, kind="metric")]  # type: ignore[arg-type]


def _finalize(tmp_path, record: RunRecord) -> Path:
    from contig.self_heal import _finalize

    run_dir = tmp_path / "runs" / "r"
    run_dir.mkdir(parents=True, exist_ok=True)
    pending_path = tmp_path / "pending_verify_corpus.jsonl"
    _finalize(
        record, [], run_dir,
        runs_dir=tmp_path / "runs", run_id="r",
        pending_verify_corpus=pending_path,
    )
    return pending_path


def test_should_capture_verification_predicate():
    from contig.verify_corpus import should_capture_verification

    inputs = {"multiqc": {"S1": {"percent_assigned": 50.0}}}
    fail = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                   qc_results=_green("fail"), verification_inputs=inputs)
    warn = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                   qc_results=_green("warn"), verification_inputs=inputs)
    assert should_capture_verification(fail) is True
    assert should_capture_verification(warn) is True

    passed = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                     qc_results=_green("pass"), verification_inputs=inputs)
    assert should_capture_verification(passed) is False

    crashed = _record(events=[TaskEvent(process="P", status="FAILED", exit=1)],
                      qc_results=_green("fail"), verification_inputs=inputs)
    assert should_capture_verification(crashed) is False

    no_inputs = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                        qc_results=_green("fail"), verification_inputs=None)
    assert should_capture_verification(no_inputs) is False

    empty_inputs = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                           qc_results=_green("fail"), verification_inputs={})
    assert should_capture_verification(empty_inputs) is False


def test_verification_case_from_run_builder_shape():
    from contig.verify_corpus import verification_case_from_run

    inputs = {"multiqc": {"S1": {"percent_assigned": 50.0}}}
    record = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                     qc_results=_green("fail"), verification_inputs=inputs)
    case = verification_case_from_run(record)

    assert case.case_id == "r-verify"
    assert case.source == "pending:r"
    assert case.expected_verdict is None  # unlabeled until promoted
    assert case.known_miss is False
    assert case.inputs == inputs  # pre-band inputs copied verbatim
    assert "rnaseq" in case.description  # assay stated
    assert "fail" in case.description  # driving verdict stated
    assert "multiqc" in case.description  # captured families stated


def test_finalize_appends_one_pending_case_for_fail(tmp_path):
    from contig.verify_corpus import load_verify_cases

    record = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                     qc_results=_green("fail"),
                     verification_inputs={"multiqc": {"S1": {"percent_assigned": 50.0}}})
    pending_path = _finalize(tmp_path, record)

    cases = load_verify_cases(pending_path)
    assert len(cases) == 1
    assert cases[0].case_id == "r-verify"
    assert cases[0].source == "pending:r"
    assert cases[0].expected_verdict is None
    assert cases[0].inputs["multiqc"]["S1"]["percent_assigned"] == 50.0


def test_finalize_appends_one_pending_case_for_warn(tmp_path):
    from contig.verify_corpus import load_verify_cases

    record = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                     qc_results=_green("warn"),
                     verification_inputs={"multiqc": {"S1": {"percent_assigned": 50.0}}})
    pending_path = _finalize(tmp_path, record)

    assert len(load_verify_cases(pending_path)) == 1


def test_finalize_appends_nothing_for_pass(tmp_path):
    record = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                     qc_results=_green("pass"),
                     verification_inputs={"multiqc": {"S1": {"percent_assigned": 90.0}}})
    pending_path = _finalize(tmp_path, record)

    assert not pending_path.exists()


def test_finalize_appends_nothing_for_a_crashed_run(tmp_path):
    record = _record(events=[TaskEvent(process="P", status="FAILED", exit=137)],
                     qc_results=_green("fail"),
                     verification_inputs={"multiqc": {"S1": {"percent_assigned": 50.0}}})
    pending_path = _finalize(tmp_path, record)

    assert not pending_path.exists()


def test_finalize_appends_nothing_without_verification_inputs(tmp_path):
    record = _record(events=[TaskEvent(process="P", status="COMPLETED", exit=0)],
                     qc_results=_green("fail"), verification_inputs=None)
    pending_path = _finalize(tmp_path, record)

    assert not pending_path.exists()
