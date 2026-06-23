"""Structural/integrity QC checks on a run's output files (ARCHITECTURE §6.1).

Real files only, via pytest tmp_path; no mocks.
"""

import gzip

import pytest

from contig.verification.structural import (
    ExpectedOutputs,
    check_bam_ok,
    check_gzip_integrity,
    check_gzip_ok,
    check_index_present,
    check_output,
    check_output_count,
    evaluate_against_manifest,
    evaluate_structural,
    manifest_for,
)

# A BGZF block ends with a fixed 28 byte empty-block EOF marker; samtools writes
# it as the last bytes of a well-formed BAM. We reuse it to forge valid and
# truncated BAMs in tests without shelling out to samtools.
_BGZF_EOF = bytes.fromhex(
    "1f8b08040000000000ff0600424302001b0003000000000000000000"
)


def _write_gzip(path, payload: bytes) -> None:
    with gzip.open(path, "wb") as fh:
        fh.write(payload)


def _write_bam(path, payload: bytes = b"BAM\x01rest") -> None:
    """A minimal BAM-like file: a real gzip stream that ends with the BGZF EOF."""
    with open(path, "wb") as fh:
        fh.write(gzip.compress(payload))
        fh.write(_BGZF_EOF)


def test_check_output_passes_on_nonempty_file(tmp_path):
    f = tmp_path / "aligned.bam"
    f.write_bytes(b"ABCDE")

    result = check_output(f)

    assert result.status == "pass"
    assert result.value == 5
    assert result.check == "output_present:aligned.bam"


def test_check_output_fails_on_missing_path(tmp_path):
    missing = tmp_path / "nope.bam"

    result = check_output(missing)

    assert result.status == "fail"
    assert result.check == "output_present:nope.bam"


def test_check_output_fails_on_empty_file(tmp_path):
    f = tmp_path / "empty.bam"
    f.write_bytes(b"")

    result = check_output(f)

    assert result.status == "fail"
    assert result.value == 0


def test_check_index_present_passes_with_sibling_bai(tmp_path):
    bam = tmp_path / "aligned.bam"
    bam.write_bytes(b"data")
    (tmp_path / "aligned.bam.bai").write_bytes(b"idx")

    result = check_index_present(bam)

    assert result.status == "pass"
    assert result.check == "index_present:aligned.bam"


def test_check_index_present_fails_without_index(tmp_path):
    bam = tmp_path / "aligned.bam"
    bam.write_bytes(b"data")

    result = check_index_present(bam)

    assert result.status == "fail"


def test_check_gzip_ok_passes_on_gzip_magic(tmp_path):
    f = tmp_path / "reads.fastq.gz"
    f.write_bytes(b"\x1f\x8b\x08\x00rest of stream")

    result = check_gzip_ok(f)

    assert result.status == "pass"
    assert result.check == "gzip_ok:reads.fastq.gz"


def test_check_gzip_ok_fails_on_plain_text(tmp_path):
    f = tmp_path / "reads.fastq.gz"
    f.write_text("@SEQ1\nACGT\n")

    result = check_gzip_ok(f)

    assert result.status == "fail"


def test_evaluate_structural_runs_output_and_index_checks(tmp_path):
    a = tmp_path / "aligned.bam"
    a.write_bytes(b"data")
    (tmp_path / "aligned.bam.bai").write_bytes(b"idx")
    b = tmp_path / "variants.vcf"
    b.write_bytes(b"vcf")

    results = evaluate_structural([a, b], index_for=[a])

    # one output check per path plus one index check for `a`
    assert len(results) == 3
    output_checks = [r for r in results if r.check.startswith("output_present:")]
    index_checks = [r for r in results if r.check.startswith("index_present:")]
    assert len(output_checks) == 2
    assert index_checks == [
        r for r in results if r.check == "index_present:aligned.bam"
    ]
    assert len(index_checks) == 1


def test_structural_results_carry_structural_kind(tmp_path):
    f = tmp_path / "aligned.bam"
    f.write_bytes(b"data")

    result = check_output(f)

    assert result.kind == "structural"


def test_check_gzip_integrity_passes_on_decompressible_stream(tmp_path):
    f = tmp_path / "reads.fastq.gz"
    _write_gzip(f, b"@SEQ1\nACGT\n+\nIIII\n")

    result = check_gzip_integrity(f)

    assert result.status == "pass"
    assert result.check == "gzip_integrity:reads.fastq.gz"


def test_check_gzip_integrity_fails_on_truncated_stream(tmp_path):
    f = tmp_path / "reads.fastq.gz"
    full = gzip.compress(b"@SEQ1\nACGT\n+\nIIII\n" * 100)
    f.write_bytes(full[: len(full) // 2])  # chop the stream so the CRC cannot verify

    result = check_gzip_integrity(f)

    assert result.status == "fail"


def test_check_bam_ok_passes_on_well_formed_bam(tmp_path):
    bam = tmp_path / "aligned.bam"
    _write_bam(bam)

    result = check_bam_ok(bam)

    assert result.status == "pass"
    assert result.check == "bam_ok:aligned.bam"


def test_check_bam_ok_fails_when_eof_marker_missing(tmp_path):
    bam = tmp_path / "aligned.bam"
    bam.write_bytes(gzip.compress(b"BAM\x01rest"))  # valid gzip but no BGZF EOF block

    result = check_bam_ok(bam)

    assert result.status == "fail"


def test_check_bam_ok_fails_on_non_gzip_bytes(tmp_path):
    bam = tmp_path / "aligned.bam"
    bam.write_bytes(b"this is not a bam at all")

    result = check_bam_ok(bam)

    assert result.status == "fail"


def test_check_output_count_passes_when_count_matches(tmp_path):
    (tmp_path / "s1.bam").write_bytes(b"x")
    (tmp_path / "s2.bam").write_bytes(b"x")

    result = check_output_count(tmp_path, "*.bam", expected=2)

    assert result.status == "pass"
    assert result.value == 2


def test_check_output_count_fails_when_fewer_than_expected(tmp_path):
    (tmp_path / "s1.bam").write_bytes(b"x")

    result = check_output_count(tmp_path, "*.bam", expected=2)

    assert result.status == "fail"


def test_evaluate_against_manifest_passes_for_present_valid_run(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    bam = results_dir / "sample.markdup.sorted.bam"
    _write_bam(bam)
    (results_dir / "sample.markdup.sorted.bam.bai").write_bytes(b"idx")

    manifest = ExpectedOutputs(
        required=["*.markdup.sorted.bam"],
        indexed=["*.markdup.sorted.bam"],
        bam=["*.markdup.sorted.bam"],
    )
    results = evaluate_against_manifest(results_dir, manifest)

    assert results
    assert all(r.status == "pass" for r in results)
    assert all(r.kind == "structural" for r in results)


def test_evaluate_against_manifest_fails_on_missing_required_output(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    manifest = ExpectedOutputs(required=["*.markdup.sorted.bam"])
    results = evaluate_against_manifest(results_dir, manifest)

    assert any(r.status == "fail" for r in results)


def test_evaluate_against_manifest_fails_on_empty_required_output(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "sample.markdup.sorted.bam").write_bytes(b"")

    manifest = ExpectedOutputs(required=["*.markdup.sorted.bam"])
    results = evaluate_against_manifest(results_dir, manifest)

    assert any(r.status == "fail" for r in results)


def test_evaluate_against_manifest_fails_on_corrupt_bam(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "sample.bam").write_bytes(b"not actually a bam")

    manifest = ExpectedOutputs(required=["*.bam"], bam=["*.bam"])
    results = evaluate_against_manifest(results_dir, manifest)

    assert any(r.status == "fail" for r in results)


def test_evaluate_against_manifest_warns_on_missing_optional_output(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "sample.bam").write_bytes(b"x")

    manifest = ExpectedOutputs(required=["*.bam"], optional=["*.cram"])
    results = evaluate_against_manifest(results_dir, manifest)

    optional_results = [r for r in results if "cram" in r.check]
    assert optional_results
    assert all(r.status == "warn" for r in optional_results)
    assert not any(r.status == "fail" for r in results)


def test_manifest_for_returns_a_manifest_for_a_known_assay():
    manifest = manifest_for("rnaseq")
    assert isinstance(manifest, ExpectedOutputs)
    assert manifest.required


def test_manifest_for_rejects_an_unknown_assay():
    with pytest.raises(ValueError):
        manifest_for("nonexistent_assay")
