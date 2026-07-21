# Card: feat reproduce-notebook-locator (C8 slice 5)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-notebook-locator/aliz`

No GitHub issue — this unit of work came from `/contig-next` (cn), 2026-07-21. The
recommendation below is the source brief.

## Brief

C8 slice 5 for `contig reproduce`: a **notebook (`.ipynb`) claim locator** — the next
unblocked step named in the slice-3 and slice-4 deferral lists in
`docs/technical/CAPABILITY_ROADMAP.md`.

A claim's locator should be able to address a **cell's output** in a Jupyter notebook,
reusing the shipped `resolve_match` regex resolver (slice 4) over the cell's `text/plain`
or stream output. Stdlib `json` only, no new dependency, no `models.py` reshape, and no
change to `classify` / `ClaimResult` / `ReproduceRecord` / signing.

## Why this was picked (from /contig-next)

- The remaining C8 deferrals are: figure/plot & table-image claims (**hard-blocked** — no
  plot-hash, and perceptual hashing would break the stdlib-only dependency contract),
  paper-parsing (own parser/model design), remote `<doi|url>` (needs network), dashboard
  card (surface, thin moat), C6 eval fold-in (**blocked** on a labeling design for
  unlabeled signals). Notebook extraction is the one with no blocker.
- Demand is grounded in the C8 PRD's own evidence base
  (`docs/planning/reproduce-published-work/prd.md:13-14`): 27,271 biomedical-paper
  **notebooks** at ~3.2% reproduction (Samuel & Mietchen, *GigaScience* 2024); Pimentel's
  1.4M-notebook study at ~4%. Notebooks are the medium C8 exists to face, and today every
  claim against one degrades to UNVERIFIED.
- Maximum reuse: a notebook is JSON, so the new surface is a **cell address** plus the
  already-shipped `resolve_match` over the cell's output text.

## The critical caveat — settle it in the dig, not late

A **committed** `.ipynb` already holds the authors' stored outputs. Reading those would
verify what was *committed*, not what *regenerated* — a silent false-`REPRODUCED`, the
exact failure mode the verdict contract exists to prevent. The slice must bind the
**executed** notebook that the `--run` command produces (e.g.
`jupyter nbconvert --execute --output out.ipynb`), and because executed-vs-committed
**cannot be reliably detected** (`execution_count` is a weak heuristic at best), the
honest degradation is **UNVERIFIED**, never a guessed `REPRODUCED`.

## Other caveats to settle in the dig

1. **Cell addressing.** Index, notebook cell `metadata.tags`, or a `source`-substring
   match — pick one and state why. Ambiguity (0 or >1 matching cells) must degrade to
   UNVERIFIED with the **count named**, mirroring the shipped `row`-key and `pattern`
   0-or-many rules.
2. **Which output.** `stream` (stdout/stderr) vs `execute_result`/`display_data`
   `text/plain`; a cell with several outputs needs a stated, non-guessing rule.
3. **Value binding.** Does the claim carry a `pattern` over the cell's text (reuse slice
   4's `resolve_match`), a structured path, or both? Prefer the smallest surface.
4. **Schema exclusivity.** `load_claims` already enforces a **three-way** mutual exclusion
   (`path` xor `column`+`row` xor `pattern`). Adding notebook fields must extend that
   check structurally, pre-run — never silently ignore a contradictory field.
5. **Containment.** The notebook `from` must flow through the existing `.source`
   containment guard unchanged (CLI pre-run refusal + engine defense-in-depth), and
   reuse the per-run parse cache pattern (`_json_cache`/`_table_cache`/`_text_cache`).
6. **Numeric-string rule.** A captured/rendered notebook output is a **string by
   construction** (like a table cell / regex capture) → follow the **slice-3/4** rule
   (strip + `float()`), not the slice-1.5 strict-UNVERIFIED JSON rule.

## Honesty contract (inherited, non-negotiable)

- Every unresolved / ambiguous / non-numeric / non-finite address degrades to
  **UNVERIFIED**, never `DIVERGED`, never a false reproduce.
- An escaping / absolute `from` is refused **pre-run** (exit non-zero, no record).
- `classify` / `ClaimResult` / `ReproduceRecord` / bundle / signing / `--fail-on-diverged`
  are reused as-is.

## Constraints

- Layer-2 only (run/verify/reproduce). Not Layer 1. Research-use, no raw-read egress.
- Stdlib-only runtime dependency contract (`pydantic`/`typer`/`cryptography`) must hold;
  `json` and `re` are stdlib. **No `nbformat`/`jupyter` runtime dependency.**
- Test-first (strict TDD): pure resolver → `load_claims` validation → engine dispatch →
  CLI e2e. Deterministic. **No real repo, notebook execution, network, or pip in CI**
  (on-disk fixture `.ipynb` files).

## Prior art in-repo (starting points for the dig)

- `src/contig/verification/reproduce.py` — `resolve_pointer`/`_parse_path` (slice 1.5),
  `_read_table`/`resolve_cell`/`_resolve_delimiter` (slice 3), `resolve_match`/
  `PatternLocator`/`_MAX_MATCH_BYTES` (slice 4), `detect_missing_module` (slice 2),
  `load_claims`, `classify`, `run_reproduction`, `_observe_located`,
  `_observe_table_located`, `_observe_pattern_located`, `reduce_reproduction`.
- `benchmark._relative_delta` — the reused float-tolerance comparison.
- Slice planning: `docs/planning/reproduce-published-work/` (slice 1),
  `reproduce-output-locator/` (1.5), `reproduce-env-resurrection/` (2),
  `reproduce-tsv-csv-locator/` (3), `reproduce-stdout-log-locator/` (4).
- Roadmap: `docs/technical/CAPABILITY_ROADMAP.md` → C8.

## Shipped state to build on (do not re-derive)

| Slice | Locator | Version |
|---|---|---|
| 1 | flat repo-written `results.json` | v0.40.0 |
| 1.5 | JSON `{from, path}` (`resolve_pointer`) | v0.41.0 |
| 2 | env resurrection (`--allow-install`) | v0.42.0 |
| 3 | TSV/CSV `{from, column, row}` (`resolve_cell`) | v0.43.0 |
| 4 | stdout/log `{pattern, from?}` (`resolve_match`) | v0.44.0 |
