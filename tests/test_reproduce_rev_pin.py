"""C8 slice 7: `contig reproduce --rev` -- check out a caller-named revision.

Slice 6 recorded `source_commit` but nothing consumed it: the clone was always
`--depth 1` of whatever HEAD happened to be at fetch time. This slice lets the
caller name the revision, so a bundle's pin can be handed back to Contig and
re-run.

No real git, network, or repo anywhere in this file -- the `Fetcher` seam is
injected throughout, per the standing C8 condition.
"""

from __future__ import annotations

import pytest

from contig.fetch import classify_rev_argument

# ---------------------------------------------------------------------------
# Phase 1: the pure --rev validator.
#
# Pure and deterministic -- no filesystem, subprocess, or network. Mirrors
# classify_repo_argument's shape (fetch.py:102) so the two read alike.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arg",
    [
        "a" * 40,  # full SHA -- the input that matters most (it IS source_commit)
        "A" * 40,  # uppercase SHA is still a full SHA
        "v2.1",  # tag
        "main",  # branch
        "feature/x",  # branch with a slash
        "release-1.0",
        "1.0.0",
    ],
)
def test_full_sha_tag_and_branch_are_accepted(arg):
    result = classify_rev_argument(arg)
    assert result.refusal is None
    assert result.rev == arg


@pytest.mark.parametrize("arg", ["v2.1", "FEATURE/X", "a" * 40])
def test_accepted_rev_is_preserved_verbatim_not_normalized(arg):
    # The rev becomes part of a provenance record, so it is kept exactly as
    # given -- same discipline as the https:// URL at fetch.py:113-115.
    assert classify_rev_argument(arg).rev == arg


@pytest.mark.parametrize(
    "arg",
    [
        "--upload-pack=/bin/sh",
        "-v2.1",
        "--depth",
        "-",
    ],
)
def test_leading_dash_is_refused(arg):
    # An option reaching `git fetch` in the ref position is an RCE shape.
    result = classify_rev_argument(arg)
    assert result.rev is None
    assert result.refusal is not None
    assert "option" in result.refusal.lower()


def test_leading_dash_is_refused_even_when_it_also_looks_like_a_sha():
    # The dash rule is checked FIRST and unconditionally: no other shape --
    # not even an otherwise-valid full SHA -- may bypass it.
    result = classify_rev_argument("-" + "a" * 39)
    assert result.rev is None
    assert "option" in result.refusal.lower()


@pytest.mark.parametrize("arg", ["", "   ", "\t", "\n"])
def test_empty_or_whitespace_only_is_refused(arg):
    result = classify_rev_argument(arg)
    assert result.rev is None
    assert result.refusal is not None


@pytest.mark.parametrize("arg", ["v2 1", "main\tx", "tag\nname", "a\x00b"])
def test_whitespace_or_control_characters_are_refused(arg):
    result = classify_rev_argument(arg)
    assert result.rev is None
    assert result.refusal is not None


@pytest.mark.parametrize(
    "arg",
    ["296569a", "296569ab", "a" * 7, "a" * 39, "0123456789abcdef"],
)
def test_short_sha_is_refused_naming_the_full_form(arg):
    # Verified against real git: `git fetch --depth 1 origin -- <7-hex>` fails
    # with "couldn't find remote ref" (exit 128) -- git cannot fetch an
    # abbreviated SHA at all. A 7-hex string is a perfectly valid refname, so
    # the refname rules below would NOT catch it; without this rule the user
    # gets a message that reads like a typo'd branch name.
    result = classify_rev_argument(arg)
    assert result.rev is None
    assert "40" in result.refusal


@pytest.mark.parametrize(
    "arg",
    [
        "v1..v2",
        "main~1",
        "main^",
        "refs:main",
        "what?",
        "glob*",
        "bracket[0]",
        "back\\slash",
        "/leading",
        "trailing/",
        ".leading",
        "trailing.",
        "branch.lock",
    ],
)
def test_refname_invalid_forms_are_refused(arg):
    result = classify_rev_argument(arg)
    assert result.rev is None
    assert result.refusal is not None


def test_rev_and_refusal_are_mutually_exclusive():
    from contig.fetch import RevArgument

    with pytest.raises(ValueError):
        RevArgument(rev="main", refusal="also refused")


def test_a_refusal_carries_no_rev():
    from contig.fetch import RevArgument

    refused = RevArgument.refuse("nope")
    assert refused.rev is None
    assert refused.refusal == "nope"


# ---------------------------------------------------------------------------
# Phase 2: the targeted-fetch argv builders.
#
# Asserted EXACTLY, as slice 6 asserts _git_clone_argv
# (test_reproduce_remote_intake.py:207). The real fetcher is never executed.
#
# Why a targeted fetch and not `git clone --depth 1 --branch <ref>`: --branch
# accepts a tag or branch ONLY and rejects a raw SHA -- and a raw SHA is the
# input that matters most, since it is what source_commit contains.
# ---------------------------------------------------------------------------


def test_git_init_argv_is_exact():
    from contig.runner import _git_init_argv

    assert _git_init_argv() == ["git", "init", "-q"]


def test_git_remote_add_argv_is_exact():
    from contig.runner import _git_remote_add_argv

    assert _git_remote_add_argv("https://github.com/lab/paper-code") == [
        "git",
        "remote",
        "add",
        "origin",
        "--",
        "https://github.com/lab/paper-code",
    ]


def test_git_fetch_argv_is_exact():
    from contig.runner import _git_fetch_argv

    assert _git_fetch_argv("v2.1") == [
        "git",
        "fetch",
        "--depth",
        "1",
        "origin",
        "--",
        "v2.1",
    ]


def test_git_checkout_argv_is_exact():
    from contig.runner import _git_checkout_argv

    # --detach is explicit so the detached state is intentional, not incidental.
    assert _git_checkout_argv() == ["git", "checkout", "--detach", "FETCH_HEAD"]


def test_remote_add_and_fetch_place_their_argument_after_the_dashdash():
    # The `--` terminator is the second line of defence behind the validator's
    # leading-dash refusal. Verified against real git that both subcommands
    # accept it.
    from contig.runner import _git_fetch_argv, _git_remote_add_argv

    remote_argv = _git_remote_add_argv("https://example.com/x")
    assert remote_argv[-2] == "--"
    assert remote_argv[-1] == "https://example.com/x"

    fetch_argv = _git_fetch_argv("main")
    assert fetch_argv[-2] == "--"
    assert fetch_argv[-1] == "main"
