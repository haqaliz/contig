"""Tests for inheritance, Mendelian consistency, and concordance."""

from pathlib import Path

from contig.family.analyze import (
    alleles,
    analyze_variant,
    inheritance,
    mendelian_consistent,
    pairwise_concordance,
    summarize,
)
from contig.family.ped import load_ped
from contig.family.vcf import read_family_variants

FIX = Path(__file__).parent / "fixtures" / "family"
VCF = FIX / "trio.vcf"
PED = FIX / "trio.ped"


def _rows():
    family = load_ped(PED)
    variants, _ = read_family_variants(VCF, family.samples)
    rows = []
    for variant in variants:
        rows.extend(analyze_variant(family, variant))
    return family, variants, rows


def test_alleles_and_missing():
    assert alleles("0/1") == [0, 1]
    assert alleles("0|1") == [0, 1]
    assert alleles("./.") is None
    assert alleles("1/1") == [1, 1]


def test_inheritance_classes():
    assert inheritance("0/1", "0/1", "0/0", "1") == "paternal"
    assert inheritance("0/1", "0/0", "0/1", "1") == "maternal"
    assert inheritance("0/1", "0/1", "0/1", "1") == "biparental"
    assert inheritance("0/0", "0/1", "0/0", "1") == "not_carried"
    assert inheritance("0/1", "0/0", "0/0", "1") == "de_novo"
    assert inheritance("0/1", "0/1", "0/1", "X") == "not_evaluated"


def test_mendelian_consistency():
    assert mendelian_consistent("0/1", "0/1", "0/0", "1") is True
    assert mendelian_consistent("1/1", "0/1", "0/1", "1") is True
    assert mendelian_consistent("1/1", "0/1", "0/0", "1") is False
    assert mendelian_consistent("0/1", "0/0", "0/0", "1") is False
    assert mendelian_consistent("0/1", "0/0", "0/1", "X") is None


def test_analyze_variant_rows_and_summary():
    _family, _variants, rows = _rows()
    assert len(rows) == 8
    summary = summarize(rows)
    assert summary["rows"] == 8
    assert summary["evaluated"] == 7
    assert summary["de_novo_candidates"] == 1
    assert summary["mendelian_inconsistent"] == 1
    assert abs(summary["mendelian_error_rate"] - 1 / 7) < 1e-9
    assert summary["inheritance_counts"]["paternal"] == 2
    assert summary["inheritance_counts"]["maternal"] == 1
    assert summary["inheritance_counts"]["biparental"] == 2
    assert summary["inheritance_counts"]["de_novo"] == 1
    assert summary["inheritance_counts"]["not_evaluated"] == 1


def test_de_novo_is_not_counted_as_a_mendelian_error():
    _family, _variants, rows = _rows()
    de_novo = next(row for row in rows if row.de_novo_candidate)
    assert de_novo.inheritance == "de_novo"
    assert de_novo.mendelian_consistent is False


def test_pairwise_concordance_reports_relationships():
    family, variants, _ = _rows()
    results = pairwise_concordance(family, variants)
    assert len(results) == 3
    by_pair = {frozenset((item["sample_a"], item["sample_b"])): item for item in results}
    parent_child = by_pair[frozenset(("CHILD", "FATHER"))]
    assert parent_child["relationship"] == "parent-child"
    assert parent_child["called"] == 8
    assert parent_child["possible_swap"] is False
    parent_parent = by_pair[frozenset(("FATHER", "MOTHER"))]
    assert parent_parent["relationship"] == "parent-parent"
