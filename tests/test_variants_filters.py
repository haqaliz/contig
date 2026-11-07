"""Tests for deterministic filters and sort order."""

from contig.variants.filters import apply_filters, clinvar_rank, sort_rows
from contig.variants.models import FilterSpec, VariantKey, VariantRecord


def _record(**kwargs):
    defaults = dict(
        key=VariantKey("17", 100, "C", "T"),
        gene="BRCA1",
        consequence="missense_variant",
        filter="PASS",
        zygosity="het",
        depth=50,
        vaf=0.5,
        gnomad_af=0.001,
        clinvar_significance="Pathogenic",
    )
    defaults.update(kwargs)
    return VariantRecord(**defaults)


def test_gene_filter_is_exact_and_case_insensitive():
    rows = [_record(gene="BRCA1"), _record(gene="GJB2", key=VariantKey("13", 1, "G", "A"))]
    kept = apply_filters(rows, FilterSpec(genes=["brca1"]))
    assert [r.gene for r in kept] == ["BRCA1"]


def test_consequence_filter_uses_substrings():
    rows = [
        _record(consequence="missense_variant"),
        _record(consequence="frameshift_variant", key=VariantKey("17", 101, "C", "T")),
    ]
    kept = apply_filters(rows, FilterSpec(consequences=["missense"]))
    assert [r.consequence for r in kept] == ["missense_variant"]


def test_max_af_uses_gnomad_first_and_drops_above_the_ceiling():
    rows = [
        _record(gnomad_af=0.001),
        _record(gnomad_af=0.02, key=VariantKey("17", 101, "C", "T")),
    ]
    kept = apply_filters(rows, FilterSpec(max_af=0.01))
    assert [r.gnomad_af for r in kept] == [0.001]


def test_max_af_falls_back_to_iranome():
    rows = [_record(gnomad_af=None, iranome_af=0.005)]
    kept = apply_filters(rows, FilterSpec(max_af=0.01))
    assert kept


def test_max_af_keeps_variants_with_unknown_frequency():
    rows = [_record(gnomad_af=None, iranome_af=None)]
    assert apply_filters(rows, FilterSpec(max_af=0.01)) == rows


def test_clinvar_significance_is_a_substring_filter():
    rows = [
        _record(clinvar_significance="Pathogenic"),
        _record(clinvar_significance="Conflicting_interpretations_of_pathogenicity", key=VariantKey("17", 101, "C", "T")),
        _record(clinvar_significance="Benign", key=VariantKey("17", 102, "C", "T")),
        _record(clinvar_significance=None, key=VariantKey("17", 103, "C", "T")),
    ]
    kept = apply_filters(rows, FilterSpec(clinvar_significance=["pathogenic"]))
    assert [r.clinvar_significance for r in kept] == ["Pathogenic"]


def test_pass_only_accepts_pass_and_unfiltered_dot():
    rows = [
        _record(filter="PASS"),
        _record(filter=".", key=VariantKey("17", 101, "C", "T")),
        _record(filter="q10", key=VariantKey("17", 102, "C", "T")),
    ]
    kept = apply_filters(rows, FilterSpec(pass_only=True))
    assert [r.filter for r in kept] == ["PASS", "."]


def test_depth_and_vaf_require_a_known_value():
    rows = [
        _record(depth=50, vaf=0.5),
        _record(depth=None, vaf=0.5, key=VariantKey("17", 101, "C", "T")),
        _record(depth=50, vaf=0.1, key=VariantKey("17", 102, "C", "T")),
    ]
    kept = apply_filters(rows, FilterSpec(min_depth=20, min_vaf=0.2))
    assert len(kept) == 1
    assert kept[0].depth == 50


def test_zygosity_and_region_filters_combine_with_and():
    rows = [
        _record(zygosity="het", key=VariantKey("17", 100, "C", "T")),
        _record(zygosity="hom", key=VariantKey("17", 101, "C", "T")),
        _record(zygosity="het", key=VariantKey("13", 100, "C", "T")),
    ]
    kept = apply_filters(rows, FilterSpec(zygosity="het", region="17:1-200"))
    assert len(kept) == 1
    assert kept[0].key.chrom == "17"


def test_clinvar_rank_orders_actionable_before_benign():
    assert clinvar_rank("Pathogenic") == 0
    assert clinvar_rank("Likely_pathogenic") == 1
    assert clinvar_rank("Conflicting_interpretations_of_pathogenicity") == 2
    assert clinvar_rank("Uncertain_significance") == 3
    assert clinvar_rank("Likely_benign") == 4
    assert clinvar_rank("Benign") == 5
    assert clinvar_rank("not_provided") == 6
    assert clinvar_rank(None) == 7


def test_sort_order_is_clinvar_then_af_then_consequence():
    rows = [
        _record(clinvar_significance=None, gnomad_af=0.001, key=VariantKey("1", 1, "A", "G")),
        _record(clinvar_significance="Benign", gnomad_af=0.001, key=VariantKey("1", 2, "A", "G")),
        _record(clinvar_significance="Pathogenic", gnomad_af=0.01, key=VariantKey("1", 3, "A", "G")),
        _record(clinvar_significance="Pathogenic", gnomad_af=0.001, key=VariantKey("1", 4, "A", "G")),
    ]
    ordered = sort_rows(rows)
    assert [(r.clinvar_significance, r.gnomad_af, r.key.pos) for r in ordered] == [
        ("Pathogenic", 0.001, 4),
        ("Pathogenic", 0.01, 3),
        ("Benign", 0.001, 2),
        (None, 0.001, 1),
    ]
