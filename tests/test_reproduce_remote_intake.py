"""Boundary tests for C8 slice 6: remote-repo intake for `contig reproduce`.

Phase 1 -- the pure repo-argument classifier `classify_repo_argument` that
decides how `contig reproduce` should treat its `repo` argument -- local path,
remote https URL, or refusal. It does no I/O of any kind; a later phase adds
the fetching.

Phase 2 -- the injectable `Fetcher` seam in src/contig/runner.py (fixed git
argv builders + the default subprocess implementation) that a later task uses
to actually clone. `classify_repo_argument`/`RepoArgument` predate this file;
strict TDD applies to each phase as it's added.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contig.fetch import FetchResult, RepoArgument, classify_repo_argument, fetch_repo
from contig.runner import _git_clone_argv, _git_rev_parse_argv, default_fetcher


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


# ---------------------------------------------------------------------------
# Fetcher seam: fixed argv builders + the default subprocess implementation.
#
# `default_fetcher`'s success path (a real `git clone`/`git rev-parse` running
# against the network) is intentionally NEVER exercised here -- mirrors
# tests/verification/test_count_quantifier.py:1-8. Only the pure argv builders
# and the FileNotFoundError -> non-zero conversion (safe: touches no git, no
# network) are tested. A later task injects a fake Fetcher for the real
# clone-orchestration tests.
# ---------------------------------------------------------------------------


def test_git_clone_argv_is_exact():
    argv = _git_clone_argv("https://github.com/lab/paper-code", Path("/tmp/dest"))
    assert argv == [
        "git",
        "clone",
        "--depth",
        "1",
        "--",
        "https://github.com/lab/paper-code",
        "/tmp/dest",
    ]


def test_git_clone_argv_places_url_after_the_dashdash_terminator():
    # Asserting on index positions (not just membership) so a refactor that
    # drops the `--` terminator -- letting a crafted url be read as an option
    # -- fails this test.
    argv = _git_clone_argv("https://github.com/lab/paper-code", Path("/tmp/dest"))
    dashdash_index = argv.index("--")
    url_index = argv.index("https://github.com/lab/paper-code")
    assert url_index == dashdash_index + 1


def test_git_rev_parse_argv_is_exact():
    assert _git_rev_parse_argv() == ["git", "rev-parse", "HEAD"]


def test_default_fetcher_converts_missing_binary_to_nonzero_not_exception(tmp_path):
    # Deliberately non-existent executable name: touches no git, no network.
    code, output = default_fetcher(["contig-nonexistent-git-binary-xyz"], tmp_path)
    assert code != 0
    assert "contig-nonexistent-git-binary-xyz" in output


# ---------------------------------------------------------------------------
# Phase 3: fetch_repo -- clone -> resolve commit -> validate -> clean up.
#
# A scripted Fetcher stands in for the injected seam (mirrors _ScriptedInstaller
# in tests/test_reproduce_env_resurrection.py): it records every (argv, cwd)
# call and returns canned (exit_code, output) tuples in call order. A
# successful clone (call 1) also creates the destination directory named in
# the clone argv and drops a marker file into it -- the filesystem side-effect
# a real `git clone` would leave -- so assertions can check the checkout tree,
# not just the fetcher's own bookkeeping. No real git or network is touched
# anywhere in this section.
# ---------------------------------------------------------------------------


class _ScriptedFetcher:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, argv: list[str], cwd: Path) -> tuple[int, str]:
        self.calls.append((list(argv), Path(cwd)))
        code, output = self.script[len(self.calls) - 1]
        if len(self.calls) == 1 and code == 0:
            # Simulate `git clone`'s filesystem effect: the destination is the
            # last argv element (see _git_clone_argv).
            dest = Path(argv[-1])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "README.md").write_text("cloned fixture content\n")
        return code, output


_A_SHA = "a" * 40


def test_fetch_repo_happy_path_returns_path_and_exact_sha(tmp_path):
    dest = tmp_path / "rp_1" / "source"
    fetcher = _ScriptedFetcher(script=[(0, "Cloning into '...'\n"), (0, _A_SHA + "\n")])

    result = fetch_repo("https://github.com/lab/paper-code", dest, fetcher=fetcher)

    assert result.refusal is None
    assert result.path == dest
    assert result.commit == _A_SHA
    assert (dest / "README.md").exists()

    assert len(fetcher.calls) == 2
    clone_argv, clone_cwd = fetcher.calls[0]
    assert clone_argv == _git_clone_argv("https://github.com/lab/paper-code", dest)
    # dest does not exist as a git repo yet -- the parent is the sensible cwd.
    assert clone_cwd == dest.parent
    rev_argv, rev_cwd = fetcher.calls[1]
    assert rev_argv == _git_rev_parse_argv()
    # rev-parse must run INSIDE the checkout.
    assert rev_cwd == dest


def test_fetch_repo_refuses_non_empty_destination_and_leaves_it_untouched(tmp_path):
    dest = tmp_path / "rp_1" / "source"
    dest.mkdir(parents=True)
    (dest / "existing.txt").write_text("do not touch")
    fetcher = _ScriptedFetcher(script=[])

    result = fetch_repo("https://github.com/lab/paper-code", dest, fetcher=fetcher)

    assert result.refusal is not None
    assert result.path is None
    assert result.commit is None
    assert (dest / "existing.txt").read_text() == "do not touch"
    assert fetcher.calls == []


def test_fetch_repo_clone_failure_refuses_naming_output_and_leaves_no_directory(tmp_path):
    dest = tmp_path / "rp_1" / "source"
    fetcher = _ScriptedFetcher(script=[(128, "fatal: repository 'x' not found")])

    result = fetch_repo("https://github.com/lab/paper-code", dest, fetcher=fetcher)

    assert result.refusal is not None
    assert "fatal: repository 'x' not found" in result.refusal
    assert not dest.exists()
    assert not dest.parent.exists()


def test_fetch_repo_rev_parse_failure_refuses_and_leaves_no_directory(tmp_path):
    dest = tmp_path / "rp_1" / "source"
    fetcher = _ScriptedFetcher(
        script=[(0, "Cloning into '...'\n"), (128, "fatal: not a git repository")]
    )

    result = fetch_repo("https://github.com/lab/paper-code", dest, fetcher=fetcher)

    assert result.refusal is not None
    assert "fatal: not a git repository" in result.refusal
    assert not dest.exists()
    assert not dest.parent.exists()


@pytest.mark.parametrize(
    "rev_output",
    [
        "",
        "a1b2c3d",  # abbreviated (7 hex chars)
        "g" + "a" * 39,  # 40 chars but one is non-hex
    ],
    ids=["empty", "abbreviated", "non-hex-char"],
)
def test_fetch_repo_refuses_non_40_hex_rev_parse_output(tmp_path, rev_output):
    dest = tmp_path / "rp_1" / "source"
    fetcher = _ScriptedFetcher(script=[(0, "Cloning into '...'\n"), (0, rev_output)])

    result = fetch_repo("https://github.com/lab/paper-code", dest, fetcher=fetcher)

    assert result.refusal is not None
    assert result.commit is None
    assert not dest.exists()
    assert not dest.parent.exists()


def test_fetch_repo_strips_trailing_newline_from_an_otherwise_valid_sha(tmp_path):
    dest = tmp_path / "rp_1" / "source"
    fetcher = _ScriptedFetcher(script=[(0, "Cloning into '...'\n"), (0, _A_SHA + "\n")])

    result = fetch_repo("https://github.com/lab/paper-code", dest, fetcher=fetcher)

    assert result.refusal is None
    assert result.commit == _A_SHA


def test_fetch_repo_refuses_multiline_rev_parse_output_even_with_a_valid_sha_present(tmp_path):
    # Sharp edge: default_fetcher merges stderr into stdout, so a warning line
    # can ride alongside a genuinely valid SHA. Scavenging a SHA-looking token
    # out of multi-line output risks recording a commit that is not actually
    # HEAD -- a false pin is worse than a refusal -- so the WHOLE stripped
    # output must be exactly one 40-hex SHA, or this refuses.
    dest = tmp_path / "rp_1" / "source"
    rev_output = f"warning: redirecting to canonical URL\n{_A_SHA}\n"
    fetcher = _ScriptedFetcher(script=[(0, "Cloning into '...'\n"), (0, rev_output)])

    result = fetch_repo("https://github.com/lab/paper-code", dest, fetcher=fetcher)

    assert result.refusal is not None
    assert result.commit is None
    assert not dest.exists()
    assert not dest.parent.exists()


def test_fetch_repo_cleanup_preserves_a_parent_the_caller_already_owned(tmp_path):
    # When <reproduce_id>/ already existed before this call (the caller put
    # other state there), a failure must remove only the source/ subtree this
    # function itself created -- never a parent it does not own.
    parent = tmp_path / "rp_1"
    parent.mkdir()
    (parent / "manifest.json").write_text("{}")
    dest = parent / "source"
    fetcher = _ScriptedFetcher(script=[(128, "fatal: repository 'x' not found")])

    result = fetch_repo("https://github.com/lab/paper-code", dest, fetcher=fetcher)

    assert result.refusal is not None
    assert not dest.exists()
    assert parent.exists()
    assert (parent / "manifest.json").read_text() == "{}"


def test_fetch_result_refusal_cannot_be_constructed_with_a_path_or_commit():
    with pytest.raises(ValueError):
        FetchResult(path=Path("/tmp/x"), commit=None, refusal="not allowed")
