"""Deterministic germline genotype-concordance metric (PRD C1, slice 1).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
"""

import gzip

from contig.verification.concordance import (
    concordance_results,
    evaluate_concordance,
    genotype_concordance,
    parse_vcf,
)

_HEADER = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"


def _vcf_line(chrom, pos, ref, alt, gt):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\tGT\t{gt}\n"


def _write_vcf(path, rows):
    """rows: list of (chrom, pos, ref, alt, gt)."""
    body = "".join(_vcf_line(*r) for r in rows)
    path.write_text(_HEADER + body)
    return path


def test_genotype_concordance_identical_calls_is_1(tmp_path):
    rows = [
        ("chr1", 100, "A", "G", "0/1"),
        ("chr1", 200, "C", "T", "1/1"),
        ("chr2", 300, "G", "A", "0/1"),
    ]
    a = _write_vcf(tmp_path / "a.vcf", rows)
    b = _write_vcf(tmp_path / "b.vcf", rows)

    stats = genotype_concordance(a, b)

    assert stats.rate == 1.0
    assert stats.overlap == 1.0


def test_genotype_concordance_one_mismatch(tmp_path):
    a = _write_vcf(
        tmp_path / "a.vcf",
        [
            ("chr1", 100, "A", "G", "0/1"),
            ("chr1", 200, "C", "T", "1/1"),
            ("chr2", 300, "G", "A", "0/1"),
        ],
    )
    b = _write_vcf(
        tmp_path / "b.vcf",
        [
            ("chr1", 100, "A", "G", "0/1"),
            ("chr1", 200, "C", "T", "0/1"),  # differs
            ("chr2", 300, "G", "A", "0/1"),
        ],
    )

    stats = genotype_concordance(a, b)

    assert stats.shared == 3
    assert stats.concordant == 2
    assert stats.rate == 2 / 3
    assert stats.overlap == 1.0


def test_site_overlap_partial(tmp_path):
    # a and b share two sites; a has an extra, b has an extra -> union 4, shared 2.
    a = _write_vcf(
        tmp_path / "a.vcf",
        [
            ("chr1", 100, "A", "G", "0/1"),
            ("chr1", 200, "C", "T", "1/1"),
            ("chr1", 400, "A", "C", "0/1"),  # only in a
        ],
    )
    b = _write_vcf(
        tmp_path / "b.vcf",
        [
            ("chr1", 100, "A", "G", "0/1"),
            ("chr1", 200, "C", "T", "0/1"),  # shared but differs
            ("chr1", 500, "T", "G", "0/1"),  # only in b
        ],
    )

    stats = genotype_concordance(a, b)

    assert stats.shared == 2
    assert stats.overlap == 0.5  # 2 shared / 4 union
    assert stats.concordant == 1
    assert stats.rate == 0.5  # computed only over the 2 shared sites


def test_no_shared_sites_is_unverified(tmp_path):
    a = _write_vcf(tmp_path / "a.vcf", [("chr1", 100, "A", "G", "0/1")])
    b = _write_vcf(tmp_path / "b.vcf", [("chr2", 999, "C", "T", "0/1")])

    stats = genotype_concordance(a, b)
    assert stats.shared == 0
    assert stats.rate is None
    assert stats.overlap == 0.0

    results = {r.check: r for r in concordance_results(a, b)}
    assert results["genotype_concordance"].status == "unverified"
    assert results["site_overlap"].status == "warn"
    assert results["site_overlap"].value == 0.0


def test_gzipped_vcf_parses(tmp_path):
    rows = [
        ("chr1", 100, "A", "G", "0/1"),
        ("chr1", 200, "C", "T", "1/1"),
    ]
    plain = _write_vcf(tmp_path / "a.vcf", rows)
    gz = tmp_path / "a.vcf.gz"
    with gzip.open(gz, "wt") as fh:
        fh.write(_HEADER + "".join(_vcf_line(*r) for r in rows))

    assert parse_vcf(gz) == parse_vcf(plain)


def test_concordance_results_tagged_kind(tmp_path):
    a = _write_vcf(tmp_path / "a.vcf", [("chr1", 100, "A", "G", "0/1")])
    b = _write_vcf(tmp_path / "b.vcf", [("chr1", 100, "A", "G", "0/1")])

    results = concordance_results(a, b)

    assert len(results) == 2
    assert all(r.kind == "concordance" for r in results)


def test_phased_and_unphased_compare_equal(tmp_path):
    a = _write_vcf(tmp_path / "a.vcf", [("chr1", 100, "A", "G", "0|1")])
    b = _write_vcf(tmp_path / "b.vcf", [("chr1", 100, "A", "G", "1/0")])

    stats = genotype_concordance(a, b)

    assert stats.concordant == 1
    assert stats.rate == 1.0


def test_evaluate_concordance_for_variant_assay(tmp_path):
    rows = [("chr1", 100, "A", "G", "0/1")]
    a = _write_vcf(tmp_path / "a.vcf", rows)
    b = _write_vcf(tmp_path / "b.vcf", rows)

    results = evaluate_concordance(a, b, assay="variant_calling")

    assert len(results) == 2
    assert all(r.kind == "concordance" for r in results)
    assert {r.check for r in results} == {"genotype_concordance", "site_overlap"}


def test_evaluate_concordance_skips_non_variant_assay(tmp_path):
    rows = [("chr1", 100, "A", "G", "0/1")]
    a = _write_vcf(tmp_path / "a.vcf", rows)
    b = _write_vcf(tmp_path / "b.vcf", rows)

    # Concordance is only defined for assays with a defined comparison; RNA-seq
    # quantification has no germline call set to corroborate.
    assert evaluate_concordance(a, b, assay="rnaseq") == []
