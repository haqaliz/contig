"""Lifecycle wiring tests for the germline annotation slice (capability C7, M1).

Proves the two integration seams Task 3 adds: `_discover_qc` emits the annotation
structural checks for a germline run that produced an annotated VCF, and
`render_methods` renders an attribution clause when annotation provenance is
present. Synthetic VCF fixtures only — no real VEP/sarek in CI.
"""

import gzip
from pathlib import Path

from contig.methods import render_methods
from contig.models import AnnotationProvenance, ExecutionTarget, RunRecord
from contig.runner import _discover_qc


def _write_gz(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


VEP_VCF = (
    "##fileformat=VCFv4.2\n"
    '##VEP="v110" cache="/vep/homo_sapiens/110_GRCh38"\n'
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="... Format: Allele|Consequence">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
    "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
)


def test_discover_qc_emits_annotation_checks_for_germline(tmp_path):
    _write_gz(tmp_path / "results" / "annotation" / "s_VEP.ann.vcf.gz", VEP_VCF)
    results = _discover_qc(tmp_path, assay="variant_calling")
    checks = {r.check for r in results}
    assert "annotation_present" in checks
    assert "annotation_complete" in checks


def test_methods_renders_annotation_clause():
    # Constructs annotation_identity as a SINGLE object -- the pre-M4 legacy
    # shape -- to exercise the back-compat validator on RunRecord construction.
    record = RunRecord(
        run_id="r1",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        assay="variant_calling",
        annotation_identity=AnnotationProvenance(tool="VEP", version="v110"),
    )
    text = render_methods(record)
    assert "VEP" in text
    assert "v110" in text


def test_methods_renders_both_annotators():
    # M4: a RunRecord carrying BOTH VEP and SnpEff provenance renders both
    # tool+version strings in the methods paragraph.
    record = RunRecord(
        run_id="r2",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        assay="variant_calling",
        annotation_identity=[
            AnnotationProvenance(tool="VEP", version="v110"),
            AnnotationProvenance(tool="SnpEff", version="5.1"),
        ],
    )
    text = render_methods(record)
    assert "VEP" in text and "v110" in text
    assert "SnpEff" in text and "5.1" in text
