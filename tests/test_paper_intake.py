"""Classifier tests for paper intake of `contig extract-claims`.

`classify_paper_argument` decides -- purely, with no I/O of any kind --
whether a `paper` argument is a DOI, a local .pdf path, a local .txt/.md
path (text), or something that must be refused outright with a named
message and nothing written. This file pins the classifier section only;
the CLI wiring that calls it lands in the cli-wiring aspect.
"""

from __future__ import annotations

import pytest

from contig.fetch import _is_doi
from contig.verification.paper_intake import PaperArgument, classify_paper_argument


# ---------------------------------------------------------------------------
# invariant: exactly one of (kind set) / (refusal set); doi only with kind=="doi"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "doi", "refusal": "x"},
        {"doi": "10.1/x"},
        {},
        {"kind": "pdf", "doi": "x"},
    ],
)
def test_paper_argument_invariant_violations_raise(kwargs):
    with pytest.raises(ValueError):
        PaperArgument(**kwargs)


def test_paper_argument_accepts_doi_kind_with_doi():
    arg = PaperArgument(kind="doi", doi="10.1/x")
    assert arg.kind == "doi"
    assert arg.doi == "10.1/x"
    assert arg.refusal is None


@pytest.mark.parametrize("kind", ["text", "pdf"])
def test_paper_argument_accepts_kind_without_doi(kind):
    arg = PaperArgument(kind=kind)
    assert arg.kind == kind
    assert arg.doi is None
    assert arg.refusal is None


# ---------------------------------------------------------------------------
# refused: leading dash (checked first, unconditionally)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arg", ["--upload-pack=x", "-x", "--help", "-"])
def test_leading_dash_is_refused(arg):
    result = classify_paper_argument(arg)
    assert result.kind is None
    assert result.doi is None
    assert result.refusal is not None
    assert "command-line option" in result.refusal


def test_leading_dash_is_refused_even_when_doi_shaped():
    # A crafted argument that starts with "-" must be refused before any DOI
    # shape is inspected, so no clever prefix can smuggle an option past the
    # dash check by also looking like an accepted DOI.
    result = classify_paper_argument("-10.1234/abc")
    assert result.kind is None
    assert result.doi is None
    assert result.refusal is not None
    assert "command-line option" in result.refusal


# ---------------------------------------------------------------------------
# accepted: DOI forms (via contig.fetch._is_doi, the single source of truth
# for the DOI shape)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg,expected_doi",
    [
        ("doi:10.1234/abc", "10.1234/abc"),
        ("DOI:10.1234/abc", "10.1234/abc"),
        ("Doi:10.1234/abc", "10.1234/abc"),
        ("10.1234/abc", "10.1234/abc"),
        ("10.5555/some.suffix", "10.5555/some.suffix"),
        ("  doi:10.1234/abc  ", "10.1234/abc"),
        ("https://doi.org/10.1038/s41586-024-00000-0", "10.1038/s41586-024-00000-0"),
        ("HTTPS://DOI.ORG/10.1/x", "10.1/x"),
    ],
)
def test_doi_forms_classify_as_doi_with_stripped_value(arg, expected_doi):
    result = classify_paper_argument(arg)
    assert result.kind == "doi"
    assert result.refusal is None
    assert result.doi == expected_doi
    assert _is_doi(result.doi)


# ---------------------------------------------------------------------------
# refused: DOI with a query/fragment, or an empty remainder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg,bad_char",
    [
        ("https://doi.org/10.1/x?utm=x", "?"),
        ("10.1/x#frag", "#"),
    ],
)
def test_doi_with_query_or_fragment_is_refused(arg, bad_char):
    # A ?/# in a DOI points at a different document than the DOI names; the
    # refusal names the offending character.
    result = classify_paper_argument(arg)
    assert result.kind is None
    assert result.doi is None
    assert result.refusal is not None
    assert bad_char in result.refusal


@pytest.mark.parametrize("arg", ["doi:", "https://doi.org/"])
def test_doi_with_empty_remainder_is_refused(arg):
    result = classify_paper_argument(arg)
    assert result.kind is None
    assert result.doi is None
    assert result.refusal is not None
    assert "empty" in result.refusal.lower()


# ---------------------------------------------------------------------------
# accepted: local .pdf (case-insensitive extension)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arg", ["paper.pdf", "dir/paper.PDF"])
def test_local_pdf_classifies_as_pdf(arg):
    result = classify_paper_argument(arg)
    assert result.kind == "pdf"
    assert result.doi is None
    assert result.refusal is None


# ---------------------------------------------------------------------------
# refused: any other URL scheme, and scp-like syntax
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg",
    ["http://x/y", "ftp://x", "ssh://x", "git://x", "file://x", "user@host:path"],
)
def test_other_schemes_and_scp_like_are_refused_naming_supported_forms(arg):
    result = classify_paper_argument(arg)
    assert result.kind is None
    assert result.doi is None
    assert result.refusal is not None
    for token in ("doi", "https://doi.org", ".pdf", ".txt", ".md"):
        assert token in result.refusal


# ---------------------------------------------------------------------------
# accepted: everything else is a local text path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arg", ["paper.txt", "paper.md", "notes", "dir/paper"])
def test_everything_else_classifies_as_text(arg):
    result = classify_paper_argument(arg)
    assert result.kind == "text"
    assert result.doi is None
    assert result.refusal is None