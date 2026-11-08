"""Tests for local cohort building."""

from pathlib import Path

import pytest

from contig.cohort.build import build_cohort

FIX = Path(__file__).parent / "fixtures" / "cohort"
PATHS = [str(FIX / "run1.json"), str(FIX / "run2.json"), str(FIX / "run3.json")]


def _by_variant(cohort):
    return {(v.chrom, v.pos, v.ref, v.alt): v for v in cohort.variants}


def test_counts_and_frequencies():
    cohort = build_cohort("Lab", PATHS)
    assert cohort.meta.total_runs == 3
    variants = _by_variant(cohort)
    brca1 = variants[("17", 43057063, "C", "CT")]
    gjb2 = variants[("13", 20189547, "G", "A")]
    egfr = variants[("7", 55191822, "T", "G")]
    assert brca1.seen_runs == 3
    assert brca1.frequency == 1.0
    assert gjb2.seen_runs == 2
    assert abs(gjb2.frequency - 2 / 3) < 1e-9
    assert egfr.seen_runs == 2


def test_gene_summaries():
    cohort = build_cohort("Lab", PATHS)
    genes = {gene.gene: gene for gene in cohort.genes}
    assert genes["BRCA1"].variant_count == 1
    assert genes["BRCA1"].runs_with_gene == 3
    assert genes["GJB2"].runs_with_gene == 2
    assert genes["EGFR"].runs_with_gene == 2


def test_anonymize_hides_paths_and_hashes_labels():
    cohort = build_cohort("Lab", PATHS, anonymize=True)
    assert cohort.meta.anonymized is True
    assert all(run.path == "" for run in cohort.meta.runs)
    assert all(len(run.label) == 12 for run in cohort.meta.runs)
    assert all("run1" not in run.label for run in cohort.meta.runs)


def test_deterministic_variants_and_genes():
    one = build_cohort("Lab", PATHS)
    two = build_cohort("Lab", PATHS)
    assert [v.model_dump() for v in one.variants] == [v.model_dump() for v in two.variants]
    assert [g.model_dump() for g in one.genes] == [g.model_dump() for g in two.genes]


def test_empty_and_missing_inputs():
    with pytest.raises(ValueError):
        build_cohort("Lab", [])
    with pytest.raises(FileNotFoundError):
        build_cohort("Lab", [str(FIX / "missing.json")])


def test_duplicate_input_content_is_counted_once():
    cohort = build_cohort("Lab", [PATHS[0], PATHS[0], PATHS[1]])
    assert cohort.meta.total_runs == 2
    brca1 = next(v for v in cohort.variants if v.genes == ["BRCA1"])
    assert brca1.seen_runs == 2
    assert brca1.frequency == 1.0
    assert any("duplicate input skipped" in note for note in cohort.meta.notes)
