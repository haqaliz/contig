"""C7 M4 phase 4: run-level discovery + auto-wiring of VEP-vs-SnpEff annotation
concordance (both metrics from phases 2-3) into `_discover_qc`, for both variant
assays, with no CLI flag -- mirrors the somatic-concordance auto-wiring pattern
exactly.

Integration tests through `_discover_qc` (see `tests/test_annotation_integration.py`
and `tests/test_annotation_somatic_gate.py` for the run-dir/gz fixture pattern this
mirrors).
"""

import gzip
from pathlib import Path

from contig.runner import _discover_qc

# VEP CSQ header: Format declares Consequence at index 1, SYMBOL at index 3.
VEP_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

# SnpEff ANN header: fixed layout, consequence ("Annotation") at index 1,
# Gene_Name at index 3.
ANN_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
    "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

# A single VCF declaring BOTH CSQ and ANN headers (single-vcf-both layout).
BOTH_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
    "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

NO_ANNOTATION_HEADER = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)


def _write_gz(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        fh.write(body)
    return path


def _sites(n, chrom="chr1", start=100):
    return [(chrom, start + i, "A", "G") for i in range(n)]


def _csq_body(sites, term="missense_variant", symbol="GENE1"):
    return "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\tCSQ={alt}|{term}|MODERATE|{symbol}\n"
        for chrom, pos, ref, alt in sites
    )


def _ann_body(sites, term="missense_variant", symbol="GENE1"):
    return "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\tANN={alt}|{term}|MODERATE|{symbol}\n"
        for chrom, pos, ref, alt in sites
    )


def _both_body(sites, term="missense_variant", symbol="GENE1"):
    return "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\t"
        f"CSQ={alt}|{term}|MODERATE|{symbol};ANN={alt}|{term}|MODERATE|{symbol}\n"
        for chrom, pos, ref, alt in sites
    )


def _concordance_results(results):
    return {
        r.check: r
        for r in results
        if r.check in {"consequence_concordance", "gene_symbol_concordance"}
    }


def test_wiring_two_file_variant_calling(tmp_path):
    sites = _sites(10)
    _write_gz(
        tmp_path / "results" / "annotation" / "vep" / "x.vcf.gz",
        VEP_HEADER + _csq_body(sites),
    )
    _write_gz(
        tmp_path / "results" / "annotation" / "snpeff" / "x.vcf.gz",
        ANN_HEADER + _ann_body(sites),
    )

    results = _discover_qc(tmp_path, assay="variant_calling")
    by_check = _concordance_results(results)

    assert "consequence_concordance" in by_check
    assert "gene_symbol_concordance" in by_check
    assert by_check["consequence_concordance"].kind == "concordance"
    assert by_check["gene_symbol_concordance"].kind == "concordance"
    assert by_check["consequence_concordance"].status == "pass"


def test_wiring_somatic_assay(tmp_path):
    sites = _sites(10)
    _write_gz(
        tmp_path / "results" / "annotation" / "vep" / "x.vcf.gz",
        VEP_HEADER + _csq_body(sites),
    )
    _write_gz(
        tmp_path / "results" / "annotation" / "snpeff" / "x.vcf.gz",
        ANN_HEADER + _ann_body(sites),
    )

    results = _discover_qc(tmp_path, assay="somatic_variant_calling")
    by_check = _concordance_results(results)

    assert "consequence_concordance" in by_check
    assert "gene_symbol_concordance" in by_check
    assert by_check["consequence_concordance"].status == "pass"


def test_wiring_single_annotator_unverified(tmp_path):
    sites = _sites(10)
    _write_gz(
        tmp_path / "results" / "annotation" / "vep" / "x.vcf.gz",
        VEP_HEADER + _csq_body(sites),
    )
    # No SnpEff VCF anywhere under the run: only one annotator ran.

    results = _discover_qc(tmp_path, assay="variant_calling")
    by_check = _concordance_results(results)

    assert by_check["consequence_concordance"].status == "unverified"
    assert by_check["consequence_concordance"].value is None
    assert by_check["gene_symbol_concordance"].status == "unverified"
    assert by_check["gene_symbol_concordance"].value is None
    # NEVER a false pass.
    assert all(r.status != "pass" for r in by_check.values())
    for r in by_check.values():
        assert "VEP" in r.message


def test_wiring_single_vcf_both(tmp_path):
    sites = _sites(10)
    _write_gz(
        tmp_path / "results" / "annotation" / "x.ann.vcf.gz",
        BOTH_HEADER + _both_body(sites),
    )

    results = _discover_qc(tmp_path, assay="variant_calling")
    by_check = _concordance_results(results)

    assert "consequence_concordance" in by_check
    assert "gene_symbol_concordance" in by_check
    assert "single-vcf-both" in by_check["consequence_concordance"].message


def test_wiring_non_variant_assay_skips(tmp_path):
    sites = _sites(10)
    _write_gz(
        tmp_path / "results" / "annotation" / "vep" / "x.vcf.gz",
        VEP_HEADER + _csq_body(sites),
    )
    _write_gz(
        tmp_path / "results" / "annotation" / "snpeff" / "x.vcf.gz",
        ANN_HEADER + _ann_body(sites),
    )

    results = _discover_qc(tmp_path, assay="rnaseq")
    by_check = _concordance_results(results)

    assert by_check == {}


def test_wiring_no_annotation_clean_skip(tmp_path):
    _write_gz(
        tmp_path / "results" / "variant_calling" / "s.vcf.gz",
        NO_ANNOTATION_HEADER + "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n",
    )

    results = _discover_qc(tmp_path, assay="variant_calling")
    by_check = _concordance_results(results)

    assert by_check == {}
