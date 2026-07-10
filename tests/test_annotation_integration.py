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

    real_fraction = next(
        r for r in results if r.check == "annotation_real_fraction:sample"
    )
    distribution = next(
        r for r in results if r.check == "annotation_consequence_distribution:sample"
    )
    assert real_fraction.status == "pass"
    assert distribution.status == "pass"

    prov = compute_annotation_identity(tmp_path)
    assert len(prov) == 1 and prov[0].tool == "VEP" and prov[0].version == "v110"


def test_all_intergenic_germline_run_warns_but_never_fails(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##VEP="v110" cache="/vep/homo_sapiens/110_GRCh38"\n'
        '##INFO=<ID=CSQ,Number=.,Type=String,Description="... Format: Allele|Consequence">\n'
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|intergenic_variant\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|intergenic_variant\n"
    )
    _write_gz(tmp_path / "results" / "annotation" / "s_VEP.ann.vcf.gz", body)

    results = _discover_qc(tmp_path, assay="variant_calling")
    distribution = next(
        r for r in results if r.check == "annotation_consequence_distribution:sample"
    )
    assert distribution.status == "warn"
    assert distribution.status != "fail"


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
    # No plausibility check (pass/warn/fail/unverified) is emitted at all — the
    # structural block already owns the honest "no annotated VCF found" case, and
    # emitting a duplicate unverified here would be noise.
    plausibility_checks = {"annotation_real_fraction", "annotation_consequence_distribution"}
    assert not any(r.check.split(":")[0] in plausibility_checks for r in results)
    assert compute_annotation_identity(tmp_path) == []
