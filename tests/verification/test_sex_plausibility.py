"""Germline karyotypic-sex plausibility from a VCF (PRD germline-sex-check-plausibility).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Mirrors the style of test_variant_metrics.py (tiny inline VCFs via _HEADER /
_vcf_line / _write_vcf).
"""

import gzip

import pytest

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
    _y_count,
    evaluate_sex_plausibility,
    sex_signals,
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


# --- Phase 3: Y presence + sex_signals assembly + inferred_sex ------------------


def _male_x_rows():
    rows = [("chrX", 3_000_000 + i, "A", "G", "0/1") for i in range(2)]
    rows += [("chrX", 4_000_000 + i, "A", "G", "0/0") for i in range(28)]
    return rows


def _female_x_rows():
    rows = [("chrX", 3_000_000 + i, "A", "G", "0/1") for i in range(24)]
    rows += [("chrX", 4_000_000 + i, "A", "G", "0/0") for i in range(3)]
    rows += [("chrX", 5_000_000 + i, "A", "G", "1/1") for i in range(3)]
    return rows


def _midband_x_rows():
    # 5 het over 30 total -> ratio 0.1667, strictly between X_HET_LOW and
    # X_HET_HIGH: implausible for either karyotype.
    rows = [("chrX", 3_000_000 + i, "A", "G", "0/1") for i in range(5)]
    rows += [("chrX", 4_000_000 + i, "A", "G", "0/0") for i in range(25)]
    return rows


def _y_rows(n, chrom="chrY", start=10_000_000):
    return [(chrom, start + i, "A", "G", "0/1") for i in range(n)]


def test_ycount_counts_nonpar_y_sites(tmp_path):
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, _y_rows(7))
    sites = parse_vcf(vcf)
    build = _detect_build(vcf)

    assert _y_count(sites, build) == 7


def test_ycount_excludes_par_y_sites(tmp_path):
    # 3 sites inside GRCh38 chrY PAR1 (10,001-2,781,479) + 5 non-PAR sites.
    rows = [("chrY", 20_000 + i, "A", "G", "0/1") for i in range(3)]
    rows += _y_rows(5)
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)
    sites = parse_vcf(vcf)
    build = _detect_build(vcf)

    assert _y_count(sites, build) == 5


def test_ycount_recognizes_bare_y_grch37(tmp_path):
    # GRCh37's chrY PAR1 (10,001-2,649,520) does NOT share chrX's PAR1 bounds;
    # use a position clearly outside both chrY PARs.
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH37, _y_rows(6, chrom="Y", start=20_000_000))
    sites = parse_vcf(vcf)
    build = _detect_build(vcf)

    assert build == "GRCh37"
    assert _y_count(sites, build) == 6


def test_sex_signals_male_pattern_is_xy(tmp_path):
    rows = _male_x_rows() + _y_rows(6)
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    signals = sex_signals(vcf)

    assert signals.inferred_sex == "XY"
    assert signals.x_het_ratio <= X_HET_LOW
    assert signals.y_variant_count == 6
    assert signals.reference_build == "GRCh38"
    assert signals.par_masked is True


def test_sex_signals_female_pattern_no_y_is_xx(tmp_path):
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, _female_x_rows())

    signals = sex_signals(vcf)

    assert signals.inferred_sex == "XX"
    assert signals.x_het_ratio >= X_HET_HIGH
    assert signals.y_variant_count == 0


def test_sex_signals_autosomal_x_het_with_y_is_discordant(tmp_path):
    rows = _female_x_rows() + _y_rows(6)
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    signals = sex_signals(vcf)

    assert signals.inferred_sex == "discordant"
    assert signals.x_het_ratio >= X_HET_HIGH
    assert signals.y_variant_count >= Y_PRESENT_FLOOR


def test_sex_signals_midband_xhet_is_discordant(tmp_path):
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, _midband_x_rows())

    signals = sex_signals(vcf)

    assert signals.inferred_sex == "discordant"
    assert X_HET_LOW < signals.x_het_ratio < X_HET_HIGH


def test_sex_signals_too_few_x_sites_is_indeterminate(tmp_path):
    rows = [("chrX", 5_000_000 + i, "A", "G", "0/1") for i in range(10)]
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    signals = sex_signals(vcf)

    assert signals.inferred_sex == "indeterminate"
    assert signals.x_het_ratio is None


def test_sex_signals_female_pattern_y_absence_never_forces_discordant(tmp_path):
    # Female-pattern X-het with zero chrY calls: Y-absence is uninformative (a
    # Y-less reference and a female sample look identical from the VCF alone),
    # so this must read XX, never discordant.
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, _female_x_rows())

    signals = sex_signals(vcf)

    assert signals.inferred_sex == "XX"


@pytest.mark.parametrize("x_chrom,y_chrom", [("chrX", "chrY"), ("X", "Y")])
def test_sex_signals_recognizes_chr_prefixed_and_bare_contigs(tmp_path, x_chrom, y_chrom):
    rows = [(x_chrom, 3_000_000 + i, "A", "G", "0/1") for i in range(2)]
    rows += [(x_chrom, 4_000_000 + i, "A", "G", "0/0") for i in range(28)]
    rows += [(y_chrom, 10_000_000 + i, "A", "G", "0/1") for i in range(6)]
    header = _HEADER_GRCH38 if x_chrom == "chrX" else _HEADER_GRCH37
    vcf = _write_vcf(tmp_path / "a.vcf", header, rows)

    signals = sex_signals(vcf)

    assert signals.inferred_sex == "XY"
    assert signals.y_variant_count == 6


# --- Phase 4: evaluate_sex_plausibility (WARN-capped, UNVERIFIED-when-weak) -----


def _by_check(results):
    return {r.check: r for r in results}


def test_evaluate_male_pattern_passes_xy(tmp_path):
    rows = _male_x_rows() + _y_rows(6)
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    results = evaluate_sex_plausibility(vcf, sample="s1")
    by_check = _by_check(results)

    sex = by_check["sex_plausibility:s1"]
    assert sex.status == "pass"
    assert sex.status != "fail"
    assert sex.kind == "metric"
    assert "XY" in sex.message

    xhet = by_check["x_het_ratio:s1"]
    assert xhet.status == "pass"
    assert xhet.kind == "metric"
    assert xhet.value == sex_signals(vcf).x_het_ratio
    assert "informational" in xhet.message.lower()


def test_evaluate_female_pattern_passes_xx(tmp_path):
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, _female_x_rows())

    results = evaluate_sex_plausibility(vcf, sample="s1")
    by_check = _by_check(results)

    sex = by_check["sex_plausibility:s1"]
    assert sex.status == "pass"
    assert "XX" in sex.message


def test_evaluate_discordant_warns_never_fails(tmp_path):
    rows = _female_x_rows() + _y_rows(6)
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    results = evaluate_sex_plausibility(vcf, sample="s1")
    by_check = _by_check(results)

    sex = by_check["sex_plausibility:s1"]
    assert sex.status == "warn"
    assert sex.status != "fail"
    assert "aneuploidy" in sex.message or "contamination" in sex.message or "sample swap" in sex.message


def test_evaluate_indeterminate_is_unverified_with_none_value(tmp_path):
    rows = [("chrX", 5_000_000 + i, "A", "G", "0/1") for i in range(10)]
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)

    results = evaluate_sex_plausibility(vcf, sample="s1")
    by_check = _by_check(results)

    sex = by_check["sex_plausibility:s1"]
    assert sex.status == "unverified"
    assert sex.value is None
    assert sex.status != "fail"

    xhet = by_check["x_het_ratio:s1"]
    assert xhet.status == "pass"  # informational-always-PASS convention
    assert xhet.value is None


def test_evaluate_gzip_matches_plain(tmp_path):
    rows = _male_x_rows() + _y_rows(6)
    plain = _write_vcf(tmp_path / "a.vcf", _HEADER_GRCH38, rows)
    gz = tmp_path / "a.vcf.gz"
    body = "".join(_vcf_line(*r) for r in rows)
    with gzip.open(gz, "wt") as fh:
        fh.write(_HEADER_GRCH38 + body)

    plain_results = evaluate_sex_plausibility(plain, sample="s1")
    gz_results = evaluate_sex_plausibility(gz, sample="s1")

    assert plain_results == gz_results


def test_evaluate_build_undetermined_falls_back_unmasked_still_warn_capped(tmp_path):
    # No ##contig header at all -> build undetermined, unmasked X-het, still
    # WARN-capped. Include a PAR-range het block that WOULD flip the read if
    # masking were silently assumed; unmasked, it correctly counts toward het.
    rows = [("chrX", 20_000 + i, "A", "G", "0/1") for i in range(24)]  # would be PAR1 if masked
    rows += [("chrX", 4_000_000 + i, "A", "G", "0/0") for i in range(6)]
    vcf = _write_vcf(tmp_path / "a.vcf", _HEADER_NO_CONTIG, rows)

    signals = sex_signals(vcf)
    assert signals.par_masked is False
    assert signals.reference_build is None

    results = evaluate_sex_plausibility(vcf, sample="s1")
    by_check = _by_check(results)
    assert by_check["sex_plausibility:s1"].status in ("pass", "warn", "unverified")
    assert by_check["sex_plausibility:s1"].status != "fail"
