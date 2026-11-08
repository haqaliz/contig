"""Tests for cohort traceability, append, merge, and list."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.cohort.build import build_cohort, merge_cohorts, write_cohort
from contig.cohort.query import render_runs, render_tsv

FIX = Path(__file__).parent / "fixtures" / "cohort"
RUN1 = str(FIX / "run1.json")
RUN2 = str(FIX / "run2.json")


def _by_variant(cohort):
    return {(v.chrom, v.pos, v.ref, v.alt): v for v in cohort.variants}


def test_trace_records_labels_per_variant():
    traced = build_cohort("Lab", [RUN1, RUN2], trace=True)
    assert traced.meta.traced is True
    assert all(variant.run_labels for variant in traced.variants)
    assert all(
        len(variant.run_labels) == variant.seen_runs for variant in traced.variants
    )
    untraced = build_cohort("Lab", [RUN1, RUN2])
    assert untraced.meta.traced is False
    assert all(variant.run_labels == [] for variant in untraced.variants)


def test_tsv_and_run_listing_show_labels():
    cohort = build_cohort("Lab", [RUN1, RUN2], trace=True)
    rows = _by_variant(cohort)
    brca1 = next(v for v in rows.values() if v.genes == ["BRCA1"])
    assert brca1.run_labels == ["run1", "run2"]
    tsv = render_tsv([brca1])
    assert tsv.splitlines()[0].split("\t")[-1] == "run_labels"
    assert "run1,run2" in tsv
    runs = render_runs(cohort)
    assert "label\tsha256\tpath" in runs
    assert "run1" in runs and "run2" in runs


def test_merge_unions_runs_and_recomputes_counts():
    one = build_cohort("A", [RUN1], trace=True)
    two = build_cohort("B", [RUN2], trace=True)
    merged = merge_cohorts(one, two, name="Both")
    assert merged.meta.name == "Both"
    assert merged.meta.total_runs == 2
    variants = _by_variant(merged)
    brca1 = next(v for v in variants.values() if v.genes == ["BRCA1"])
    gjb2 = next(v for v in variants.values() if v.genes == ["GJB2"])
    egfr = next(v for v in variants.values() if v.genes == ["EGFR"])
    assert brca1.run_labels == ["run1", "run2"]
    assert brca1.seen_runs == 2 and brca1.frequency == 1.0
    assert gjb2.seen_runs == 1 and gjb2.frequency == 0.5
    assert egfr.seen_runs == 1 and egfr.frequency == 0.5
    genes = {gene.gene: gene for gene in merged.genes}
    assert genes["BRCA1"].runs_with_gene == 2
    assert genes["GJB2"].runs_with_gene == 1
    assert genes["EGFR"].runs_with_gene == 1


def test_merge_dedupes_the_same_content_under_a_different_path(tmp_path):
    copy = tmp_path / "copy.json"
    shutil.copyfile(RUN1, copy)
    one = build_cohort("A", [RUN1], trace=True)
    two = build_cohort("B", [str(copy)], trace=True)
    merged = merge_cohorts(one, two)
    assert merged.meta.total_runs == 1
    brca1 = next(v for v in merged.variants if v.genes == ["BRCA1"])
    assert brca1.run_labels == ["run1"]
    assert brca1.seen_runs == 1


def test_merge_requires_traced_cohorts_and_matching_anonymization():
    untraced = build_cohort("A", [RUN1])
    traced = build_cohort("B", [RUN2], trace=True)
    with pytest.raises(ValueError, match="--trace"):
        merge_cohorts(untraced, traced)
    with pytest.raises(ValueError, match="anonymization"):
        merge_cohorts(
            build_cohort("A", [RUN1], trace=True),
            build_cohort("B", [RUN2], trace=True, anonymize=True),
        )


def test_cli_lifecycle(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    merged = tmp_path / "merged.json"
    for args in (
        ["cohort-build", "--name", "A", "--variants", RUN1, "--trace", "--out", str(a)],
        ["cohort-build", "--name", "B", "--variants", RUN2, "--trace", "--out", str(b)],
    ):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output

    result = CliRunner().invoke(
        app, ["cohort-merge", str(a), str(b), "--out", str(merged)]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(merged.read_text())
    assert payload["meta"]["total_runs"] == 2

    listed = CliRunner().invoke(app, ["cohort-list", "--cohort", str(merged)])
    assert listed.exit_code == 0
    assert "run1" in listed.output and "run2" in listed.output
    as_json = CliRunner().invoke(
        app, ["cohort-list", "--cohort", str(merged), "--json"]
    )
    assert as_json.exit_code == 0
    payload = json.loads(as_json.output[as_json.output.index("["):])
    assert payload[0]["label"] == "run1"

    queried = CliRunner().invoke(
        app, ["cohort-query", "--cohort", str(merged), "--gene", "BRCA1"]
    )
    assert queried.exit_code == 0
    assert "run_labels" in queried.output
    assert "run1,run2" in queried.output

    appended = tmp_path / "appended.json"
    result = CliRunner().invoke(
        app,
        ["cohort-append", "--cohort", str(a), "--variants", RUN2, "--out", str(appended)],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(appended.read_text())["meta"]["total_runs"] == 2
