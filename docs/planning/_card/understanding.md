# Understanding: single-cell-plausibility (Phase 2 deep dig)

## What the work was assumed to be

The `contig-next` pick assumed scrnaseq is a shipped assay with **no biological
verdict**, and the task was to add a `SCRNASEQ_PLAUSIBILITY_PACK` + evaluator +
`_discover_qc` gate, mirroring the RNA-seq plausibility slice.

## What the code + research actually show (the contradiction)

**1. A scrnaseq biological pack already exists.** `rule_pack.py:87–116`
`SCRNASEQ_RULE_PACK` already scores the exact metrics C3 names for single cell —
`estimated_cells`, `median_genes_per_cell`, `fraction_reads_in_cells`,
`pct_reads_mito` — and it is **registered** in `_RULE_PACKS` (rule_pack.py:281–288),
so it runs today via `rule_pack_for("scrnaseq")` → `evaluate_run_qc`. It even carries
**FAIL bands** (e.g. `estimated_cells` fail_below 100, `pct_reads_mito` fail_above 50).
So the premise "no biological verdict" is wrong: the checks are wired.

**2. But they almost never fire — the metrics aren't ingested on the default path.**
The pinned `nf-core/scrnaseq@4.1.0` default aligner is **`simpleaf` (alevin-fry)**,
not STARsolo/Cell Ranger. On that default path the cell-level QC lives in
**AlevinQC/QCatch standalone HTML**, not MultiQC `general_stats`. The stock MultiQC
**STAR module does not parse STARsolo `Summary.csv`**; only the **Cell Ranger** module
surfaces `estimated cells / genes-per-cell / fraction-in-cells` into general stats.
Since `evaluate()` (rule_pack.py:332–351) **silently skips any absent metric**, the
existing scrnaseq pack **degrades to UNVERIFIED on an out-of-the-box run** — it reads
as "wired" but produces no verdict.

**3. Two of the C3 single-cell checks can't fire at all on the base pipeline:**
- `pct_reads_mito` needs downstream **scanpy** (`pct_counts_mt`); the base 4.1.0
  pipeline does not run scanpy QC → this check is silently dead on every real run.
- **doublet rate** needs scDblFinder/scrublet, which the base pipeline does not run at
  all → cannot be added meaningfully.

**4. The existing FAIL bands are uncalibrated** (rule_pack.py:85 "illustrative,
tunable engineering defaults"), which sits uneasily with the standing C3 posture
"WARN-capped, no FAIL until calibrated on real data" that every plausibility slice has
honored.

## So the real gap is NOT "add a pack" — it is "make the pack fire"

The genuine Layer-2 hole the dig uncovered: **single-cell cell-level QC metrics never
reach the verdict on a default run.** The metrics the pipeline *does* write to disk
(STARsolo `Summary.csv`, Cell Ranger `metrics_summary.csv`) are not parsed into the
`{sample: {slug: value}}` dict that the checks consume. Fixing that is what turns a
dormant single-cell verdict into a live one.

## Affected code (file:line anchors from the dig)

- `verification/rule_pack.py` — `SCRNASEQ_RULE_PACK` (87–116); `evaluate()` skips absent
  metric (338–339); `_status_for` WARN-cap (299–318); `_RULE_PACKS` (281–288).
- `verification/rnaseq_plausibility.py` — the evaluator+unverified template (whole file).
- `verification/qc_ingest.py` — `parse_multiqc_general_stats_file` → `{sample:{slug:val}}`
  (the only current metric source; 5–30).
- `runner.py:_discover_qc` (40–121) — assay-gated plausibility; rnaseq gate at 118–120.
- `registry.py:42–48` — scrnaseq entry, pinned `4.1.0`; default aligner is simpleaf.
- `verification/structural.py:262–264` — scrnaseq manifest (`*.h5ad`, `*matrix.mtx*`).
- Tests to mirror: `tests/verification/test_rule_pack.py` (203–278 scrnaseq pack;
  487–561 rnaseq-plausibility pack), `tests/verification/test_rnaseq_plausibility.py`,
  `tests/verification/test_run_qc.py:119–142` (runner-gate integration).
- Precedent planning docs: `docs/planning/rnaseq-plausibility/` (prd + spec + plan).

## Guardrails check

Layer-2 (verify) ✓. No raw-read egress — a Summary.csv/metrics_summary.csv parser reads
small text QC files on the user's compute ✓. No over-claiming — keep WARN-capped,
UNVERIFIED-when-absent ✓. No Layer-1 ✓. Research-use only ✓. Test-first with synthetic
fixtures, no real nf-core run in CI ✓.

## Open decision for the review (before the PRD)

The finding forks the scope; see the three options presented to the user. The
recommended direction is the metric-ingestion slice (make the checks fire), not the
thin duplicate-pack slice the brief literally described.
