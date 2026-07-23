"""C8 slice 6: classify the `repo` argument to `contig reproduce`.

`classify_repo_argument` decides -- purely, with no I/O of any kind -- whether
a `repo` argument is a local path, a fetchable https:// git URL, or something
that must be refused outright. A later slice adds the `Fetcher` seam that
actually clones a remote URL; this module only decides which branch a given
argument belongs in.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from contig.runner import (
    Fetcher,
    _git_checkout_argv,
    _git_clone_argv,
    _git_fetch_argv,
    _git_init_argv,
    _git_remote_add_argv,
    _git_rev_parse_argv,
)


@dataclass(frozen=True)
class RepoArgument:
    """The result of classifying one `contig reproduce` repo argument.

    Exactly one of (`kind` set) / (`refusal` set) is populated. This is
    enforced in `__post_init__` rather than left as a convention, so a
    refused argument can never be misread as an accepted one by code that
    only checks `kind`. Construct via `RepoArgument.local()`, `.remote(url)`,
    or `.refuse(reason)` -- the bare constructor is kept public only because
    `frozen=True` dataclasses need one, and because tests exercise the
    invariant directly.
    """

    kind: Literal["local", "remote"] | None
    url: str | None
    refusal: str | None

    def __post_init__(self) -> None:
        if self.refusal is not None:
            if self.kind is not None or self.url is not None:
                raise ValueError("a refused RepoArgument must not also carry kind/url")
            return
        if self.kind is None:
            raise ValueError("RepoArgument requires either kind or refusal")
        if self.kind == "remote" and self.url is None:
            raise ValueError("kind='remote' requires a url")
        if self.kind == "local" and self.url is not None:
            raise ValueError("kind='local' must not carry a url")

    @classmethod
    def local(cls) -> "RepoArgument":
        return cls(kind="local", url=None, refusal=None)

    @classmethod
    def remote(cls, url: str) -> "RepoArgument":
        return cls(kind="remote", url=url, refusal=None)

    @classmethod
    def refuse(cls, reason: str) -> "RepoArgument":
        return cls(kind=None, url=None, refusal=reason)


# A DOI has either an explicit "doi:" prefix or is a bare "10.<digits>/<suffix>"
# (the DOI registrant-code shape; see doi.org/doi_handbook). Checked ahead of
# the generic local-path fallback so a pasted DOI gets a message that names
# the actual problem instead of "No such repo directory: 10.1234/xyz".
_DOI_PREFIX_RE = re.compile(r"^doi:", re.IGNORECASE)
_BARE_DOI_RE = re.compile(r"^10\.\d+/\S+$")

# Any "scheme://..." other than https, matched case-insensitively so
# "HTTP://", "SSH://", "FILE://" etc. don't slip past as local paths just
# because the literal lowercase prefix doesn't match.
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*)://", re.IGNORECASE)

# git's alternate "ext::<command>" transport shells out to an arbitrary
# command -- it has no "//" so it doesn't match _SCHEME_RE and needs its own
# check.
_EXT_SCHEME_RE = re.compile(r"^ext::", re.IGNORECASE)

# The scp-like shorthand git accepts (`user@host:path`, most commonly
# `git@github.com:org/repo.git`): a bare token, "@", another bare token, ":".
# Deliberately excludes "/" from both sides of "@" so it doesn't fire on
# something like "https://user@host/path" (that's already handled by the
# https/scheme checks above it in the decision order).
_SCP_LIKE_RE = re.compile(r"^[^\s/@:]+@[^\s/@:]+:")


def _is_doi(arg: str) -> bool:
    return bool(_DOI_PREFIX_RE.match(arg) or _BARE_DOI_RE.match(arg))


def _rejected_scheme(arg: str) -> str | None:
    """Return the offending scheme token if `arg` is a non-https URL, else None."""
    if _EXT_SCHEME_RE.match(arg):
        return "ext::"
    match = _SCHEME_RE.match(arg)
    if match is not None:
        return f"{match.group(1)}://"
    return None


def classify_repo_argument(arg: str) -> RepoArgument:
    """Classify a `contig reproduce` repo argument as local, remote, or refused.

    Pure and deterministic: no filesystem, subprocess, or network access.
    Decision order (each rule only applies if none above it matched):

    1. A leading "-" is refused before any scheme parsing at all. `git clone
       --` is used downstream, so an argument like "--upload-pack=/bin/sh"
       reaching git as an option -- rather than as the repo positional -- is
       a remote-code-execution shape. Checking this first, unconditionally,
       means no scheme or path pattern can be crafted to bypass it.
    2. "https://..." (case-insensitive) is accepted as remote, with the
       original string preserved verbatim as `url` -- it is not normalized,
       because it becomes part of a provenance record.
    3. A DOI is refused, naming DOI explicitly.
    4. Any other URL-ish form (http, ssh, git, file, ext::, or scp-like
       `user@host:path`) is refused, naming https:// as the accepted form.
    5. Anything else is a local path.
    """
    if arg.startswith("-"):
        return RepoArgument.refuse(
            f"{arg!r} looks like a command-line option, not a repo; "
            "pass a path or an https:// git URL"
        )

    if arg.lower().startswith("https://"):
        return RepoArgument.remote(arg)

    if _is_doi(arg):
        return RepoArgument.refuse(
            "DOI intake is not supported yet; pass an https:// git URL"
        )

    rejected = _rejected_scheme(arg)
    if rejected is not None:
        return RepoArgument.refuse(
            f"{rejected} is not supported; pass an https:// git URL"
        )

    if _SCP_LIKE_RE.match(arg):
        return RepoArgument.refuse(
            "scp-like git syntax (user@host:path) is not supported; "
            "pass an https:// git URL"
        )

    return RepoArgument.local()


@dataclass(frozen=True)
class RevArgument:
    """The result of classifying one `contig reproduce --rev` argument.

    Exactly one of `rev` / `refusal` is populated, enforced in `__post_init__`
    for the same reason as `RepoArgument`: a refused revision must never be
    misread as an accepted one by code that only checks `rev`.
    """

    rev: str | None
    refusal: str | None

    def __post_init__(self) -> None:
        if self.refusal is not None:
            if self.rev is not None:
                raise ValueError("a refused RevArgument must not also carry a rev")
            return
        if self.rev is None:
            raise ValueError("RevArgument requires either rev or refusal")

    @classmethod
    def accept(cls, rev: str) -> "RevArgument":
        return cls(rev=rev, refusal=None)

    @classmethod
    def refuse(cls, reason: str) -> "RevArgument":
        return cls(rev=None, refusal=reason)


# An abbreviated SHA git cannot fetch: `git fetch --depth 1 origin -- <7-hex>`
# fails with "couldn't find remote ref". Checked BEFORE the refname rules,
# because a 7-hex string is a perfectly valid refname and would otherwise be
# accepted and then fail with a message that reads like a typo'd branch.
_SHORT_SHA_RE = re.compile(r"^[0-9a-f]{7,39}$", re.IGNORECASE)

# The full SHA shape, accepted outright.
_REV_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)

# Refname forms git itself rejects (see git-check-ref-format), plus the
# characters that carry meaning in a revision expression (`~`, `^`, `:`).
_REFNAME_INVALID_SUBSTRINGS = ("..", "~", "^", ":", "?", "*", "[", "\\")


def classify_rev_argument(arg: str) -> RevArgument:
    """Classify a `contig reproduce --rev` argument as accepted or refused.

    Pure and deterministic: no filesystem, subprocess, or network access.
    Decision order (each rule only applies if none above it matched):

    1. A leading "-" is refused before anything else, unconditionally. The
       rev is passed to `git fetch`, so an argument like "--upload-pack=..."
       reaching git as an option -- rather than as the ref positional -- is a
       remote-code-execution shape. Checking this first means no other shape,
       not even an otherwise-valid SHA, can be crafted to bypass it.
    2. Empty / whitespace-only is refused.
    3. Any whitespace or control character anywhere is refused.
    4. A full 40-hex SHA is accepted outright (it is not a valid refname by
       the rules below, but it is the single most important input: it is what
       `source_commit` contains).
    5. A 7-to-39-hex abbreviated SHA is refused, naming the full form.
    6. A refname-invalid form is refused.
    7. Anything else is accepted verbatim and unnormalized -- it becomes part
       of a provenance record.
    """
    if arg.startswith("-"):
        return RevArgument.refuse(
            f"{arg!r} looks like a command-line option, not a revision; "
            "pass a commit SHA, tag, or branch"
        )

    if not arg.strip():
        return RevArgument.refuse("--rev must not be empty")

    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in arg):
        return RevArgument.refuse(
            f"{arg!r} contains whitespace or a control character; "
            "pass a commit SHA, tag, or branch"
        )

    if _REV_FULL_SHA_RE.match(arg):
        return RevArgument.accept(arg)

    if _SHORT_SHA_RE.match(arg):
        return RevArgument.refuse(
            f"{arg!r} looks like an abbreviated commit SHA; git cannot fetch "
            "one. Pass the full 40-character SHA (or a tag or branch)"
        )

    if (
        any(bad in arg for bad in _REFNAME_INVALID_SUBSTRINGS)
        or arg.startswith(("/", "."))
        or arg.endswith(("/", "."))
        or arg.endswith(".lock")
    ):
        return RevArgument.refuse(
            f"{arg!r} is not a valid git revision name; "
            "pass a commit SHA, tag, or branch"
        )

    return RevArgument.accept(arg)


@dataclass(frozen=True)
class FetchResult:
    """The result of `fetch_repo`: a clone + resolved commit, or a refusal.

    Exactly one of (`path`/`commit` set) / (`refusal` set) is populated,
    enforced in `__post_init__` for the same reason as `RepoArgument`: a
    refused fetch must never be misread as a successful one by code that only
    checks `path`. Construct via `FetchResult.ok(path, commit)` or
    `.refuse(reason)` -- the bare constructor is kept public only because
    `frozen=True` dataclasses need one, and because tests exercise the
    invariant directly.
    """

    path: Path | None
    commit: str | None
    refusal: str | None

    def __post_init__(self) -> None:
        if self.refusal is not None:
            if self.path is not None or self.commit is not None:
                raise ValueError("a refused FetchResult must not also carry path/commit")
            return
        if self.path is None or self.commit is None:
            raise ValueError("FetchResult requires either (path and commit) or refusal")

    @classmethod
    def ok(cls, path: Path, commit: str) -> "FetchResult":
        return cls(path=path, commit=commit, refusal=None)

    @classmethod
    def refuse(cls, reason: str) -> "FetchResult":
        return cls(path=None, commit=None, refusal=reason)


# The full-SHA shape `git rev-parse HEAD` is expected to produce. Matched with
# fullmatch against the STRIPPED output -- not searched for as a substring --
# so a multi-line output (default_fetcher merges stderr into stdout, so a
# warning line can ride alongside a real SHA) can never be scavenged for a
# SHA-looking token. An unvalidated or fabricated pin is worse than no pin at
# all, since the whole point of this slice is that the recorded commit is
# trustworthy.
_FULL_SHA_RE = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)


# The shape git uses when a server refuses `want <sha>` -- i.e. it does not
# enable uploadpack.allowReachableSHA1InWant. Matched as a case-insensitive
# substring (not a regex) so an unrelated fetch failure is never mislabelled
# with a cause it does not have.
_NOT_OUR_REF_MARKERS = ("not our ref", "upload-pack")


def fetch_repo(
    url: str, dest: Path, *, fetcher: Fetcher, rev: str | None = None
) -> FetchResult:
    """Clone `url` into `dest`, resolve HEAD, and validate the pin.

    With `rev` set, a targeted fetch of that revision replaces the shallow
    clone: `git init` / `remote add` / `fetch --depth 1 <rev>` / `checkout
    --detach FETCH_HEAD`, all run with `dest` as cwd. `git clone --depth 1`
    cannot check out an arbitrary commit, and `--branch <ref>` accepts only a
    tag or branch -- while a raw SHA is the input that matters most, since it
    is what `source_commit` contains.

    `rev=None` keeps the clone path byte-identical to what shipped in slice 6.

    Sequence: refuse a non-empty `dest` outright (something else owns that
    path); wipe/recreate `dest` as fresh scratch (mirrors the run-scoped
    scratch convention in self_heal.py: STAR-index rebuild and reference
    recompress both `rmtree(ignore_errors=True)` then `mkdir(parents=True,
    exist_ok=True)` before writing into a directory they own); clone; resolve
    the commit; validate it is a bare 40-hex SHA. Any failure after the
    directory is created is cleaned up so a refused run leaves no litter --
    a half-cloned or empty directory would look like a real run bundle to
    anything scanning the runs directory.

    Cleanup scope: `dest` is what this function is asked to create and own.
    Its parent (typically `<runs_dir>/<reproduce_id>/`) is only removed if
    THIS call is the one that created it -- if the caller already had that
    directory (e.g. holding other run state this function knows nothing
    about), a failure here must not delete it out from under the caller.
    """
    # Made absolute BEFORE anything is built from it. The clone runs with
    # `dest.parent` as its cwd, so a RELATIVE dest would be resolved a second
    # time against that cwd -- `runs/<id>/source` cloned from inside
    # `runs/<id>/` lands in `runs/<id>/runs/<id>/source`, leaving the real
    # dest an empty non-repo that `git rev-parse` then fails in. The CLI's
    # default `--runs-dir runs` produces exactly that relative path, so this
    # is the normal case, not an edge one. `.absolute()` (not `.resolve()`)
    # deliberately: prepending the cwd is all that is needed, and resolving
    # symlinks here would change the path the caller gets back.
    dest = Path(dest).absolute()

    if dest.exists() and any(dest.iterdir()):
        return FetchResult.refuse(
            f"destination {dest} already exists and is not empty; "
            "refusing to clone into it"
        )

    # This call owns dest.parent's creation only if it doesn't exist yet --
    # remembered now, before mkdir(parents=True) below can create it, so
    # cleanup on failure knows whether it may remove the parent too.
    parent_created_here = not dest.parent.exists()

    # Fresh scratch dir: wipe any residue (e.g. from a stale prior attempt) so
    # the clone below writes into a directory only this call has touched.
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    def _cleanup() -> None:
        shutil.rmtree(dest.parent if parent_created_here else dest, ignore_errors=True)

    if rev is None:
        # dest does not exist as a git repo yet -- the parent is the sensible cwd
        # for the clone command (dest itself is just the clone's target argument).
        clone_code, clone_output = fetcher(_git_clone_argv(url, dest), dest.parent)
        if clone_code != 0:
            _cleanup()
            return FetchResult.refuse(f"git clone failed: {clone_output.strip()}")
    else:
        # Every step runs INSIDE dest: `git init` makes it a repo, and the
        # remaining steps operate on that repo. Each failure refuses, cleans
        # up, and surfaces git's own output -- git's stderr is the only useful
        # diagnostic, and default_fetcher merges it into the returned text.
        steps = (
            ("git init", _git_init_argv()),
            ("git remote add", _git_remote_add_argv(url)),
            ("git fetch", _git_fetch_argv(rev)),
            ("git checkout", _git_checkout_argv()),
        )
        for label, argv in steps:
            code, output = fetcher(argv, dest)
            if code == 0:
                continue
            _cleanup()
            reason = f"{label} failed: {output.strip()}"
            if label == "git fetch" and any(
                marker in output.lower() for marker in _NOT_OUR_REF_MARKERS
            ):
                # The remote accepted the connection but refused to serve this
                # revision by name -- overwhelmingly because it does not enable
                # uploadpack.allowReachableSHA1InWant. Say so, and say what
                # works instead. Deliberately NOT a silent fallback to a full
                # clone: that can pull gigabytes on exactly the large published
                # repos this targets.
                reason += (
                    "\nThe remote may not allow fetching a bare commit "
                    "(uploadpack.allowReachableSHA1InWant). Pass a tag or "
                    "branch to --rev instead."
                )
            return FetchResult.refuse(reason)

    # Resolve HEAD from inside the checkout.
    rev_code, rev_output = fetcher(_git_rev_parse_argv(), dest)
    if rev_code != 0:
        _cleanup()
        return FetchResult.refuse(f"git rev-parse HEAD failed: {rev_output.strip()}")

    commit = rev_output.strip()
    if not _FULL_SHA_RE.fullmatch(commit):
        _cleanup()
        return FetchResult.refuse(
            "git rev-parse HEAD did not return a single 40-character hex commit "
            f"SHA (refusing to record an unvalidated pin): {rev_output!r}"
        )

    # Normalized only on the --rev path: R1 promises the no-rev path stays
    # byte-identical to slice 6, which recorded rev-parse's output as-is.
    if rev is not None:
        commit = commit.lower()

    # When the caller named a full SHA, the checkout must actually be at it.
    # A pin that isn't what was asked for is worse than no pin -- the whole
    # point of --rev is that the recorded commit is the requested one. A tag
    # or branch has nothing to compare against: whatever resolved is the
    # answer.
    if rev is not None and _REV_FULL_SHA_RE.match(rev) and commit != rev.lower():
        _cleanup()
        return FetchResult.refuse(
            f"requested revision {rev} but the checkout resolved to {commit}; "
            "refusing to record a pin that is not what was asked for"
        )

    return FetchResult.ok(dest, commit)
