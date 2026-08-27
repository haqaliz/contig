"""Tests for the DOI/PDF intake of `contig extract-claims` (reproduce-doi-pdf-
intake, aspect `cli-wiring`): the `--allow-fetch` gate, the paper-argument
classifier refusals, the scripted fetch/extract seams, and the guard ordering.

Mirrors tests/test_cli_extract_claims.py conventions: no conftest, tmp_path,
CliRunner, and monkeypatch. The network and pdftotext are never touched in CI:
`contig.cli.default_paper_fetcher` / `contig.cli.default_pdf_text_extractor`
are monkeypatched with scripted seams, and fixture PDF bytes only.
"""

from __future__ import annotations

import json
import os

from typer.testing import CliRunner

from contig.cli import app
from contig.verification.paper_intake import MAX_PDF_BYTES
from contig.verification.reproduce import _MAX_MATCH_BYTES, load_claims

runner = CliRunner()

# "Real fixture PDF bytes": the extractor seam is scripted, so the magic
# prefix is the only part that must look like a PDF.
_PDF_BYTES = b"%PDF-1.4\n% contig test fixture (never parsed by a real pdftotext)\n"

# The same fixture paragraph the sibling test file uses: two named-metric
# numeric claims the deterministic core reliably picks up.
_FIXTURE_TEXT = (
    "We evaluated the classifier on the held-out set. "
    "The model reached an AUC of 0.91 on the test cohort. "
    "Overall accuracy was 87% across all folds.\n"
)


def _scripted_fetcher(pdf_bytes):
    """Return a seam callable that writes `pdf_bytes` to `dest` and returns
    `(0, "fetched")`, recording every `(doi, dest)` invocation on `.calls`."""

    def _fetch(doi, dest):
        _fetch.calls.append((doi, dest))
        dest.write_bytes(pdf_bytes)
        return (0, "fetched")

    _fetch.calls = []
    return _fetch


def _scripted_extractor(text, code=0):
    """Return a seam callable returning `(code, text)`, recording every
    invocation's PDF path on `.calls`."""

    def _extract(pdf):
        _extract.calls.append(pdf)
        return (code, text)

    _extract.calls = []
    return _extract


def _invoke(args):
    return runner.invoke(app, args)


def _pdf(tmp_path, name="paper.pdf"):
    path = tmp_path / name
    path.write_bytes(_PDF_BYTES)
    return path


# ---------------------------------------------------------------------------
# Refusals and guard ordering
# ---------------------------------------------------------------------------


def test_doi_without_allow_fetch_refused_before_any_io(tmp_path, monkeypatch):
    fetcher = _scripted_fetcher(_PDF_BYTES)
    monkeypatch.setattr("contig.cli.default_paper_fetcher", fetcher)
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        [
            "extract-claims",
            "https://doi.org/10.1234/abc",
            "--out",
            str(out),
            "--no-llm",
        ]
    )
    assert result.exit_code == 1
    assert "--allow-fetch" in result.output
    assert not out.exists()
    assert fetcher.calls == []


def test_leading_dash_paper_arg_refused_by_classifier(tmp_path):
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        [
            "extract-claims",
            "--out",
            str(out),
            "--no-llm",
            "--",
            "--upload-pack=evil",
        ]
    )
    assert result.exit_code == 1
    assert "looks like a command-line option" in result.output
    assert not out.exists()


def test_url_scheme_paper_arg_refused_naming_supported_forms(tmp_path):
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        [
            "extract-claims",
            "http://example.com/paper.pdf",
            "--out",
            str(out),
            "--no-llm",
        ]
    )
    assert result.exit_code == 1
    assert "scheme is not supported" in result.output
    assert not out.exists()


def test_existing_out_without_force_refuses_doi_before_fetcher(tmp_path, monkeypatch):
    fetcher = _scripted_fetcher(_PDF_BYTES)
    monkeypatch.setattr("contig.cli.default_paper_fetcher", fetcher)
    out = tmp_path / "claims.draft.json"
    out.write_text("PRE-EXISTING", encoding="utf-8")
    result = _invoke(
        [
            "extract-claims",
            "10.1234/abc",
            "--out",
            str(out),
            "--allow-fetch",
            "--no-llm",
        ]
    )
    assert result.exit_code == 1
    assert "--force" in result.output
    assert out.read_text(encoding="utf-8") == "PRE-EXISTING"
    assert fetcher.calls == []


def test_out_equals_input_still_refuses_for_local_pdf(tmp_path):
    pdf = _pdf(tmp_path)
    result = _invoke(
        ["extract-claims", str(pdf), "--out", str(pdf), "--no-llm"]
    )
    assert result.exit_code == 1
    assert "--out must not be the input paper path" in result.output
    assert pdf.read_bytes() == _PDF_BYTES


def test_doi_paper_arg_skips_out_equals_input_check(tmp_path, monkeypatch):
    # A DOI is not a path, so the --out == input clobber check must be skipped:
    # the run proceeds to the --allow-fetch refusal, not the clobber refusal.
    # (paper and --out are the same token, so Path equality would trip if the
    # check ran for DOIs.)
    fetcher = _scripted_fetcher(_PDF_BYTES)
    monkeypatch.setattr("contig.cli.default_paper_fetcher", fetcher)
    result = _invoke(
        ["extract-claims", "10.1234/abc", "--out", "10.1234/abc", "--no-llm"]
    )
    assert result.exit_code == 1
    assert "--allow-fetch" in result.output
    assert "--out must not be the input paper path" not in result.output
    assert fetcher.calls == []


# ---------------------------------------------------------------------------
# Success paths (scripted seams)
# ---------------------------------------------------------------------------


def test_doi_with_flag_writes_draft_sidecar_and_stripped_doi(tmp_path, monkeypatch):
    fetcher = _scripted_fetcher(_PDF_BYTES)
    extractor = _scripted_extractor(_FIXTURE_TEXT)
    monkeypatch.setattr("contig.cli.default_paper_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_pdf_text_extractor", extractor)
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        [
            "extract-claims",
            "https://doi.org/10.1234/abc",
            "--out",
            str(out),
            "--allow-fetch",
            "--no-llm",
        ]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    loaded = load_claims(out)
    assert len(loaded) >= 1
    sidecar = tmp_path / "claims.draft.review.md"
    assert sidecar.exists()
    body = sidecar.read_text()
    assert "Source:" in body
    assert "10.1234/abc" in body
    assert fetcher.calls[0][0] == "10.1234/abc"  # the stripped DOI, not the URL


def test_local_pdf_writes_draft_and_source_sidecar(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    extractor = _scripted_extractor(_FIXTURE_TEXT)
    monkeypatch.setattr("contig.cli.default_pdf_text_extractor", extractor)
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        ["extract-claims", str(pdf), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert load_claims(out)
    sidecar = tmp_path / "claims.draft.review.md"
    body = sidecar.read_text()
    assert "Source:" in body
    assert str(pdf) in body


def test_empty_extraction_via_pdf_path_is_exit_zero(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    extractor = _scripted_extractor("")
    monkeypatch.setattr("contig.cli.default_pdf_text_extractor", extractor)
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        ["extract-claims", str(pdf), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text()) == []
    sidecar = tmp_path / "claims.draft.review.md"
    assert sidecar.exists()
    assert "no numeric claims found" in sidecar.read_text().lower()


# ---------------------------------------------------------------------------
# Failure paths: nothing written, no leftover temp
# ---------------------------------------------------------------------------


def test_fetch_failure_echoes_and_leaves_no_temp(tmp_path, monkeypatch):
    calls = []

    def _fail_fetch(doi, dest):
        calls.append((doi, dest))
        return (
            1,
            "no citation_pdf_url found (the paper may be paywalled); "
            "download the PDF and pass its path instead",
        )

    monkeypatch.setattr("contig.cli.default_paper_fetcher", _fail_fetch)
    # Pin the process temp dir under tmp_path so "no leftover temp" is asserted
    # hermetically (the shared system temp dir is written to by foreign tools).
    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(temp_dir))
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        [
            "extract-claims",
            "10.1234/paywalled",
            "--out",
            str(out),
            "--allow-fetch",
            "--no-llm",
        ]
    )
    assert result.exit_code == 1
    assert "no citation_pdf_url found" in result.output
    assert not out.exists()
    assert calls[0][0] == "10.1234/paywalled"
    assert not os.path.exists(str(calls[0][1]))  # the temp dest is gone
    assert os.listdir(temp_dir) == []  # nothing left in the temp dir


def test_extractor_failure_echoes_and_writes_nothing(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    extractor = _scripted_extractor(
        "pdftotext executable not found; install poppler "
        "(brew install poppler / apt install poppler-utils)",
        code=127,
    )
    monkeypatch.setattr("contig.cli.default_pdf_text_extractor", extractor)
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        ["extract-claims", str(pdf), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 1
    assert "pdftotext executable not found" in result.output
    assert not out.exists()


def test_pdf_over_max_bytes_refused_naming_size(tmp_path, monkeypatch):
    pdf = tmp_path / "big.pdf"
    with open(pdf, "wb") as handle:
        handle.truncate(MAX_PDF_BYTES + 1)  # sparse: no 64 MiB actually written
    extractor = _scripted_extractor("")
    monkeypatch.setattr("contig.cli.default_pdf_text_extractor", extractor)
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        ["extract-claims", str(pdf), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 1
    assert str(MAX_PDF_BYTES + 1) in result.output
    assert not out.exists()
    assert extractor.calls == []  # refused before extraction


def test_extracted_text_over_match_cap_refused_naming_size(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path)
    extractor = _scripted_extractor("x" * (_MAX_MATCH_BYTES + 1))
    monkeypatch.setattr("contig.cli.default_pdf_text_extractor", extractor)
    out = tmp_path / "claims.draft.json"
    result = _invoke(
        ["extract-claims", str(pdf), "--out", str(out), "--no-llm"]
    )
    assert result.exit_code == 1
    assert str(_MAX_MATCH_BYTES + 1) in result.output
    assert not out.exists()


# ---------------------------------------------------------------------------
# Click introspection
# ---------------------------------------------------------------------------


def test_extract_claims_registers_allow_fetch_flags():
    import typer

    cmd = typer.main.get_command(app).commands["extract-claims"]
    opts = [o for p in cmd.params for o in (list(p.opts) + list(p.secondary_opts))]
    assert "--allow-fetch" in opts
    assert "--no-allow-fetch" in opts