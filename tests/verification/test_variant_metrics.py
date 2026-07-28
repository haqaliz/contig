"""Deterministic germline variant metrics: ts_tv and het_hom (PRD C3, slice 1).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Mirrors the style of test_concordance.py (tiny inline VCFs).
"""

import gzip

from contig.verification.rule_pack import _status_for
from contig.verification.variant_metrics import (
    _rule_by_check,
    evaluate_variant_plausibility,
    variant_metrics,
)

_HEADER = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n"


def _vcf_line(chrom, pos, ref, alt, gt):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\tPASS\t.\tGT\t{gt}\n"


def _write_vcf(path, rows):
    """rows: list of (chrom, pos, ref, alt, gt)."""
    body = "".join(_vcf_line(*r) for r in rows)
    path.write_text(_HEADER + body)
    return path


def test_ts_tv_counts_transitions_over_transversions(tmp_path):
    # Two transitions (A>G, C>T) and one transversion (A>C) -> ratio 2.0.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # transition
        ("chr1", 200, "C", "T", "0/1"),  # transition
        ("chr1", 300, "A", "C", "0/1"),  # transversion
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    metrics = variant_metrics(vcf)

    assert metrics.ts_tv == 2.0


def test_ts_tv_ignores_indels_and_multiallelic(tmp_path):
    # Only the two SNVs (one transition, one transversion) count: ratio 1.0.
    # The indel rows and the multiallelic (comma in ALT) row are excluded.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # SNV transition (counts)
        ("chr1", 150, "A", "C", "0/1"),  # SNV transversion (counts)
        ("chr1", 200, "AT", "G", "0/1"),  # multi-base REF (indel, excluded)
        ("chr1", 250, "A", "GT", "0/1"),  # multi-base ALT (indel, excluded)
        ("chr1", 300, "A", "G,T", "1/2"),  # multiallelic ALT (excluded)
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    metrics = variant_metrics(vcf)

    assert metrics.ts_tv == 1.0


def test_ts_tv_none_when_no_transversions(tmp_path):
    # Only transitions present -> no divide-by-zero, ts_tv is None.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # transition
        ("chr1", 200, "C", "T", "0/1"),  # transition
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    metrics = variant_metrics(vcf)

    assert metrics.ts_tv is None


def test_het_hom_counts_genotypes(tmp_path):
    # Three het (0/1) and two hom-alt (1/1) -> ratio 1.5.
    # Hom-ref (0/0) and missing (./.) are excluded from both counts.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # het
        ("chr1", 200, "C", "T", "0/1"),  # het
        ("chr1", 300, "G", "A", "0/1"),  # het
        ("chr1", 400, "A", "C", "1/1"),  # hom-alt
        ("chr1", 500, "T", "G", "1/1"),  # hom-alt
        ("chr1", 600, "A", "G", "0/0"),  # hom-ref (excluded)
        ("chr1", 700, "C", "T", "./."),  # missing (excluded)
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    metrics = variant_metrics(vcf)

    assert metrics.het_hom == 1.5


def test_het_hom_multiallelic_genotype_is_het(tmp_path):
    # A multiallelic-site genotype like 1/2 has two differing alleles, so it is
    # counted as heterozygous (documented decision). One 1/2 het and one 1/1
    # hom-alt -> ratio 1.0.
    rows = [
        ("chr1", 100, "A", "G,T", "1/2"),  # het (alleles differ)
        ("chr1", 200, "C", "T", "1/1"),  # hom-alt
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    metrics = variant_metrics(vcf)

    assert metrics.het_hom == 1.0


def test_het_hom_none_when_no_hom_alt(tmp_path):
    # Only het genotypes -> no divide-by-zero, het_hom is None.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # het
        ("chr1", 200, "C", "T", "0/1"),  # het
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    metrics = variant_metrics(vcf)

    assert metrics.het_hom is None


def test_gzip_vcf_supported(tmp_path):
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # transition, het
        ("chr1", 200, "C", "T", "1/1"),  # transition, hom-alt
        ("chr1", 300, "A", "C", "0/1"),  # transversion, het
    ]
    plain = _write_vcf(tmp_path / "a.vcf", rows)
    gz = tmp_path / "a.vcf.gz"
    with gzip.open(gz, "wt") as fh:
        fh.write(_HEADER + "".join(_vcf_line(*r) for r in rows))

    plain_metrics = variant_metrics(plain)
    gz_metrics = variant_metrics(gz)

    assert gz_metrics == plain_metrics
    assert gz_metrics.ts_tv == 2.0
    assert gz_metrics.het_hom == 2.0


# --- variant_count metric (Phase 1): distinct primary-sample sites -------------


def test_variant_count_counts_distinct_sites(tmp_path):
    # Three distinct (CHROM,POS,REF,ALT) sites -> variant_count == 3.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),
        ("chr1", 200, "C", "T", "0/1"),
        ("chr1", 300, "A", "C", "1/1"),
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    metrics = variant_metrics(vcf)

    assert metrics.variant_count == 3


def test_variant_count_dedups_repeated_site(tmp_path):
    # A duplicated (CHROM,POS,REF,ALT) line counts once: len(parse_vcf()) semantics
    # (parse_vcf keys by site, so a repeated site key collapses to one).
    rows = [
        ("chr1", 100, "A", "G", "0/1"),
        ("chr1", 100, "A", "G", "0/1"),  # exact duplicate site -> counted once
        ("chr1", 200, "C", "T", "0/1"),
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    metrics = variant_metrics(vcf)

    assert metrics.variant_count == 2


def test_variant_count_gzip(tmp_path):
    rows = [
        ("chr1", 100, "A", "G", "0/1"),
        ("chr1", 200, "C", "T", "1/1"),
        ("chr1", 300, "A", "C", "0/1"),
    ]
    gz = tmp_path / "a.vcf.gz"
    with gzip.open(gz, "wt") as fh:
        fh.write(_HEADER + "".join(_vcf_line(*r) for r in rows))

    metrics = variant_metrics(gz)

    assert metrics.variant_count == 3


def test_variant_count_multisample_counts_sites(tmp_path):
    # A multi-sample VCF: variant_count is the number of distinct sites, not
    # per-sample. Two sites, each with two sample columns -> count 2.
    header = (
        "##fileformat=VCFv4.2\n"
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\tS2\n"
    )
    body = (
        "chr1\t100\t.\tA\tG\t.\tPASS\t.\tGT\t0/1\t1/1\n"
        "chr1\t200\t.\tC\tT\t.\tPASS\t.\tGT\t0/0\t0/1\n"
    )
    vcf = tmp_path / "multi.vcf"
    vcf.write_text(header + body)

    metrics = variant_metrics(vcf)

    assert metrics.variant_count == 2


def test_variant_count_empty_vcf_is_zero(tmp_path):
    # Header-only VCF (no records) -> variant_count == 0.
    vcf = tmp_path / "empty.vcf"
    vcf.write_text(_HEADER)

    metrics = variant_metrics(vcf)

    assert metrics.variant_count == 0


# --- plausibility evaluator (Phase 2): WARN-capped, explicit unverified --------


def test_plausibility_in_band_passes(tmp_path):
    # A ts_tv inside the band [1.8, 2.4] yields a PASS ts_tv_ratio check. Three
    # transitions to two transversions is 1.5, so build a clean ~2.0 instead:
    # four transitions (A>G, C>T, G>A, T>C) over two transversions (A>C, G>T) = 2.0.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # transition
        ("chr1", 200, "C", "T", "0/1"),  # transition
        ("chr1", 300, "G", "A", "0/1"),  # transition
        ("chr1", 400, "T", "C", "0/1"),  # transition
        ("chr1", 500, "A", "C", "1/1"),  # transversion, also a hom-alt
        ("chr1", 600, "G", "T", "0/1"),  # transversion
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    results = evaluate_variant_plausibility(vcf)

    ts_tv = [r for r in results if r.check == "ts_tv_ratio:sample"]
    assert len(ts_tv) == 1
    assert ts_tv[0].status == "pass"
    assert ts_tv[0].kind == "metric"
    assert ts_tv[0].value == 2.0


def test_plausibility_grossly_out_of_band_fails(tmp_path):
    # ts_tv grossly below the band (one transition over two transversions = 0.5)
    # is a broken call set and must FAIL: 0.5 < fail_below (1.2). The value and
    # expected range are still populated.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # transition
        ("chr1", 200, "A", "C", "1/1"),  # transversion, hom-alt
        ("chr1", 300, "G", "T", "0/1"),  # transversion
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    results = evaluate_variant_plausibility(vcf)

    ts_tv = [r for r in results if r.check == "ts_tv_ratio:sample"]
    assert len(ts_tv) == 1
    assert ts_tv[0].status == "fail"
    assert ts_tv[0].value == 0.5
    assert ts_tv[0].expected_range is not None


def test_plausibility_ts_tv_warn_band_still_warns(tmp_path):
    # A ts_tv between fail_below (1.2) and warn_below (1.8) must WARN, not FAIL:
    # three transitions to two transversions = 1.5. Proves the WARN band survives
    # and FAIL is strictly outside it.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # transition
        ("chr1", 200, "C", "T", "0/1"),  # transition
        ("chr1", 300, "G", "A", "0/1"),  # transition
        ("chr1", 400, "A", "C", "0/1"),  # transversion
        ("chr1", 500, "G", "T", "0/1"),  # transversion
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    results = evaluate_variant_plausibility(vcf)

    ts_tv = [r for r in results if r.check == "ts_tv_ratio:sample"]
    assert len(ts_tv) == 1
    assert ts_tv[0].status == "warn"
    assert ts_tv[0].value == 1.5


def test_plausibility_wes_ti_tv_not_fail(tmp_path):
    # A WES-level Ti/Tv (~3.3: 33 transitions to 10 transversions) is high but not
    # grossly implausible, so it must NOT FAIL (WES-safe bands, G2). It rides as a
    # WARN above warn_above (2.4) but below fail_above (3.6).
    rows = [("chr1", 1000 + i, "A", "G", "0/1") for i in range(33)]  # transitions
    rows += [("chr2", 1000 + i, "A", "C", "0/1") for i in range(10)]  # transversions
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    results = evaluate_variant_plausibility(vcf)

    ts_tv = [r for r in results if r.check == "ts_tv_ratio:sample"]
    assert len(ts_tv) == 1
    assert ts_tv[0].status != "fail"
    assert ts_tv[0].value == 3.3


def test_het_hom_grossly_out_of_band_fails(tmp_path):
    # het/hom grossly below the band (fail_below 1.0) is a broken genotype balance
    # and must FAIL: one het (0/1) over two hom-alt (1/1) = 0.5.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # het
        ("chr1", 200, "C", "T", "1/1"),  # hom-alt
        ("chr1", 300, "G", "A", "1/1"),  # hom-alt
    ]
    vcf = _write_vcf(tmp_path / "fail.vcf", rows)

    results = evaluate_variant_plausibility(vcf)
    het_hom = next(r for r in results if r.check == "het_hom_ratio:sample")
    assert het_hom.value == 0.5
    assert het_hom.status == "fail"

    # A normal het/hom (~1.5: three het over two hom-alt) is inside the band, so it
    # must NOT FAIL.
    normal_rows = [
        ("chr1", 100, "A", "G", "0/1"),  # het
        ("chr1", 200, "C", "T", "0/1"),  # het
        ("chr1", 300, "G", "A", "0/1"),  # het
        ("chr1", 400, "A", "C", "1/1"),  # hom-alt
        ("chr1", 500, "T", "G", "1/1"),  # hom-alt
    ]
    normal_vcf = _write_vcf(tmp_path / "normal.vcf", normal_rows)
    normal_results = evaluate_variant_plausibility(normal_vcf)
    normal_het_hom = next(
        r for r in normal_results if r.check == "het_hom_ratio:sample"
    )
    assert normal_het_hom.value == 1.5
    assert normal_het_hom.status != "fail"


def test_plausibility_uncomputable_is_unverified(tmp_path):
    # No transversion -> ts_tv is None -> ts_tv_ratio is unverified (not skipped,
    # not pass). No homozygous-alt -> het_hom is None -> het_hom_ratio unverified.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # transition, het
        ("chr1", 200, "C", "T", "0/1"),  # transition, het
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    results = evaluate_variant_plausibility(vcf)
    by_check = {r.check: r for r in results}

    assert by_check["ts_tv_ratio:sample"].status == "unverified"
    assert by_check["ts_tv_ratio:sample"].kind == "metric"
    assert by_check["ts_tv_ratio:sample"].value is None
    assert by_check["het_hom_ratio:sample"].status == "unverified"
    assert by_check["het_hom_ratio:sample"].kind == "metric"
    assert by_check["het_hom_ratio:sample"].value is None


# --- variant_count band (Phase 2): WARN-capped, never unverified ---------------


def _n_distinct_sites(n):
    """n distinct het SNV rows at increasing positions (all A>G transitions)."""
    return [("chr1", 100 + i, "A", "G", "0/1") for i in range(n)]


def test_variant_count_in_band_passes(tmp_path):
    # A normal count (12 distinct sites) is inside [10, 20000000] -> PASS, with
    # the two-sided expected_range rendered.
    vcf = _write_vcf(tmp_path / "a.vcf", _n_distinct_sites(12))

    results = evaluate_variant_plausibility(vcf)

    count = [r for r in results if r.check == "variant_count:sample"]
    assert len(count) == 1
    assert count[0].status == "pass"
    assert count[0].kind == "metric"
    assert count[0].value == 12
    assert count[0].expected_range == "[10, 20000000]"


def test_variant_count_below_band_warns(tmp_path):
    # 2 distinct sites is below warn_below (10) -> WARN, never FAIL.
    vcf = _write_vcf(tmp_path / "a.vcf", _n_distinct_sites(2))

    results = evaluate_variant_plausibility(vcf)

    count = [r for r in results if r.check == "variant_count:sample"]
    assert len(count) == 1
    assert count[0].status == "warn"
    assert count[0].status != "fail"
    assert count[0].value == 2


def test_variant_count_zero_fails_not_unverified(tmp_path):
    # Header-only VCF -> variant_count == 0 -> FAIL (0 < fail_below 1). Critically
    # it is NOT unverified: a real 0 must not route into the ts_tv/het_hom
    # unverified branch (PRD R4). The count metric is always computable.
    vcf = tmp_path / "empty.vcf"
    vcf.write_text(_HEADER)

    results = evaluate_variant_plausibility(vcf)
    by_check = {r.check: r for r in results}

    assert by_check["variant_count:sample"].status == "fail"
    assert by_check["variant_count:sample"].status != "unverified"
    assert by_check["variant_count:sample"].value == 0


def test_empty_vcf_verdict_is_fail(tmp_path):
    # PRD R7: a header-only VCF has variant_count 0 (FAIL, below fail_below 1)
    # while ts_tv/het_hom are UNVERIFIED (no records to compute). The combined
    # verdict must reduce to FAIL — an empty call set is a hard failure, not an
    # easy-to-miss WARN.
    from contig.models import overall_verdict

    vcf = tmp_path / "empty.vcf"
    vcf.write_text(_HEADER)

    results = evaluate_variant_plausibility(vcf)
    by_check = {r.check: r for r in results}

    assert by_check["variant_count:sample"].status == "fail"
    assert by_check["ts_tv_ratio:sample"].status == "unverified"
    assert by_check["het_hom_ratio:sample"].status == "unverified"
    assert overall_verdict(results) == "fail"


def test_variant_count_above_band_warns_via_rule(tmp_path):
    # The upper tripwire fires above warn_above (20_000_000) without building a
    # 20M-record VCF: exercise the band directly at the rule level.
    rule = _rule_by_check("variant_count")
    assert _status_for(20_000_001, rule) == "warn"
    assert _status_for(5000, rule) == "pass"


def test_variant_count_check_key_and_grouping(tmp_path):
    # The count result's check key is exactly variant_count:sample, .value is the
    # int count, and it sits alongside the ts_tv_ratio / het_hom_ratio rows.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # transition, het
        ("chr1", 200, "C", "T", "0/1"),  # transition, het
        ("chr1", 300, "G", "A", "0/1"),  # transition, het
        ("chr1", 400, "T", "C", "0/1"),  # transition, het
        ("chr1", 500, "A", "C", "1/1"),  # transversion, hom-alt
        ("chr1", 600, "G", "T", "0/1"),  # transversion, het
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    results = evaluate_variant_plausibility(vcf)
    checks = {r.check for r in results}

    assert "variant_count:sample" in checks
    assert "ts_tv_ratio:sample" in checks
    assert "het_hom_ratio:sample" in checks
    count = next(r for r in results if r.check == "variant_count:sample")
    assert count.value == 6
