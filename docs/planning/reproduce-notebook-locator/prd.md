# PRD — Notebook (`.ipynb`) claim locator for `contig reproduce` (C8, slice 5)

**Slug:** `reproduce-notebook-locator`
**Branch:** `feat/reproduce-notebook-locator/aliz`
**Capability:** C8 (`docs/technical/CAPABILITY_ROADMAP.md` → C8) — slice 5, the notebook
extraction named as deferred-but-unblocked in the slice-3 and slice-4 entries.
**Status:** Interview complete; pending prd-generator critique + review-gate approval.

---

## Problem Statement

`contig reproduce` can now bind a claim's observed value out of a repo's JSON (slice 1.5,
v0.41.0), a TSV/CSV cell (slice 3, v0.43.0), or free text via regex (slice 4, v0.44.0).
It cannot read a **Jupyter notebook**, so every claim against a published `.ipynb`
degrades to `UNVERIFIED`.

That is the single largest remaining hole in C8's reach, and the C8 PRD's own evidence base
is entirely about notebooks: of 27,271 biomedical-paper notebooks only ~3.2% reproduced the
original result (Samuel & Mietchen, *GigaScience* 2024), and Pimentel's 1.4M-notebook study
finds ~4% (`docs/planning/reproduce-published-work/prd.md:13-14`). Notebooks are the medium
the reproducibility crisis is measured in, and the medium Contig currently cannot face.

**Who has the problem:** persona A, the lone computational biologist / reviewer, who wants
to know whether a paper's headline numbers regenerate before building on them. Today, if
the paper ships a notebook — the common case — Contig's honest answer is "unverified,"
which is correct but useless.

**Cost of the status quo:** the C8 surface reads three artifact families and misses the one
its own problem statement cites. A reviewer's only options are to modify the third-party
repo (the "cooperative repo" trap slice 1.5 existed to escape) or read the numbers by hand.

## Goals & Success Metrics

- **G1 — A notebook claim binds and classifies.** A claim carrying `{"from": "<x.ipynb>",
  "cell": …, "pattern": …}` resolves its observed value out of the addressed cell's output
  and classifies through the **unchanged** `classify`. *Measured:* engine tests at
  `reproduced` / `within_tolerance` / `diverged` / `unverified`.
- **G2 — No false pass from a stale notebook.** A notebook the run did not rewrite is
  `UNVERIFIED` naming the staleness, **never** `REPRODUCED`. *Measured:* a fixture notebook
  whose mtime predates the run start is UNVERIFIED even when its stored output matches the
  claim exactly — the single most important test in this slice.
- **G3 — Honest degradation everywhere else.** Missing / unparseable / non-notebook `from`,
  out-of-range or ambiguous cell address, a cell with no outputs, a pattern matching 0 or
  >1 times, an unparseable or non-finite capture → all `UNVERIFIED`, never `DIVERGED`.
  *Measured:* one test per path.
- **G4 — Pre-run schema validation.** A malformed notebook claim is a `ClaimsError` that
  exits non-zero with **nothing written** — no run, no record, no bundle. *Measured:* CLI
  tests assert exit 1 and an empty runs dir.
- **G5 — Zero new dependencies, deterministic, offline.** *Measured:* `pyproject.toml`
  runtime deps unchanged (no `nbformat`, no `jupyter`); the suite runs with on-disk fixture
  notebooks, scripted executors, explicit `os.utime` mtimes, and no network.

**Non-metric goal:** keep the fifth locator a *sibling*, not a reshape —
`classify` / `ClaimResult` / `ReproduceRecord` / bundle / signing / `--fail-on-diverged`
reused as-is, **no `models.py` change**.

**Post-merge validation (outside CI, mirroring slice 1's G2 self-critique):** run it once
against a real cloned public repo with a notebook and a hand-written claims file, and
confirm the per-claim verdict is sensible. That is the honest proof the surface works.

## User Personas & Scenarios

- **A — lone computational biologist / reviewer (primary).** Clones a paper's repo, runs
  its notebook through `jupyter nbconvert --execute --output out.ipynb`, and writes a
  claims file naming the cell and the printed number. Gets a per-claim verdict and a signed
  record to cite.
- **D — biotech researcher / core facility.** Same bundle, consumed as a defensible artifact
  recording which of a dependency-repo's numbers regenerated.

## Requirements

### Must-have

- **M1 — `NotebookLocator`.** A new frozen dataclass, sibling of `Locator` / `TableLocator`
  / `PatternLocator`, with fields `source: str` (the claims file's `from`; named `source`
  so it reuses every existing `.source` code path, including the CLI containment loop —
  **no `cli.py` containment change**), `cell: int | dict[str, str]`, and `pattern: str`.
- **M2 — Cell addressing: `int | {"contains": "<substring>"}`.** Mirrors the shipped
  `TableLocator.row` duality exactly.
  - An **integer** indexes the notebook's `cells` array (0-based, JSON-faithful — *all*
    cells, not code-cells-only); out of range → unresolved naming the cell count.
  - A **`{"contains": "<substring>"}`** object selects the cell whose `source` contains
    that substring, scanning the same full `cells` array. **0 or >1 matches → unresolved
    with the count named**, never an arbitrary pick (the shipped `resolve_cell` row-key and
    `resolve_match` rules).
- **M3 — Output text extraction: stdout + `text/plain`, in output order.** The addressed
  cell's `outputs` are concatenated in order, taking `stream` outputs whose `name` is
  `stdout` and `execute_result`/`display_data` outputs' `data["text/plain"]`. **Excluded:**
  `stderr` streams (progress bars/warnings are accidental match surface) and `error`
  tracebacks (a claim must never bind a number out of a traceback). `source` and `text`
  are `str` **or** `list[str]` per nbformat — both handled, list joined with no separator.
  A cell with no qualifying output → unresolved.
- **M4 — `pattern` is required and does the capture.** The extracted cell text is fed to
  the **shipped, unchanged `resolve_match`**, which supplies the capture rule (group 1 if
  the pattern has groups, else the whole match) and the strict 0-or-many ambiguity guard.
  No second binding path.
- **M5 — Numeric-string rule: slice-3/4, not slice-1.5.** A notebook output is a string by
  construction, so the capture is `.strip()`ed and `float()`-parsed; unparseable or
  non-finite → `UNVERIFIED`.
- **M6 — Freshness guard (the load-bearing requirement).** A notebook locator resolves only
  if the file's **mtime is at or after the run's start**; otherwise `UNVERIFIED` with a
  message naming that the notebook was not rewritten by this run. The run-start wall-clock
  timestamp is **passed into `run_reproduction`** (never generated inside it) so the engine
  stays deterministic and testable, consistent with how `created_at`/`reproduce_id` are
  already handled.
  - Rationale: "executed vs committed" is undecidable (`execution_count` is non-null in any
    committed notebook); "**rewritten by this run**" is decidable, and it is the property we
    actually need. Without it, a committed notebook — which always looks like a successful
    result — yields a silent false `REPRODUCED`.
  - Comparison is `mtime >= run_start` with **no fudge tolerance** (a tolerance would be a
    hole); the coarse-filesystem-granularity risk is named in Risks rather than papered over.
  - **What it proves, stated honestly:** the guard proves the notebook was *rewritten by
    this run*, not that its numbers were *recomputed*. A `--run` of `cp committed.ipynb
    out.ipynb` (or a `touch`, or restoring a cached artifact) passes it while computing
    nothing. That is out of scope by design: Contig defends against the easy honest mistake
    (binding to the authors' committed notebook), not against a user deceiving themselves.
    This is the same honesty boundary slice 1's "re-runnable" drew (its R3) — stated so M6
    is not read as a stronger guarantee than it is.
  - **Interaction with `--allow-install` (M6a):** run-start is stamped **once, before the
    first run**, and is *not* re-stamped on the retry. So a notebook written by either the
    first or the retried run passes the guard — the intended, more permissive reading (the
    retried run is still "this run"). The record carries one run-start, matching the single
    `created_at`.
- **M7 — Pre-run schema validation in `load_claims`.** The current three-way exclusion
  (`path` xor `column`+`row` xor `pattern`) becomes four-way. Specifically:
  - `cell` **requires** both `from` and `pattern`; either missing → `ClaimsError`.
  - `cell` with `path` or with **any** table field (`column`/`row`/`header`/`delimiter`) →
    `ClaimsError` (rejected, never silently ignored — the slice-4 precedent).
  - `cell` must be a non-negative int (not `bool`), or a **single-key** `{"contains": str}`
    object with a non-empty string value; anything else → `ClaimsError`.
  - `pattern` keeps its shipped rules (non-empty string, **must compile**).
  - A `pattern` + `from` claim **without** `cell` stays a slice-4 `PatternLocator` over that
    file — full back-compat, byte-identical.
- **M8 — Never-raise pure resolver.** The new notebook resolver returns `(value, reason)`
  and never raises on any input — a non-dict document, a missing/non-list `cells`, a
  non-dict cell, a missing `outputs`, a `text` that is neither str nor list, a `data` that
  is not a dict. Mirrors `resolve_pointer`/`resolve_cell`/`resolve_match`.
- **M9 — Containment + size bound + cache.** The `from` flows through the existing CLI
  pre-run refusal and the engine's `relative_to(repo_root)` guard, unchanged. The file size
  is `stat()`ed **before** any read against `_MAX_MATCH_BYTES`, oversize → `UNVERIFIED`
  naming the size (slice-4 precedent). A per-run `_notebook_cache` parses each notebook at
  most once, keyed by resolved absolute path.

### Should-have

- **S1 — CLI docstring documents the notebook locator** alongside the JSON / table /
  pattern forms, with a worked example.

### Nice-to-have (explicitly later)

- A notebook-specific size bound or output-stripping (see Risks R3).
- `metadata.tags` cell addressing; multi-key `contains`; regex cell matching.
- Extending the freshness guard to the JSON/table locators (see Risks R2).
- Paper-parsing, remote `<doi|url>`, dashboard card, C6 eval fold-in — unchanged from the
  standing C8 deferral list. Figures stay hard-blocked (no plot-hash, stdlib-only).

## Data Model / Artifact Contracts

Claims file entry (new form):

```json
{"id": "auc", "value": 0.91, "tolerance": 0.01,
 "from": "out.ipynb", "cell": 7, "pattern": "AUC: ([0-9.]+)"}

{"id": "auc", "value": 0.91,
 "from": "out.ipynb", "cell": {"contains": "print(auc)"}, "pattern": "AUC: ([0-9.]+)"}
```

`NotebookLocator(source: str, cell: int | dict[str, str], pattern: str)`.
`ClaimResult`, `ReproduceRecord`, `ClaimStatus`, the bundle, and the signature are
**unchanged**; `claims_sha256` already covers the new fields.

## Technical Considerations

- **Reuse, don't rebuild.** New pure code is exactly one thing — a notebook → addressed
  cell → output-text extractor. Capture, ambiguity, classification, containment, caching,
  signing, and the exit-code gate are all shipped and reused.
- **Two responsibilities, kept apart.** The extractor (`resolve_cell_output` or similar) is
  where the never-raise surface lives; `resolve_match` is composed on top of it. TDD tests
  them separately.
- **Dispatch.** The `isinstance` chain in `run_reproduction` gains a `NotebookLocator`
  branch. It must be added **before** the final `else` (which assumes `Locator`), for the
  same documented reason slice 4 made the chain explicit: a wrong branch raises
  `AttributeError` at runtime.
- **Signature change (decided, not punted).** `run_reproduction` gains a run-start
  timestamp parameter (M6). The guard is **non-bypassable**: whenever a notebook locator is
  present, it is active. A missing run-start is a **programming error, not a silent
  bypass** — the guard's entire purpose is preventing a false pass, so a `None` default
  meaning "guard off" is explicitly rejected. tech-plan chooses only *how* to make this loud
  (a required keyword; or a defaulted parameter where a notebook locator with no run-start
  raises rather than resolving). Non-notebook locators are unaffected either way, so
  existing callers/tests that pass no notebook claim keep working.
- **Reproducibility/verification impact:** this is the point of the slice. M6 in particular
  strengthens the reproduce guarantee: it is the first locator that verifies the artifact
  was *produced by the run being verified*, not merely present on disk.
- **Determinism/CI:** on-disk fixture `.ipynb` files, mtimes set explicitly with
  `os.utime`, scripted executors, no notebook execution, no network, no pip.

## Risks & Open Questions

- **R1 — Freshness guard vs. filesystem granularity.** On a filesystem with coarse mtime
  resolution (some network/FAT mounts) a genuinely regenerated notebook could report an
  mtime marginally before the recorded run start, yielding a false `UNVERIFIED`. Accepted
  deliberately: a false UNVERIFIED is honest and recoverable; a false REPRODUCED is not.
  No fudge tolerance is added, because a tolerance is exactly the size of the hole it
  opens. Named here so it is not later "fixed" by quietly widening the window.
- **R1a — The guard proves "rewritten," not "recomputed."** A `--run` that copies or
  `touch`es the notebook, or restores a cached artifact, passes M6 while computing nothing.
  Accepted: this slice closes the *dominant, honest* hole (binding to the committed
  notebook), not an adversarial user deceiving themselves. Stated in M6 so the guarantee is
  never read as stronger than it is.
- **R2 — Guard scope is deliberately inconsistent.** Slices 1.5 and 3 have the *same*
  stale-artifact hole (a committed `results.json` or `de.tsv` reproduces just as falsely).
  Widening the guard to them would change shipped behavior and belongs in its own slice.
  This slice states the inconsistency rather than hiding it.
- **R3 — `_MAX_MATCH_BYTES` (8 MiB) may be tight for notebooks.** A notebook with embedded
  base64 figures easily exceeds 8 MiB while its *text* is tiny, so a legitimate claim can
  degrade to UNVERIFIED on size alone. Reusing the shipped constant is the consistent
  choice for this slice; a notebook-specific bound is a named follow-on.
- **R4 — Cell-index brittleness.** An integer `cell` silently re-points if the notebook
  changes upstream. Mitigated but not solved by `pattern`'s 1-match strictness (a re-pointed
  cell usually matches 0 times → UNVERIFIED) and by offering `{"contains": …}`.
- **R5 — Uniform scan over all cells.** `{"contains": …}` scans *all* cells, so a markdown
  cell quoting the same code produces a 2-match ambiguity → UNVERIFIED rather than a silent
  shadow. Honest, but it can surprise; the alternative (code-cells-only) was rejected for
  uniformity with the integer index. Revisit if it proves annoying in practice.
- **R6 — Open:** should a `cell` addressing a markdown cell (no `outputs` key at all) carry
  a distinct message from a code cell with an empty `outputs` list? Cosmetic; settle in
  tech-plan.

## Out of Scope (explicit)

- **Executing notebooks.** Contig never runs Jupyter; the user's `--run` command does. No
  `nbformat`/`nbconvert`/`jupyter` dependency, at runtime or in tests.
- **Reading a notebook's *committed* outputs as evidence.** Explicitly refused by M6.
- **Non-text outputs** — images, HTML, JSON mime bundles, widgets. Figures remain
  hard-blocked (no plot-hash; perceptual hashing would break the stdlib-only contract).
- **Notebook *structure* verification** (did every cell run, are execution counts
  monotonic). A different capability; not a claim locator.
- **Paper-parsing, remote `<doi|url>`, dashboard card, C6 eval fold-in.**
- **Any judgement on the paper's conclusions** — we report whether the *computation*
  regenerates the stated *numbers*.

## Guardrail check (`CLAUDE.md`)

Layer 2 only (verify/reproduce; no NL→workflow authoring, no conclusions verdict) ✅ ·
Moat = verification/reproducibility infra + corpus ✅ · Gets better as base models improve
(a model authoring claims files is a consumer of this surface, not a replacement for it) ✅ ·
Founder's edge, stdlib-only ✅ · No raw-read egress (containment reused) ✅ · Test-first ✅.
