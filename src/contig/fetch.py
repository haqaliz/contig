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

from contig.runner import Fetcher, _git_clone_argv, _git_rev_parse_argv


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


def fetch_repo(url: str, dest: Path, *, fetcher: Fetcher) -> FetchResult:
    """Clone `url` into `dest`, resolve HEAD, and validate the pin.

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
    dest = Path(dest)

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

    # dest does not exist as a git repo yet -- the parent is the sensible cwd
    # for the clone command (dest itself is just the clone's target argument).
    clone_code, clone_output = fetcher(_git_clone_argv(url, dest), dest.parent)
    if clone_code != 0:
        _cleanup()
        return FetchResult.refuse(f"git clone failed: {clone_output.strip()}")

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

    return FetchResult.ok(dest, commit)
