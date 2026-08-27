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
from contig.verification.paper_intake import (
    PaperArgument,
    PaperIntakeError,
    _doi_url,
    _looks_like_pdf,
    classify_paper_argument,
    resolve_pdf_url,
)


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


@pytest.mark.parametrize("arg", ["https://example.com/paper.pdf", "http://x/y.pdf"])
def test_url_ending_in_pdf_is_refused_as_a_scheme_not_read_as_local_pdf(arg):
    # A URL is refused by scheme even when its path ends in .pdf: a remote
    # paper is never silently downgraded to a local-path stat failure.
    result = classify_paper_argument(arg)
    assert result.kind is None
    assert result.doi is None
    assert result.refusal is not None
    assert "scheme" in result.refusal


# ---------------------------------------------------------------------------
# accepted: everything else is a local text path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arg", ["paper.txt", "paper.md", "notes", "dir/paper"])
def test_everything_else_classifies_as_text(arg):
    result = classify_paper_argument(arg)
    assert result.kind == "text"
    assert result.doi is None
    assert result.refusal is None


# ---------------------------------------------------------------------------
# doi-fetch: _doi_url builder (verbatim, no normalization)
# ---------------------------------------------------------------------------


def test_doi_url_builder():
    assert _doi_url("10.1038/x") == "https://doi.org/10.1038/x"


def test_doi_url_builder_is_verbatim_no_normalization():
    # The classifier already stripped/normalized the DOI; the builder must
    # not second-guess it: no stripping, quoting, or scheme sniffing.
    assert _doi_url("10.1038/x?q=1") == "https://doi.org/10.1038/x?q=1"
    assert _doi_url(" 10.1038/x ") == "https://doi.org/ 10.1038/x "


# ---------------------------------------------------------------------------
# doi-fetch: resolve_pdf_url over landing-page HTML fixtures
# ---------------------------------------------------------------------------

_PDF_URL = "https://example.com/paper.pdf"

_LANDING_NAME_FIRST = (
    "<html><head>"
    f'<meta name="citation_pdf_url" content="{_PDF_URL}">'
    "</head><body>Landing page</body></html>"
)

_LANDING_CONTENT_FIRST = (
    "<html><head>"
    f'<meta content="{_PDF_URL}" name="citation_pdf_url">'
    "</head></html>"
)

_LANDING_UPPERCASE_NAME = (
    "<html><head>"
    f'<meta NAME="CITATION_PDF_URL" content="{_PDF_URL}">'
    "</head></html>"
)

_LANDING_SINGLE_QUOTES = (
    "<html><head>"
    f"<meta name='citation_pdf_url' content='{_PDF_URL}'>"
    "</head></html>"
)


@pytest.mark.parametrize(
    "html",
    [
        _LANDING_NAME_FIRST,
        _LANDING_CONTENT_FIRST,
        _LANDING_UPPERCASE_NAME,
        _LANDING_SINGLE_QUOTES,
    ],
)
def test_resolve_pdf_url_extracts_single_meta(html):
    assert resolve_pdf_url(html) == _PDF_URL


@pytest.mark.parametrize(
    "html",
    [
        "<html><head></head><body>Landing page</body></html>",
        "<!DOCTYPE html><html><head><title>Paper</title></head></html>",
    ],
)
def test_resolve_pdf_url_absent_meta_raises(html):
    with pytest.raises(PaperIntakeError):
        resolve_pdf_url(html)


def test_resolve_pdf_url_duplicate_metas_raise_naming_count():
    html = (
        "<html><head>"
        '<meta name="citation_pdf_url" content="https://a.example.com/p.pdf">'
        '<meta name="citation_pdf_url" content="https://b.example.com/p.pdf">'
        "</head></html>"
    )
    with pytest.raises(PaperIntakeError, match="2"):
        resolve_pdf_url(html)


def test_resolve_pdf_url_empty_content_meta_skipped_raises_absent():
    html = '<html><head><meta name="citation_pdf_url" content=""></head></html>'
    with pytest.raises(PaperIntakeError):
        resolve_pdf_url(html)


def test_resolve_pdf_url_unrelated_metas_ignored():
    html = (
        "<html><head>"
        '<meta name="citation_title" content="A paper">'
        '<meta name="citation_author" content="Jane Doe">'
        f'<meta name="citation_pdf_url" content="{_PDF_URL}">'
        "</head></html>"
    )
    assert resolve_pdf_url(html) == _PDF_URL


# ---------------------------------------------------------------------------
# doi-fetch: _looks_like_pdf magic-prefix sniff
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data,expected",
    [
        (b"%PDF-1.4\n%\xe2\xe3\xcf\xd3", True),
        (b"<!DOCTYPE html><html></html>", False),
        (b"", False),
    ],
)
def test_looks_like_pdf(data, expected):
    assert _looks_like_pdf(data) is expected


# ---------------------------------------------------------------------------
# doi-fetch: default_paper_fetcher seam -- shape, PDF-first, landing path,
# and every give-up honest (all urllib behavior through patched _urlopen)
# ---------------------------------------------------------------------------

import inspect

from urllib.error import URLError

import contig.verification.paper_intake as paper_intake

from contig.verification.paper_intake import default_paper_fetcher


class _FakeResponse:
    """A context-manager file-like stand-in for a `urlopen` response."""

    def __init__(self, body: bytes, content_type: str = "text/html") -> None:
        self.body = body
        self.headers = {"Content-Type": content_type}
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n == -1:
            chunk = self.body[self._pos :]
            self._pos = len(self.body)
            return chunk
        chunk = self.body[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def close(self) -> None:
        pass

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


_PDF_BODY = b"%PDF-1.4\n1 0 obj\n%%EOF"


def test_default_paper_fetcher_is_callable_and_never_runs_in_ci(monkeypatch, tmp_path):
    # Shape: the seam is a 2-arg callable, and its urllib entry point is the
    # module-level `_urlopen`, which the test patches so a stray real call
    # (which would hit the network in CI) surfaces as a named refusal, never
    # a silent slip.
    assert callable(default_paper_fetcher)
    assert len(inspect.signature(default_paper_fetcher).parameters) == 2

    def fake_urlopen(url, **kwargs):
        raise RuntimeError("stray real call would hit the network")

    monkeypatch.setattr(paper_intake, "_urlopen", fake_urlopen)
    code, message = default_paper_fetcher("10.1/x", tmp_path / "paper.pdf")
    assert code != 0
    assert "stray real call" in message


def test_default_paper_fetcher_success_pdf_first(monkeypatch, tmp_path):
    calls = []

    def fake_urlopen(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse(_PDF_BODY, content_type="application/pdf")

    monkeypatch.setattr(paper_intake, "_urlopen", fake_urlopen)
    dest = tmp_path / "paper.pdf"
    code, message = default_paper_fetcher("10.1/x", dest)
    assert code == 0
    assert dest.read_bytes() == _PDF_BODY
    assert calls[0][0] == "https://doi.org/10.1/x"


def test_default_paper_fetcher_landing_page_path(monkeypatch, tmp_path):
    landing = (
        f'<html><head><meta name="citation_pdf_url" content="{_PDF_URL}">'
        "</head></html>"
    ).encode()
    urls = []

    def fake_urlopen(url, **kwargs):
        urls.append(url)
        if url == "https://doi.org/10.1/x":
            return _FakeResponse(landing)
        return _FakeResponse(_PDF_BODY, content_type="application/pdf")

    monkeypatch.setattr(paper_intake, "_urlopen", fake_urlopen)
    dest = tmp_path / "paper.pdf"
    code, message = default_paper_fetcher("10.1/x", dest)
    assert code == 0
    assert dest.read_bytes() == _PDF_BODY
    assert urls == ["https://doi.org/10.1/x", _PDF_URL]


def test_default_paper_fetcher_no_meta_gives_up_paywall_message(
    monkeypatch, tmp_path
):
    def fake_urlopen(url, **kwargs):
        return _FakeResponse(b"<html><head></head></html>")

    monkeypatch.setattr(paper_intake, "_urlopen", fake_urlopen)
    dest = tmp_path / "paper.pdf"
    code, message = default_paper_fetcher("10.1/x", dest)
    assert code != 0
    assert "paywalled" in message
    assert "path" in message
    assert not dest.exists()


def test_default_paper_fetcher_duplicate_metas_give_up_naming_count(
    monkeypatch, tmp_path
):
    html = (
        '<html><head>'
        '<meta name="citation_pdf_url" content="https://a.example.com/p.pdf">'
        '<meta name="citation_pdf_url" content="https://b.example.com/p.pdf">'
        "</head></html>"
    ).encode()

    def fake_urlopen(url, **kwargs):
        return _FakeResponse(html)

    monkeypatch.setattr(paper_intake, "_urlopen", fake_urlopen)
    dest = tmp_path / "paper.pdf"
    code, message = default_paper_fetcher("10.1/x", dest)
    assert code != 0
    assert "2" in message
    assert not dest.exists()


def test_default_paper_fetcher_urlopen_error_gives_up_with_reason(
    monkeypatch, tmp_path
):
    def fake_urlopen(url, **kwargs):
        raise URLError("no route to host")

    monkeypatch.setattr(paper_intake, "_urlopen", fake_urlopen)
    dest = tmp_path / "paper.pdf"
    dest.write_bytes(b"partial garbage")
    code, message = default_paper_fetcher("10.1/x", dest)
    assert code != 0
    assert "no route to host" in message
    assert not dest.exists()


def test_default_paper_fetcher_oversized_landing_gives_up_naming_bound(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(paper_intake, "_LANDING_READ_BOUND", 1024)

    def fake_urlopen(url, **kwargs):
        return _FakeResponse(b"<html>" + b"x" * 4096 + b"</html>")

    monkeypatch.setattr(paper_intake, "_urlopen", fake_urlopen)
    dest = tmp_path / "paper.pdf"
    code, message = default_paper_fetcher("10.1/x", dest)
    assert code != 0
    assert "1024" in message
    assert not dest.exists()


def test_default_paper_fetcher_urlopen_called_with_timeout(monkeypatch, tmp_path):
    calls = []

    def fake_urlopen(url, **kwargs):
        calls.append(kwargs)
        return _FakeResponse(_PDF_BODY, content_type="application/pdf")

    monkeypatch.setattr(paper_intake, "_urlopen", fake_urlopen)
    code, message = default_paper_fetcher("10.1/x", tmp_path / "paper.pdf")
    assert code == 0
    assert calls[0]["timeout"] == 30