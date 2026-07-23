"""C8 slice 6: classify the `repo` argument to `contig reproduce`.

`classify_repo_argument` decides -- purely, with no I/O of any kind -- whether
a `repo` argument is a local path, a fetchable https:// git URL, or something
that must be refused outright. A later slice adds the `Fetcher` seam that
actually clones a remote URL; this module only decides which branch a given
argument belongs in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


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
