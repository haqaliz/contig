# Spec: pdf-text-seam (PDF → text extraction)

Aspect of: `reproduce-doi-pdf-intake`. Source: PRD M3 + the dependency contract.

## Problem slice and user outcome

A local `.pdf` (or a DOI-fetched PDF) becomes text for the shipped extractor
through an **injectable external-tool seam** — the `Fetcher`/`Installer` mould
(`runner.py:714-743`) — with `pdftotext` (poppler) as the default and **no new
Python dependency**. `pdftotext` is never executed in CI; tests inject fakes.

## In-scope requirements

- `PdfTextExtractor = Callable[[Path], tuple[int, str]]` seam type in
  `src/contig/verification/paper_intake.py`.
- `_pdftotext_argv(pdf: Path) -> list[str]` — pure, fixed argv:
  `["pdftotext", "-layout", str(pdf), "-"]` (stdout mode).
- `default_pdf_text_extractor(pdf: Path) -> tuple[int, str]`:
  - `subprocess.run(argv, capture_output=True)`; success → `(0, stdout text)`.
  - Missing executable (`FileNotFoundError`) → `(127, …)` naming `pdftotext`
    and the install (`brew install poppler` / `apt install poppler-utils`) —
    never a traceback (the `default_fetcher` `(127, "git executable not
    found")` precedent, `runner.py:1165`).
  - Non-zero exit → `(rc, stderr-or-message)`; the message is the refusal
    text.
- The extracted text is **not** size-checked inside the seam — the 8 MiB
  `_MAX_MATCH_BYTES` check on extracted text is enforced by `cli-wiring`
  (extractor input contract). The seam returns text; bounds are the caller's
  job (single-responsibility, mirrors the text path where the CLI stats).
- The default is import-safe and lazy: importing `paper_intake` pulls no
  external tool; `pdftotext` is resolved at call time via PATH.

## Out-of-scope boundaries

- No Python PDF library (stdlib-only contract — the hard-block precedent,
  `CAPABILITY_ROADMAP.md:2160-2167`).
- No fallback tool ladder (`textutil`, `mutool`) in v1 — one tool, fixed argv
  (N2 in the PRD: a `--pdf-extractor` override is a future slice).
- No `pdftotext` invocation in CI: the default is shape-asserted only; all
  behavioral tests use a scripted extractor or a monkeypatched
  `subprocess.run`.
- No PDF→text quality engineering (two-column degradation is the PRD R1
  accepted caveat; the draft-only invariant is the safety net).

## Acceptance criteria (testable)

- `_pdftotext_argv(Path("a.pdf"))` == `["pdftotext", "-layout", "a.pdf", "-"]`
  (exact list, no shell, no interpolation).
- `default_pdf_text_extractor` with monkeypatched `subprocess.run`:
  - fake return `(0, b"text")` → `(0, "text")`;
  - `FileNotFoundError` → `(127, …)` with `"pdftotext"` and
    `"poppler"`/`"brew"` in the message;
  - fake `(1, b"boom")` → `(1, "boom")` (stderr surfaced).
- The seam never runs in CI: a test asserts `default_pdf_text_extractor` is
  callable and that `subprocess.run` is patchable at module scope (the call
  site is `paper_intake.subprocess.run` — the test patches that name, proving
  the production code path is injectable).

## Dependencies and sequencing notes

- Independent of `doi-fetch` (both only need the module file from
  `intake-classifier`); can run in parallel. Both are prerequisites of
  `cli-wiring`.
- `MAX_PDF_BYTES = 64 * 1024 * 1024` (the PDF size cap) is defined in this
  aspect's module (a public constant, enforced by `cli-wiring`).

## Open questions / risks

- `pdftotext -layout` output quality on two-column papers is unmeasured
  (reasoned-not-observed); the manual gate (PRD R2) is the go/no-go.
- PATH resolution: a user without poppler gets the `(127, …)` refusal naming
  the install — the documented behavior, not a defect.