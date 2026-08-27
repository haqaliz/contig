# PRD: reproduce-doi-pdf-intake (DOI / PDF intake for `contig extract-claims`)

Status: draft for review. Owner: aliz.
Branch: `feat/reproduce-doi-pdf-intake/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff brief, 2026-08-27),
`docs/planning/_card/understanding.md` (Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md`
C8, `docs/planning/reproduce-paper-claims/prd.md` (the shipped extract-claims slice).
Capability: **C8, next slice** — the PDF parsing / DOI resolution / paper fetching item
deferred in the extract-claims PRD's own words (`reproduce-paper-claims/prd.md:164,171`;
`CHANGELOG.md:1097-1098`; `CAPABILITY_ROADMAP.md:2050-2051`).

## Problem Statement

`contig extract-claims <paper.txt|md> --out <draft.json>` turns a paper's plain text
into a draft claims file. It ships (v0.52.0) but accepts **local text/markdown only**.
A real published analysis lives as a PDF — often reachable only through a DOI — so the
tool's first gesture ("give me a paper, get a draft claims file") still requires the
user to hunt down a PDF, convert it to text themselves, and save it as `.txt`/`.md`
before Contig can look at it. That is a manual step in the middle of the C8 promise
("paste a paper, get per-claim verdicts") — and the exact step every prior C8 slice
deferred as "paper-parsing / PDF / DOI".

This slice widens the **input surface only**: `contig extract-claims` accepts a paper
**DOI** (`doi:10.xxx/y`, bare `10.xxx/y`, `https://doi.org/…` — fetched over the
network behind an opt-in flag) or a **local `.pdf`**, converts it to text through an
injectable `pdftotext` seam, and feeds the **shipped extractor unchanged**. Nothing
downstream changes: the draft-only `load_claims` round-trip invariant holds, and any
wrongly-extracted claim degrades to `UNVERIFIED` at reproduce time, never a false
`REPRODUCED`.

**Who has the problem.** Persona A (lone computational biologist reproducing a paper
before building on it) and Persona D (biotech researcher checking a published result)
— the same personas the extract-claims PRD named, one step earlier in their flow.

**Evidence it's real.** The C8 problem statement is built on the reproducibility
crisis (only ~3.2% of 27,271 biomedical-paper notebooks reproduced — Samuel &
Mietchen 2024, cited in `CAPABILITY_ROADMAP.md:2172-2175`). The whole reproduce spine
and claim extraction exist; the paper-to-text step is the remaining manual barrier,
and it is deferred-for-scope, never blocked: "No dig has ever recorded a blocker"
(remote-intake precedent, `docs/planning/reproduce-remote-intake/prd.md:34-39`).

## Goals & Success Metrics

1. **Turnkey paper input.** `contig extract-claims <doi:…|10.x/y|https://doi.org/…|paper.pdf> --out <draft.json>`
   accepts a DOI or a local PDF and produces the same draft + review sidecar as the
   text path. *Measure:* the DOI and PDF paths run end-to-end on scripted fixtures
   and produce a draft that loads through `load_claims`.
2. **Zero blast radius on the verdict path.** No change to `run_reproduction`,
   `classify`, `ClaimResult`, `ReproduceRecord`, the bundle, signing, or any exit
   code; the shipped extractor core is byte-unchanged. *Measure:* the entire existing
   reproduce and claim-extraction suite is untouched and green.
3. **Honest on every boundary, in the standing vocabulary.** Leading-`-` refused
   first; a DOI without the opt-in network flag refused naming the flag; an
   unreachable DOI, a landing page without a `citation_pdf_url`, a PDF over the size
   cap, an extracted text over the text cap, a missing `pdftotext` — every path exits
   non-zero with **nothing written**, naming the reason. *Measure:* one pinned test
   per boundary.
4. **No new Python dependency.** PDF→text goes through an injectable external-tool
   seam (`pdftotext`, poppler) mirroring `Fetcher`/`Installer`; DOI→PDF fetch is
   stdlib (`urllib` + `html.parser`). *Measure:* `uv.lock` unchanged.
5. **Reasoned, not observed — stated as such.** No real network, PDF, or
   `pdftotext` in CI (injected seams, fixture HTML/PDF bytes only); the go/no-go is a
   manual post-merge gate on one real public DOI and one real paper PDF, named in the
   PRD and run by the founder.

## User Personas & Scenarios

- **A — lone computational biologist.** Has a paper's DOI (or the PDF on disk) and
  its repo cloned. Runs `contig extract-claims doi:10.1038/s41586-024-XXXXX --allow-fetch --out claims.draft.json`,
  reviews the sidecar, adds locators, runs `contig reproduce`. No text conversion
  step.
- **D — biotech researcher.** Downloads a paper's PDF from the publisher, runs
  `contig extract-claims paper.pdf --out claims.draft.json` locally — no network
  flag needed, no text ever leaves the machine.
- **B — wet-lab scientist who cannot code.** The DOI gesture ("paste the DOI") is
  the approachable form; the draft + sidecar still give the reviewable starting
  point.

## Requirements

### Must-have (v1)

- **M1 — Pure paper-argument classification.** `classify_paper_argument(arg) ->
  PaperArgument` (no filesystem/network/subprocess), mirroring
  `classify_repo_argument` (`src/contig/fetch.py:110-155`):
  - Leading `-` refused first, unconditionally (the RCE-shape posture).
  - `doi:` (case-insensitive), bare `10.<digits>/…` (reuse `_is_doi`,
    `fetch.py:75-76,96-97`), and `https://doi.org/…` → kind `doi`.
  - A local path with a `.pdf` extension (case-insensitive) → kind `pdf`.
  - Any other URL scheme (`http`, `ftp`, `ssh`, …) → refusal naming what is
    supported (`doi`, `https://doi.org/…`, local `.pdf`/`.txt`/`.md`).
  - Everything else → the existing local text path, byte-identical behavior.
  - `PaperArgument` carries exactly one of `kind` or `refusal` (the
    `RepoArgument` `__post_init__` invariant).
- **M2 — Opt-in DOI fetch in the `--allow-fetch` posture.** `extract-claims` gains
  `--allow-fetch` (off by default, Click-param-introspected in tests). A `doi`-kind
  argument without it is refused naming the flag, before anything is written or
  fetched. With it: resolve `https://doi.org/<doi>` (urllib, redirects followed),
  locate the PDF via `<meta name="citation_pdf_url" content="…">` on the landing
  page, download the PDF to a run-scoped temp location, and continue. Every
  give-up — unresolvable DOI, non-HTML response, absent `citation_pdf_url`,
  download failure, oversized PDF — exits non-zero with nothing written and no
  leftover files.
- **M3 — Injectable PDF→text seam.** A `PdfTextExtractor` seam in the
  `Fetcher`/`Installer` mould (`runner.py:714-743`): `default_pdf_text_extractor(pdf)
  -> tuple[int, str]` shells a fixed argv `pdftotext -layout <pdf> -`
  (poppler); a missing executable returns `(127, …)` naming the install
  (`brew install poppler` / `apt install poppler-utils`), never a traceback.
  Tests inject fakes; `pdftotext` is **never executed in CI**; the argv builder is
  shape-asserted only. The returned text is bounded: extracted text over the
  existing 8 MiB `_MAX_MATCH_BYTES` input contract is refused naming the size
  (the extractor's input contract, `reproduce.py:51`).
- **M4 — CLI wiring, text path unchanged.** `extract-claims` classifies `paper`,
  branches: `doi` → (flag-checked) fetch → PDF; `pdf` → stat-before-read with a
  64 MiB `MAX_PDF_BYTES` cap (8× the text cap; a reasoned, uncalibrated bound for
  figure-bearing papers) → extract; `text` → existing behavior byte-identical.
  All three feed the **unchanged** `default_extractor` and the unchanged temp →
  `load_claims` → `os.replace` commit with the review sidecar. Empty extraction
  still exits 0. Nothing is written on any failure.
- **M5 — Test-first, per the repo discipline.** One test file per aspect:
  classifier boundaries (leading `-` first; every DOI form; `.pdf`; refused
  schemes; text unchanged), refusal-before-write (DOI without flag names
  `--allow-fetch` and writes nothing), scripted fetcher + scripted extractor
  driving the real command end-to-end (draft loads via `load_claims`; sidecar
  written), size caps (sparse-file PDF over cap; extracted text over cap), missing
  `pdftotext` refusal, Click-param introspection (`--allow-fetch` registered),
  and pure `resolve_pdf_url(html)` against fixture HTML (present, absent,
  duplicate, quoting variants). The entire existing suite stays green and
  untouched.

### Should-have

- **S1 — Sidecar provenance for the new sources.** The `<out>.review.md` header
  records where the text came from: the resolved DOI/landing URL (fetched) or the
  local PDF path — the same provenance-register the text path already uses.

### Nice-to-have

- **N1 — Loopback-server test of the real urllib path.** A deterministic
  `http.server` fixture on localhost exercising the real redirect + meta + download
  code (the repo's "no real network in CI" posture currently excludes this; it
  stays a nice-to-have unless the posture is relaxed).
- **N2 — `--pdf-extractor` override** to name a custom pdftotext binary. Not
  needed for v1 (the argv is fixed; PATH lookup suffices).

## Technical Considerations

- **Module placement.** New `src/contig/verification/paper_intake.py` for the
  classifier, `resolve_pdf_url`, the fetch/extract seams and their defaults —
  sibling to `claim_extraction.py`, keeping `runner.py` and `fetch.py` untouched
  (the reproduce command's DOI *refusal* in `classify_repo_argument` stays
  exactly as is). CLI wiring only in `src/contig/cli.py`; the CLI imports the
  defaults and passes them explicitly, so tests monkeypatch
  `contig.cli.default_paper_fetcher` / `contig.cli.default_pdf_text_extractor`
  (the `contig.cli.default_fetcher` precedent, `tests/test_reproduce_remote_intake.py:521`).
- **No `models.py` change, no signed-field change.** The record, bundle, and
  signing are untouched; this slice never writes into a run directory (temp files
  only, cleaned on every path).
- **DOI normalization is minimal on purpose.** Strip surrounding whitespace; a
  `https://doi.org/` prefix is stripped to the DOI; otherwise the DOI is used
  verbatim (the slice-6 "verbatim, unnormalized" provenance posture). No guessing
  at other resolvers.
- **`citation_pdf_url` is a convention, not a guarantee.** The landing page may
  lack it (paywalled articles, non-conforming publishers). The honest response is
  a refusal naming the reason — never a heuristic guess at a PDF URL (the
  slice-6 PRD's "confidently wrong" objection, `remote-intake/prd.md:244-246`).
- **Reproducibility/verification impact.** None on the verdict path. The draft is
  still locator-less and human-reviewed; the safety net is the verdict contract —
  an unreviewed or wrongly-extracted claim degrades to `UNVERIFIED` at reproduce
  time, never `REPRODUCED`.
- **Dependency contract.** stdlib-only holds: `urllib`/`html.parser` for fetch,
  `pdftotext` as an external binary behind the seam (the git/pip/samtools
  precedent). `uv.lock` is unchanged.

## Risks & Open Questions

- **R1 — Two-column scientific PDFs degrade text extraction.** `pdftotext -layout`
  handles two-column layouts imperfectly; claim sentences can garble. Mitigation:
  the draft-only invariant — a garbled claim is a wrong draft entry the human
  prunes, and anything unreviewed degrades to `UNVERIFIED`. This is the
  brief's stated caveat; accepted by design.
- **R2 — The whole fetch/extract path is reasoned, not observed.** No real
  network, PDF, or `pdftotext` in CI; the urllib redirect+meta code and the
  poppler behavior are reasoned. Mitigation: the committed **manual post-merge
  gate with a stated decision rule** — fetch one real public DOI and extract one
  real paper PDF. The gate **passes** when (a) at least one real public DOI
  yields a reviewable draft through the real urllib path, and (b) every failure
  mode encountered (paywall, missing `citation_pdf_url`, garbled two-column
  text) is **recorded in the CHANGELOG entry** — including a deliberate attempt
  on a paywalled DOI to observe the refusal message in the wild. A gate that
  only ever tried open-access papers and never recorded a refusal does not
  pass. Same tier as the slice-6 manual gate that has not yet run; this slice
  does not claim otherwise.
- **R3 — `citation_pdf_url` absence is publisher-dependent.** Some DOIs resolve to
  landing pages with no public PDF. The honest refusal naming "no PDF URL found on
  the landing page" is the product behavior, not a bug. Revisit trigger: the first
  real DOI where the reason is unhelpful.
- **R4 — Caps are reasoned, not calibrated.** 64 MiB PDF cap and the 8 MiB
  extracted-text cap are engineering bounds, not measured distributions. A
  legitimately larger PDF fails honestly (naming the size) — acceptable, and the
  revisit trigger is the first real paper blocked by either cap.
- **Open question — flag-name reuse.** `--allow-fetch` already means "reach the
  network" on `contig reproduce`; reusing it on `extract-claims` keeps one
  vocabulary. Confirmed in interview; a future split (e.g. `--allow-network`) is a
  separate chore if it ever matters.
- **Pinned decisions for the specs (from the PRD self-critique).**
  - **Duplicate `citation_pdf_url` metas are never guessed:** two or more metas
    on one landing page → honest refusal naming the count, in the
    `resolve_pdf_url` contract (the pattern-locator 0-or->1 precedent).
  - **DOI normalization is pinned precisely:** strip surrounding whitespace;
    strip a leading `https://doi.org/`; **refuse** any DOI containing `?` or `#`
    (fragments/query are a different document); otherwise verbatim.
  - **Paywall refusal wording is product-surface, not engineering:** the "no
    PDF URL found on the landing page" message must say the paper may be
    paywalled and suggest the local-`.pdf` path, so the headline DOI gesture
    degrades into the offline path rather than dead-ending.

## Out of Scope

- **Direct `https://…pdf` URLs** other than `https://doi.org/…` — refused naming
  what is supported.
- **Locator inference** — the paper gives values, not where they live in a repo;
  inventing locators stays dishonest (extract-claims PRD R5).
- **Figure/plot and table-image claims** — hard-blocked (no plot-hash, stdlib-only
  dependency contract, `CAPABILITY_ROADMAP.md:2160-2167`).
- **PDF table extraction, PDF→text quality engineering, batch mode.**
- **Any change to `run_reproduction`, `classify`, `ClaimResult`, `ReproduceRecord`,
  the bundle, signing, or exit codes.**
- **Changes to the reproduce command's DOI refusal** (`classify_repo_argument`
  keeps refusing DOIs for git URLs).

## Non-Functional Requirements

- Test-first (RED before GREEN); deterministic, offline tests only.
- No new runtime dependency; `uv.lock` unchanged.
- Nothing written on any failure; no leftover temp files.
- All new tests mirror the repo conventions: no conftest, `tmp_path`,
  `CliRunner`, `monkeypatch` on `contig.cli.*` names.
- CHANGELOG entry in the standing C8 honest-scope register, naming the manual
  post-merge gate.

## Proposed aspect decomposition

1. `intake-classifier/` — M1: pure argument classification + `PaperArgument`.
2. `doi-fetch/` — M2: opt-in `--allow-fetch` wiring + stdlib DOI→PDF fetch +
   pure `resolve_pdf_url`.
3. `pdf-text-seam/` — M3: injectable `pdftotext` seam + size-bound wiring.
4. `cli-wiring/` — M4 + S1: branch wiring, sidecar provenance, all boundary
   refusals, Click introspection.

Sequencing: 1 → 2 → 3 → 4 (each aspect's acceptance is test-first and lands on the
same branch).