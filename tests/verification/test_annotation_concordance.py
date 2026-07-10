"""VEP-vs-SnpEff most-severe-consequence concordance (C7 M4, phase 2: pure core).

Phase 1 (`annotation_structural.py`) proves annotation ran; phase 2 here
(`annotation_plausibility.py`) proves a single tool's consequence distribution
looks plausible. This module cross-checks the two tools against each other:
for the variant sites both VEP (CSQ) and SnpEff (ANN) annotated, do they agree
on the most-severe consequence term? Agreement corroborates; it is NOT ground
truth, so this is WARN-capped -- never a FAIL, mirroring `somatic_concordance.py`.

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
"""

from pathlib import Path

from contig.verification.annotation_concordance import (
    _most_severe_term,
    evaluate_consequence_concordance,
    parse_consequences,
)

# VEP CSQ header: Format declares Consequence at index 1.
VEP_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

# SnpEff ANN header: fixed layout, consequence ("Annotation") at index 1.
ANN_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
    "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

# A single VCF declaring BOTH CSQ and ANN headers (single-VCF-both layout).
BOTH_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|Consequence|IMPACT|SYMBOL">\n'
    '##INFO=<ID=ANN,Number=.,Type=String,Description="Functional annotations: '
    "'Allele | Annotation | Annotation_Impact | Gene_Name'\">\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)

# A VCF with neither CSQ nor ANN declared/present.
NO_ANNOTATION_HEADER = (
    "##fileformat=VCFv4.2\n"
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def _csq_rec(chrom, pos, ref, alt, term):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\tCSQ={alt}|{term}|MODERATE|GENE1\n"


def _ann_rec(chrom, pos, ref, alt, term):
    return f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\tANN={alt}|{term}|MODERATE|GENE1\n"


def _sites(n, chrom="chr1", start=100):
    """n distinct (chrom, pos, ref, alt) site tuples, deterministic and disjoint."""
    return [(chrom, start + i, "A", "G") for i in range(n)]


def _build_vcf(tmp_path, name, header, rec_fn, sites, terms):
    body = header + "".join(
        rec_fn(*site, term) for site, term in zip(sites, terms)
    )
    return _write(tmp_path, name, body)


# --- Unit: _most_severe_term -----------------------------------------------------


def test_most_severe_term_none_when_empty():
    assert _most_severe_term([]) is None


def test_most_severe_term_picks_max_rank():
    # missense_variant outranks synonymous_variant.
    assert _most_severe_term(["synonymous_variant", "missense_variant"]) == "missense_variant"


def test_most_severe_term_single_term():
    assert _most_severe_term(["intron_variant"]) == "intron_variant"


# --- test_consequence_concordant (RED first: module doesn't exist yet) -----------


def test_consequence_concordant(tmp_path):
    sites = _sites(10)
    terms = ["missense_variant"] * 10
    vep = _build_vcf(tmp_path, "vep.vcf", VEP_HEADER, _csq_rec, sites, terms)
    snpeff = _build_vcf(tmp_path, "snpeff.vcf", ANN_HEADER, _ann_rec, sites, terms)

    vep_map = parse_consequences(vep, "CSQ")
    snpeff_map = parse_consequences(snpeff, "ANN")

    results = evaluate_consequence_concordance(vep_map, snpeff_map, layout="two-file")

    assert len(results) == 1
    result = results[0]
    assert result.check == "consequence_concordance"
    assert result.status == "pass"
    assert result.value == 1.0
    assert result.kind == "concordance"


def test_consequence_divergent(tmp_path):
    sites = _sites(10)
    vep_terms = ["missense_variant"] * 10
    # 5/10 mismatched -> fraction 0.5 < 0.90 -> WARN.
    snpeff_terms = ["missense_variant"] * 5 + ["synonymous_variant"] * 5
    vep = _build_vcf(tmp_path, "vep.vcf", VEP_HEADER, _csq_rec, sites, vep_terms)
    snpeff = _build_vcf(tmp_path, "snpeff.vcf", ANN_HEADER, _ann_rec, sites, snpeff_terms)

    vep_map = parse_consequences(vep, "CSQ")
    snpeff_map = parse_consequences(snpeff, "ANN")

    result = evaluate_consequence_concordance(vep_map, snpeff_map, layout="two-file")[0]

    assert result.status == "warn"
    assert result.value == 0.5
    assert "vep" in result.message
    assert "snpeff" in result.message


def test_consequence_boundary(tmp_path):
    # 20 shared sites, exactly 18 match -> fraction 0.90 -> PASS (>= is pass).
    sites = _sites(20)
    vep_terms = ["missense_variant"] * 20
    snpeff_terms = ["missense_variant"] * 18 + ["synonymous_variant"] * 2
    vep = _build_vcf(tmp_path, "vep.vcf", VEP_HEADER, _csq_rec, sites, vep_terms)
    snpeff = _build_vcf(tmp_path, "snpeff.vcf", ANN_HEADER, _ann_rec, sites, snpeff_terms)

    vep_map = parse_consequences(vep, "CSQ")
    snpeff_map = parse_consequences(snpeff, "ANN")

    result = evaluate_consequence_concordance(vep_map, snpeff_map, layout="two-file")[0]

    assert result.value == 0.9
    assert result.status == "pass"


def test_below_floor_unverified(tmp_path):
    # Only 5 shared sites (< _MIN_SHARED_VARIANTS=10) -> UNVERIFIED.
    sites = _sites(5)
    terms = ["missense_variant"] * 5
    vep = _build_vcf(tmp_path, "vep.vcf", VEP_HEADER, _csq_rec, sites, terms)
    snpeff = _build_vcf(tmp_path, "snpeff.vcf", ANN_HEADER, _ann_rec, sites, terms)

    vep_map = parse_consequences(vep, "CSQ")
    snpeff_map = parse_consequences(snpeff, "ANN")

    result = evaluate_consequence_concordance(vep_map, snpeff_map, layout="two-file")[0]

    assert result.status == "unverified"
    assert result.value is None
    assert result.kind == "concordance"


def test_empty_maps_unverified():
    result = evaluate_consequence_concordance({}, {}, layout="two-file")[0]

    assert result.status == "unverified"
    assert result.value is None
    assert result.kind == "concordance"


def test_single_vcf_both_keys(tmp_path):
    # ONE VCF declares BOTH CSQ and ANN headers, and each record carries both
    # fields with (possibly) different terms -> parse_consequences("CSQ") and
    # parse_consequences("ANN") must each return the correct INDEPENDENT map.
    sites = _sites(10)
    body = BOTH_HEADER + "".join(
        f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t50\tPASS\t"
        f"CSQ={alt}|missense_variant|MODERATE|GENE1;ANN={alt}|missense_variant|MODERATE|GENE1\n"
        for chrom, pos, ref, alt in sites
    )
    vcf = _write(tmp_path, "both.vcf", body)

    vep_map = parse_consequences(vcf, "CSQ")
    snpeff_map = parse_consequences(vcf, "ANN")

    assert len(vep_map) == 10
    assert len(snpeff_map) == 10
    assert set(vep_map) == set(snpeff_map)
    assert all(term == "missense_variant" for term in vep_map.values())
    assert all(term == "missense_variant" for term in snpeff_map.values())

    result = evaluate_consequence_concordance(
        vep_map, snpeff_map, layout="single-vcf-both"
    )[0]

    assert result.status == "pass"
    assert "single-vcf-both" in result.message


def test_boundary_band_status_from_raw_not_rounded_regression():
    # Regression for a Critical false-PASS bug: status was decided from the
    # ROUNDED fraction, not the raw ratio. 1808/2009 = 0.8999502239920358 --
    # strictly below the 0.90 WARN floor -- but round(_, 4) == 0.9000, which
    # is >= _WARN_BELOW and was wrongly reported as "pass". The status must
    # be computed from the raw ratio; only the reported `value` may be rounded.
    n = 2009
    matches = 1808
    sites = _sites(n)
    vep_map = {site: "missense_variant" for site in sites}
    snpeff_map = {
        site: ("missense_variant" if i < matches else "synonymous_variant")
        for i, site in enumerate(sites)
    }

    raw = matches / n
    assert raw < 0.90
    assert round(raw, 4) == 0.9000  # the deceptive rounded display value

    result = evaluate_consequence_concordance(vep_map, snpeff_map, layout="two-file")[0]

    assert result.status == "warn", (
        f"raw agreement {raw} is < 0.90 and must WARN, even though it "
        f"rounds to {round(raw, 4)} for display"
    )
    assert result.value == 0.9  # rounding is still fine for the reported value


def test_undeclared_key_empty(tmp_path):
    body = NO_ANNOTATION_HEADER + "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
    vcf = _write(tmp_path, "unannotated.vcf", body)

    assert parse_consequences(vcf, "CSQ") == {}
    assert parse_consequences(vcf, "ANN") == {}
