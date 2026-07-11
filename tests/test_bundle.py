"""Tests for the reproducibility bundle module (ARCHITECTURE §7)."""

import json

import pytest

from contig.bundle import (
    compute_input_checksums,
    compute_output_checksums,
    compute_reference_identity,
    load_bundle,
    write_bundle,
)
from contig.models import ExecutionTarget, QCResult, RunRecord, TaskEvent, sha256_file
from contig.signing import (
    canonical_sha256,
    generate_keypair,
    signing_available,
    verify_signature,
)


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


def test_compute_input_checksums_rejects_duplicate_basenames(tmp_path):
    import pytest

    d1 = tmp_path / "s1"
    d1.mkdir()
    d2 = tmp_path / "s2"
    d2.mkdir()
    f1 = d1 / "reads.fastq"
    f1.write_bytes(b"x")
    f2 = d2 / "reads.fastq"
    f2.write_bytes(b"y")
    with pytest.raises(ValueError):
        compute_input_checksums([f1, f2])


def test_load_preserves_fail_verdict(tmp_path):
    rec = _minimal_record()
    rec.qc_results = [QCResult(check="contamination", status="fail", message="too high")]
    assert rec.verdict == "fail"

    loaded = load_bundle(write_bundle(rec, tmp_path).parent)

    assert loaded.verdict == "fail"


# --- output checksums (PRD contract B: output integrity) -----------------------
def test_compute_output_checksums_maps_relpath_to_sha256(tmp_path):
    results = tmp_path / "results"
    (results / "multiqc").mkdir(parents=True)
    top = results / "summary.txt"
    top.write_bytes(b"summary")
    nested = results / "multiqc" / "report.html"
    nested.write_bytes(b"report")

    sums = compute_output_checksums(results)

    # Keyed by path RELATIVE to results_dir, so the record is portable and the
    # nested file keeps its subdirectory.
    assert set(sums) == {"summary.txt", "multiqc/report.html"}
    assert sums["summary.txt"] == sha256_file(top)
    assert sums["multiqc/report.html"] == sha256_file(nested)


def test_compute_output_checksums_uses_posix_relpaths(tmp_path):
    results = tmp_path / "results"
    (results / "star").mkdir(parents=True)
    (results / "star" / "log.txt").write_bytes(b"x")

    sums = compute_output_checksums(results)

    # Forward slashes on every platform, so the key matches across a re-hash.
    assert "star/log.txt" in sums


def test_compute_output_checksums_skips_absent_results_dir(tmp_path):
    assert compute_output_checksums(tmp_path / "nope") == {}


def test_compute_output_checksums_empty_dir_is_empty_map(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    assert compute_output_checksums(results) == {}


# --- signed records (PRD contract E: signature sidecar) ------------------------
requires_signing = pytest.mark.skipif(
    not signing_available(), reason="cryptography not installed"
)


def test_write_bundle_writes_no_sidecar_without_a_signing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTIG_SIGNING_KEY", raising=False)

    write_bundle(_minimal_record(), tmp_path)

    assert not (tmp_path / "signature.json").exists()


@requires_signing
def test_write_bundle_writes_signature_sidecar_when_key_is_set(tmp_path, monkeypatch):
    private_key, public_key = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)
    record = _full_record()

    write_bundle(record, tmp_path)

    sidecar = tmp_path / "signature.json"
    assert sidecar.is_file()
    payload = json.loads(sidecar.read_text())
    assert payload["algo"] == "ed25519"
    assert payload["public_key"] == public_key
    assert payload["signed_sha256"] == canonical_sha256(record)
    assert verify_signature(record, payload["signature"], payload["public_key"]) is True


@requires_signing
def test_signature_sidecar_does_not_sign_itself(tmp_path, monkeypatch):
    # The signature signs the canonical record content; writing the sidecar must
    # not change what the signature covers. Reloading the record and re-verifying
    # against the sidecar still passes.
    private_key, _ = generate_keypair()
    monkeypatch.setenv("CONTIG_SIGNING_KEY", private_key)
    record = _full_record()

    write_bundle(record, tmp_path)

    payload = json.loads((tmp_path / "signature.json").read_text())
    loaded = load_bundle(tmp_path)
    assert verify_signature(loaded, payload["signature"], payload["public_key"]) is True


# --- compute_reference_identity (provenance capture: reference genome) ----------

def test_compute_reference_identity_explicit_mode(tmp_path):
    fa = tmp_path / "genome.fa"
    gtf = tmp_path / "annotation.gtf"
    fa.write_bytes(b"ACGT" * 100)
    gtf.write_bytes(b"# GTF header\n")

    result = compute_reference_identity({"fasta": str(fa), "gtf": str(gtf)})

    assert result is not None
    assert result.mode == "explicit"
    assert result.fasta == str(fa)
    assert result.gtf == str(gtf)
    assert result.fasta_sha256 == sha256_file(fa)
    assert result.gtf_sha256 == sha256_file(gtf)


def test_compute_reference_identity_igenomes_mode():
    result = compute_reference_identity({"genome": "GRCh38"})

    assert result is not None
    assert result.mode == "igenomes"
    assert result.genome == "GRCh38"
    assert result.fasta_sha256 is None
    assert result.gtf_sha256 is None


def test_compute_reference_identity_no_reference_returns_none():
    result = compute_reference_identity({"outdir": "/x", "input": "/y"})

    assert result is None


def test_compute_reference_identity_missing_explicit_file_degrades_gracefully(tmp_path):
    gtf = tmp_path / "annotation.gtf"
    gtf.write_bytes(b"# GTF header\n")

    result = compute_reference_identity(
        {"fasta": str(tmp_path / "nope.fa"), "gtf": str(gtf)}
    )

    assert result is not None
    assert result.fasta_sha256 is None
    assert result.gtf_sha256 == sha256_file(gtf)


def test_compute_reference_identity_deterministic(tmp_path):
    fa = tmp_path / "genome.fa"
    gtf = tmp_path / "annotation.gtf"
    fa.write_bytes(b"TTGCAA" * 50)
    gtf.write_bytes(b"# stable bytes\n")
    params = {"fasta": str(fa), "gtf": str(gtf)}

    first = compute_reference_identity(params)
    second = compute_reference_identity(params)

    assert first is not None
    assert second is not None
    assert first.fasta_sha256 == second.fasta_sha256
    assert first.gtf_sha256 == second.gtf_sha256


def test_compute_reference_identity_empty_params_returns_none():
    assert compute_reference_identity({}) is None


def test_compute_reference_identity_none_params_returns_none():
    assert compute_reference_identity(None) is None


# --- compute_sex_inference (provenance capture: germline karyotypic sex) --------
# VCF discovery mirrors runner._discover_qc exactly (manifest_for("variant_calling")
# .required[0] rglob'd under run_dir, vcfs[0]) so provenance and the verdict
# describe the same call set -- see tests/verification/test_sex_plausibility.py
# for the male-pattern row shapes reused here.

_SEX_VCF_HEADER = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chr1,length=248956422>\n"
    "##contig=<ID=chrX,length=156040895>\n"
    "##contig=<ID=chrY,length=57227415>\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
)


def _sex_vcf_line(chrom, pos, ref, alt, gt):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\tGT\t{gt}\n"


def _write_male_pattern_vcf(path):
    """A gzipped germline VCF with a male-pattern chrX/chrY call set (low
    X-het, chrY variants present), placed under the manifest's `*.vcf.gz` glob."""
    import gzip

    rows = [("chrX", 3_000_000 + i, "A", "G", "0/1") for i in range(2)]
    rows += [("chrX", 4_000_000 + i, "A", "G", "0/0") for i in range(28)]
    rows += [("chrY", 10_000_000 + i, "A", "G", "0/1") for i in range(6)]
    body = "".join(_sex_vcf_line(*r) for r in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(_SEX_VCF_HEADER + body)
    return path


def test_compute_sex_inference_male_pattern_vcf_returns_xy(tmp_path):
    from contig.bundle import compute_sex_inference

    _write_male_pattern_vcf(tmp_path / "results" / "variant_calling" / "sample.vcf.gz")

    result = compute_sex_inference(tmp_path)

    assert result is not None
    assert result.inferred_sex == "XY"
    assert result.y_variant_count == 6


def test_compute_sex_inference_no_vcf_returns_none(tmp_path):
    from contig.bundle import compute_sex_inference

    assert compute_sex_inference(tmp_path) is None
