"""Tests for the curated pipeline registry.

The registry maps an assay to an ALREADY-VALIDATED pipeline; `match_assay` is a
deterministic keyword matcher (a replaceable rule-based intent provider, not an
LLM and not the moat). These tests pin both the curated data and the rules.
"""

import pytest

from contig.models import PipelineEntry
from contig.registry import REGISTRY, UnknownAssayError, match_assay, select_pipeline


def test_registry_has_rnaseq_entry():
    rnaseq = [e for e in REGISTRY if e.assay == "rnaseq"]
    assert len(rnaseq) == 1
    assert isinstance(rnaseq[0], PipelineEntry)
    assert rnaseq[0].pipeline == "nf-core/rnaseq"


def test_select_pipeline_returns_entry_for_known_assay():
    entry = select_pipeline("rnaseq")
    assert entry.assay == "rnaseq"
    assert entry.pipeline == "nf-core/rnaseq"
    assert entry in REGISTRY


def test_select_pipeline_raises_for_unknown_assay():
    with pytest.raises(KeyError) as excinfo:
        select_pipeline("unknownassay")
    # The custom error is a KeyError subclass so callers can catch either.
    assert isinstance(excinfo.value, UnknownAssayError)
    assert "unknownassay" in str(excinfo.value)


def test_match_assay_matches_differential_expression_phrase():
    goal = "find differentially expressed genes between treated and control"
    assert match_assay(goal) == "rnaseq"


def test_match_assay_is_case_insensitive():
    assert match_assay("I have RNA-seq data") == "rnaseq"


def test_match_assay_returns_none_for_unregistered_assay():
    assert match_assay("call germline variants from my WGS") is None


def test_match_assay_returns_none_for_empty_goal():
    assert match_assay("") is None
