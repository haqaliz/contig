# Spec: cli-wiring (extract-claims DOI/PDF intake)

Aspect of: `reproduce-doi-pdf-intake`. Source: PRD M2, M4, S1, R2-R4 + pinned decisions.

## Problem slice and user outcome

The `contig extract-claims` command accepts DOI / local-PDF / text inputs,
applies the opt-in `--allow-fetch` posture for DOIs, acquires the source text
through the seams, and lands it in the **unchanged** extractor + draft commit
path. Every refusal is a named message with nothing written; the existing text
path is byte-identical in observable behavior.

## In-scope requirements

- `extract-claims` gains `--allow-fetch/--no-allow-fetch` (default off),
  registered via Click and asserted by param introspection.
- Command body restructure (preserving every existing refusal message and
  guard test for the text path):
  1. `classify_paper_argument(paper)` → any `refusal` → echo + `Exit(1)`
     (before any I/O).
  2. `kind == "doi"` and not `allow_fetch` → echo naming `--allow-fetch`
     (the flag mistake reports the flag mistake — the `--rev`-precedence
     precedent) + `Exit(1)`.
  3. `kind in ("text", "pdf")`: the existing `--out == input` check (the
     `--out` would overwrite the paper). Skipped for `doi` (a DOI cannot be
     resolved to a path; `Path.resolve()` on it would be nonsense).
  4. Existing `--out` without `--force` refusal — **before any fetch** (don't
     pay for the network then refuse; the remote-intake ordering precedent).
  5. Existing `--out` directory check.
  6. Source acquisition:
     - `text`: existing stat-before-read + UTF-8 read (unchanged code).
     - `pdf`: stat-before-read with `MAX_PDF_BYTES` (64 MiB) cap (missing /
       not-a-file / over-cap → named refusals, nothing written); then
       `default_pdf_text_extractor(pdf)`; non-zero → refusal echoing the
       seam's message.
     - `doi`: `default_paper_fetcher(doi, tmp_dest)` (temp file, cleaned in
       `finally`); non-zero → refusal echoing the fetcher's message; then the
       same stat-cap + extractor path as `pdf`.
  7. Extracted-text size check for `pdf`/`doi` kinds: text over
     `_MAX_MATCH_BYTES` (8 MiB) bytes → refusal naming the size (the
     extractor input contract). The `text` kind is already bounded by its
     stat check.
  8. **Unchanged tail:** `default_extractor(text, use_llm=not no_llm)` →
     draft → temp → `load_claims` round-trip → `os.replace` → sidecar; empty
     extraction exits 0.
- **S1 — sidecar provenance:** for `doi`/`pdf` kinds the review sidecar header
  gains a `Source:` line (the DOI as fetched, or the local PDF path). The
  `text` path's sidecar is byte-identical to today.
- The command imports the seams from `contig.verification.paper_intake` at
  module level and passes them explicitly (`default_paper_fetcher`,
  `default_pdf_text_extractor`), so tests monkeypatch
  `contig.cli.default_paper_fetcher` / `contig.cli.default_pdf_text_extractor`
  (the `contig.cli.default_fetcher` precedent).
- Nothing is written on any failure; fetched temp files are removed on every
  path (success and failure).

## Out-of-scope boundaries

- No change to `run_reproduction`, `classify`, `ClaimResult`,
  `ReproduceRecord`, the bundle, signing, or exit codes.
- No change to the reproduce command (`--allow-fetch` there is untouched).
- No locator inference; no direct non-doi.org URL intake.
- No change to `claim_extraction.py` or the existing `test_cli_extract_claims.py`
  tests (they must pass untouched).

## Acceptance criteria (testable)

New test file `tests/test_cli_extract_claims_intake.py` (repo conventions: no
conftest, `CliRunner`, `tmp_path`, `monkeypatch`):

- DOI without `--allow-fetch`: exit 1, `"--allow-fetch"` in output, nothing
  written, no fetcher call (scripted fetcher must not be invoked).
- DOI with flag + scripted fetcher (writes a real fixture PDF to `dest`) +
  scripted extractor (returns known text): draft written, `load_claims(draft)`
  loads, sidecar written with a `Source:` line.
- Local `.pdf` + scripted extractor: draft written and loads; sidecar has the
  PDF path.
- Fetcher non-zero: exit 1, fetcher's message echoed, nothing written, temp
  cleaned.
- Extractor non-zero (`(127, …)`): exit 1, message echoed, nothing written.
- PDF over `MAX_PDF_BYTES` (sparse file, `truncate`): exit 1, size named,
  nothing written.
- Extracted text over `_MAX_MATCH_BYTES` (scripted extractor returns a string
  of that many bytes): exit 1, size named, nothing written.
- Existing `--out` without `--force`: refuses **before** the fetcher is called
  (scripted fetcher records it was never invoked).
- Click introspection: `--allow-fetch` (and `--no-allow-fetch`) registered on
  `extract-claims`.
- Empty extraction via the PDF path: `[]` draft + "no numeric claims found"
  sidecar, exit 0.
- Text-path guards unchanged: the existing `tests/test_cli_extract_claims.py`
  file passes without modification.

## Dependencies and sequencing notes

- Requires `intake-classifier` (classifier), `doi-fetch` (fetcher +
  `PaperIntakeError`), `pdf-text-seam` (extractor + `MAX_PDF_BYTES`).
- `src/contig/cli.py` is the only production file changed in this aspect.

## Open questions / risks

- The guard-order restructure is the highest-risk change: the existing
  refusal-message tests pin behavior, and the plan preserves them by keeping
  the text-path branch byte-identical. The `--out == input` check must be
  skipped only for `doi` kind.
- Temp-file lifecycle: `tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")`
  (or `mkdtemp`) with cleanup in `finally`; a leak on an untested path is a
  defect — one test asserts no leftover temp after a failing fetch.