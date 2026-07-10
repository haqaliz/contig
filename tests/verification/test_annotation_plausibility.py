"""Deterministic CSQ/ANN consequence-parsing plausibility metrics.

Real files only, via pytest tmp_path; no mocks, no tool execution, no network.
Mirrors the fixture style of test_annotation_structural.py (module-level header
constants + a `_write(tmp_path, name, body, gz=False)` helper) and the metrics
philosophy of test_somatic_plausibility.py (never a false pass — an uncomputable
metric is None, not a guessed value).
"""

import gzip
from pathlib import Path

import pytest

from contig.verification.annotation_plausibility import (
    _SEVERITY_RANK,
    _UNKNOWN_RANK,
    AnnotationPlausibilityMetrics,
    _consequence_index_csq,
    _most_severe_rank,
    annotation_plausibility_metrics,
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

# VEP CSQ header whose Format string omits "Consequence" entirely -> unresolvable.
CSQ_NO_CONSEQUENCE_HEADER = (
    "##fileformat=VCFv4.2\n"
    '##INFO=<ID=CSQ,Number=.,Type=String,Description="Consequence annotations from '
    'Ensembl VEP. Format: Allele|IMPACT|SYMBOL">\n'
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
)


def _write(tmp_path: Path, name: str, body: str, gz: bool = False) -> Path:
    p = tmp_path / name
    if gz:
        with gzip.open(p, "wt") as fh:
            fh.write(body)
    else:
        p.write_text(body)
    return p


# --- Unit: _most_severe_rank ----------------------------------------------------


def test_most_severe_rank_none_when_no_terms():
    assert _most_severe_rank([]) is None


def test_most_severe_rank_known_term():
    assert _most_severe_rank(["missense_variant"]) == _SEVERITY_RANK["missense_variant"]


def test_most_severe_rank_unknown_term_beats_intergenic():
    # An unknown, non-empty term ranks above intergenic_variant (rank 0) -> the
    # variant is never misclassified as intergenic just because a term is novel.
    rank = _most_severe_rank(["intergenic_variant", "some_brand_new_term"])
    assert rank == _UNKNOWN_RANK
    assert rank > _SEVERITY_RANK["intergenic_variant"]


def test_most_severe_rank_picks_max_across_multiple_terms():
    # missense_variant outranks splice_region_variant and synonymous_variant.
    rank = _most_severe_rank(
        ["synonymous_variant", "splice_region_variant", "missense_variant"]
    )
    assert rank == _SEVERITY_RANK["missense_variant"]


# --- Unit: _consequence_index_csq -----------------------------------------------


def test_consequence_index_csq_found():
    header_lines = VEP_HEADER.splitlines(keepends=True)
    assert _consequence_index_csq(header_lines) == 1


def test_consequence_index_csq_missing_returns_none():
    header_lines = CSQ_NO_CONSEQUENCE_HEADER.splitlines(keepends=True)
    assert _consequence_index_csq(header_lines) is None


def test_consequence_index_csq_no_csq_line_returns_none():
    header_lines = ANN_HEADER.splitlines(keepends=True)
    assert _consequence_index_csq(header_lines) is None


# --- Metrics: VEP CSQ multi-transcript aggregation ------------------------------


def test_vep_csq_multi_transcript_aggregation(tmp_path):
    # R1: two transcripts, one &-joined -> most severe is missense_variant -> real.
    # R2: single intergenic_variant transcript -> intergenic.
    # R3: single intron_variant transcript (rank >= 1, not 0) -> real.
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\t"
        "CSQ=G|missense_variant&splice_region_variant|MODERATE|BRCA1,"
        "G|synonymous_variant|LOW|BRCA1\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|intergenic_variant|MODIFIER|.\n"
        "chr1\t300\t.\tG\tA\t50\tPASS\tCSQ=A|intron_variant|MODIFIER|GENE1\n"
    )
    vcf = _write(tmp_path, "vep.vcf", body)

    m = annotation_plausibility_metrics(vcf)

    assert m == AnnotationPlausibilityMetrics(
        real_consequence_fraction=pytest.approx(2 / 3),
        intergenic_fraction=pytest.approx(1 / 3),
    )


# --- Metrics: SnpEff ANN fixed-index aggregation --------------------------------


def test_snpeff_ann_fixed_index_aggregation(tmp_path):
    body = ANN_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tANN=G|stop_gained|HIGH|TP53\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tANN=T|intergenic_variant|MODIFIER|.\n"
    )
    vcf = _write(tmp_path, "snpeff.vcf.gz", body, gz=True)

    m = annotation_plausibility_metrics(vcf)

    assert m == AnnotationPlausibilityMetrics(
        real_consequence_fraction=pytest.approx(0.5),
        intergenic_fraction=pytest.approx(0.5),
    )


# --- Metrics: all-intergenic -----------------------------------------------------


def test_all_intergenic_fraction_is_one(tmp_path):
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|intergenic_variant|MODIFIER|.\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T|intergenic_variant|MODIFIER|.\n"
    )
    vcf = _write(tmp_path, "intergenic.vcf", body)

    m = annotation_plausibility_metrics(vcf)

    assert m.intergenic_fraction == 1.0
    assert m.real_consequence_fraction == 0.0


# --- Metrics: field-present-but-empty consequence -------------------------------


def test_empty_consequence_counts_as_empty_not_intergenic(tmp_path):
    # R1 real; R2 carries CSQ but the Consequence subfield is empty -> "empty",
    # which lowers real_fraction but must NOT be counted as intergenic.
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|missense_variant|MODERATE|BRCA1\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tCSQ=T||MODIFIER|.\n"
    )
    vcf = _write(tmp_path, "empty.vcf", body)

    m = annotation_plausibility_metrics(vcf)

    assert m.real_consequence_fraction == 0.5
    assert m.intergenic_fraction == 0.0


# --- Metrics: unresolvable CSQ Format --------------------------------------------


def test_unresolvable_csq_format_is_none(tmp_path):
    body = CSQ_NO_CONSEQUENCE_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tCSQ=G|MODERATE|BRCA1\n"
    )
    vcf = _write(tmp_path, "unresolvable.vcf", body)

    m = annotation_plausibility_metrics(vcf)

    assert m.real_consequence_fraction is None
    assert m.intergenic_fraction is None


# --- Metrics: no annotated records ------------------------------------------------


def test_no_annotated_records_is_none(tmp_path):
    body = VEP_HEADER + (
        "chr1\t100\t.\tA\tG\t50\tPASS\tDP=30\n"
        "chr1\t200\t.\tC\tT\t50\tPASS\tDP=45\n"
    )
    vcf = _write(tmp_path, "unannotated.vcf", body)

    m = annotation_plausibility_metrics(vcf)

    assert m.real_consequence_fraction is None
    assert m.intergenic_fraction is None
