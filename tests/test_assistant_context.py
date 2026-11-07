"""Tests for assistant context loading."""

from pathlib import Path

import pytest

from contig.assistant.context import load_context
from contig.workspace import RunNotFoundError

FIX = Path(__file__).parent / "fixtures" / "reporting"
RUNS = FIX / "runs"
VARIANTS = FIX / "variants.json"
READINESS = FIX / "readiness.json"


def test_loads_run_and_attached_tables():
    context = load_context(RUNS, "r1", variants_path=VARIANTS, readiness_path=READINESS)
    assert context.record.run_id == "r1"
    assert context.variants is not None
    assert context.readiness is not None
    assert set(context.citations) == {"run_record", "variants", "readiness"}
    assert all(len(citation.sha256) == 64 for citation in context.citations.values())


def test_missing_run_is_a_domain_error(tmp_path):
    with pytest.raises(RunNotFoundError):
        load_context(tmp_path, "missing")


def test_missing_table_is_an_honest_error():
    with pytest.raises(FileNotFoundError):
        load_context(RUNS, "r1", variants_path=FIX / "missing.json")
