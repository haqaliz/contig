"""Deterministic somatic VAF plausibility metrics from a tumor-normal VCF.

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Mirrors the style of test_variant_metrics.py (tiny inline two-sample VCFs with a
``##tumor_sample=`` header so tumor identification is by name, not by position).
"""

import gzip

import pytest

from contig.verification.somatic_plausibility import (
    evaluate_somatic_plausibility,
    somatic_metrics,
)

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


# --- Phase 2: WARN-capped rule pack + plausibility evaluator --------------------


def _recs_with_af(af, n, start_pos=100):
    """n biallelic records, each tumor AF == af (deterministic median == af)."""
    return [
        _rec("chr1", start_pos + i, "A", "G", f"0/1:{af}:14,6:20")
        for i in range(n)
    ]


def test_median_vaf_in_band_passes(tmp_path):
    # median 0.30 is inside the band [0.05, 0.95] -> one median_vaf:TUMOR check
    # with status pass, kind metric, value 0.30.
    vcf = _write(tmp_path / "a.vcf", _header(), _recs_with_af(0.30, 12))

    results = evaluate_somatic_plausibility(vcf)

    mv = [r for r in results if r.check == "median_vaf:TUMOR"]
    assert len(mv) == 1
    assert mv[0].status == "pass"
    assert mv[0].kind == "metric"
    assert mv[0].value == pytest.approx(0.30)


def test_median_vaf_out_of_band_warns_never_fails(tmp_path):
    # All tumor AF ~= 0.99 -> median above the band -> WARN, never FAIL (WARN-cap).
    vcf = _write(tmp_path / "a.vcf", _header(), _recs_with_af(0.99, 12))

    results = evaluate_somatic_plausibility(vcf)

    mv = [r for r in results if r.check == "median_vaf:TUMOR"]
    assert len(mv) == 1
    assert mv[0].status == "warn"
    assert mv[0].status != "fail"
    assert mv[0].expected_range is not None


def test_median_vaf_uncomputable_is_unverified(tmp_path):
    # No VAF derivable (FORMAT GT only) -> median_vaf:TUMOR is unverified (not
    # skipped, not pass), value None, kind metric.
    recs = [_rec("chr1", 100, "A", "G", "0/1", normal_fmt="0/0", fmt="GT")]
    vcf = _write(tmp_path / "a.vcf", _header(), recs)

    results = evaluate_somatic_plausibility(vcf)
    by_check = {r.check: r for r in results}

    assert by_check["median_vaf:TUMOR"].status == "unverified"
    assert by_check["median_vaf:TUMOR"].value is None
    assert by_check["median_vaf:TUMOR"].kind == "metric"


def test_variant_count_in_band_passes(tmp_path):
    # 12 considered records is inside the count band [10, 100000] -> pass.
    vcf = _write(tmp_path / "a.vcf", _header(), _recs_with_af(0.30, 12))

    results = evaluate_somatic_plausibility(vcf)

    vc = [r for r in results if r.check == "somatic_variant_count:TUMOR"]
    assert len(vc) == 1
    assert vc[0].status == "pass"
    assert vc[0].value == 12


def test_variant_count_out_of_band_warns(tmp_path):
    # 2 considered records is below the warn floor (10) but at or above the fail
    # floor (1) -> WARN.
    vcf = _write(tmp_path / "a.vcf", _header(), _recs_with_af(0.30, 2))

    results = evaluate_somatic_plausibility(vcf)

    vc = [r for r in results if r.check == "somatic_variant_count:TUMOR"]
    assert len(vc) == 1
    assert vc[0].status == "warn"
    assert vc[0].status != "fail"


def test_empty_somatic_vcf_count_fails(tmp_path):
    # PRD AC1-AC3: a header-only VCF has somatic_variant_count 0, which is below
    # fail_below (1) -> FAIL, while median_vaf is uncomputable -> UNVERIFIED. A
    # single FAIL dominates the reduction (models.py overall_verdict), so the
    # combined verdict is FAIL.
    from contig.models import overall_verdict

    vcf = _write(tmp_path / "empty.vcf", _header(), [])

    results = evaluate_somatic_plausibility(vcf)
    by_check = {r.check: r for r in results}

    assert by_check["somatic_variant_count:TUMOR"].status == "fail"
    assert by_check["somatic_variant_count:TUMOR"].value == 0
    # AC2: a real 0 must not be misread as "couldn't compute". This assert looks
    # redundant next to == "fail" and is deliberate: it names the failure mode,
    # mirroring test_variant_metrics.py::test_variant_count_zero_fails_not_unverified.
    assert by_check["somatic_variant_count:TUMOR"].status != "unverified"
    assert by_check["median_vaf:TUMOR"].status == "unverified"
    assert overall_verdict(results) == "fail"


def test_sample_label_is_tumor_name(tmp_path):
    # The sample label is the header tumor name; the check is "median_vaf:TUMOR".
    vcf = _write(tmp_path / "a.vcf", _header(), _recs_with_af(0.30, 12))

    results = evaluate_somatic_plausibility(vcf)

    assert any(r.check == "median_vaf:TUMOR" for r in results)


def test_sample_label_falls_back_when_unidentifiable(tmp_path):
    # No ##tumor_sample= header -> tumor unidentifiable -> label "sample".
    recs = [_rec("chr1", 100, "A", "G", "0/1:0.30:14,6:20")]
    vcf = _write(tmp_path / "a.vcf", _header(tumor_line=False), recs)

    results = evaluate_somatic_plausibility(vcf)

    assert any(r.check == "median_vaf:sample" for r in results)


# --- Phase 3: panel-of-normals presence check (header scan) --------------------

_GATK_PON = (
    '##GATKCommandLine=<ID=Mutect2,CommandLine="Mutect2 --panel-of-normals '
    'pon.vcf.gz --input tumor.bam">'
)
_GATK_NO_PON = (
    '##GATKCommandLine=<ID=Mutect2,CommandLine="Mutect2 --input tumor.bam">'
)
_GATK_SHORT_PON = (
    '##GATKCommandLine=<ID=Mutect2,CommandLine="Mutect2 --pon pon.vcf.gz '
    '--input tumor.bam">'
)


def _pon_check(results):
    matches = [r for r in results if r.check == "pon_applied"]
    assert len(matches) == 1
    return matches[0]


def test_pon_present_passes(tmp_path):
    header = _header(extra=[_GATK_PON])
    vcf = _write(tmp_path / "a.vcf", header, _recs_with_af(0.30, 12))

    results = evaluate_somatic_plausibility(vcf)

    assert _pon_check(results).status == "pass"


def test_pon_absent_warns(tmp_path):
    header = _header(extra=[_GATK_NO_PON])
    vcf = _write(tmp_path / "a.vcf", header, _recs_with_af(0.30, 12))

    results = evaluate_somatic_plausibility(vcf)

    assert _pon_check(results).status == "warn"


def test_pon_no_gatk_header_unverified(tmp_path):
    # No ##GATKCommandLine line at all -> cannot tell -> unverified, value None.
    vcf = _write(tmp_path / "a.vcf", _header(), _recs_with_af(0.30, 12))

    results = evaluate_somatic_plausibility(vcf)

    pon = _pon_check(results)
    assert pon.status == "unverified"
    assert pon.value is None


def test_pon_short_flag_recognized(tmp_path):
    header = _header(extra=[_GATK_SHORT_PON])
    vcf = _write(tmp_path / "a.vcf", header, _recs_with_af(0.30, 12))

    results = evaluate_somatic_plausibility(vcf)

    assert _pon_check(results).status == "pass"
