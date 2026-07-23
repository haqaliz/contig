"""Boundary tests for C8 slice 6 phase 1: the pure repo-argument classifier
`classify_repo_argument` that decides how `contig reproduce` should treat its
`repo` argument -- local path, remote https URL, or refusal.

Strict TDD: this file is written before `classify_repo_argument`/`RepoArgument`
exist in src/contig/fetch.py.

`classify_repo_argument` does no I/O of any kind. It only classifies the
string; a later slice adds the fetching.
"""

from __future__ import annotations

import pytest

from contig.fetch import RepoArgument, classify_repo_argument


# ---------------------------------------------------------------------------
# accepted: https
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg",
    [
        "https://github.com/lab/paper-code",
        "https://github.com/lab/paper-code.git",
        "HTTPS://github.com/lab/paper-code",
        "HttpS://github.com/lab/paper-code.git",
    ],
)
def test_https_url_is_accepted_as_remote(arg):
    result = classify_repo_argument(arg)
    assert result.kind == "remote"
    assert result.refusal is None


@pytest.mark.parametrize(
    "arg",
    [
        "https://github.com/lab/paper-code",
        "https://github.com/lab/paper-code.git",
        "HTTPS://github.com/lab/paper-code",
    ],
)
def test_https_url_is_preserved_verbatim_not_normalized(arg):
    # The recorded URL becomes part of a provenance record -- it must be the
    # exact string the user passed, not a lowercased/normalized rewrite.
    result = classify_repo_argument(arg)
    assert result.url == arg


# ---------------------------------------------------------------------------
# accepted: local paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arg", ["x", "./x", "/abs/x", "../x", "~/x"])
def test_plain_path_is_accepted_as_local(arg):
    result = classify_repo_argument(arg)
    assert result.kind == "local"
    assert result.refusal is None


# ---------------------------------------------------------------------------
# refused: leading dash (checked first, before any scheme parsing)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arg", ["--upload-pack=/bin/sh", "-x", "-"])
def test_leading_dash_is_refused(arg):
    result = classify_repo_argument(arg)
    assert result.kind is None
    assert result.refusal is not None


def test_leading_dash_is_refused_even_when_it_also_looks_like_a_url():
    # A crafted argument that starts with "-" must be refused before any
    # scheme is inspected, so no clever prefix can smuggle an option past the
    # dash check by also looking like an accepted https:// URL.
    result = classify_repo_argument("-https://evil/--upload-pack=/bin/sh")
    assert result.kind is None
    assert result.refusal is not None


# ---------------------------------------------------------------------------
# refused: wrong scheme
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg",
    [
        "http://github.com/lab/repo",
        "HTTP://github.com/lab/repo",
        "ssh://git@github.com/lab/repo.git",
        "SSH://git@github.com/lab/repo.git",
        "git://github.com/lab/repo.git",
        "GIT://github.com/lab/repo.git",
        "file:///tmp/x",
        "FILE:///tmp/x",
        "ext::sh -c x",
        "EXT::sh -c x",
    ],
)
def test_wrong_scheme_is_refused(arg):
    result = classify_repo_argument(arg)
    assert result.kind is None
    assert result.refusal is not None
    assert "https" in result.refusal.lower()


# ---------------------------------------------------------------------------
# refused: scp-like syntax
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg",
    [
        "git@github.com:lab/repo.git",
        "GIT@github.com:lab/repo.git",
        "user@host:path",
    ],
)
def test_scp_like_syntax_is_refused(arg):
    result = classify_repo_argument(arg)
    assert result.kind is None
    assert result.refusal is not None
    assert "https" in result.refusal.lower()


# ---------------------------------------------------------------------------
# refused: DOI (named explicitly, so the user isn't sent to debug the wrong
# thing -- falling through to the local-path branch would instead report
# something like "No such repo directory: 10.1234/xyz")
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg",
    [
        "doi:10.1234/abc",
        "DOI:10.1234/abc",
        "Doi:10.1234/ABC",
        "10.1234/abc",
        "10.5555/some.suffix",
    ],
)
def test_doi_is_refused_naming_doi_explicitly(arg):
    result = classify_repo_argument(arg)
    assert result.kind is None
    assert result.refusal is not None
    assert "doi" in result.refusal.lower()


# ---------------------------------------------------------------------------
# invariant: exactly one of (kind set) / (refusal set)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg",
    [
        "https://github.com/lab/paper-code",
        "x",
        "-x",
        "http://github.com/lab/repo",
        "git@github.com:lab/repo.git",
        "doi:10.1234/abc",
    ],
)
def test_kind_and_refusal_are_mutually_exclusive(arg):
    result = classify_repo_argument(arg)
    assert (result.kind is None) != (result.refusal is None)


def test_refusal_cannot_be_constructed_with_a_kind():
    with pytest.raises(ValueError):
        RepoArgument(kind="local", url=None, refusal="not allowed")
