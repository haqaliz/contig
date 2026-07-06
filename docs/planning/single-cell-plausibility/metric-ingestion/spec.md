# Aspect spec: metric-ingestion

Parent PRD: [`../prd.md`](../prd.md) · Slug: `single-cell-plausibility` · Aspect: `metric-ingestion`

## Problem slice & outcome

The scrnaseq `SCRNASEQ_RULE_PACK` silently no-ops because its metrics never reach the
verdict. This aspect makes them reach it: deterministic parsers for the cell-level QC the
pipeline writes to disk, wired into a dedicated `_discover_qc` scrnaseq gate so the pack
emits real PASS/WARN/FAIL/UNVERIFIED. This is the whole feature — one aspect.

## In scope

- `verification/scrnaseq_metrics.py`: parsers for STARsolo `Summary.csv` (M1),
  Cell Ranger `metrics_summary.csv` (M2), and best-effort simpleaf/alevin-fry (M3, floor
  = degrade to UNVERIFIED). All pure functions returning `{sample: {slug: float}}`.
- A run-dir locator + dedicated scrnaseq gate in `runner._discover_qc` (M4).
- Remove the dead `pct_reads_mito` check from `SCRNASEQ_RULE_PACK` (M5); keep FAIL bands
  on the remaining three (M6).
- Multi-output disambiguation + per-sample keying (should-have).

## Out of scope

- Doublet-rate / mito-fraction checks (need downstream scanpy/scDblFinder).
- Band calibration; any FAIL/WARN threshold change beyond removing `pct_reads_mito`.
- A separate `SCRNASEQ_PLAUSIBILITY_PACK` (redundant once ingestion works).
- HTML scraping for simpleaf; a real nf-core run in CI; Layer-1 anything.

## Acceptance criteria (testable)

1. `parse_starsolo_summary(path)` maps documented STARsolo fields → slugs
   `estimated_cells`, `median_genes_per_cell`, `fraction_reads_in_cells`; unknown rows
   skipped; returns `{sample: {slug: float}}`.
2. `parse_cellranger_metrics(path)` handles `"1,234"`→1234.0 and `"92.3%"`→0.923
   (fraction unit for `fraction_reads_in_cells`), mapping the three slugs.
3. simpleaf parser returns metrics from a structured artifact **if the spike confirms
   one**, else returns `{}` → gate emits UNVERIFIED (never a false pass).
4. `_discover_qc(run_dir, "scrnaseq")` locates the aligner artifact, parses, evaluates
   `SCRNASEQ_RULE_PACK`: healthy fixture → pass; near-empty capture → **fail**; absent
   metric/file → **unverified**. Non-scrnaseq assays unchanged.
5. `pct_reads_mito` no longer in `SCRNASEQ_RULE_PACK`; the other three keep their
   `fail_*` bands.
6. Full suite green (baseline 1157). No real nf-core run. No raw-read egress.

## Dependencies & sequencing

Spike (simpleaf source) → M5 (pack cleanup, isolated) ∥ M1/M2 (parsers) → M3 → M4 (gate,
depends on parsers + pack). See the plan for the ordered phases.

## Aspect-specific risks

- R1 (simpleaf source unconfirmed) — resolved/bounded by the opening spike; floor is
  UNVERIFIED.
- Unit collision (`%` vs fraction) — explicit per-path test.
- `_RULE_PACKS` scrnaseq entry: keep it (harmless — MultiQC carries none of these slugs);
  the dedicated gate is the live path. Removing it is NOT required and is out of scope to
  avoid blast radius.
