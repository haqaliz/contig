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


# ---------------------------------------------------------------------------
# Phase 3: fetch_repo's targeted-fetch branch.
#
# A scripted Fetcher stands in for the injected seam (mirrors _ScriptedFetcher
# in test_reproduce_remote_intake.py:254). The difference from the clone path:
# `git init` (call 1) creates nothing new -- fetch_repo already created dest --
# and it is the CHECKOUT (call 4) that materialises the worktree files.
# ---------------------------------------------------------------------------

_A_SHA = "a" * 40
_B_SHA = "b" * 40
_URL = "https://github.com/lab/paper-code"


class _ScriptedRevFetcher:
    """Records every (argv, cwd) and returns canned (exit_code, output) in order."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[tuple[list[str], object]] = []

    def __call__(self, argv, cwd):
        from pathlib import Path

        self.calls.append((list(argv), Path(cwd)))
        code, output = self.script[len(self.calls) - 1]
        # The checkout is what puts files in the worktree.
        if argv[:2] == ["git", "checkout"] and code == 0:
            (Path(cwd) / "README.md").write_text("checked-out fixture content\n")
        return code, output


def _ok_script(sha=_A_SHA):
    """init, remote add, fetch, checkout, rev-parse -- all succeeding."""
    return [(0, ""), (0, ""), (0, ""), (0, ""), (0, sha + "\n")]


@pytest.mark.parametrize("rev", ["a" * 40, "v2.1", "main"])
def test_targeted_fetch_happy_path_returns_path_and_sha(tmp_path, rev):
    from contig.fetch import fetch_repo
    from contig.runner import (
        _git_checkout_argv,
        _git_fetch_argv,
        _git_init_argv,
        _git_remote_add_argv,
        _git_rev_parse_argv,
    )

    dest = tmp_path / "rp_1" / "source"
    # A tag/branch resolves to whatever the remote says; a full SHA must match
    # itself (asserted separately below).
    sha = rev if len(rev) == 40 else _A_SHA
    fetcher = _ScriptedRevFetcher(_ok_script(sha))

    result = fetch_repo(_URL, dest, fetcher=fetcher, rev=rev)

    assert result.refusal is None
    assert result.path == dest
    assert result.commit == sha
    assert (dest / "README.md").exists()

    # Exactly five calls, in order, EVERY ONE with dest as cwd -- unlike the
    # clone path, which runs in dest.parent. `git init` makes dest a repo, so
    # every later step runs inside it.
    assert [argv for argv, _ in fetcher.calls] == [
        _git_init_argv(),
        _git_remote_add_argv(_URL),
        _git_fetch_argv(rev),
        _git_checkout_argv(),
        _git_rev_parse_argv(),
    ]
    assert all(cwd == dest for _, cwd in fetcher.calls)


def test_no_rev_keeps_the_slice6_clone_path_byte_identical(tmp_path):
    """The back-compat guarantee: rev=None must behave exactly as slice 6 did."""
    from contig.fetch import fetch_repo
    from contig.runner import _git_clone_argv, _git_rev_parse_argv

    dest = tmp_path / "rp_1" / "source"

    class _CloneFetcher:
        def __init__(self):
            self.calls = []

        def __call__(self, argv, cwd):
            from pathlib import Path

            self.calls.append((list(argv), Path(cwd)))
            if len(self.calls) == 1:
                Path(argv[-1]).mkdir(parents=True, exist_ok=True)
                return 0, "Cloning...\n"
            return 0, _A_SHA + "\n"

    fetcher = _CloneFetcher()
    result = fetch_repo(_URL, dest, fetcher=fetcher)

    assert result.commit == _A_SHA
    assert [argv for argv, _ in fetcher.calls] == [
        _git_clone_argv(_URL, dest),
        _git_rev_parse_argv(),
    ]
    assert fetcher.calls[0][1] == dest.parent


@pytest.mark.parametrize("failing_step", [0, 1, 2, 3, 4])
def test_each_git_step_failing_refuses_and_leaves_no_directory(tmp_path, failing_step):
    from contig.fetch import fetch_repo

    dest = tmp_path / "rp_1" / "source"
    script = _ok_script()
    script[failing_step] = (128, "fatal: something went wrong\n")
    fetcher = _ScriptedRevFetcher(script)

    result = fetch_repo(_URL, dest, fetcher=fetcher, rev="v2.1")

    assert result.path is None
    assert result.commit is None
    assert result.refusal is not None
    assert "something went wrong" in result.refusal
    # This call created dest.parent, so cleanup removes it entirely -- no
    # half-fetched directory left looking like a real run bundle.
    assert not dest.exists()
    assert not dest.parent.exists()


def test_failed_fetch_does_not_remove_a_parent_it_did_not_create(tmp_path):
    from contig.fetch import fetch_repo

    parent = tmp_path / "rp_1"
    parent.mkdir(parents=True)
    (parent / "other_run_state.json").write_text("{}")
    dest = parent / "source"

    script = _ok_script()
    script[2] = (128, "fatal: bad ref\n")
    result = fetch_repo(_URL, dest, fetcher=_ScriptedRevFetcher(script), rev="v2.1")

    assert result.refusal is not None
    assert not dest.exists()
    # The caller owned this directory; a failed fetch must not delete it.
    assert (parent / "other_run_state.json").exists()


def test_requested_full_sha_must_equal_the_resolved_sha(tmp_path):
    """R4: never record a pin that isn't what the caller asked for."""
    from contig.fetch import fetch_repo

    dest = tmp_path / "rp_1" / "source"
    # Asked for _A_SHA; the checkout resolved to _B_SHA.
    fetcher = _ScriptedRevFetcher(_ok_script(_B_SHA))

    result = fetch_repo(_URL, dest, fetcher=fetcher, rev=_A_SHA)

    assert result.commit is None
    assert result.refusal is not None
    assert _A_SHA in result.refusal and _B_SHA in result.refusal
    assert not dest.exists()


def test_requested_sha_matching_case_insensitively_is_accepted_and_lowercased(tmp_path):
    from contig.fetch import fetch_repo

    dest = tmp_path / "rp_1" / "source"
    fetcher = _ScriptedRevFetcher(_ok_script(_A_SHA.upper()))

    result = fetch_repo(_URL, dest, fetcher=fetcher, rev=_A_SHA)

    assert result.refusal is None
    assert result.commit == _A_SHA  # recorded lowercase


def test_a_tag_has_no_sha_to_compare_against_so_any_resolved_sha_is_kept(tmp_path):
    from contig.fetch import fetch_repo

    dest = tmp_path / "rp_1" / "source"
    result = fetch_repo(
        _URL, dest, fetcher=_ScriptedRevFetcher(_ok_script(_B_SHA)), rev="v2.1"
    )

    assert result.refusal is None
    assert result.commit == _B_SHA


def test_remote_refusing_fetch_by_commit_names_the_likely_cause(tmp_path):
    """R6/D1: honest refusal, never a silent fallback to a full clone."""
    from contig.fetch import fetch_repo

    dest = tmp_path / "rp_1" / "source"
    script = _ok_script()
    script[2] = (128, f"fatal: git upload-pack: not our ref {_A_SHA}\n")

    result = fetch_repo(_URL, dest, fetcher=_ScriptedRevFetcher(script), rev=_A_SHA)

    assert result.refusal is not None
    assert "allowReachableSHA1InWant" in result.refusal
    # And it tells the user what to do instead.
    assert "tag" in result.refusal.lower() or "branch" in result.refusal.lower()


def test_an_ordinary_fetch_failure_does_not_claim_the_sha_cause(tmp_path):
    from contig.fetch import fetch_repo

    dest = tmp_path / "rp_1" / "source"
    script = _ok_script()
    script[2] = (128, "fatal: could not read Username for 'https://host'\n")

    result = fetch_repo(_URL, dest, fetcher=_ScriptedRevFetcher(script), rev="v2.1")

    assert result.refusal is not None
    assert "allowReachableSHA1InWant" not in result.refusal


def test_unvalidated_rev_parse_output_is_still_refused_on_the_rev_path(tmp_path):
    from contig.fetch import fetch_repo

    dest = tmp_path / "rp_1" / "source"
    script = _ok_script()
    script[4] = (0, "warning: something\n" + _A_SHA + "\n")

    result = fetch_repo(_URL, dest, fetcher=_ScriptedRevFetcher(script), rev="v2.1")

    # Multi-line output is refused outright, never scavenged for a SHA.
    assert result.commit is None
    assert result.refusal is not None
    assert not dest.exists()


def test_non_empty_destination_is_refused_before_any_git_runs(tmp_path):
    from contig.fetch import fetch_repo

    dest = tmp_path / "rp_1" / "source"
    dest.mkdir(parents=True)
    (dest / "existing.txt").write_text("do not touch")
    fetcher = _ScriptedRevFetcher(_ok_script())

    result = fetch_repo(_URL, dest, fetcher=fetcher, rev="v2.1")

    assert result.refusal is not None
    assert fetcher.calls == []
    assert (dest / "existing.txt").read_text() == "do not touch"


# ---------------------------------------------------------------------------
# Phase 4: requested_rev in the UNSIGNED invocation manifest.
#
# D2: the requested ref is invocation metadata, not an attested fact. It goes
# in reproduce.json, which is not signed -- so every v0.47.0 signed reproduce
# bundle keeps verifying. The resolved source_commit remains the attested pin.
# ---------------------------------------------------------------------------


def _a_record():
    from contig.models import ClaimResult, ReproduceRecord

    return ReproduceRecord(
        reproduce_id="rp_1",
        repo=_URL,
        run_command="python train.py",
        claims_sha256="a" * 64,
        claim_results=[
            ClaimResult(
                id="c1",
                status="reproduced",
                claimed=0.9,
                observed=0.9,
                tolerance=0.02,
                delta=0.0,
                message="ok",
            )
        ],
        exit_code=0,
        created_at="2026-07-23T00:00:00Z",
        interpreter="cpython-3.12",
        tool="contig",
        source_url=_URL,
        source_commit=_A_SHA,
    )


def test_requested_rev_is_written_to_the_manifest(tmp_path):
    import json

    from contig.bundle import write_reproduce_bundle

    write_reproduce_bundle(_a_record(), tmp_path, requested_rev="v2.1")

    manifest = json.loads((tmp_path / "reproduce.json").read_text())
    assert manifest["requested_rev"] == "v2.1"
    assert manifest["source_commit"] == _A_SHA


def test_requested_rev_is_emitted_unconditionally_as_null_when_absent(tmp_path):
    import json

    from contig.bundle import write_reproduce_bundle

    write_reproduce_bundle(_a_record(), tmp_path)

    manifest = json.loads((tmp_path / "reproduce.json").read_text())
    # Present and null -- a consumer never needs a .get() dance, matching how
    # source_url/source_commit are emitted.
    assert "requested_rev" in manifest
    assert manifest["requested_rev"] is None


def test_requested_rev_does_not_change_the_signature(tmp_path):
    """D2's whole point: adding a manifest key breaks no existing signature."""
    import json

    from contig.bundle import write_reproduce_bundle
    from contig.signing import generate_keypair, signing_available, verify_signature

    if not signing_available():
        pytest.skip("signing backend unavailable")

    private_key, _ = generate_keypair()
    record = _a_record()

    unpinned = tmp_path / "unpinned"
    pinned = tmp_path / "pinned"
    import os

    os.environ["CONTIG_SIGNING_KEY"] = private_key
    try:
        write_reproduce_bundle(record, unpinned)
        write_reproduce_bundle(record, pinned, requested_rev="v2.1")
    finally:
        del os.environ["CONTIG_SIGNING_KEY"]

    sig_a = json.loads((unpinned / "signature.json").read_text())
    sig_b = json.loads((pinned / "signature.json").read_text())

    # Same record -> same signed payload, regardless of the manifest field.
    assert sig_a["signed_sha256"] == sig_b["signed_sha256"]
    assert verify_signature(record, sig_b["signature"], sig_b["public_key"])


# ---------------------------------------------------------------------------
# Phase 5: CLI wiring.
#
# Drives the real `reproduce` command through CliRunner with two seams faked
# (Fetcher, command executor), following test_reproduce_remote_intake.py:413.
# ---------------------------------------------------------------------------

import json  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

from typer.testing import CliRunner  # noqa: E402

from contig.cli import app  # noqa: E402

runner = CliRunner()


class _ScriptedRevCheckoutFetcher:
    """Simulates the 5-call targeted fetch, materializing the tree at CHECKOUT.

    `files` are written by the checkout call -- the step that actually puts
    files in the worktree -- so each file's mtime is the checkout instant,
    exactly as a real fetch+checkout leaves it. `settle` makes that instant
    measurably earlier than anything the CLI stamps afterwards, so the
    ordering assertion cannot flake on a shared float mtime.
    """

    def __init__(self, files=None, commit=_A_SHA, fail_at=None, fail_output="", settle=0.05):
        self.files = dict(files or {})
        self.commit = commit
        self.fail_at = fail_at
        self.fail_output = fail_output
        self.settle = settle
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, argv, cwd):
        self.calls.append((list(argv), Path(cwd)))
        idx = len(self.calls) - 1
        if self.fail_at == idx:
            return 128, self.fail_output
        if argv[:2] == ["git", "checkout"]:
            for name, text in self.files.items():
                path = Path(cwd) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            time.sleep(self.settle)
            return 0, ""
        if argv[:2] == ["git", "rev-parse"]:
            return 0, self.commit + "\n"
        return 0, ""


def _claims_file(tmp_path, claims):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(claims))
    return path


def _bundle_dirs(runs_dir):
    if not runs_dir.exists():
        return []
    return sorted(p for p in runs_dir.iterdir() if p.is_dir())


def _read_record(runs_dir):
    (bundle,) = _bundle_dirs(runs_dir)
    return json.loads((bundle / "reproduce_record.json").read_text())


def _invoke(claims, runs_dir, *, repo=_URL, extra=()):
    return runner.invoke(
        app,
        [
            "reproduce",
            repo,
            "--run",
            "python eval.py",
            "--claims",
            str(claims),
            "--runs-dir",
            str(runs_dir),
            *extra,
        ],
    )


def test_committed_results_in_a_rev_checkout_stays_unverified(tmp_path, monkeypatch):
    """The ordering regression (spec criterion 11, PRD RISK-2).

    The checkout must happen BEFORE run_started_at is stamped. If it were
    stamped first, every author-committed artifact would look freshly written
    by this run and the freshness guard would be silently disabled on exactly
    the published repos it exists for.

    Here the repo COMMITS a results.json whose value exactly equals the claim.
    A correct implementation reports `unverified`; an incorrectly-ordered one
    reports `reproduced`.
    """
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedRevCheckoutFetcher(files={"results.json": json.dumps({"auc": 0.9})})
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    # The run itself writes nothing -- the only results.json is the committed one.
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(claims, runs_dir, extra=["--allow-fetch", "--rev", "v2.1"])

    assert result.exit_code == 0, result.output
    (claim,) = _read_record(runs_dir)["claim_results"]
    assert claim["status"] == "unverified"


def test_rev_run_records_the_requested_ref_and_the_resolved_commit(tmp_path, monkeypatch):
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedRevCheckoutFetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        lambda cmd, cwd: (
            (cwd / "results.json").write_text(json.dumps({"auc": 0.9})),
            (0, ""),
        )[1],
    )

    result = _invoke(claims, runs_dir, extra=["--allow-fetch", "--rev", "v2.1"])

    assert result.exit_code == 0, result.output
    record = _read_record(runs_dir)
    assert record["source_commit"] == _A_SHA
    assert record["repo"] == _URL

    (bundle,) = _bundle_dirs(runs_dir)
    manifest = json.loads((bundle / "reproduce.json").read_text())
    assert manifest["requested_rev"] == "v2.1"
    assert manifest["source_commit"] == _A_SHA

    # The targeted fetch ran, not a clone.
    assert [argv[:2] for argv, _ in fetcher.calls] == [
        ["git", "init"],
        ["git", "remote"],
        ["git", "fetch"],
        ["git", "checkout"],
        ["git", "rev-parse"],
    ]


def test_rev_with_a_local_repo_is_refused_before_anything_is_written(tmp_path, monkeypatch):
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    local_repo = tmp_path / "repo"
    local_repo.mkdir()
    fetcher = _ScriptedRevCheckoutFetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(claims, runs_dir, repo=str(local_repo), extra=["--rev", "v2.1"])

    assert result.exit_code != 0
    assert "--rev" in result.output
    assert fetcher.calls == []
    assert _bundle_dirs(runs_dir) == []


def test_rev_without_allow_fetch_hits_the_existing_allow_fetch_refusal(tmp_path, monkeypatch):
    """The URL is refused first, naming --allow-fetch -- precedence is pinned."""
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedRevCheckoutFetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(claims, runs_dir, extra=["--rev", "v2.1"])

    assert result.exit_code != 0
    assert "--allow-fetch" in result.output
    assert fetcher.calls == []
    assert _bundle_dirs(runs_dir) == []


@pytest.mark.parametrize("bad_rev", ["--upload-pack=/bin/sh", "296569a", "main~1", ""])
def test_invalid_rev_is_refused_before_any_git_runs(tmp_path, monkeypatch, bad_rev):
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedRevCheckoutFetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(claims, runs_dir, extra=["--allow-fetch", "--rev", bad_rev])

    assert result.exit_code != 0
    assert fetcher.calls == []
    assert _bundle_dirs(runs_dir) == []


def test_failed_rev_fetch_exits_nonzero_and_leaves_no_bundle(tmp_path, monkeypatch):
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedRevCheckoutFetcher(
        fail_at=2, fail_output=f"fatal: git upload-pack: not our ref {_A_SHA}\n"
    )
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(claims, runs_dir, extra=["--allow-fetch", "--rev", _A_SHA])

    assert result.exit_code != 0
    assert "allowReachableSHA1InWant" in result.output
    assert _bundle_dirs(runs_dir) == []


def test_no_rev_remote_run_still_clones_and_records_null_requested_rev(tmp_path, monkeypatch):
    """Back-compat (spec criterion 12): the slice-6 path is unchanged."""
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"

    class _CloneFetcher:
        def __init__(self):
            self.calls = []

        def __call__(self, argv, cwd):
            self.calls.append((list(argv), Path(cwd)))
            if len(self.calls) == 1:
                Path(argv[-1]).mkdir(parents=True, exist_ok=True)
                time.sleep(0.05)
                return 0, "Cloning...\n"
            return 0, _A_SHA + "\n"

    fetcher = _CloneFetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        lambda cmd, cwd: (
            (cwd / "results.json").write_text(json.dumps({"auc": 0.9})),
            (0, ""),
        )[1],
    )

    result = _invoke(claims, runs_dir, extra=["--allow-fetch"])

    assert result.exit_code == 0, result.output
    assert [argv[:2] for argv, _ in fetcher.calls] == [
        ["git", "clone"],
        ["git", "rev-parse"],
    ]
    (bundle,) = _bundle_dirs(runs_dir)
    manifest = json.loads((bundle / "reproduce.json").read_text())
    assert manifest["requested_rev"] is None
