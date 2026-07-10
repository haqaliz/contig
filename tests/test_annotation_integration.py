# tests/test_annotation_integration.py
import gzip
from pathlib import Path

from contig.runner import _discover_qc
from contig.bundle import compute_annotation_identity


def _write_gz(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


def test_annotated_germline_run_verifies_and_captures_provenance(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##VEP="v110" cache="/vep/homo_sapiens/110_GRCh38"\n'
        '##INFO=<ID=CSQ,Number=.,Type=String,Description="... Format: Allele|Consequence">\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|synonymous_variant\n"
    )
    _write_gz(tmp_path / "results" / "annotation" / "s_VEP.ann.vcf.gz", body)

    results = _discover_qc(tmp_path, assay="variant_calling")
    present = next(r for r in results if r.check == "annotation_present")
    complete = next(r for r in results if r.check == "annotation_complete")
    assert present.status == "pass"
    assert complete.status == "pass" and complete.value == 1.0

    prov = compute_annotation_identity(tmp_path)
    assert prov is not None and prov.tool == "VEP" and prov.version == "v110"


def test_unannotated_germline_run_yields_no_false_pass(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
    )
    _write_gz(tmp_path / "results" / "variantcalling" / "s.vcf.gz", body)
    results = _discover_qc(tmp_path, assay="variant_calling")
    ann = [r for r in results if r.check.startswith("annotation_")]
    # An un-annotated germline run simply has no annotated VCF: no annotation check
    # fires (skipped), and NONE reports pass.
    assert all(r.status != "pass" for r in ann)
    assert compute_annotation_identity(tmp_path) is None
