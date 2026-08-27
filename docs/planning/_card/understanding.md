# Understanding: reproduce-doi-pdf-intake (Phase-2 dig)

## What the work is really asking

`contig extract-claims` today takes a local `.txt`/`.md` paper and produces a
draft claims file (`cli.py:1275-1416`). The C8 standing deferral — recorded in
every slice (`CAPABILITY_ROADMAP.md:2050-2051`, extract-claims PRD R5,
`CHANGELOG.md:1097-1098`) — is PDF parsing, DOI resolution, and paper
fetching. This slice widens the **input surface only**: a paper DOI
(`doi:10.xxx/y` / bare `10.xxx/y` / `https://doi.org/…`) or a local
`paper.pdf` becomes an accepted input; the PDF is turned into text and fed
into the **shipped extractor unchanged**. The `load_claims` round-trip
invariant (never emit a draft the reproduce path rejects, `cli.py:1360-1389`)
and the zero-blast-radius rule (no change to `run_reproduction`/`classify`/
`ClaimResult`/bundle/signing) are load-bearing constraints, not suggestions.

## Affected areas (from the code map)

- `src/contig/cli.py:1275-1416` — `extract_claims` command: argument is a
  local path with stat-before-read, 8 MiB `_MAX_MATCH_BYTES` cap (imported
  from `contig.verification.reproduce:51`), UTF-8 check, `--out` guards,
  `default_extractor` seam (`cli.py:265-280`), temp→`load_claims`→`os.replace`.
- `src/contig/verification/claim_extraction.py` — pure stdlib core, never
  raises; `extract_claims(text: str)`; untouched by this slice.
- Seam pattern to mirror: `Fetcher = Callable[[list[str], Path], tuple[int, str]]`
  (`runner.py:736`), `default_fetcher` (`runner.py:1165`, FileNotFoundError →
  `(127, "git executable not found")`), CLI passes the default explicitly and
  tests monkeypatch `contig.cli.default_fetcher` (`test_reproduce_remote_intake.py:521`).
- `--allow-fetch` posture: flag off by default (`cli.py:940-949`); pure
  `classify_repo_argument` refuses leading `-` first, then accepts https,
  refuses DOI by name (`fetch.py:110-155`); CLI refuses URL-without-flag
  naming the flag (`cli.py:999-1010`). **`_is_doi` already exists**
  (`fetch.py:75-76,96-97`) — reusable for the extract-claims classifier; the
  reproduce command's DOI *refusal* must stay.
- Tests: `tests/test_cli_extract_claims.py` (295 lines, Click-param
  introspection for flags, sparse-file size-cap test), `tests/test_reproduce_remote_intake.py`
  (709 lines, `_ScriptedCheckoutFetcher` fake pattern), no conftest anywhere.

## Design shape implied by the constraints

1. **Argument classification** — a pure `classify_paper_argument` mirroring
   `classify_repo_argument`: leading `-` refused first; DOI forms → kind
   `doi`; local `.pdf` → kind `pdf`; other URL schemes refused naming what's
   supported; everything else stays the existing local text path.
2. **Network** — DOI → PDF requires a fetch: `https://doi.org/<doi>` follows
   redirects to the publisher **landing page**, then `<meta
   name="citation_pdf_url">` (de-facto standard across publishers) names the
   PDF. Two hops, both stdlib (`urllib` + `html.parser`). Opt-in flag in the
   `--allow-fetch` posture: a DOI without the flag is refused naming the flag.
3. **PDF→text** — an injectable seam in the Fetcher/Installer mould, default
   shelling to an external tool (`pdftotext -layout <pdf> -`, poppler),
   missing tool → honest `(127, …)`-style refusal naming the install. Never
   executed in CI (injected fakes). This keeps the stdlib-only dependency
   contract (external binaries like git/pip/samtools are the established
   pattern — `runner.py:714-743`).
4. **Honest boundaries** — PDF size cap (stat before fetch/read), extracted
   text still bounded (extractor input contract), nothing written on any
   failure, empty extraction stays exit 0, draft-only invariant intact,
   reasoned-not-observed framing with the manual real-paper gate named.

## Ambiguities / open questions

- **Flag name**: reuse `--allow-fetch` on `extract-claims` (consistent with
  `reproduce`) vs a new name. Lean: `--allow-fetch`.
- **URL scope**: DOI + local PDF only (tight, per the brief), or also accept
  direct `https://…pdf` URLs. Lean: refuse other schemes.
- **PDF→text tool**: `pdftotext` (poppler) is the cross-platform standard;
  macOS has `textutil` built-in. One tool, fixed argv, seam-injected. Tool
  choice is a product decision worth confirming.
- **Size caps**: PDF cap (papers with figures run 2–20 MB; 8 MiB would refuse
  legitimate arXiv PDFs) vs extracted-text cap (8 MiB existing). Lean: PDF
  cap larger (e.g. 64 MiB), extracted text still capped at `_MAX_MATCH_BYTES`.
- **DOI→PDF is not deterministic** (the slice-6 PRD's own objection at
  `remote-intake/prd.md:244-246` applies): `citation_pdf_url` is a
  convention, not a guarantee. Missing meta tag → honest failure, never a
  guess. This is the nearest feasibility risk, stated honestly.

## Guardrail check

Layer 2 (input generation for reproduce verification; no NL→workflow
authoring), founder's edge (public papers, no wet-lab/clinical), not
deferred-for-a-blocker (PDF/DOI was deferred for *scope* — R5 mitigation —
with no recorded blocker; the "no plot-hash" hard block does not apply to
text extraction). Pass.