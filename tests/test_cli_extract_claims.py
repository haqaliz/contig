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
from contig.verification.reproduce import load_claims

runner = CliRunner()


def _paper(tmp_path, text=None, name="paper.md"):
    path = tmp_path / name
    path.write_text(text if text is not None else _FIXTURE_TEXT, encoding="utf-8")
    return path

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


# --- Phase 2: the command -- happy path + round-trip invariant -----------------


def test_extract_claims_writes_load_claims_valid_draft(tmp_path):
    paper = _paper(tmp_path)
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    # The central invariant: whatever we emit loads cleanly through the
    # unchanged reproduce loader.
    loaded = load_claims(out)
    assert len(loaded) >= 1
    # Sidecar exists and carries a source sentence.
    sidecar = tmp_path / "claims.draft.review.md"
    assert sidecar.exists()
    body = sidecar.read_text()
    assert "AUC" in body or "0.91" in body


def test_extract_claims_draft_is_locator_less(tmp_path):
    paper = _paper(tmp_path)
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    draft = json.loads(out.read_text())
    assert isinstance(draft, list) and draft
    for entry in draft:
        assert set(entry.keys()) == {"id", "value", "tolerance"}


def test_extract_claims_sidecar_path_json_suffix(tmp_path):
    paper = _paper(tmp_path)
    out = tmp_path / "claims.json"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "claims.review.md").exists()
    assert not (tmp_path / "claims.json.review.md").exists()


def test_extract_claims_sidecar_path_non_json_suffix(tmp_path):
    paper = _paper(tmp_path)
    out = tmp_path / "claims.draft"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "claims.draft.review.md").exists()


def test_extract_claims_summary_mentions_out_and_sidecar(tmp_path):
    paper = _paper(tmp_path)
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert "claims.draft.json" in result.output
    assert "review.md" in result.output
    assert "locator" in result.output.lower()
