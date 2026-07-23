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

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contig.cli import app
from contig.fetch import FetchResult, RepoArgument, classify_repo_argument, fetch_repo
from contig.runner import _git_clone_argv, _git_rev_parse_argv, default_fetcher

runner = CliRunner()


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


# ---------------------------------------------------------------------------
# Phase 4: the CLI wiring -- `contig reproduce <https url> --allow-fetch`.
#
# These drive the real `reproduce` command through CliRunner with two seams
# faked: the Fetcher (no git, no network) and the command executor (no
# subprocess), following tests/test_cli_reproduce.py's conventions.
#
# The fetcher below materializes a checkout tree the way a real `git clone`
# does -- every file written AT CLONE TIME -- because the ordering of the
# clone against the CLI's `run_started_at` freshness stamp is precisely what
# the first test in this section pins.
# ---------------------------------------------------------------------------


class _ScriptedCheckoutFetcher:
    """A Fetcher that simulates `git clone` by materializing a checkout tree.

    `files` maps checkout-relative paths to text. The clone call (call 1)
    writes them into the destination named in the clone argv, so each file's
    mtime is the CLONE INSTANT -- exactly as a real clone leaves it. Call 2
    is `git rev-parse HEAD` and returns `commit`.

    `settle` sleeps briefly after the write so the clone instant is
    measurably earlier than anything the CLI timestamps afterwards; without
    it a correctly-ordered clone could share a float mtime with the stamp
    taken microseconds later and make the freshness assertion flaky.
    """

    def __init__(
        self,
        files=None,
        commit=_A_SHA,
        clone_code=0,
        clone_output="Cloning into '...'\n",
        settle=0.05,
    ):
        self.files = dict(files or {})
        self.commit = commit
        self.clone_code = clone_code
        self.clone_output = clone_output
        self.settle = settle
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, argv: list[str], cwd: Path) -> tuple[int, str]:
        self.calls.append((list(argv), Path(cwd)))
        if len(self.calls) == 1:
            if self.clone_code != 0:
                return self.clone_code, self.clone_output
            dest = Path(argv[-1])
            for name, text in self.files.items():
                path = dest / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            time.sleep(self.settle)
            return 0, self.clone_output
        return 0, self.commit + "\n"


_URL = "https://github.com/lab/paper-code"


def _claims_file(tmp_path, claims):
    path = tmp_path / "claims.json"
    path.write_text(json.dumps(claims))
    return path


def _bundle_dirs(runs_dir: Path) -> list[Path]:
    if not runs_dir.exists():
        return []
    return sorted(p for p in runs_dir.iterdir() if p.is_dir())


def _read_record(runs_dir: Path) -> dict:
    (bundle,) = _bundle_dirs(runs_dir)
    return json.loads((bundle / "reproduce_record.json").read_text())


def _invoke(tmp_path, claims, runs_dir, *, repo=_URL, extra=()):
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


def test_committed_results_file_in_a_fetched_checkout_stays_unverified(
    tmp_path, monkeypatch
):
    """THE freshness regression: a clone must precede the run-start stamp.

    The checkout ships a COMMITTED results.json whose value exactly equals the
    claim, and the run rewrites nothing. If the clone runs before the
    `run_started_at` stamp (correct), every cloned file is older than the
    boundary and the claim stays UNVERIFIED. If the clone runs after the stamp,
    every author-committed artifact looks freshly written and this reports a
    false REPRODUCED -- the exact hole the freshness guard exists to close, on
    the one code path (real published repos) where it matters most.
    """
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedCheckoutFetcher(files={"results.json": json.dumps({"auc": 0.9})})
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    # The run itself writes nothing: only the authors' committed file is on disk.
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(tmp_path, claims, runs_dir, extra=["--allow-fetch"])

    assert result.exit_code == 0, result.output
    record = _read_record(runs_dir)
    (claim,) = record["claim_results"]
    assert claim["status"] == "unverified", record


def test_remote_url_without_allow_fetch_is_refused_and_writes_no_bundle(
    tmp_path, monkeypatch
):
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedCheckoutFetcher(files={"results.json": json.dumps({"auc": 0.9})})
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(tmp_path, claims, runs_dir)

    assert result.exit_code != 0
    assert "--allow-fetch" in result.output
    assert fetcher.calls == []
    assert _bundle_dirs(runs_dir) == []


def test_remote_run_records_source_url_and_commit_and_keeps_repo_as_the_url(
    tmp_path, monkeypatch
):
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedCheckoutFetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        lambda cmd, cwd: ((cwd / "results.json").write_text(json.dumps({"auc": 0.9})), (0, ""))[1],
    )

    result = _invoke(tmp_path, claims, runs_dir, extra=["--allow-fetch"])

    assert result.exit_code == 0, result.output
    record = _read_record(runs_dir)
    assert record["source_url"] == _URL
    assert record["source_commit"] == _A_SHA
    # The URL, never the local scratch checkout path.
    assert record["repo"] == _URL

    (bundle,) = _bundle_dirs(runs_dir)
    manifest = json.loads((bundle / "reproduce.json").read_text())
    assert manifest["source_url"] == _URL
    assert manifest["source_commit"] == _A_SHA
    assert manifest["repo"] == _URL

    (claim,) = record["claim_results"]
    assert claim["status"] == "reproduced"


def test_failed_fetch_exits_nonzero_and_leaves_no_bundle_directory(tmp_path, monkeypatch):
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedCheckoutFetcher(
        clone_code=128, clone_output="fatal: repository not found"
    )
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(tmp_path, claims, runs_dir, extra=["--allow-fetch"])

    assert result.exit_code != 0
    assert "clone" in result.output.lower()
    assert _bundle_dirs(runs_dir) == []


def test_locator_escaping_the_repo_is_refused_before_any_clone(tmp_path, monkeypatch):
    """Containment must still bite in remote mode.

    Joining onto a raw URL string would make the guard a lexical no-op
    (`Path("https://x/y") / "../../etc/passwd"` resolves "inside"
    `Path("https://x/y")`), silently disabling it exactly when the repo is
    untrusted third-party code. The guard runs against the prospective
    checkout path, so it refuses BEFORE the clone -- asserted here by the
    fetcher never being called.
    """
    claims = _claims_file(
        tmp_path,
        [{"id": "auc", "value": 0.9, "from": "../../etc/passwd", "path": "auc"}],
    )
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedCheckoutFetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(tmp_path, claims, runs_dir, extra=["--allow-fetch"])

    assert result.exit_code != 0
    assert "escapes the repo" in result.output
    assert fetcher.calls == []
    assert _bundle_dirs(runs_dir) == []


def test_results_path_escaping_the_repo_is_refused_before_any_clone(tmp_path, monkeypatch):
    claims = _claims_file(tmp_path, [{"id": "auc", "value": 0.9}])
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedCheckoutFetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr("contig.cli.default_command_executor", lambda cmd, cwd: (0, ""))

    result = _invoke(
        tmp_path,
        claims,
        runs_dir,
        extra=["--allow-fetch", "--results", "../../secret.json"],
    )

    assert result.exit_code != 0
    assert "--results path escapes the repo" in result.output
    assert fetcher.calls == []
    assert _bundle_dirs(runs_dir) == []


def test_locator_containment_is_evaluated_against_the_checkout_not_the_url(
    tmp_path, monkeypatch
):
    """The guard's base must be the prospective checkout path, not the URL.

    This is the discriminating case. A `from` of "../source/results.json"
    stays INSIDE the checkout (`<runs_dir>/<id>/source`) and must be allowed.
    Joining it onto the raw URL string instead gives a relative path anchored
    at the process cwd -- `Path("https://github.com/lab/paper-code") /
    "../source/results.json"` resolves to `<cwd>/https:/github.com/lab/source/
    results.json`, outside `<cwd>/https:/github.com/lab/paper-code` -- so the
    guard would refuse a legitimate locator. Escaping paths (tested above) are
    refused under either base, which is why they alone cannot catch a wrong
    base; this one can.
    """
    claims = _claims_file(
        tmp_path,
        [{"id": "auc", "value": 0.9, "from": "../source/results.json", "path": "auc"}],
    )
    runs_dir = tmp_path / "runs"
    fetcher = _ScriptedCheckoutFetcher()
    monkeypatch.setattr("contig.cli.default_fetcher", fetcher)
    monkeypatch.setattr(
        "contig.cli.default_command_executor",
        lambda cmd, cwd: (
            (cwd / "results.json").write_text(json.dumps({"auc": 0.9})),
            (0, ""),
        )[1],
    )

    result = _invoke(tmp_path, claims, runs_dir, extra=["--allow-fetch"])

    assert result.exit_code == 0, result.output
    assert "escapes the repo" not in result.output
    (claim,) = _read_record(runs_dir)["claim_results"]
    assert claim["status"] == "reproduced"
