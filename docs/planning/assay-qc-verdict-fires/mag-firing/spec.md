# Aspect spec — mag-firing

Parent PRD: `../prd.md`. Fast-follow #3 of `assay-qc-verdict-fires`, on the seam the
methylseq slice established. Independent of the ampliseq slice.

## Problem slice & user outcome

Make the `mag` (shotgun-metagenomics, nf-core/mag) biological QC verdict fire by
ingesting the per-bin assembly + bin-quality stats, with explicit UNVERIFIED when it
can't compute. A researcher gets a real PASS/WARN/FAIL on assembly N50, bin
completeness, and bin contamination.

## Artifact reality (grounds the parser)

`MAG_RULE_PACK` (`rule_pack.py:204-226`) slugs: `n50`, `completeness`,
`contamination`.

- **Entity key = the BIN.** This matches the pack's own test (`_healthy_mag_sample`,
  `test_rule_pack.py:460` — one key carrying all three metrics) and nf-core/mag's
  per-bin QC. No forced merge across granularities; no user decision needed.
- **QUAST per-bin report** (`transposed_report.tsv` — one row per bin/assembly, an
  `N50` column) → `{bin: {n50}}`.
- **CheckM summary** (a quality TSV with `Bin Id`, `Completeness`, `Contamination`
  columns) → `{bin: {completeness, contamination}}`.
- Merge by bin id (QUAST bin names and CheckM Bin Ids both derive from the bin fasta
  basename).

**Structural difference from methylseq:** multi-entity files (one file → many
bins). Parsers return `{bin: {slug: float}}` directly; `_locate_mag_qc` merges by
bin id.

## In scope

- New `verification/mag_metrics.py`: `parse_quast_report(path) -> {bin: {n50}}` and
  `parse_checkm_summary(path) -> {bin: {completeness, contamination}}`. Floor
  principle: absent/non-numeric omitted, unrecognized file → `{}`. `contamination`
  is an upper-bound check (`warn_above`/`fail_above`), unchanged.
- A dedicated `assay == "mag"` gate in `runner._discover_qc` mirroring the methylseq
  gate; `_locate_mag_qc` merges by bin.
- M6: add `"mag"` to `_DEDICATED_METRIC_ASSAYS`; keep it registered in `_RULE_PACKS`
  (existing test `test_rule_pack_for_mag_returns_the_mag_pack` must stay green).
- Realistic hand-authored QUAST `transposed_report.tsv` + CheckM summary fixtures;
  unit + gate tests; `[Unreleased]` CHANGELOG line.

## Out of scope

ampliseq firing; band re-calibration; BUSCO as an alternate completeness source
(CheckM only this slice); MultiQC aliasing; any change to other assays.

## Acceptance criteria (testable)

- **C1.** Healthy QUAST + CheckM → non-UNVERIFIED `assembly_n50:<bin>`,
  `bin_completeness:<bin>`, `bin_contamination:<bin>`.
- **C2.** A grossly-failed bin (N50 below 1000, completeness below 50, or
  contamination above 10) → FAIL on that check.
- **C3.** A bin located but yielding zero usable metrics → one explicit
  `mag_qc:<bin>` UNVERIFIED. No artifact at all → silent skip, no crash.
- **C4.** Partial: only QUAST present (no CheckM) → `assembly_n50` evaluates;
  completeness/contamination absent; no whole-bin UNVERIFIED.
- **C5.** Multi-bin files → each bin keyed separately; no cross-bin bleed.
- **C6.** No double-emit with a MultiQC carrying a matching slug. `rule_pack_for(
  "mag")` still returns the pack.
- **C7.** Gate not applied to any other assay.

## Dependencies & sequencing

Parsers → gate + M6 → fixture + docs. No new runtime dep; stdlib only; no real
nf-core run in CI. Watch the per-bin id alignment between QUAST and CheckM (merge
key); a bin present in only one file keeps whatever parsed (C4).

## Aspect-specific risk

Real QUAST/CheckM column labels (`N50`, `Completeness`, `Contamination`) and file
names pinned from realistic fixtures; the floor + explicit-UNVERIFIED net makes a
wrong label fail loudly, never silently — same caveat as methylseq's conversion
rate.
