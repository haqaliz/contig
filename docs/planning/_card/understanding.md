# Understanding — feat / scrnaseq-concordance (Phase 2 deep dig)

Grounded in a full code map of the worktree (path:line cited). Read with `_card/issue.md`.

## What the work is really asking

Extend the shipped cross-tool concordance primitive (capability C1) to the `scrnaseq`
assay — the last assay without it. A user supplies a **second** single-cell count matrix
(from a different quantifier); Contig corroborates the run's own matrix against it and
adds a WARN-capped `kind="concordance"` axis to the verdict. Same honest contract as the
four shipped concordance slices: **at most WARN, never changes the `verify` exit code,
`unverified` (never a false pass) below a shared-gene floor.**

## The central technical finding (drives the whole design)

The concordance **core is reusable**; the **parser is not**.

- **Reusable unchanged** (`verification/count_concordance.py:192-306`): `count_concordance()`
  → `CountConcordanceStats(shared, rho, fraction_agreeing, overlap)`, the hand-rolled
  stdlib `_spearman`/`_rank`/`_pearson` (148-162), `_agrees` 10% tolerance (165-171), the
  shared-gene floor `_MIN_SHARED_GENES=10` (43), and `concordance_results()` which emits the
  three QCResults — `spearman_concordance` (WARN < 0.90), `fraction_agreeing` (WARN < 0.90),
  `gene_overlap` (informational, always PASS). All `kind="concordance"`, all WARN-capped.
  It operates on any `dict[str, float]` = `{gene_id: total}`.
- **NOT reusable** (`count_concordance.py:80-112`): `parse_count_matrix` assumes a **dense
  gene×sample TSV** (first col = gene id, sums remaining numeric columns). Single-cell
  matrices are **sparse MatrixMarket `.mtx`(.gz)** with sibling `features.tsv`/`barcodes.tsv`,
  and/or **AnnData `.h5ad`**. Feeding an `.mtx` to `parse_count_matrix` yields garbage.
- **No single-cell matrix parser exists anywhere in the repo** (confirmed: no `read_mtx`,
  `scipy`, `h5py`, `anndata`). The scrnaseq matrix is referenced only *structurally* —
  `structural.py:262-264` requires `*.h5ad` + `*matrix.mtx*` for presence, never parsed.
- **Dependency constraint:** the module is pure-stdlib by contract ("No scipy/numpy",
  `count_concordance.py:152`). A `.mtx` triplet reader **can stay stdlib-only**; `.h5ad`
  parsing would pull in `anndata`/`h5py` — a new dependency the repo avoids.

**Conclusion:** the slice = a new stdlib **`.mtx`-triplet loader** that sums counts across
cells to a per-gene pseudobulk `{gene_id: float}` (mapping matrix rows→gene ids via
`features.tsv`), then feeds the *unchanged* concordance core. `.h5ad`-only inputs degrade to
an honest skip/UNVERIFIED (deferred until a stdlib-safe reader or an accepted dep exists).

## Affected code (confirmed by the map)

- **CLI `verify`** (`cli.py:746-791` flags, `820-832` mutual-exclusion sum, `842-855` branch
  dispatch, `857-904` result injection + exit code). Exit is driven ONLY by output drift
  (`result["ok"]`) and `sig_bad`; concordance is surfaced (`result["concordance"]`,
  `_echo_concordance` 1080-1087) but **never feeds the exit code** — asserted in
  `tests/test_cli.py:1541`. To mirror: add a flag near cli.py:780, add to the exclusion tuple
  at 823, add an `elif` at ~853, write `_evaluate_run_sc_counts_concordance` +
  `_resolve_primary_sc_matrix` modeled on `cli.py:993-1036`.
- **Primary-matrix locator:** new helper mirroring `_resolve_primary_counts` (`cli.py:993-1020`)
  — assay-gate to `scrnaseq` via `assay_for_pipeline(record.pipeline)` (`registry.py:62-63`),
  `results_dir.rglob("*matrix.mtx*")`, resolve sibling `features.tsv`/`barcodes.tsv`, else skip
  note → `None`.
- **Concordance module:** either add `"scrnaseq"` to `_COUNT_CONCORDANCE_ASSAYS`
  (`count_concordance.py:47`) OR a parallel `evaluate_sc_count_concordance` entry point — the
  latter is cleaner because `evaluate_count_concordance` hardwires the dense `parse_count_matrix`.
  New parser likely lives in a new `verification/sc_count_concordance.py` (or added to
  `count_concordance.py`) reusing the core.
- **QCResult / QCStatus / QCKind** (`models.py:55/64/67-75`): `kind="concordance"` already
  exists; `overall_verdict` (78-96) is not called by verify on concordance — reuse as-is.

## Test approach (mirror exactly)

- Module tests `tests/verification/test_count_concordance.py` — real `tmp_path` files, no
  mocks/network. New: `tests/verification/test_sc_count_concordance.py` with synthetic
  MatrixMarket fixtures (tiny `matrix.mtx` + `features.tsv` + `barcodes.tsv` written as text).
- CLI tests `tests/test_cli.py:1477-1624` — `_write_*_run_with_*` + `_write_second_*` +
  `runner.invoke(app, ["verify", ...])`. New: write a scrnaseq `RunRecord`
  (`pipeline="nf-core/scrnaseq"`) with a `results/…/matrix.mtx` triplet, a second triplet, and
  assert emits/at-most-warn-exit/json/non-scrnaseq-skip/mutual-exclusion.
- **No real nf-core/scrnaseq run in CI** — hard rule.

## Open questions for the interview (product decisions the code can't resolve)

1. **Second-matrix input shape.** A single-cell matrix is a 3-file triplet, awkward as one CLI
   arg. Options: (a) a **directory** holding `matrix.mtx`+`features.tsv`+`barcodes.tsv`;
   (b) the `matrix.mtx` path with siblings auto-resolved; (c) also accept a pre-collapsed
   **dense pseudobulk gene TSV** (reuses `parse_count_matrix`). Recommendation: accept a
   `.mtx` path (siblings auto-resolved) **and** a dense `.tsv` (sniff by extension) — max reuse,
   least user burden.
2. **`.h5ad` handling.** Defer (skip/UNVERIFIED with an honest note) to keep stdlib-only, no
   `anndata`/`h5py` dep? Recommendation: yes, defer — `.mtx` first slice.
3. **Metric = pseudobulk gene-level Spearman + fraction-agreeing** (reuse core), deferring
   cell-count and cluster-stability agreement (need cell-calling/clustering Contig doesn't run).
   Confirm this is the accepted first-slice metric.
4. **Flag name:** `--concordance-counts-sc` (brief) vs `--concordance-sc-counts` (reads better
   next to `--concordance-counts`). Cosmetic.

## Guardrail check (CLAUDE.md)

On-thesis Layer-2 verification depth. No Layer-1 drift. No raw-read egress (compares gene
totals on the user's compute). No over-claiming (WARN-capped, UNVERIFIED-never-PASS). Test-first.
No new dependency in the first slice (stdlib `.mtx` reader).
