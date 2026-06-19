"""Tests for the reproducibility bundle module (ARCHITECTURE §7)."""

from contig.bundle import compute_input_checksums, load_bundle, write_bundle
from contig.models import ExecutionTarget, QCResult, RunRecord, TaskEvent


def _minimal_record() -> RunRecord:
    return RunRecord(
        run_id="r1",
        pipeline="nf-core/rnaseq",
        pipeline_revision="3.14.0",
        target=ExecutionTarget(
            backend="local", container_runtime="docker", work_dir="/work"
        ),
        input_checksums={"reads.fastq.gz": "a" * 64},
    )


def _full_record() -> RunRecord:
    return RunRecord(
        run_id="r2",
        pipeline="nf-core/sarek",
        pipeline_revision="3.4.0",
        target=ExecutionTarget(
            backend="aws_batch",
            container_runtime="singularity",
            work_dir="s3://bkt/work",
            engine="nextflow",
            credentials_ref="aws-default",
        ),
        input_checksums={"sample.bam": "b" * 64},
        parameters={"genome": "GRCh38", "threads": 8},
        container_digests={"sarek": "sha256:deadbeef"},
        nextflow_version="24.04.2",
        contig_version="0.0.1",
        events=[TaskEvent(process="ALIGN", status="COMPLETED", exit=0, task_id="t1", name="ALIGN (1)")],
        qc_results=[QCResult(check="depth", status="pass", message="ok", value=42.0, expected_range="30-50")],
        output_checksums={"variants.vcf.gz": "c" * 64},
    )


def test_write_bundle_creates_non_empty_run_record(tmp_path):
    json_path = write_bundle(_minimal_record(), tmp_path)
    assert json_path == tmp_path / "run_record.json"
    assert json_path.is_file()
    assert json_path.stat().st_size > 0


def test_round_trip_preserves_full_record(tmp_path):
    original = _full_record()
    json_path = write_bundle(original, tmp_path)
    loaded = load_bundle(json_path.parent)
    assert loaded == original
    assert loaded.target == original.target
    assert loaded.events[0] == original.events[0]
    assert loaded.qc_results[0] == original.qc_results[0]


def test_write_bundle_creates_missing_dest_dir(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"
    assert not nested.exists()
    json_path = write_bundle(_minimal_record(), nested)
    assert json_path.is_file()
    assert json_path.parent == nested


def test_compute_input_checksums_maps_basename_to_sha256(tmp_path):
    a = tmp_path / "a.fastq"
    b = tmp_path / "b.fastq"
    a.write_bytes(b"same content")
    b.write_bytes(b"same content")

    sums = compute_input_checksums([a, b])

    assert set(sums) == {"a.fastq", "b.fastq"}
    for digest in sums.values():
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)
    # identical content -> identical digest
    assert sums["a.fastq"] == sums["b.fastq"]


def test_load_preserves_fail_verdict(tmp_path):
    rec = _minimal_record()
    rec.qc_results = [QCResult(check="contamination", status="fail", message="too high")]
    assert rec.verdict == "fail"

    loaded = load_bundle(write_bundle(rec, tmp_path).parent)

    assert loaded.verdict == "fail"
