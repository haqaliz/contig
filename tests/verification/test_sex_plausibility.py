"""Germline karyotypic-sex plausibility from a VCF (PRD germline-sex-check-plausibility).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Mirrors the style of test_variant_metrics.py (tiny inline VCFs via _HEADER /
_vcf_line / _write_vcf).
"""

from contig.verification.rule_pack import (
    MIN_X_SITES,
    X_HET_HIGH,
    X_HET_LOW,
    Y_PRESENT_FLOOR,
)
from contig.verification.sex_plausibility import (
    _CHRX_LENGTH_GRCH37,
    _CHRX_LENGTH_GRCH38,
    _detect_build,
)

# ##contig lines included so build detection (##contig=<ID=...X,length=L>) is
# exercised; POS is 1-based, matching parse_vcf's verbatim string handling.
_HEADER_GRCH38 = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chr1,length=248956422>\n"
    "##contig=<ID=chrX,length=156040895>\n"
    "##contig=<ID=chrY,length=57227415>\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
)
_HEADER_GRCH37 = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=1,length=249250621>\n"
    "##contig=<ID=X,length=155270560>\n"
    "##contig=<ID=Y,length=59373566>\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
)
_HEADER_NO_CONTIG = (
    "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
)
_HEADER_UNKNOWN_LENGTH = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chrX,length=999999999>\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"
)


def _vcf_line(chrom, pos, ref, alt, gt):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\tGT\t{gt}\n"


def _write_vcf(path, header, rows):
    """rows: list of (chrom, pos, ref, alt, gt)."""
    body = "".join(_vcf_line(*r) for r in rows)
    path.write_text(header + body)
    return path


# --- Phase 1: thresholds + PAR tables + build detection ------------------------


def test_pinned_thresholds():
    assert X_HET_LOW == 0.10
    assert X_HET_HIGH == 0.20
    assert MIN_X_SITES == 20
    assert Y_PRESENT_FLOOR == 5


def test_pinned_chrx_lengths():
    assert _CHRX_LENGTH_GRCH37 == 155_270_560
    assert _CHRX_LENGTH_GRCH38 == 156_040_895


def test_detect_build_grch38_chrx(tmp_path):
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, [])
    assert _detect_build(vcf) == "GRCh38"


def test_detect_build_grch37_bare_x(tmp_path):
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH37, [])
    assert _detect_build(vcf) == "GRCh37"


def test_detect_build_none_when_no_contig_header(tmp_path):
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_NO_CONTIG, [])
    assert _detect_build(vcf) is None


def test_detect_build_none_when_unrecognized_length(tmp_path):
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_UNKNOWN_LENGTH, [])
    assert _detect_build(vcf) is None
