import gzip
from pathlib import Path

from contig.verification.annotation_structural import (
    AnnotationMetrics,
    annotation_metrics,
    evaluate_annotation_structural,
)

VEP_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)


def _write(tmp_path: Path, name: str, body: str, gz: bool = False) -> Path:
    p = tmp_path / name
    if gz:
        with gzip.open(p, "wt") as fh:
            fh.write(body)
    else:
        p.write_text(body)
    return p


def test_all_records_annotated_passes(tmp_path):
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant|MODERATE|BRCA1\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|synonymous_variant|LOW|BRCA1\n"
    )
    vcf = _write(tmp_path, "ann.vcf", body)
    m = annotation_metrics(vcf)
    assert m == AnnotationMetrics(info_key="CSQ", total_records=2, annotated_records=2)
    results = evaluate_annotation_structural(vcf)
    by_check = {r.check: r for r in results}
    assert by_check["annotation_present"].status == "pass"
    assert by_check["annotation_present"].kind == "structural"
    assert by_check["annotation_complete"].status == "pass"
    assert by_check["annotation_complete"].value == 1.0


def test_partial_annotation_warns(tmp_path):
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant|MODERATE|BRCA1\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tDP=30\n"  # no CSQ on this record
    )
    vcf = _write(tmp_path, "partial.vcf", body)
    results = evaluate_annotation_structural(vcf)
    by_check = {r.check: r for r in results}
    assert by_check["annotation_complete"].status == "warn"
    assert by_check["annotation_complete"].value == 0.5


def test_no_annotation_info_is_unverified(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
    )
    vcf = _write(tmp_path, "plain.vcf", body)
    results = evaluate_annotation_structural(vcf)
    statuses = {r.check: r.status for r in results}
    assert statuses["annotation_present"] == "unverified"


def test_snpeff_ann_key_and_gzip(tmp_path):
    body = (
        "##fileformat=VCFv4.2\n"
        '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
        "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
        "chr1\t100\t.\tA\tG\t50\tPASS\tANN=G|missense_variant|MODERATE|TP53\n"
    )
    vcf = _write(tmp_path, "snpeff.vcf.gz", body, gz=True)
    m = annotation_metrics(vcf)
    assert m.info_key == "ANN"
    assert m.annotated_records == 1
