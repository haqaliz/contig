"""Structural/integrity QC checks on a run's output files (ARCHITECTURE §6.1).

Real files only, via pytest tmp_path; no mocks.
"""

from contig.verification.structural import (
    check_gzip_ok,
    check_index_present,
    check_output,
    evaluate_structural,
)


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
