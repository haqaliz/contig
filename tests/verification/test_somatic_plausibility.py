"""Deterministic somatic VAF plausibility metrics from a tumor-normal VCF.

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Mirrors the style of test_variant_metrics.py (tiny inline two-sample VCFs with a
``##tumor_sample=`` header so tumor identification is by name, not by position).
"""

import gzip

import pytest

from contig.verification.somatic_plausibility import somatic_metrics

_TUMOR = "TUMOR"
_NORMAL = "NORMAL"


def _header(tumor=_TUMOR, normal=_NORMAL, tumor_line=True, extra=()):
    lines = ["##fileformat=VCFv4.2"]
    if tumor_line:
        lines.append(f"##tumor_sample={tumor}")
    lines.extend(extra)
    # column order: NORMAL then TUMOR, to prove we select by name not position
    lines.append(
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t"
        f"{normal}\t{tumor}"
    )
    return "\n".join(lines) + "\n"


def _rec(chrom, pos, ref, alt, tumor_fmt, normal_fmt="0/0:0.0:10,0:10", fmt="GT:AF:AD:DP"):
    # tumor_fmt like "0/1:0.30:14,6:20"; column order NORMAL then TUMOR
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\t{fmt}\t{normal_fmt}\t{tumor_fmt}\n"


def _write(path, header, recs):
    path.write_text(header + "".join(recs))
    return path


# --- Phase 1: tumor-aware VAF parsing + metrics --------------------------------


def test_median_vaf_from_af(tmp_path):
    # Two records; tumor AF 0.20 and 0.40 -> even count -> mean of the two middles
    # = 0.30. NORMAL AF is 0.0, so a correct read of the TUMOR column (not the
    # position-0 NORMAL) is required to get 0.30.
    recs = [
        _rec("chr1", 100, "A", "G", "0/1:0.20:16,4:20"),
        _rec("chr1", 200, "C", "T", "0/1:0.40:12,8:20"),
    ]
    vcf = _write(tmp_path / "a.vcf", _header(), recs)

    m = somatic_metrics(vcf)

    assert m.median_vaf == pytest.approx(0.30)
    assert m.variant_count == 2


def test_vaf_ad_dp_fallback_when_no_af(tmp_path):
    # No AF in FORMAT; tumor AD=14,6 DP=20 -> VAF = 6/20 = 0.30.
    recs = [
        _rec(
            "chr1", 100, "A", "G", "0/1:14,6:20",
            normal_fmt="0/0:10,0:10", fmt="GT:AD:DP",
        ),
    ]
    vcf = _write(tmp_path / "a.vcf", _header(), recs)

    m = somatic_metrics(vcf)

    assert m.median_vaf == pytest.approx(0.30)
    assert m.variant_count == 1


def test_af_preferred_over_ad_dp(tmp_path):
    # Both present: AF=0.25, while AD/DP (10,10 / 20) would give 0.50. AF wins.
    recs = [
        _rec("chr1", 100, "A", "G", "0/1:0.25:10,10:20"),
    ]
    vcf = _write(tmp_path / "a.vcf", _header(), recs)

    m = somatic_metrics(vcf)

    assert m.median_vaf == 0.25


def test_multiallelic_excluded(tmp_path):
    # A>G,T (comma in ALT) is excluded from the VAF list and from variant_count.
    # The sibling biallelic record still counts.
    recs = [
        _rec("chr1", 100, "A", "G,T", "0/1:0.30,0.10:10,6,4:20"),  # excluded
        _rec("chr1", 200, "C", "T", "0/1:0.40:12,8:20"),  # counts
    ]
    vcf = _write(tmp_path / "a.vcf", _header(), recs)

    m = somatic_metrics(vcf)

    assert m.median_vaf == 0.40
    assert m.variant_count == 1


def test_indel_included(tmp_path):
    # AT>A biallelic indel with a tumor AF contributes a VAF.
    recs = [
        _rec("chr1", 100, "AT", "A", "0/1:0.35:13,7:20"),
    ]
    vcf = _write(tmp_path / "a.vcf", _header(), recs)

    m = somatic_metrics(vcf)

    assert m.median_vaf == 0.35
    assert m.variant_count == 1


def test_dp_zero_guarded(tmp_path):
    # GT:AD:DP tumor 0/1:0,0:0 -> DP==0, no AF -> contributes no VAF (no divide by
    # zero). It is the only record, so median_vaf is None. The record is still a
    # considered biallelic record for the count.
    recs = [
        _rec(
            "chr1", 100, "A", "G", "0/1:0,0:0",
            normal_fmt="0/0:10,0:10", fmt="GT:AD:DP",
        ),
    ]
    vcf = _write(tmp_path / "a.vcf", _header(), recs)

    m = somatic_metrics(vcf)

    assert m.median_vaf is None
    assert m.variant_count == 1


def test_median_vaf_none_when_no_vaf(tmp_path):
    # A record whose tumor has neither AF nor usable AD/DP -> no VAF derivable.
    recs = [
        _rec(
            "chr1", 100, "A", "G", "0/1",
            normal_fmt="0/0", fmt="GT",
        ),
    ]
    vcf = _write(tmp_path / "a.vcf", _header(), recs)

    m = somatic_metrics(vcf)

    assert m.median_vaf is None
    assert m.variant_count == 1


def test_missing_tumor_header_yields_no_vafs(tmp_path):
    # No ##tumor_sample= header -> tumor column unidentifiable -> never read a
    # guessed column -> median_vaf is None.
    recs = [
        _rec("chr1", 100, "A", "G", "0/1:0.30:14,6:20"),
    ]
    vcf = _write(tmp_path / "a.vcf", _header(tumor_line=False), recs)

    m = somatic_metrics(vcf)

    assert m.median_vaf is None


def test_gzip_supported(tmp_path):
    recs = [
        _rec("chr1", 100, "A", "G", "0/1:0.20:16,4:20"),
        _rec("chr1", 200, "C", "T", "0/1:0.40:12,8:20"),
    ]
    plain = _write(tmp_path / "a.vcf", _header(), recs)
    gz = tmp_path / "a.vcf.gz"
    with gzip.open(gz, "wt") as fh:
        fh.write(_header() + "".join(recs))

    plain_m = somatic_metrics(plain)
    gz_m = somatic_metrics(gz)

    assert gz_m == plain_m
    assert gz_m.median_vaf == pytest.approx(0.30)
