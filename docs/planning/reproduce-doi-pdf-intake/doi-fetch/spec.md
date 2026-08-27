# Spec: doi-fetch (DOI → PDF fetch)

Aspect of: `reproduce-doi-pdf-intake`. Source: PRD M2, R3, the pinned decisions.

## Problem slice and user outcome

A `doi`-kind paper argument must turn into a local PDF **behind an opt-in
network flag** (`--allow-fetch`, wired in `cli-wiring`). The fetch itself is
stdlib-only (`urllib` + `html.parser`), injectable as a seam, and never
executed in CI. The user outcome: paste a DOI, get the draft — with every
give-up an honest named refusal, never a guess.

## In-scope requirements

- `PaperFetcher = Callable[[str, Path], tuple[int, str]]` seam type in
  `src/contig/verification/paper_intake.py` (the `Fetcher` shape, `runner.py:736`):
  `(0, message)` on success (PDF written to `dest`), non-zero + message on any
  give-up (no partial file at `dest`).
- `default_paper_fetcher(doi: str, dest: Path) -> tuple[int, str]`:
  1. URL = `https://doi.org/<doi>` via a pure `_doi_url(doi)` builder
     (verbatim DOI, no normalization beyond what the classifier already did).
  2. `urllib.request.urlopen(url, timeout=30)` following redirects (default).
  3. **PDF-first sniff:** if the response is itself a PDF — `Content-Type`
     `application/pdf` or the bytes start with `%PDF` — save it directly to
     `dest` and return `(0, …)`. (Many DOIs redirect straight to the PDF;
     meta-only would fail them.)
  4. Otherwise read the landing HTML (bytes → str, tolerant of any encoding
     error), call `resolve_pdf_url(html)` (below), then download the PDF URL
     (same `urlopen` path, timeout 30, size-bounded read) to `dest`.
  5. Every give-up — DNS/HTTP error, non-HTML non-PDF response, no
     `citation_pdf_url`, duplicate metas, oversized body — returns
     `(nonzero, reason)` with the reason naming the cause; `dest` never left
     partial (remove on failure).
- `resolve_pdf_url(html: str) -> str` (pure, `html.parser.HTMLParser`
  subclass): collects `<meta name="citation_pdf_url" content="…">` (name
  case-insensitive; attribute order agnostic; empty `content` skipped). Exactly
  one non-empty meta → its URL; **zero → raises `PaperIntakeError`** ("no
  citation_pdf_url found"); **two or more → raises `PaperIntakeError` naming
  the count** (never guessed — pinned decision). `PaperIntakeError(ValueError)`
  defined in the module.
- Honest-failure vocabulary: every message names the cause; the paywall case
  reads like product copy, not an exception: "no PDF URL found on the landing
  page (the paper may be paywalled); download the PDF and pass its path
  instead".

## Out-of-scope boundaries

- No `?`/`#` DOIs (refused upstream by the classifier).
- No direct non-`doi.org` URL fetching.
- No PDF-download size cap inside the fetcher beyond an honest read bound
  (the 64 MiB `MAX_PDF_BYTES` cap is enforced by `cli-wiring` after the
  fetch).
- The real urllib path is **never executed in CI** — reasoned-not-observed;
  tests inject a scripted `PaperFetcher` fake at the CLI seam. A loopback
  `http.server` test of the real path stays N1 (deferred).

## Acceptance criteria (testable)

- `_doi_url`: `"10.1038/x"` → `"https://doi.org/10.1038/x"`, verbatim, no
  normalization.
- `resolve_pdf_url` fixture-HTML tests: single meta (name-before-content and
  content-before-name orders), case-insensitive `NAME`/`name`, absent → raises
  `PaperIntakeError`, duplicate metas → `PaperIntakeError` message naming the
  count `2`, empty-content metas skipped (a lone empty one → raises absent),
  unrelated metas ignored.
- A scripted-fetcher integration test at the CLI level (in `cli-wiring`)
  proves the seam is called with the stripped DOI and a writable `dest`, and
  that its non-zero return is surfaced as a refusal with nothing written.
- `%PDF`-magic and `Content-Type` sniff: pure helper `_looks_like_pdf(bytes)`
  pinned (fixture bytes starting `%PDF-1.4` → True; HTML bytes → False).

## Dependencies and sequencing notes

- Depends on the `doi` kind existing (conceptually from `intake-classifier`;
  the fetch only reads a DOI string, so it can be built in parallel with
  `pdf-text-seam` — both are prerequisites of `cli-wiring`).
- Adds `PaperIntakeError` (module-local; no `models.py` change).

## Open questions / risks

- `citation_pdf_url` is a publisher convention, not a guarantee (PRD R3):
  the honest refusal is the product behavior; the paywall-wording decision is
  pinned above.
- Redirect loops / giant landing pages: `urlopen` raises on HTTP errors and
  redirect loops; the landing-page read is bounded (e.g. first 2 MiB) so a
  pathological page cannot hang the fetch — the bound is a constant with its
  own test.