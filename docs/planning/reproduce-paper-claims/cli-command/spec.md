# Aspect spec: cli-command

Parent PRD: `../prd.md`. Aspect 3 of 3. Depends on `extractor-core` + `llm-assist`.

## Problem slice & user outcome

The user-facing command: read a paper's local text, run the extractor, and write a
**schema-valid draft claims file** plus a **review sidecar** — never touching the verdict path.
This is what makes the feature usable and what guarantees we never emit a file our own
`load_claims` would reject.

## In scope

- **New `@app.command()` `extract_claims`** (CLI name `extract-claims`) in `src/contig/cli.py`,
  placed **after** `reproduce` (~line 994). It must **not** import or call `run_reproduction`.
- **Signature:**
  - `paper: str` — positional Argument, a local `.txt`/`.md` path.
  - `--out <path>` — required, the draft claims JSON.
  - `--no-llm` — bool (default False): force core-only even when a provider is configured.
  - `--force` — bool (default False): overwrite an existing `--out` (else refuse).
- **Composition seam for tests:** a module-level `default_extractor(text: str, *, use_llm: bool)
  -> list[ExtractedClaim]` in `cli.py` (mirrors `default_command_executor`/`default_installer`/
  `default_fetcher`) that runs `extract_claims` and, when `use_llm` and a provider is configured,
  merges `extract_with_llm` via `merge_claims`. CLI tests monkeypatch
  `contig.cli.default_extractor` — no seam plumbing into the extractor internals from tests.
- **Input handling (honest, nothing-written-on-failure):**
  - Missing / directory / unreadable path → exit non-zero, nothing written.
  - **Size-bounded:** `stat()` **before** read; over the cap (reuse `reproduce._MAX_MATCH_BYTES`
    = 8 MiB, or a sibling constant) → exit non-zero naming the size and cap.
  - Read as UTF-8; a non-UTF-8 file → exit non-zero, nothing written.
- **Draft build & the load_claims round-trip invariant (load-bearing):**
  - Build a list of **locator-less** claims: `{"id", "value", "tolerance"}` only (tolerance =
    default `0.1`), **no other keys** — all provenance goes to the sidecar.
  - **Validate by round-trip before committing the output:** serialize the list, write to a
    temp file in the destination dir, call the unchanged `load_claims` on it; on success
    `os.replace` to `--out`; on failure remove the temp and exit non-zero with an
    internal-error message (this path is a bug — a test pins that it never fires for real
    extractor output). We never leave a draft our reproduce path can't load.
  - **Overwrite guard:** if `--out` exists and `--force` is not set → exit non-zero naming
    `--force`; nothing written.
- **Review sidecar `<out>.review.md`** (path: `out.with_suffix(".review.md")` when `out`
  ends in `.json`, else `str(out) + ".review.md"`):
  - Header explaining the workflow: each claim needs a locator (`from`+`path` / `pattern` /
    `column`+`row` / `cell`+`pattern`) added before `contig reproduce`, and any `%`-unit claim
    needs its scale reconciled against the repo's output (resolves PRD 🟡 #2, empty/unit half).
  - Per claim: `id`, `value`, `unit` (or "—"), `origin` (`heuristic`/`llm`), and the
    `source_text` sentence. `llm`-origin (and any flagged) candidates ordered/marked "review
    first."
- **Empty extraction is not an error:** write `[]` to `--out` + a sidecar stating "no numeric
  claims found; add claims by hand or check the input," echo the same, exit **0**.
- **Success output:** echo a summary — n claims, the out path, the sidecar path, and "review
  and add locators before running contig reproduce."

## Out of scope (this aspect)

- The extractor logic itself (aspects 1–2). Any change to `reproduce`/`run_reproduction`/the
  verdict/bundle/exit contract. A dashboard surface. PDF/DOI/fetch.

## Acceptance criteria (test-first)

Using the `test_cli_reproduce.py` discipline (`CliRunner`, `tmp_path`, `monkeypatch`, on-disk
fixtures; the real LLM never called):

- A fixture `.md` → `--out` draft **loads cleanly through `load_claims`** (the central invariant),
  and the `.review.md` sidecar exists with the source sentences.
- Missing input → exit≠0, **no** `--out`, **no** sidecar written.
- Oversized input (`stat` over the cap) → exit≠0 naming the size; nothing written.
- Non-UTF-8 input → exit≠0; nothing written.
- Existing `--out` without `--force` → exit≠0 naming `--force`; the existing file is untouched.
  With `--force` → overwritten.
- `--no-llm` → core-only even when a (dummy) provider is configured (monkeypatched
  `default_extractor` asserts `use_llm=False`); default → llm merged when configured.
- Empty extraction → `[]` draft + sidecar + exit **0**.
- **Flag/arg registration asserted by introspecting the Click command params** (`--out`,
  `--no-llm`, `--force`), **never** by scraping Rich-rendered `--help` text (that flakes under
  CI's no-TTY — per the repo's standing rule).
- The reproduce test suite and CLI thereof are untouched and green (zero blast radius).

## Dependencies & sequencing

Last. After `extractor-core` and `llm-assist`. This is the integration aspect.

## Open questions / risks

- Sidecar exact wording/ordering — settle in implementation; keep it greppable and instructive.
- Whether `--no-llm` is must- or should-have — spec includes it (cheap, honest); tech-plan may
  stage it.
