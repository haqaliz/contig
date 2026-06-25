"""Deterministic germline variant metrics: ts_tv and het_hom (PRD C3, slice 1).

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Mirrors the style of test_concordance.py (tiny inline VCFs).
"""

import gzip

from contig.verification.variant_metrics import (
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


def test_plausibility_out_of_band_warns_never_fails(tmp_path):
    # ts_tv far below the band (one transition over two transversions = 0.5) must
    # WARN, never FAIL (the germline rules are WARN-capped in this slice). The
    # value and expected range are populated.
    rows = [
        ("chr1", 100, "A", "G", "0/1"),  # transition
        ("chr1", 200, "A", "C", "1/1"),  # transversion, hom-alt
        ("chr1", 300, "G", "T", "0/1"),  # transversion
    ]
    vcf = _write_vcf(tmp_path / "a.vcf", rows)

    results = evaluate_variant_plausibility(vcf)

    ts_tv = [r for r in results if r.check == "ts_tv_ratio:sample"]
    assert len(ts_tv) == 1
    assert ts_tv[0].status == "warn"
    assert ts_tv[0].status != "fail"
    assert ts_tv[0].value == 0.5
    assert ts_tv[0].expected_range is not None


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
