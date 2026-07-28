"""Lifecycle wiring tests for the germline annotation slice (capability C7, M1).

Proves the two integration seams Task 3 adds: `_discover_qc` emits the annotation
structural checks for a germline run that produced an annotated VCF, and
`render_methods` renders an attribution clause when annotation provenance is
present. Synthetic VCF fixtures only — no real VEP/sarek in CI.
"""

import gzip
from pathlib import Path

from contig.methods import render_methods
from contig.models import AnnotationProvenance, ExecutionTarget, QCResult, RunRecord
from contig.runner import _discover_qc


def _consequence_pass() -> QCResult:
    return QCResult(
        check="consequence_concordance",
        status="pass",
        message=(
            "vep vs snpeff: 47/50 shared site(s) agree on the most-severe "
            "consequence (agreement 0.94); layout=two-file"
        ),
        value=0.94,
        expected_range=">= 0.9",
        kind="concordance",
    )


def _gene_symbol_pass() -> QCResult:
    return QCResult(
        check="gene_symbol_concordance",
        status="pass",
        message=(
            "vep vs snpeff: 45/50 resolvable gene-symbol pair(s) agree "
            "(agreement 0.9); informational only, never affects the verdict"
        ),
        value=0.9,
        expected_range=None,
        kind="concordance",
        informational=True,
    )


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


def test_methods_renders_cache_build_when_db_version_present():
    # M5: an annotation provenance entry carrying a db_version renders the
    # cache/build identifier honestly labeled as "cache/build" (never "database
    # version"), alongside tool + tool-version.
    record = RunRecord(
        run_id="r-cb",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        assay="variant_calling",
        annotation_identity=[
            AnnotationProvenance(tool="VEP", version="v110", db_version="110_GRCh38"),
        ],
    )
    text = render_methods(record)
    assert "VEP" in text and "v110" in text
    assert "cache/build 110_GRCh38" in text
    # Must never over-claim it is a database version (PRD D1/R2).
    assert "database version" not in text


def test_methods_renders_no_orphan_cache_build_when_db_version_absent():
    # M5: an entry without a db_version renders tool+version only -- no orphan
    # "(cache/build )" label.
    record = RunRecord(
        run_id="r-nocb",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        assay="variant_calling",
        annotation_identity=[
            AnnotationProvenance(tool="SnpEff", version="5.1"),
        ],
    )
    text = render_methods(record)
    assert "SnpEff" in text and "5.1" in text
    assert "cache/build" not in text


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


def test_methods_appends_corroboration_sentence_when_dual_annotated():
    # M5: when M4's concordance results are present, render_methods appends the
    # shared corroborated-by sentence sourced from the pure helper.
    record = RunRecord(
        run_id="r-corro-methods",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        assay="variant_calling",
        qc_results=[_consequence_pass(), _gene_symbol_pass()],
        annotation_identity=[
            AnnotationProvenance(tool="VEP", version="v110"),
            AnnotationProvenance(tool="SnpEff", version="5.1d"),
        ],
    )
    text = render_methods(record)
    assert "Corroborated by VEP and SnpEff" in text
    assert "47/50 consequences agree" in text


def test_methods_omits_corroboration_when_single_annotator():
    # M5: a single-annotator run (concordance UNVERIFIED, value None) yields no
    # corroboration sentence -- helper returns None, nothing is appended (D2).
    record = RunRecord(
        run_id="r-single-methods",
        pipeline="nf-core/sarek",
        pipeline_revision="3.5.1",
        target=ExecutionTarget(backend="local", container_runtime="docker", work_dir="w"),
        input_checksums={},
        assay="variant_calling",
        qc_results=[
            QCResult(
                check="consequence_concordance",
                status="unverified",
                message="only VEP annotation is present under this run",
                value=None,
                expected_range=">= 0.9",
                kind="concordance",
            ),
        ],
        annotation_identity=[AnnotationProvenance(tool="VEP", version="v110")],
    )
    text = render_methods(record)
    assert "Corroborated by" not in text
