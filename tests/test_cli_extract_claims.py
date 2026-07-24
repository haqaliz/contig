"""Tests for `contig extract-claims` (reproduce-paper-claims, aspect
`cli-command`): the user-facing command that reads a paper's local text, runs
the extractor, and writes a load_claims-valid draft + a review sidecar -- never
touching the verdict path.

Mirrors tests/test_cli_reproduce.py conventions: no conftest, tmp_path,
CliRunner, and monkeypatch. The real LLM is never called in CI.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import contig.cli as cli
from contig.cli import app, default_extractor
from contig.verification.claim_extraction import ExtractedClaim, extract_claims

runner = CliRunner()

# A fixture paragraph with two named-metric numeric claims the deterministic
# core reliably picks up.
_FIXTURE_TEXT = (
    "We evaluated the classifier on the held-out set. "
    "The model reached an AUC of 0.91 on the test cohort. "
    "Overall accuracy was 87% across all folds.\n"
)


# --- Phase 1: the default_extractor composition seam ---------------------------


def test_default_extractor_core_only_matches_extract_claims():
    assert default_extractor(_FIXTURE_TEXT, use_llm=False) == extract_claims(_FIXTURE_TEXT)


def test_default_extractor_unconfigured_llm_is_core_only(monkeypatch):
    # use_llm=True but no provider configured: extract_with_llm returns [], so
    # the merged result is the deterministic core alone.
    monkeypatch.delenv("CONTIG_LLM_PROVIDER", raising=False)
    assert default_extractor(_FIXTURE_TEXT, use_llm=True) == extract_claims(_FIXTURE_TEXT)


def test_default_extractor_merges_llm_when_use_llm(monkeypatch):
    extra = ExtractedClaim(
        id="f1", value=0.75, metric="F1", source_text="F1 was 0.75.", origin="llm"
    )
    monkeypatch.setattr(cli, "extract_with_llm", lambda text: [extra])
    result = default_extractor(_FIXTURE_TEXT, use_llm=True)
    core = extract_claims(_FIXTURE_TEXT)
    assert len(result) == len(core) + 1
    assert any(c.origin == "llm" and c.value == 0.75 for c in result)


def test_default_extractor_no_llm_ignores_configured_provider(monkeypatch):
    # use_llm=False must never call the llm assist even if a provider is set.
    called = []
    monkeypatch.setattr(cli, "extract_with_llm", lambda text: called.append(text) or [])
    default_extractor(_FIXTURE_TEXT, use_llm=False)
    assert called == []
