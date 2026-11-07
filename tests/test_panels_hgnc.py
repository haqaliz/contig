"""Tests for HGNC symbol resolution."""

from pathlib import Path

from contig.panels.hgnc import load_hgnc, resolve_symbols

FIX = Path(__file__).parent / "fixtures" / "panels"
HGNC = FIX / "hgnc.tsv"


def test_resolves_approved_alias_and_previous_symbols():
    index = load_hgnc(HGNC)
    approved, unknown = resolve_symbols(["BRCA1", "RNF53", "DFNB1"], index)
    assert approved == ["BRCA1", "GJB2"]
    assert unknown == []


def test_unknown_symbols_are_returned_not_guessed():
    index = load_hgnc(HGNC)
    approved, unknown = resolve_symbols(["BRCA1", "NOTAGENE"], index)
    assert approved == ["BRCA1"]
    assert unknown == ["NOTAGENE"]


def test_duplicate_symbols_collapse_case_insensitively():
    index = load_hgnc(HGNC)
    approved, unknown = resolve_symbols(["brca1", "BRCA1", "RNF53"], index)
    assert approved == ["BRCA1"]
    assert unknown == []
