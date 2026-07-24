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


def test_extract_claims_real_output_never_trips_internal_error(tmp_path):
    # Pins the load-bearing invariant: for real extractor output the round-trip
    # through load_claims never fails, so the internal-error path never fires.
    paper = _paper(tmp_path)
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert "internal error" not in result.output.lower()
    load_claims(out)  # loads without raising


# --- Phase 3: guards -- input failures, overwrite, empty, flags ----------------


def test_extract_claims_missing_input_writes_nothing(tmp_path):
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(tmp_path / "nope.md"), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code != 0
    assert not out.exists()
    assert not (tmp_path / "claims.draft.review.md").exists()


def test_extract_claims_directory_input_refused(tmp_path):
    d = tmp_path / "adir"
    d.mkdir()
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(d), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code != 0
    assert not out.exists()


def test_extract_claims_oversized_input_refused(tmp_path):
    from contig.verification.reproduce import _MAX_MATCH_BYTES

    paper = tmp_path / "big.md"
    with open(paper, "wb") as handle:
        handle.truncate(_MAX_MATCH_BYTES + 1)  # sparse: no 8 MiB actually written
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code != 0
    assert str(_MAX_MATCH_BYTES) in result.output or "cap" in result.output.lower()
    assert not out.exists()


def test_extract_claims_non_utf8_input_refused(tmp_path):
    paper = tmp_path / "bad.md"
    paper.write_bytes(b"\xff\xfe\x00 not utf-8 \xff")
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code != 0
    assert not out.exists()


def test_extract_claims_out_equals_input_refused(tmp_path):
    paper = _paper(tmp_path, name="claims.md")
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(paper), "--no-llm"]
    )
    assert result.exit_code != 0
    # The paper is untouched.
    assert paper.read_text(encoding="utf-8") == _FIXTURE_TEXT


def test_extract_claims_existing_out_without_force_refused(tmp_path):
    paper = _paper(tmp_path)
    out = tmp_path / "claims.draft.json"
    out.write_text("PRE-EXISTING", encoding="utf-8")
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code != 0
    assert "--force" in result.output
    assert out.read_text(encoding="utf-8") == "PRE-EXISTING"  # untouched


def test_extract_claims_force_overwrites(tmp_path):
    paper = _paper(tmp_path)
    out = tmp_path / "claims.draft.json"
    out.write_text("PRE-EXISTING", encoding="utf-8")
    result = runner.invoke(
        app,
        ["extract-claims", str(paper), "--out", str(out), "--no-llm", "--force"],
    )
    assert result.exit_code == 0, result.output
    assert out.read_text(encoding="utf-8") != "PRE-EXISTING"
    load_claims(out)


def test_extract_claims_no_llm_passes_use_llm_false(tmp_path, monkeypatch):
    seen = {}

    def _recorder(text, *, use_llm):
        seen["use_llm"] = use_llm
        return extract_claims(text)

    monkeypatch.setattr(cli, "default_extractor", _recorder)
    paper = _paper(tmp_path)
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert seen["use_llm"] is False


def test_extract_claims_default_passes_use_llm_true(tmp_path, monkeypatch):
    seen = {}

    def _recorder(text, *, use_llm):
        seen["use_llm"] = use_llm
        return extract_claims(text)

    monkeypatch.setattr(cli, "default_extractor", _recorder)
    paper = _paper(tmp_path)
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(app, ["extract-claims", str(paper), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert seen["use_llm"] is True


def test_extract_claims_empty_extraction_is_exit_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "default_extractor", lambda text, *, use_llm: [])
    paper = _paper(tmp_path, text="This paragraph has no numeric metric claims at all.\n")
    out = tmp_path / "claims.draft.json"
    result = runner.invoke(
        app, ["extract-claims", str(paper), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text()) == []
    sidecar = tmp_path / "claims.draft.review.md"
    assert sidecar.exists()
    assert "no numeric claims found" in sidecar.read_text().lower()
    assert "no numeric claims found" in result.output.lower()


def test_extract_claims_registers_flags_and_arg():
    import typer

    cmd = typer.main.get_command(app).commands["extract-claims"]
    opts = [o for p in cmd.params for o in (list(p.opts) + list(p.secondary_opts))]
    assert "--out" in opts
    assert "--no-llm" in opts
    assert "--force" in opts
    # The positional `paper` argument is registered.
    arg_names = [p.name for p in cmd.params if p.param_type_name == "argument"]
    assert "paper" in arg_names
