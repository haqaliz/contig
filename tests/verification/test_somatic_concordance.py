"""Deterministic somatic PASS-site-overlap concordance metric (PRD C4 follow-on).

Phase 1 only: the pure module (`parse_pass_sites`, `read_caller_sites`,
`evaluate_somatic_concordance`). Real files only, via pytest tmp_path; no mocks,
no tool execution, no network.
"""

import gzip

from contig.verification.somatic_concordance import (
    evaluate_somatic_concordance,
    parse_pass_sites,
    read_caller_sites,
)

_HEADER = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"


def _rec(chrom, pos, ref, alt, filt="PASS"):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\t{filt}\t.\n"


def _write_vcf(path, records):
    """records: (chrom, pos, ref, alt[, filt]) tuples."""
    body = "".join(_rec(*r) for r in records)
    path.write_text(_HEADER + body)
    return path


def _sites(n, chrom="chr1", start=100):
    """n distinct PASS-site tuples, deterministic and disjoint by `start`."""
    return [(chrom, start + i, "A", "G") for i in range(n)]


def test_identical_pass_sites_is_pass(tmp_path):
    rows = _sites(12)
    a = _write_vcf(tmp_path / "mutect2.vcf", rows)
    b = _write_vcf(tmp_path / "strelka.vcf", rows)

    results = evaluate_somatic_concordance([a], [b])

    assert len(results) == 1
    result = results[0]
    assert result.check == "somatic_site_overlap"
    assert result.status == "pass"
    assert result.value == 1.0
    assert result.kind == "concordance"
    assert result.expected_range == ">= 0.9"


def test_half_disjoint_is_warn(tmp_path):
    # Disjoint sets -> union 24, shared 0, jaccard 0.0 (well below the WARN band).
    a_rows = _sites(12, start=100)
    b_rows = _sites(12, start=500)
    a = _write_vcf(tmp_path / "mutect2.vcf", a_rows)
    b = _write_vcf(tmp_path / "strelka.vcf", b_rows)

    results = evaluate_somatic_concordance([a], [b])

    assert len(results) == 1
    result = results[0]
    assert result.status == "warn"
    assert result.value < 0.90


def test_union_below_floor_is_unverified(tmp_path):
    rows = _sites(3)  # union will be 3 < _MIN_SHARED_SITES
    a = _write_vcf(tmp_path / "mutect2.vcf", rows)
    b = _write_vcf(tmp_path / "strelka.vcf", rows)

    results = evaluate_somatic_concordance([a], [b])

    assert len(results) == 1
    result = results[0]
    assert result.status == "unverified"
    assert result.value is None
    assert result.kind == "concordance"


def test_non_pass_record_excluded_from_its_set(tmp_path):
    rows = _sites(12)
    a_rows = rows + [("chr1", 999, "A", "G", "clustered_events")]  # mutect2 filter
    b_rows = rows + [("chr1", 888, "A", "G", "weak_evidence")]  # strelka filter

    a = _write_vcf(tmp_path / "mutect2.vcf", a_rows)
    b = _write_vcf(tmp_path / "strelka.vcf", b_rows)

    a_sites = parse_pass_sites(a)
    b_sites = parse_pass_sites(b)

    assert ("chr1", "999", "A", "G") not in a_sites
    assert ("chr1", "888", "A", "G") not in b_sites
    # The excluded, non-shared records don't change either set beyond `rows`.
    assert a_sites == b_sites


def test_dot_filter_is_treated_as_pass(tmp_path):
    rows = _sites(11) + [("chr1", 9999, "A", "G", ".")]
    a = _write_vcf(tmp_path / "a.vcf", rows)

    sites = parse_pass_sites(a)

    assert ("chr1", "9999", "A", "G") in sites


def test_strelka_split_snv_indel_files_are_unioned(tmp_path):
    snvs = _sites(6, start=100)
    indels = _sites(6, start=900)
    snv_path = _write_vcf(tmp_path / "T_vs_N.strelka.somatic_snvs.vcf", snvs)
    indel_path = _write_vcf(tmp_path / "T_vs_N.strelka.somatic_indels.vcf", indels)

    sites = read_caller_sites([snv_path, indel_path])

    assert len(sites) == 12


def test_gzipped_input_matches_plaintext(tmp_path):
    rows = _sites(12)
    plain = _write_vcf(tmp_path / "a.vcf", rows)
    gz = tmp_path / "a.vcf.gz"
    with gzip.open(gz, "wt") as fh:
        fh.write(_HEADER + "".join(_rec(*r) for r in rows))

    assert parse_pass_sites(gz) == parse_pass_sites(plain)


def test_gzipped_end_to_end_matches_plaintext(tmp_path):
    rows = _sites(12)
    a_plain = _write_vcf(tmp_path / "mutect2.vcf", rows)
    b_plain = _write_vcf(tmp_path / "strelka.vcf", rows[:8])

    a_gz = tmp_path / "mutect2.vcf.gz"
    with gzip.open(a_gz, "wt") as fh:
        fh.write(_HEADER + "".join(_rec(*r) for r in rows))
    b_gz = tmp_path / "strelka.vcf.gz"
    with gzip.open(b_gz, "wt") as fh:
        fh.write(_HEADER + "".join(_rec(*r) for r in rows[:8]))

    plain_results = evaluate_somatic_concordance([a_plain], [b_plain])
    gz_results = evaluate_somatic_concordance([a_gz], [b_gz])

    assert plain_results[0].value == gz_results[0].value
    assert plain_results[0].status == gz_results[0].status


def test_message_names_both_callers_and_counts(tmp_path):
    rows = _sites(12)
    a = _write_vcf(tmp_path / "mutect2.vcf", rows)
    b = _write_vcf(tmp_path / "strelka.vcf", rows)

    result = evaluate_somatic_concordance([a], [b])[0]

    assert "mutect2" in result.message
    assert "strelka" in result.message
    assert "12" in result.message  # shared/union count


def test_never_fail_and_always_concordance_kind(tmp_path):
    rows = _sites(12)
    a = _write_vcf(tmp_path / "mutect2.vcf", rows)
    b = _write_vcf(tmp_path / "strelka.vcf", rows[:6])  # partial overlap -> warn

    results = evaluate_somatic_concordance([a], [b])

    assert results
    assert all(r.kind == "concordance" for r in results)
    assert all(r.status != "fail" for r in results)


def test_custom_labels_used_in_message(tmp_path):
    rows = _sites(12)
    a = _write_vcf(tmp_path / "a.vcf", rows)
    b = _write_vcf(tmp_path / "b.vcf", rows)

    result = evaluate_somatic_concordance(
        [a], [b], label_a="tumor_caller", label_b="other_caller"
    )[0]

    assert "tumor_caller" in result.message
    assert "other_caller" in result.message
