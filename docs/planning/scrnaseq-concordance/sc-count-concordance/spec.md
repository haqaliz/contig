# Aspect spec: sc-count-concordance

Parent PRD: `../prd.md`. The single aspect for this feature — the whole slice fits one
buildable unit.

## Problem slice & user outcome

A user runs `contig verify <id> --concordance-sc-counts <second>` on an `scrnaseq` run and
gets a WARN-capped cross-tool concordance axis (`kind="concordance"`) corroborating the
run's own cell×gene matrix against a second matrix — pseudobulk gene-level Spearman +
fraction-agreeing — with the standing concordance contract (at most WARN, exit code
untouched, UNVERIFIED-never-PASS below the shared-gene floor).

## In scope

- New stdlib `verification/sc_count_concordance.py`: a MatrixMarket `.mtx`(.gz) triplet
  loader that pseudobulk-collapses cells→genes to `{gene_id: float}`; an extension-sniff
  router (`.mtx*` → loader, else the dense `parse_count_matrix`); an
  `evaluate_sc_count_concordance(primary_mtx, second, assay)` entry point that reuses the
  unchanged `count_concordance` core.
- `verify` CLI wiring: `--concordance-sc-counts` flag, mutual-exclusion with the other four
  concordance flags, an `elif` branch, `_resolve_primary_sc_matrix` (locate + sibling-resolve
  + filtered-over-raw preference, assay-gated to `scrnaseq`), `_evaluate_run_sc_counts_concordance`.
- Tests-first: module unit tests + CLI integration tests, synthetic fixtures, no real tool.
- Docs: CHANGELOG `[Unreleased]`, CAPABILITY_ROADMAP C1 single-cell marker.

## Out of scope

`.h5ad`/AnnData parsing; autorun second quantifier; cell-count & cluster-stability
agreement; FAIL severity; verdict-card/dashboard surfacing. (See PRD "Out of Scope".)

## Acceptance criteria (testable)

- AC1 — `load_mtx_pseudobulk(dir)` returns `{gene_id: summed_count}`; correct for both
  gene×cell and cell×gene orientation; gzip-transparent; skips `%%MatrixMarket` banner and
  `%` comments; gene id = `features.tsv` column 1 (multi-col) or sole column.
- AC2 — sniff router sends `*.mtx`/`*.mtx.gz` to the loader and everything else to
  `parse_count_matrix`; both yield `{gene_id: float}`.
- AC3 — a concordant pair → `spearman_concordance` PASS with the value; a divergent pair →
  WARN naming the value, **exit 0**; fewer than 10 shared genes → UNVERIFIED (`value=None`).
- AC4 — `evaluate_sc_count_concordance` gates to `scrnaseq`; a non-scrnaseq assay → `[]`.
- AC5 — CLI: `--concordance-sc-counts` is mutually exclusive with the other four flags
  (exit 1 on two); a non-scrnaseq run prints a skip note and emits no checks;
  `result["concordance"]` appears under `--json`.
- AC6 — honesty branches each have a test: primary `.mtx` found but a sibling
  `features.tsv`/`barcodes.tsv` missing/malformed → one explicit UNVERIFIED (located-but-
  unparseable), **not** a silent `[]`; no `*matrix.mtx*` at all → silent skip note + `[]`;
  orientation genuinely ambiguous → UNVERIFIED.
- AC7 — full suite green; no import of `scipy`/`numpy`/`anndata`/`h5py`.

## Dependencies & sequencing

Phase 1 (module) has no prerequisites. Phase 2 (CLI) depends on Phase 1's entry point.
Phase 3 (docs) last. No new package dependency.

## Open questions / risks

None blocking. Risks (MatrixMarket orientation ambiguity; gene-id-vs-symbol overlap;
adoption before autorun) are carried from the PRD and handled by honest UNVERIFIED/skip +
informational `gene_overlap`.
