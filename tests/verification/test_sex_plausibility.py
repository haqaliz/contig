"""Germline karyotypic-sex plausibility from a VCF (PRD germline-sex-check-plausibility).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Mirrors the style of test_variant_metrics.py (tiny inline VCFs via _HEADER /
_vcf_line / _write_vcf).
"""

from contig.verification.concordance import parse_vcf
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
    _x_signals,
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


# --- Phase 2: X-heterozygosity with PAR masking ---------------------------------


def _xhet(vcf):
    sites = parse_vcf(vcf)
    build = _detect_build(vcf)
    return _x_signals(sites, build)


def test_xhet_female_pattern_reads_high_ratio(tmp_path):
    # 24 het + 6 hom (hom-ref/hom-alt) non-PAR chrX sites, positions safely
    # outside GRCh38 PAR -> ratio 24/30 = 0.8, well above X_HET_HIGH.
    rows = [("chrX", 3_000_000 + i, "A", "G", "0/1") for i in range(24)]
    rows += [("chrX", 4_000_000 + i, "A", "G", "0/0") for i in range(3)]
    rows += [("chrX", 5_000_000 + i, "A", "G", "1/1") for i in range(3)]
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    ratio, x_sites = _xhet(vcf)

    assert x_sites == 30
    assert ratio == 0.8
    assert ratio >= X_HET_HIGH


def test_xhet_male_pattern_reads_low_ratio(tmp_path):
    # 2 het + 28 hom non-PAR chrX sites -> ratio 2/30 ~ 0.0667, at/below X_HET_LOW.
    rows = [("chrX", 3_000_000 + i, "A", "G", "0/1") for i in range(2)]
    rows += [("chrX", 4_000_000 + i, "A", "G", "0/0") for i in range(28)]
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    ratio, x_sites = _xhet(vcf)

    assert x_sites == 30
    assert round(ratio, 4) == round(2 / 30, 4)
    assert ratio <= X_HET_LOW


def test_xhet_par_sites_excluded_from_denominator(tmp_path):
    # Load-bearing masking test: the ONLY het chrX sites sit inside GRCh38 PAR1
    # (10,001-2,781,479); 25 non-PAR sites are all hom. If PAR masking were
    # broken, the 5 PAR-het sites would leak into the denominator and produce a
    # mid-band (discordant) ratio (5/30 ~= 0.167) instead of a clean male read.
    rows = [("chrX", 20_000 + i, "A", "G", "0/1") for i in range(5)]  # PAR1, het
    rows += [("chrX", 5_000_000 + i, "A", "G", "0/0") for i in range(25)]  # non-PAR, hom
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    ratio, x_sites = _xhet(vcf)

    assert x_sites == 25
    assert ratio == 0.0
    assert ratio <= X_HET_LOW


def test_xhet_none_when_fewer_than_min_sites(tmp_path):
    rows = [("chrX", 5_000_000 + i, "A", "G", "0/1") for i in range(10)]
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    ratio, x_sites = _xhet(vcf)

    assert x_sites == 10
    assert ratio is None


def test_xhet_none_and_zero_sites_when_no_chrx_contig(tmp_path):
    rows = [("chr1", 1000 + i, "A", "G", "0/1") for i in range(30)]
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    ratio, x_sites = _xhet(vcf)

    assert x_sites == 0
    assert ratio is None
