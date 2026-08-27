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
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Literal

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
    3. Any other URL scheme or scp-like user@host:path is refused, naming the
       supported forms -- before the local .pdf check, so a remote URL ending
       in .pdf is refused by scheme, never read as a local path.
    4. A local .pdf path (case-insensitive extension) is accepted.
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

    if stripped.lower().endswith(".pdf"):
        return PaperArgument(kind="pdf", refusal=None, doi=None)

    return PaperArgument(kind="text", refusal=None, doi=None)

# ---------------------------------------------------------------------------
# doi-fetch: DOI -> PDF fetch (stdlib urllib + html.parser), behind a seam
# ---------------------------------------------------------------------------


class PaperIntakeError(ValueError):
    """A DOI landing page that cannot be turned into one PDF URL."""


def _doi_url(doi: str) -> str:
    """Build the doi.org URL for a DOI, verbatim (no normalization)."""
    return _DOI_URL_PREFIX + doi


class _PdfUrlParser(HTMLParser):
    """Collect non-empty `citation_pdf_url` meta contents from a landing page.

    Attribute order is irrelevant (`name` before `content` or vice versa) and
    the attribute names are matched case-insensitively, since publishers do
    not reliably agree on either. Metas with an empty `content` are skipped:
    they carry no URL to guess from.
    """

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        names = [value for key, value in attrs if key.lower() == "name"]
        contents = [value for key, value in attrs if key.lower() == "content"]
        if any(name is not None and name.lower() == "citation_pdf_url" for name in names):
            for content in contents:
                if content:
                    self.urls.append(content)


def resolve_pdf_url(html: str) -> str:
    """Return the single `citation_pdf_url` from a landing page, or refuse.

    Zero matches (including a lone empty-content meta) raise
    `PaperIntakeError` with the paywall-aware product copy; two or more
    matches raise naming the count -- a PDF URL is never guessed.
    """
    parser = _PdfUrlParser()
    parser.feed(html)
    parser.close()
    if not parser.urls:
        raise PaperIntakeError(
            "no citation_pdf_url found on the landing page (the paper may be "
            "paywalled); download the PDF and pass its path instead"
        )
    if len(parser.urls) > 1:
        raise PaperIntakeError(
            f"found {len(parser.urls)} citation_pdf_url metas on the landing "
            "page; refusing to guess which is the paper"
        )
    return parser.urls[0]


def _looks_like_pdf(data: bytes) -> bool:
    """True when `data` starts with the `%PDF` magic prefix."""
    return data.startswith(b"%PDF")


def _looks_like_pdf(data: bytes) -> bool:
    """True when `data` starts with the `%PDF` magic prefix."""
    return data.startswith(b"%PDF")


# A fetcher turns a DOI string into a local PDF at `dest`. The default hits
# the network via urllib; tests patch the module-level `_urlopen` seam so no
# real network is touched in CI (mirrors Fetcher in runner.py).
PaperFetcher = Callable[[str, Path], tuple[int, str]]

_FETCH_TIMEOUT = 30

# The landing page is read bounded so a pathological page cannot hang the
# fetch; a bigger-than-bound page is an honest give-up naming the bound.
_LANDING_READ_BOUND = 2 * 1024 * 1024  # 2 MiB

# The PDF download is bounded too, but generously: real paper PDFs (figures,
# supplements) are routinely tens of MiB, and cli-wiring enforces the
# 64 MiB product cap (`MAX_PDF_BYTES`) after the fetch. This bound only
# keeps a single read() call honest.
_PDF_READ_BOUND = 64 * 1024 * 1024  # 64 MiB


def _urlopen(url: str, timeout: int):
    """The only network entry point of this module; patched in tests."""
    return urllib.request.urlopen(url, timeout=timeout)


def default_paper_fetcher(doi: str, dest: Path) -> tuple[int, str]:
    """Fetch the PDF for a DOI to `dest`, or give up with a named refusal.

    `(0, message)` on success with the PDF written to `dest`; `(nonzero,
    message)` on every give-up with `dest` removed. Flow: doi.org URL via
    `_doi_url`, then a PDF-first sniff (Content-Type `application/pdf` or
    `%PDF` magic -- many DOIs redirect straight to the PDF), else a bounded
    landing-page read resolved through `resolve_pdf_url`, then a bounded
    download of the meta URL. Every failure names its cause and leaves
    nothing behind.
    """
    url = _doi_url(doi)
    try:
        with _urlopen(url, timeout=_FETCH_TIMEOUT) as response:
            content_type = response.headers.get("Content-Type", "")
            first = response.read(5)
            if "application/pdf" in content_type.lower() or _looks_like_pdf(first):
                dest.write_bytes(first + response.read())
                return (0, f"downloaded the PDF for {doi!r} to {dest}")
            landing = first + response.read(_LANDING_READ_BOUND + 1)
            if len(landing) > _LANDING_READ_BOUND:
                raise PaperIntakeError(
                    f"the landing page for {doi!r} exceeds the "
                    f"{_LANDING_READ_BOUND}-byte read bound; download the "
                    "PDF and pass its path instead"
                )
            html = landing.decode("utf-8", errors="replace")
            pdf_url = resolve_pdf_url(html)
        with _urlopen(pdf_url, timeout=_FETCH_TIMEOUT) as pdf_response:
            data = pdf_response.read(_PDF_READ_BOUND + 1)
            if len(data) > _PDF_READ_BOUND:
                raise PaperIntakeError(
                    f"the PDF at {pdf_url} exceeds the {_PDF_READ_BOUND}-byte "
                    "read bound; download the PDF and pass its path instead"
                )
            dest.write_bytes(data)
        return (0, f"downloaded the PDF for {doi!r} to {dest}")
    except PaperIntakeError as exc:
        dest.unlink(missing_ok=True)
        return (1, str(exc))
    except Exception as exc:
        dest.unlink(missing_ok=True)
        return (1, f"failed to fetch the PDF for {doi!r} from {url}: {exc}")

# ---------------------------------------------------------------------------
# pdf-text-seam: pdftotext PDF -> text extraction (stdlib subprocess)
# ---------------------------------------------------------------------------

import subprocess  # module-level name so tests can patch paper_intake.subprocess

# PDF size cap: reasoned bound, 8x the 8 MiB text cap for figure-bearing
# papers, uncalibrated per PRD R4.
MAX_PDF_BYTES = 64 * 1024 * 1024

# A PDF-text extractor turns a local PDF path into (exit code, text). The
# default shells out to poppler's pdftotext; tests inject a fake via the
# module-level `subprocess` name so no real pdftotext runs in CI (mirrors
# Fetcher in runner.py).
PdfTextExtractor = Callable[[Path], tuple[int, str]]


def _pdftotext_argv(pdf: Path) -> list[str]:
    """Build the fixed pdftotext argv: -layout, the PDF path, stdout to "-"."""
    return ["pdftotext", "-layout", str(pdf), "-"]


def default_pdf_text_extractor(pdf: Path) -> tuple[int, str]:
    """Extract text from a PDF via pdftotext, or give up with a named refusal.

    `(0, text)` on success; `(127, …)` when poppler is missing, naming the
    install so the user can act on it; `(rc, stderr-or-message)` on any
    non-zero exit with the refusal text surfaced. No path raises: arbitrary
    bytes are decoded with `errors="replace"`.
    """
    try:
        result = subprocess.run(_pdftotext_argv(pdf), capture_output=True)
    except FileNotFoundError:
        return (
            127,
            "pdftotext executable not found; install poppler "
            "(brew install poppler / apt install poppler-utils)",
        )
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace") or (
            f"pdftotext exited {result.returncode}"
        )
        return (result.returncode, message)
    return (0, result.stdout.decode(errors="replace"))
