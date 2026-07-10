# tests/test_annotation_somatic_gate.py
"""C7 M2: the SAME shipped germline annotation structural verifier + provenance
capture, enabled + gated for the somatic assay. No new verification algorithm —
enablement + gating only. Mirrors tests/test_annotation_integration.py."""
import gzip
from pathlib import Path

from contig.models import ExecutionTarget
from contig.runner import _discover_qc
from contig.self_heal import self_heal_run


def _write_gz(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


_VEP_BODY = (
    "##fileformat=VCFv4.2\n"
    '##VEP="v110" cache="/vep/homo_sapiens/110_GRCh38"\n'
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="... Format: Allele|Consequence">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
    "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|synonymous_variant\n"
)

_UNANNOTATED_BODY = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
)


# ---------------------------------------------------------------------------
# 1. Structural verifier gated to the somatic assay (mirrors
#    tests/test_annotation_integration.py's germline coverage). Fixture path
#    mirrors sarek's somatic annotation output shape (D3); detection itself is
#    path-agnostic (rglob + first-CSQ/ANN-header-wins).
# ---------------------------------------------------------------------------


def test_annotated_somatic_run_verifies(tmp_path):
    _write_gz(
        tmp_path
        / "results"
        / "annotation"
        / "tumorA_vs_normalA"
        / "mutect2"
        / "tumorA_VEP.ann.vcf.gz",
        _VEP_BODY,
    )

    results = _discover_qc(tmp_path, assay="somatic_variant_calling")
    present = next(r for r in results if r.check == "annotation_present")
    complete = next(r for r in results if r.check == "annotation_complete")
    assert present.status == "pass"
    assert complete.status == "pass" and complete.value == 1.0


def test_unannotated_somatic_run_yields_no_false_pass(tmp_path):
    _write_gz(
        tmp_path / "results" / "variant_calling" / "mutect2" / "tumorA_vs_normalA.vcf.gz",
        _UNANNOTATED_BODY,
    )

    results = _discover_qc(tmp_path, assay="somatic_variant_calling")
    ann = [r for r in results if r.check.startswith("annotation_")]
    # A somatic run with no CSQ/ANN-declaring VCF at all: the annotation check
    # simply doesn't fire (mirrors the germline no-annotation case verbatim —
    # the structural block finds no annotated VCF and skips), and NONE reports
    # pass either way.
    assert all(r.status != "pass" for r in ann)


# ---------------------------------------------------------------------------
# 2. Provenance-gating (AnnotationProvenance capture at self_heal._finalize):
#    both variant assays capture it; a non-variant assay whose output
#    incidentally carries a CSQ-like token must NOT (drives the real seam).
# ---------------------------------------------------------------------------


def _target(d):
    return ExecutionTarget(backend="local", container_runtime="docker", work_dir=str(d))


def _trace_ok():
    return (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\n"
        "1\tab/cd\t1\tNFCORE_RNASEQ:STAR_ALIGN (S1)\tCOMPLETED\t0\t-\t-\t-\n"
    )


def _heal_with_incidental_vcf(tmp_path, assay):
    run_dir = tmp_path / "runs" / "r"
    # An output VCF that incidentally carries a CSQ-like token, written UNDER
    # the run dir BEFORE the run executes, so it's present when _finalize scans
    # for it via compute_annotation_identity.
    _write_gz(run_dir / "results" / "incidental_VEP.ann.vcf.gz", _VEP_BODY)

    def executor(cmd, trace_path):
        Path(trace_path).write_text(_trace_ok())
        (Path(trace_path).parent / "run.log").write_text("done")
        return 0

    return self_heal_run(
        pipeline="nf-core/rnaseq",
        revision="3.26.0",
        profiles=["test", "docker"],
        target=_target(tmp_path / "w"),
        input_paths=[],
        runs_dir=tmp_path / "runs",
        run_id="r",
        executor=executor,
        max_attempts=3,
        assay=assay,
    )


def test_non_variant_assay_does_not_capture_annotation_provenance(tmp_path):
    record = _heal_with_incidental_vcf(tmp_path, assay="rnaseq")
    assert record.annotation_identity is None


def test_germline_variant_assay_captures_annotation_provenance(tmp_path):
    record = _heal_with_incidental_vcf(tmp_path, assay="variant_calling")
    assert record.annotation_identity is not None
    assert record.annotation_identity.tool == "VEP"


def test_somatic_variant_assay_captures_annotation_provenance(tmp_path):
    record = _heal_with_incidental_vcf(tmp_path, assay="somatic_variant_calling")
    assert record.annotation_identity is not None
    assert record.annotation_identity.tool == "VEP"
