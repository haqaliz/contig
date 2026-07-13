"""Strelka2 tier-count VAF parser (SNV AU/CU/GU/TU, indel TAR/TIR).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Mirrors the style of test_somatic_plausibility.py: tiny inline VCFs, streamed
FORMAT/sample columns, gzip-transparent open.

Strelka2 defines its own tumor allele-fraction from tier1 (high-confidence) tier
counts rather than an AF/AD FORMAT field: for SNVs, VAF = tier1({ALT}U) /
(tier1({REF}U) + tier1({ALT}U)) over the base-count fields AU/CU/GU/TU; for
indels, VAF = tier1(TIR) / (tier1(TAR) + tier1(TIR)). This is Strelka2's own
documented AF definition (see the project's user guide "Variant Allele
Frequency" section), not something this codebase invents.
"""

import gzip

import pytest

from contig.verification.strelka_vaf import (
    read_strelka_vafs,
    strelka_median_vaf,
)

_TUMOR = "TUMOR"
_NORMAL = "NORMAL"


def _snv_header(tumor=_TUMOR, normal=_NORMAL):
    # column order: NORMAL then TUMOR, to prove selection is by name not position
    return (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t"
        f"{normal}\t{tumor}\n"
    )


def _snv_rec(chrom, pos, ref, alt, tumor_fmt, normal_fmt="0,0:0,0:0,0:0,0"):
    fmt = "AU:CU:GU:TU"
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\t{fmt}\t{normal_fmt}\t{tumor_fmt}\n"


def _indel_header(tumor=_TUMOR, normal=_NORMAL):
    return (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t"
        f"{normal}\t{tumor}\n"
    )


def _indel_rec(chrom, pos, ref, alt, tumor_fmt, normal_fmt="0,0:0,0"):
    fmt = "TAR:TIR"
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\t{fmt}\t{normal_fmt}\t{tumor_fmt}\n"


def _write(path, header, recs):
    path.write_text(header + "".join(recs))
    return path


def test_snv_vaf_exact(tmp_path):
    # REF=C ALT=A; tumor AU=6,7 CU=14,15 GU=0,0 TU=0,0
    # VAF = tier1(AU) / (tier1(CU) + tier1(AU)) = 6 / (14 + 6) = 0.30
    recs = [_snv_rec("chr1", 100, "C", "A", "6,7:14,15:0,0:0,0")]
    vcf = _write(tmp_path / "snv.vcf", _snv_header(), recs)

    vafs, tumor_found = read_strelka_vafs(snv_path=vcf)

    assert tumor_found is True
    assert vafs == [pytest.approx(0.30)]


def test_indel_vaf_exact(tmp_path):
    # tumor TAR=18,20 TIR=2,3 -> VAF = 2 / (18 + 2) = 0.10
    recs = [_indel_rec("chr1", 100, "AT", "A", "18,20:2,3")]
    vcf = _write(tmp_path / "indel.vcf", _indel_header(), recs)

    vafs, tumor_found = read_strelka_vafs(indel_path=vcf)

    assert tumor_found is True
    assert vafs == [pytest.approx(0.10)]


def test_pooled_median_exact(tmp_path):
    # SNV file gives 0.30 and 0.50; indel file gives 0.10.
    # Pooled median of [0.10, 0.30, 0.50] == 0.30.
    snv_recs = [
        _snv_rec("chr1", 100, "C", "A", "6,7:14,15:0,0:0,0"),  # 6/(14+6)=0.30
        _snv_rec("chr1", 200, "A", "G", "10,10:0,0:10,10:0,0"),  # 10/(10+10)=0.50
    ]
    snv_vcf = _write(tmp_path / "snv.vcf", _snv_header(), snv_recs)
    indel_recs = [_indel_rec("chr1", 300, "AT", "A", "18,20:2,3")]  # 2/(18+2)=0.10
    indel_vcf = _write(tmp_path / "indel.vcf", _indel_header(), indel_recs)

    median, tumor_found = strelka_median_vaf(snv_path=snv_vcf, indel_path=indel_vcf)

    assert tumor_found is True
    assert median == pytest.approx(0.30)


def test_multiallelic_excluded(tmp_path):
    # Comma-ALT SNV record contributes nothing; only the biallelic sibling counts.
    recs = [
        _snv_rec("chr1", 100, "C", "A,G", "6,7:14,15:0,0:0,0"),
        _snv_rec("chr1", 200, "A", "G", "10,10:0,0:10,10:0,0"),  # 0.50
    ]
    vcf = _write(tmp_path / "snv.vcf", _snv_header(), recs)

    vafs, tumor_found = read_strelka_vafs(snv_path=vcf)

    assert tumor_found is True
    assert vafs == [pytest.approx(0.50)]


def test_zero_denominator_and_malformed_omitted(tmp_path):
    # Zero denominator (AU=0,0 CU=0,0) and a non-numeric field both contribute
    # nothing -- never 0.0, never crash.
    recs = [
        _snv_rec("chr1", 100, "C", "A", "0,0:0,0:0,0:0,0"),  # denom 0
        _snv_rec("chr1", 200, "C", "A", "x,7:14,15:0,0:0,0"),  # malformed AU
        _snv_rec("chr1", 300, "A", "G", "10,10:0,0:10,10:0,0"),  # 0.50, still counts
    ]
    vcf = _write(tmp_path / "snv.vcf", _snv_header(), recs)

    vafs, tumor_found = read_strelka_vafs(snv_path=vcf)

    assert tumor_found is True
    assert vafs == [pytest.approx(0.50)]


def test_snv_non_acgt_skipped(tmp_path):
    # A multi-base REF in the SNV file (e.g. an indel-shaped record that leaked
    # into the SNV file) is skipped outright, never mis-indexed into AU/CU/GU/TU.
    recs = [
        _snv_rec("chr1", 100, "AT", "A", "6,7:14,15:0,0:0,0"),  # skipped: REF not single base
        _snv_rec("chr1", 200, "A", "G", "10,10:0,0:10,10:0,0"),  # 0.50, still counts
    ]
    vcf = _write(tmp_path / "snv.vcf", _snv_header(), recs)

    vafs, tumor_found = read_strelka_vafs(snv_path=vcf)

    assert tumor_found is True
    assert vafs == [pytest.approx(0.50)]


def test_no_tumor_column_returns_none(tmp_path):
    # Header has only NORMAL (no column literally named TUMOR) -> tumor_found is
    # False and the VAF list is empty (never a positional guess).
    header = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tNORMAL\n"
    )
    recs = [
        "chr1\t100\t.\tC\tA\t.\tPASS\t.\tAU:CU:GU:TU\t6,7:14,15:0,0:0,0\n",
    ]
    vcf = _write(tmp_path / "snv.vcf", header, recs)

    vafs, tumor_found = read_strelka_vafs(snv_path=vcf)

    assert tumor_found is False
    assert vafs == []


def test_gzip_supported(tmp_path):
    recs = [_snv_rec("chr1", 100, "C", "A", "6,7:14,15:0,0:0,0")]
    plain = _write(tmp_path / "snv.vcf", _snv_header(), recs)
    gz = tmp_path / "snv.vcf.gz"
    with gzip.open(gz, "wt") as fh:
        fh.write(_snv_header() + "".join(recs))

    plain_vafs, _ = read_strelka_vafs(snv_path=plain)
    gz_vafs, _ = read_strelka_vafs(snv_path=gz)

    assert gz_vafs == plain_vafs
    assert gz_vafs == [pytest.approx(0.30)]


def test_median_none_when_empty(tmp_path):
    median, tumor_found = strelka_median_vaf()

    assert median is None
    assert tumor_found is False
