"""Inheritance, Mendelian consistency, and pairwise concordance."""

from __future__ import annotations

from collections import Counter

from contig.family.models import Family, FamilyRow, FamilyVariant
from contig.variants.vcf import normalize_chrom

SEX_CHROMS = {"X", "Y", "MT"}


def alleles(gt: str | None) -> list[int] | None:
    if not gt or gt in {".", "./.", ".|."}:
        return None
    parts = gt.replace("|", "/").split("/")
    if any(part == "." for part in parts):
        return None
    try:
        return [int(part) for part in parts]
    except ValueError:
        return None


def has_alt(values: list[int] | None) -> bool:
    return bool(values) and any(value > 0 for value in values)


def inheritance(child_gt: str | None, father_gt: str | None, mother_gt: str | None, chrom: str) -> str:
    if normalize_chrom(chrom) in SEX_CHROMS:
        return "not_evaluated"
    child = alleles(child_gt)
    father = alleles(father_gt)
    mother = alleles(mother_gt)
    if child is None or father is None or mother is None:
        return "unknown"
    if not has_alt(child):
        return "not_carried"
    father_alt = has_alt(father)
    mother_alt = has_alt(mother)
    if not father_alt and not mother_alt:
        return "de_novo"
    if father_alt and not mother_alt:
        return "paternal"
    if mother_alt and not father_alt:
        return "maternal"
    return "biparental"


def mendelian_consistent(
    child_gt: str | None,
    father_gt: str | None,
    mother_gt: str | None,
    chrom: str,
) -> bool | None:
    if normalize_chrom(chrom) in SEX_CHROMS:
        return None
    child = alleles(child_gt)
    father = alleles(father_gt)
    mother = alleles(mother_gt)
    if child is None or father is None or mother is None or len(child) < 2:
        return None
    a, b = child[0], child[1]
    return (a in father and b in mother) or (a in mother and b in father)


def analyze_variant(family: Family, variant: FamilyVariant) -> list[FamilyRow]:
    rows: list[FamilyRow] = []
    for child in family.children:
        child_gt = variant.genotypes.get(child.sample_id)
        father_gt = variant.genotypes.get(child.father_id)
        mother_gt = variant.genotypes.get(child.mother_id)
        state = inheritance(child_gt, father_gt, mother_gt, variant.key.chrom)
        consistent = mendelian_consistent(child_gt, father_gt, mother_gt, variant.key.chrom)
        rows.append(FamilyRow(
            family_id=family.family_id,
            child=child.sample_id,
            key=variant.key,
            gene=variant.gene,
            consequence=variant.consequence,
            child_gt=child_gt,
            father_gt=father_gt,
            mother_gt=mother_gt,
            inheritance=state,
            mendelian_consistent=consistent,
            de_novo_candidate=state == "de_novo",
        ))
    return rows


def summarize(rows: list[FamilyRow]) -> dict[str, object]:
    evaluated = [row for row in rows if row.mendelian_consistent is not None]
    de_novo = [row for row in rows if row.de_novo_candidate]
    inconsistent = [
        row for row in rows
        if row.mendelian_consistent is False and not row.de_novo_candidate
    ]
    counts = Counter(row.inheritance for row in rows)
    return {
        "rows": len(rows),
        "evaluated": len(evaluated),
        "de_novo_candidates": len(de_novo),
        "mendelian_inconsistent": len(inconsistent),
        "mendelian_error_rate": (len(inconsistent) / len(evaluated)) if evaluated else 0.0,
        "not_evaluated": len(rows) - len(evaluated),
        "inheritance_counts": dict(sorted(counts.items())),
    }


def _relationship(family: Family, a: str, b: str) -> str:
    ma, mb = family.members[a], family.members[b]
    if ma.father_id == b or ma.mother_id == b or mb.father_id == a or mb.mother_id == a:
        return "parent-child"
    if any(child.father_id == a and child.mother_id == b or child.father_id == b and child.mother_id == a
           for child in family.children):
        return "parent-parent"
    child_ids = {child.sample_id for child in family.children}
    if a in child_ids and b in child_ids:
        return "child-child"
    return "other"


def pairwise_concordance(family: Family, variants: list[FamilyVariant]) -> list[dict[str, object]]:
    samples = family.samples
    results: list[dict[str, object]] = []
    for i, a in enumerate(samples):
        for b in samples[i + 1:]:
            called = same = opposite = 0
            for variant in variants:
                left = alleles(variant.genotypes.get(a))
                right = alleles(variant.genotypes.get(b))
                if left is None or right is None:
                    continue
                called += 1
                if sorted(left) == sorted(right):
                    same += 1
                if (set(left) == {0} and set(right) == {1}) or (set(left) == {1} and set(right) == {0}):
                    opposite += 1
            same_rate = same / called if called else 0.0
            ibs0_rate = opposite / called if called else 0.0
            relationship = _relationship(family, a, b)
            possible_swap = relationship == "parent-child" and (ibs0_rate > 0.01 or same_rate > 0.99)
            results.append({
                "sample_a": a,
                "sample_b": b,
                "relationship": relationship,
                "called": called,
                "same_genotype": same,
                "opposite_homozygote": opposite,
                "same_rate": same_rate,
                "ibs0_rate": ibs0_rate,
                "possible_swap": possible_swap,
            })
    return results
