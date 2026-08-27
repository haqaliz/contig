"""Pure paper-argument classifier for `contig extract-claims`.

`classify_paper_argument` decides -- with no filesystem, network, or
subprocess access of any kind -- whether a `paper` argument is a DOI, a
local .pdf path, or a local .txt/.md path (text), or something that must
be refused outright with a named message and nothing written. It mirrors
`contig.fetch`'s `classify_repo_argument` posture: the same pure,
deterministic, refuse-by-name shape, applied to the paper side of intake.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from contig.fetch import _is_doi  # single source of truth for the DOI shape


@dataclass(frozen=True)
class PaperArgument:
    """The result of classifying one `contig extract-claims` paper argument.

    Exactly one of (`kind` set) / (`refusal` set) is populated, enforced in
    `__post_init__` for the same reason as `RepoArgument` in fetch.py: a
    refused argument must never be misread as an accepted one by code that
    only checks `kind`. `doi` is set only when `kind == "doi"`.
    """

    kind: Literal["text", "pdf", "doi"] | None = None
    refusal: str | None = None
    doi: str | None = None

    def __post_init__(self) -> None:
        if self.refusal is not None:
            if self.kind is not None or self.doi is not None:
                raise ValueError("a refused PaperArgument must not also carry kind/doi")
            return
        if self.kind is None:
            raise ValueError("PaperArgument requires either kind or refusal")
        if self.kind == "doi" and self.doi is None:
            raise ValueError("kind='doi' requires a doi")
        if self.kind != "doi" and self.doi is not None:
            raise ValueError("doi may only be set when kind='doi'")


_DOI_URL_PREFIX = "https://doi.org/"

_DOI_PREFIX = "doi:"

# Any "scheme://..." other than the accepted doi.org prefix, matched
# case-insensitively so "HTTP://", "FTP://" etc. can't slip past as text.
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*)://")

# The scp-like shorthand (`user@host:path`): a bare token, "@", another bare
# token, ":". Deliberately excludes "/" from both sides of "@" so it doesn't
# fire on something like "https://user@host/path" (already scheme-refused).
_SCP_LIKE_RE = re.compile(r"^[^/]+@[^:]+:")

_SUPPORTED_FORMS = (
    "pass a DOI (doi:10.1234/x or https://doi.org/10.1234/x), "
    "or a local .pdf/.txt/.md path"
)


def _doi_candidate_refusal(arg: str, candidate: str, *, prefix_label: str) -> str | None:
    """Return a refusal reason if `candidate` is not a usable DOI remainder, else None."""
    if not candidate:
        return f"{arg!r} has an empty DOI after the {prefix_label}; " + _SUPPORTED_FORMS
    for ch in ("?", "#"):
        if ch in candidate:
            return (
                f"{arg!r} looks like a DOI with a query or fragment ({ch!r}); "
                "a DOI names one document and must not contain '?' or '#'"
            )
    if not _is_doi(candidate):
        return f"{arg!r} does not contain a valid DOI after the {prefix_label}; " + _SUPPORTED_FORMS
    return None


def classify_paper_argument(arg: str) -> PaperArgument:
    """Classify a `contig extract-claims` paper argument as doi, pdf, text, or refused.

    Pure and deterministic: no filesystem, network, or subprocess access.
    Decision order (each rule only applies if none above it matched):

    1. A leading "-" is refused before anything else, unconditionally. The
       paper is passed to downstream tooling as a positional, so an argument
       like "--upload-pack=..." reaching it as an option is a
       remote-code-execution shape (the same posture as classify_repo_argument).
    2. A DOI (doi: prefix, bare 10.<digits>/..., or an https://doi.org/ URL,
       all case-insensitive) is accepted with the whitespace-stripped DOI in
       the `doi` field; a ?/# or an empty remainder is refused.
    3. A local .pdf path (case-insensitive extension) is accepted.
    4. Any other URL scheme or scp-like user@host:path is refused, naming the
       supported forms.
    5. Everything else is a local .txt/.md path (text).
    """
    if arg.startswith("-"):
        return PaperArgument(
            kind=None,
            refusal=(
                f"{arg!r} looks like a command-line option, not a paper; "
                "pass a DOI or a path to a .pdf/.txt/.md paper"
            ),
            doi=None,
        )

    stripped = arg.strip()

    if stripped.lower().startswith(_DOI_PREFIX):
        candidate = stripped[len(_DOI_PREFIX) :].strip()
        refusal = _doi_candidate_refusal(arg, candidate, prefix_label="'doi:' prefix")
        if refusal is not None:
            return PaperArgument(kind=None, refusal=refusal, doi=None)
        return PaperArgument(kind="doi", refusal=None, doi=candidate)

    if _is_doi(stripped):
        refusal = _doi_candidate_refusal(arg, stripped, prefix_label="DOI")
        if refusal is not None:
            return PaperArgument(kind=None, refusal=refusal, doi=None)
        return PaperArgument(kind="doi", refusal=None, doi=stripped)

    if stripped.lower().startswith(_DOI_URL_PREFIX):
        candidate = stripped[len(_DOI_URL_PREFIX) :].strip()
        refusal = _doi_candidate_refusal(
            arg, candidate, prefix_label="https://doi.org/ prefix"
        )
        if refusal is not None:
            return PaperArgument(kind=None, refusal=refusal, doi=None)
        return PaperArgument(kind="doi", refusal=None, doi=candidate)

    if stripped.lower().endswith(".pdf"):
        return PaperArgument(kind="pdf", refusal=None, doi=None)

    scheme = _SCHEME_RE.match(stripped)
    if scheme is not None:
        return PaperArgument(
            kind=None,
            refusal=f"the {scheme.group(1)}:// scheme is not supported; " + _SUPPORTED_FORMS,
            doi=None,
        )

    if _SCP_LIKE_RE.match(stripped):
        return PaperArgument(
            kind=None,
            refusal=(
                f"{arg!r} looks like scp syntax (user@host:path), which is not "
                "supported; " + _SUPPORTED_FORMS
            ),
            doi=None,
        )

    return PaperArgument(kind="text", refusal=None, doi=None)