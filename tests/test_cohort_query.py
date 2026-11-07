"""Tests for local cohort queries."""

import json
from pathlib import Path

import pytest

from contig.cohort.build import build_cohort
from contig.cohort.query import query_cohort, render_json, render_tsv

FIX = Path(__file__).parent / "fixtures" / "cohort"
PATHS = [str(FIX / "run1.json"), str(FIX / "run2.json"), str(FIX / "run3.json")]


def _cohort():
    return build_cohort("Lab", PATHS)


def test_gene_query():
    rows = query_cohort(_cohort(), gene="BRCA1")
    assert len(rows) == 1
    assert rows[0].genes == ["BRCA1"]


def test_variant_query():
    rows = query_cohort(_cohort(), variant="17-43057063-C-CT")
    assert len(rows) == 1
    assert rows[0].seen_runs == 3


def test_min_runs_filter():
    rows = query_cohort(_cohort(), min_runs=3)
    assert len(rows) == 1
    assert rows[0].chrom == "17"


def test_no_match_returns_empty():
    assert query_cohort(_cohort(), gene="NOPE") == []


def test_invalid_variant_is_refused():
    with pytest.raises(ValueError, match="CHROM-POS-REF-ALT"):
        query_cohort(_cohort(), variant="bad")


def test_tsv_and_json_rendering():
    cohort = _cohort()
    rows = query_cohort(cohort, gene="BRCA1")
    assert render_tsv(rows).startswith("chrom\tpos")
    payload = json.loads(render_json(cohort, rows))
    assert payload["meta"]["total_runs"] == 3
    assert len(payload["variants"]) == 1
