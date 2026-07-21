# PRD — TSV/CSV output-locator for `contig reproduce` (C8 slice 3)

**Slug:** `reproduce-tsv-csv-locator`
**Branch:** `feat/reproduce-tsv-csv-locator/aliz`
**Capability:** C8 (`docs/technical/CAPABILITY_ROADMAP.md:1047-1178`) — the TSV/CSV locator
deferred as "the named next step" by both shipped output-locator slices
(`CAPABILITY_ROADMAP.md:1093,1122`; `reproduce-output-locator/prd.md:121`).
**Parent PRDs:** slice 1 `reproduce-published-work/prd.md` · slice 1.5
`reproduce-output-locator/prd.md`.
**Status:** Interview complete (3 shaping decisions locked via AskUserQuestion). Pending
prd-generator critique + review-gate approval.

---

## Problem Statement

`contig reproduce` binds each claim's observed value either from a flat Contig-shaped
`results.json` (slice 1) or from a **JSON** output-locator `{"from":…, "path":"$.a.b[0]"}`
(slice 1.5, `reproduce.py:112-132,315-362`). Both only read repos that emit **structured
JSON**. But in bioinformatics the numbers a paper reports overwhelmingly live in
**tabular** output — DESeq2 results tables, count matrices, feature/stat tables — as
`.tsv`/`.csv` (often gzipped). Against those repos every claim degrades to `UNVERIFIED`
today: an honest but useless "couldn't check."

JSON-only is therefore a *weak* locator for this domain specifically. A **TSV/CSV cell
locator** — "the number for this claim is the `log2FoldChange` column of the row whose
`gene_id` is `ENSG…`, in `results/deseq2.tsv`" — is what lets `contig reproduce` read the
numbers real cloned bioinformatics repos already emit, without modifying the repo.

**Evidence it's real:** the C8 reproducibility numbers (~3.2% of 27,271 biomedical
notebooks reproduce; `CAPABILITY_ROADMAP.md:1136-1141`); both shipped locator slices name
TSV/CSV as the explicit next step; tabular output is the dominant numeric-result format in
nf-core / Bioconductor / DESeq2 workflows. On-thesis Layer 2 (a resolver over verify
output; never NL→workflow, never a conclusions verdict).

## Goals & Success Metrics

- **G1 — A claim can locate its value in a repo's tabular output.** A claim carrying
  `{"from": <repo-relative .tsv/.csv[.gz]>, "row": …, "column": …}` binds its observed
  number from that cell and classifies with the existing verdict. *Measured:* a fixture
  repo emitting `results/deseq2.tsv` (a shape Contig never dictated) yields
  `REPRODUCED`/`WITHIN-TOLERANCE`/`DIVERGED` per claim through the table locator (engine +
  CLI tests).
- **G2 — Two addressing modes work.** Named (header column name + `row` key-column match)
  **and** positional (integer column index + integer row index, incl. `header:false`),
  each proven by tests.
- **G3 — No false reproduce, ever.** Every unresolved / ambiguous / unparseable / non-finite
  address yields `UNVERIFIED`, never `DIVERGED`. *Measured:* dedicated tests for each
  failure mode assert `unverified`.
- **G4 — Stdlib-only, no new dependency.** Parsing uses stdlib `csv` + `gzip`; the runtime
  dep set stays `pydantic`/`typer`/`cryptography` (`pyproject.toml:30-34`). *Measured:* no
  dependency added; suite green (baseline **1757 passed, 1 skipped**).
- **G5 — No egress / containment holds.** An escaping/absolute `from` on a table claim is
  refused **before any run** (exit non-zero, no record), and the engine never reads outside
  the repo. *Measured:* CLI + engine containment tests, mirroring the JSON-locator tests.
- **G6 — Full back-compat.** JSON-locator claims, flat `results.json` claims, models,
  bundle, signing, `--fail-on-diverged` all behave byte-identically. *Measured:* existing
  reproduce/locator suites unchanged and green.

## User Personas & Scenarios

- **A, lone computational biologist:** clones a published RNA-seq repo that writes
  `results/deseq2_results.tsv`. Writes a claims file: "the paper says gene X has
  log2FC −2.31; find it in that table." `contig reproduce` reads the cell and reports
  `REPRODUCED`/`DIVERGED` — no edit to the repo, no JSON export step.
- **C, core facility:** batch-checks many labs' published pipelines; most emit TSV count /
  stats tables. Wants a per-claim verdict over those tables with the same honesty contract
  as a first-party run.

## Requirements

### Must-have (this slice)

- **M1 — Table locator schema (extends `load_claims`, `reproduce.py:210-222`).** When a
  claim has `from`, it must carry **exactly one** addressing mode:
  - **JSON** (existing): `path` (string). Unchanged.
  - **Table** (new): `column` **and** `row`, with optional `delimiter` and `header`.
  Validation (structural, repo-agnostic — raises `ClaimsError`, exit non-zero, nothing
  written):
  - `from` present ⟹ exactly one of {`path`} XOR {`column`+`row`}; presence of both a
    `path` and any table field is a contradiction → error.
  - `from` present with neither `path` nor a complete `{column,row}` → error (the existing
    "must set both 'from' and 'path', or neither" rule generalizes).
  - `column`: a non-empty **string** (header name) **or** a **non-negative int** (0-based
    field index). Anything else → error.
  - `row`: a **non-negative int** (0-based data-row index) **or** a non-empty **object**
    `{col: value}` (key-column match; `col` a non-empty string, exactly one pair this
    slice) → else error.
  - `delimiter` (optional): a **single-character** string; else error. Absent ⟹ inferred
    from extension. **An unknown/unsupported extension (e.g. `.txt`) with no explicit
    `delimiter` is a `ClaimsError` at load time** (pre-run, structural — never a silent
    wrong-delimiter parse). Supported inferrable extensions: `.tsv`/`.tab` → tab,
    `.csv` → comma, each also with a `.gz` suffix.
  - `header` (optional): a **bool**, default `true`; else error.
  - **Structural contradiction rejected pre-run:** `row` as a key-match object **requires**
    named columns, so `row`-object **+** `header:false` → `ClaimsError` (a header is
    required to name a key column). `column` as a string with `header:false` likewise →
    `ClaimsError`. (These are input-shape contradictions, not repo-data facts, so they
    belong in `load_claims`, not the run-time reader.)
  - Table fields present **without** `from` → error (locator fields require a source).
- **M2 — Typed carrier.** Add a `TableLocator(source, column, row, delimiter, header)`
  dataclass alongside the existing JSON `Locator` (`reproduce.py:139-150`); widen
  `Claim.locator` to `Locator | TableLocator | None` (`reproduce.py:165`). The JSON
  `Locator` is untouched.
- **M3 — Delimiter + parser (stdlib).** Inferred delimiter: `.tsv`/`.tab`(+`.gz`) → `\t`,
  `.csv`(+`.gz`) → `,`; an explicit `delimiter` overrides for any extension. Files are read
  with stdlib `csv.reader`; `.gz`/`.tsv.gz`/`.csv.gz` are read transparently via stdlib
  `gzip` (text mode, utf-8). A non-utf-8 or unreadable/unparseable file → that claim
  `UNVERIFIED` (never raises), mirroring the JSON reader's `_observe_located` failure
  handling.
- **M4 — Cell resolution → observed value (new reader, sibling of `_observe_located`).**
  For a located table claim on a completed run:
  - **Header mode (default, `header:true`):** row 0 is the header. Resolve the **column**:
    a string matches a header name (a **duplicate** header name → UNVERIFIED, never an
    arbitrary pick); an int is a 0-based field index (out of range → UNVERIFIED). Resolve
    the **row**: an int is a 0-based index over **data rows** (after the header; out of
    range → UNVERIFIED); an object `{key_col: val}` selects the data row whose `key_col`
    cell equals `val` as a **string compare** — **0 matches or >1 matches → UNVERIFIED**
    (omit-never-guess).
  - **Headerless mode (`header:false`):** no header row; **column** must be an int (field
    index), **row** must be an int (index over all rows). (The string-column /
    object-row combinations were already rejected in M1.)
  - **Degenerate/ragged tables → UNVERIFIED, never a raise.** An empty file, a header-only
    file (0 data rows), a `from` that resolves to a directory, or a **row shorter than the
    addressed column index** (ragged row) is treated as an out-of-range/uncomputable
    address → `UNVERIFIED`. The reader must be crash-proof on any shape (mirrors
    `resolve_pointer`'s "never raises").
  - **Key-column compare is exact on the `.strip()`ed cell string** (consistent with the
    `float()` `.strip()` below) — no case-folding, no quote-stripping beyond what
    `csv.reader` already removes. A near-miss (trailing space handled by strip; a genuinely
    different string) simply doesn't match → the 0-match path, not a fuzzy guess.
  - The selected cell is a **string**; parse it with `float()`. A cell that does not parse
    as a float (empty, `"NA"`, `"1,024"`, text) → **UNVERIFIED**. **Note (differs from
    JSON):** a numeric *string* is the **normal, valid** case for a table cell (every cell
    is a string), so the JSON rule "numeric string is strictly UNVERIFIED" does **not**
    transfer — the table contract is "float-parse the cell; parseable finite float =
    observed value, else UNVERIFIED." A parsed `nan`/`inf` → UNVERIFIED (reuse the
    finite-guard). `bool` is not reachable (cells are strings), so no bool guard is needed
    in this branch.
  - The observed float feeds the **unchanged** `classify` (`reproduce.py:236-274`) →
    REPRODUCED/WITHIN-TOLERANCE/DIVERGED. Any resolution failure returns `(None, message)`
    → `UNVERIFIED`, never `DIVERGED`.
- **M5 — Path safety (reject pre-run), reusing the JSON guard.** A table claim's `from`
  flows through **`Locator.source`/`TableLocator.source`** so the existing CLI containment
  loop (`cli.py:800-816`) and the engine defense-in-depth guard (`reproduce.py:321-325`)
  already cover it **iff** the field is named `source`. Requirement: the CLI pre-check must
  iterate table locators too — an escaping/absolute `from` → exit non-zero, **no record**;
  a path reaching the engine directly → that claim `UNVERIFIED`, file **never read**.
- **M6 — Per-file parse cache.** A table `from` file is parsed **at most once per run**
  (multiple claims can target different cells of the same big table), mirroring the JSON
  `_json_cache` (`reproduce.py:313,327-339`). Cache the parsed rows (a `list[list[str]]`)
  keyed by resolved absolute path.
- **M7 — Verdict / model / bundle reuse unchanged.** `classify`, `reduce_reproduction`,
  `ClaimResult`, `ReproduceRecord`, `write_reproduce_bundle`, signing,
  `render_reproduction`, `--fail-on-diverged` all reused as-is. **No `models.py` change** —
  the locator lives on the input `Claim`; a `ClaimResult` records only the resolved observed
  number. `claims_sha256` already covers the new keys (claims-file bytes).

### Should-have

- **S1 — Message quality.** A table-locator `UNVERIFIED` names *why*:
  `from 'results/de.tsv' missing`, `column 'log2FoldChange' not found in header`,
  `row {gene_id: X} matched 0 rows` / `matched 3 rows`, `row index 900 out of range
  (412 data rows)`, `cell 'NA' at (row…, col…) is not a finite number`. A
  `DIVERGED`/`WITHIN-TOLERANCE` still names observed-vs-stated + delta (unchanged).
- **S2 — `contig reproduce` docs / help.** A one-line note that a claim locator may target
  a JSON path **or** a TSV/CSV cell; a short claims-file example in the reproduce help or
  docs.

### Nice-to-have (explicitly later slices, NOT this one)

- Multi-key row match (`{colA: x, colB: y}`), regex/numeric row predicates, column ranges.
- stdout/log scraping; notebook (`.ipynb`) numeric extraction.
- Paper-parsing to auto-extract claims + locators; **figure/plot & table-image claims**
  (hard-blocked: no plot-hash, stdlib-only, `CHANGELOG` slice-1 correction).
- Remote `<doi|url>`; dashboard card; C6 eval fold-in.

## Technical Considerations

- **Localized change, mirroring slice 1.5.** New: a `TableLocator` dataclass + table
  branch in `load_claims` validation + a new cell-reader (sibling of `_observe_located`) +
  an isinstance dispatch at the `run_reproduction` branch (`reproduce.py:458`) + the CLI
  containment loop learning table locators. Everything downstream of "observed value" is
  untouched.
- **Stdlib-only.** `csv` (with the resolved delimiter) + `gzip` (transparent decompress) +
  `math.isnan/isinf` (already imported). No pandas/numpy — confirmed absent
  (`pyproject.toml:30-34`); a table is a `list[list[str]]`, not a DataFrame.
- **Indices are 0-based**, matching the JSON locator's `[n]` list indices, so the two
  locators share one mental model. Stated in help/docs to avoid a 1-based misread.
- **Reproducibility/verification impact:** widens *what* the signed verdict can be computed
  over (repos that emit tables as-is) **without** weakening the honesty contract —
  `UNVERIFIED`-on-any-doubt is load-bearing and preserved; ambiguity is surfaced, never
  guessed.
- **Determinism/CI:** no real repo, no network, no pip. Scripted executor + on-disk fixture
  `.tsv`/`.csv`/`.tsv.gz` files in `tmp_path`, mirroring `tests/test_reproduce.py`,
  `tests/test_reproduce_locator.py`, `tests/test_cli_reproduce.py`.

## Data Model / Artifact Contracts

**Claims file (input), extended — a claim is one of three shapes:**
```json
[
  {"id": "brca1_lfc", "value": -2.31, "tolerance": 0.05,
   "from": "results/deseq2.tsv",
   "row": {"gene_id": "ENSG00000012048"}, "column": "log2FoldChange"},

  {"id": "cell_42_count", "value": 1204,
   "from": "out/counts.csv.gz",
   "row": 41, "column": 2, "header": false},

  {"id": "auc", "value": 0.91, "from": "out/summary.json", "path": "$.model.auc"},

  {"id": "mean_cov", "value": 30.4}
]
```
1. **Table (named):** `from` + `column` (str) + `row` ({key:val}), header assumed.
2. **Table (positional):** `from` + `column` (int) + `row` (int) + `header:false`.
3. **JSON (slice 1.5):** `from` + `path`. **Flat (slice 1):** neither — id lookup in
   `--results`.

- **`from`:** repo-relative path to a `.tsv`/`.csv`/`.tab`(+`.gz`) file the repo produces.
- **`delimiter`** (optional, table only): single char overriding the extension inference.
- **`header`** (optional, table only): bool, default `true`.
- **`ClaimResult` / `ReproduceRecord`:** **unchanged**. A located table claim populates
  `observed`/`delta`/`status`/`message` through the same fields.

## Risks & Open Questions

- **R1 — Row-key ambiguity is the false-reproduce trap.** A key that matches 2 rows must
  never silently pick one. Guardrail: 0 or >1 matches → `UNVERIFIED` with the count in the
  message (G3). A dedicated test asserts this.
- **R2 — Locale/format cells.** `"1,024"` (thousands), `"1.2e-3"`, `"NA"`, `"1.5%"`,
  trailing spaces. Decision: plain Python `float()` after `.strip()`; anything it rejects
  → `UNVERIFIED` (never a heuristic un-comma). Scientific notation `1.2e-3` parses
  natively; `NA`/`%`/thousands do not → honest UNVERIFIED. Stated so it isn't mistaken for
  a bug.
- **R3 — "Located but still UNVERIFIED" stays common.** Numbers in prose, plots, or
  notebooks aren't reached by this slice (scope: delimited tables). Honest framing: the win
  is "reads repos that emit TSV/CSV tables," not "reads any repo."
- **R4 — Engine-vs-CLI containment split.** Same split as slice 1.5 — containment rejects
  pre-run in the CLI (has the repo path); the engine keeps a defensive UNVERIFIED for an
  escaping `from`. Both must hold "no egress." Confirm in tech-plan the loop at
  `cli.py:800-816` iterates table locators (reusing `.source`).
- **R5 — Discriminator clarity.** `path` vs `column`+`row` must be unambiguous; a claim
  mixing them is a `ClaimsError` (M1), not a silent precedence. Test the contradiction.
- **R6 — Degenerate & ragged tables.** Empty file, header-only, directory `from`, or a row
  shorter than the column index must all yield `UNVERIFIED` without raising (M4). A ragged
  row is the likeliest crash source — explicit test required.
- **R7 — Unknown extension.** A `.txt`/`.dat` table with no `delimiter` is a load-time
  `ClaimsError` (M1/M3), never a silent wrong-delimiter parse.

## Out of Scope (explicit)

- Multi-key/predicate row match, column ranges, regex — single key-column equality only.
- stdout scraping, notebook/prose parsing, figures/plots/table-images (hard-blocked: no
  plot-hash; stdlib-only).
- Any new dependency (pandas/numpy/JSONPath/jq). Any `models.py`/bundle/signing change.
- Environment resurrection (shipped, slice 2), paper-parsing, remote fetch, dashboard card,
  C6 eval fold-in — all other slices.
- Any judgement on the paper's conclusions. Computation-vs-numbers only.

## Post-merge validation (not a CI test)

Per the slice-1/1.5 greenlight discipline: after merge, run `contig reproduce` against
**≥1 real cloned public repo** that emits a TSV/CSV table (e.g. an nf-core/rnaseq or a
DESeq2 results table), with a hand-written claims file using a table locator, and confirm
the per-claim verdict is sensible. The honest go/no-go signal for investing in the next
slice. Manual, offline-optional, not gated in CI.

## Guardrail check (`CLAUDE.md`)

Layer 2 only (a cell resolver over verify output; never NL→workflow, never a conclusions
verdict) ✅ · Moat = verification/reproducibility infra + corpus ✅ · Gets better as base
models improve (claim/locator extraction in later slices) ✅ · Founder's edge / stdlib-only
✅ · No raw-data egress (repo-relative, escape-guarded; only hashes + claim diffs leave the
box) ✅ · Test-first ✅.
