# Aspect spec: verify-autorun

Parent PRD: `docs/planning/sc-concordance-autorun/prd.md`. This is the sole aspect of the
slice (the feature is one cohesive vertical: a quantifier seam + one CLI verb branch).

## Problem slice & user outcome

A `scrnaseq` user runs `contig verify --concordance-sc-counts-auto --reads <sheet> --index
<STAR genome dir> --whitelist <path> [--chemistry 10xv3]` and gets a cross-tool corroboration
line for their single-cell count matrix — Contig runs STARsolo itself as the independent
second quantifier, with no user-produced second matrix.

## In scope

1. `src/contig/verification/sc_count_quantifier.py` — an injectable STARsolo seam mirroring
   `count_quantifier.py`: `ScCountQuantifier` type, `SecondScQuantifierError`, a chemistry
   preset table, a pure `starsolo_command(...)` argv builder, a pure CB/cDNA read-order
   derivation from the sample sheet, and `run_starsolo_quantifier(...)` (validate-before-spawn;
   never run in CI).
2. `src/contig/cli.py` `verify` — `--concordance-sc-counts-auto` (+ `--whitelist`,
   `--chemistry`; reuse `--reads`/`--index`); dispatch `_evaluate_run_sc_counts_concordance_auto`
   (resolve primary → validate inputs → inject-or-run STARsolo → `evaluate_sc_count_concordance`);
   extend mutual-exclusion 5→6; `--index` help disambiguation.

## Out of scope

Everything in the PRD "Out of Scope": auto-deriving inputs from the run record, cluster/cell-count
agreement, FAIL/calibration, dashboard surface, `.h5ad`, an in-output divergence note.

## Acceptance criteria (testable)

- **AC1** argv builder: `starsolo_command` pins `--readFilesIn <cDNA> <CB>` order and 10x-v3
  CB/UMI geometry; asserted **without executing** STAR.
- **AC2** read-order derivation: a pure function maps a sample sheet's `fastq_1`(CB/R1),
  `fastq_2`(cDNA/R2) → `(cDNA, CB)` = `(fastq_2, fastq_1)`; unit-tested.
- **AC3** chemistry presets: `10xv3` → CBstart1/CBlen16/UMIstart17/UMIlen12; unknown chemistry →
  `SecondScQuantifierError` (never a guessed geometry).
- **AC4** runner error paths (no real STAR): missing binary / missing reads / missing index /
  missing whitelist / nonzero exit / missing Solo `matrix.mtx` → `SecondScQuantifierError`.
- **AC5** CLI concordant pair (fake quantifier writes a synthetic triplet) → PASS checks;
  divergent → WARN; both name the two tools.
- **AC6** exit code untouched on WARN (exit 0); too-few-shared-genes → one UNVERIFIED.
- **AC7** skip paths emit **zero** checks and never spawn the tool: non-`scrnaseq` run, primary
  matrix absent, missing `--reads`/`--index`/`--whitelist` (assert a "boom" quantifier is never
  called), `SecondScQuantifierError`.
- **AC8** 6-flag mutual-exclusion: any two concordance flags → exit 1 with the listing message.
- **AC9** full suite green; no new dependency.

## Dependencies & sequencing

Phase 1 (seam) → Phase 2 (CLI) — Phase 2's dispatch imports Phase 1's runner + error. Reuses
unchanged: `evaluate_sc_count_concordance`, `load_sc_matrix` (`sc_count_concordance.py`),
`_resolve_primary_sc_matrix`, `_echo_concordance` (`cli.py`), `fastq_paths`
(`samplesheet.py`).

## Open questions / risks (aspect-specific)

- Read-order footgun (AC2) is the highest-risk detail — STARsolo's `cDNA,CB` order is the
  reverse of sample-sheet `fastq_1,fastq_2`. Covered by an explicit unit test.
- WARN-only semantics + unproven washout carried from the PRD (R-risk-1/4); no code impact.
