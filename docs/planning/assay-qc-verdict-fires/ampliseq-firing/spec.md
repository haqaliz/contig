# Aspect spec — ampliseq-firing

Parent PRD: `../prd.md`. Fast-follow #2 of `assay-qc-verdict-fires`, on the seam the
methylseq slice established. Independent of the mag slice.

## Problem slice & user outcome

Make the `ampliseq` (16S/ITS amplicon, DADA2) biological QC verdict fire by
ingesting DADA2's own on-disk stats, with explicit UNVERIFIED when it can't compute
— never a silent no-op. A researcher running nf-core/ampliseq gets a real
PASS/WARN/FAIL on read retention, ASV count, and sample read depth.

## Artifact reality (grounds the parser)

`AMPLISEQ_RULE_PACK` (`rule_pack.py:167-189`) slugs: `percent_retained`,
`asv_count`, `input_reads`.

- **DADA2 `overall_summary.tsv`** — a **multi-sample** TSV (header row + one row per
  sample) with per-step read counts. Key columns: the DADA2 input count and the
  post-chimera-removal (`nonchim`) count. → `input_reads` = input column;
  `percent_retained` = `nonchim / input * 100`.
- **ASV table** (`*ASV_table*` — the structural manifest's required output;
  rows=ASVs, columns=samples, integer counts) — per-sample `asv_count` = number of
  ASV rows with a non-zero count for that sample's column.

**Structural difference from methylseq:** these are **multi-entity files** (one
file → many samples). Parsers therefore return `{sample: {slug: float}}` directly,
and `_locate_ampliseq_qc` merges the summary + ASV-table dicts by sample.

## In scope

- New `verification/ampliseq_metrics.py`: `parse_dada2_overall_summary(path) ->
  {sample: {input_reads, percent_retained}}` and `parse_asv_table(path) ->
  {sample: {asv_count}}`. Floor principle: absent/non-numeric omitted, unrecognized
  file → `{}`.
- A dedicated `assay == "ampliseq"` gate in `runner._discover_qc` mirroring the
  methylseq gate; `_locate_ampliseq_qc` merges by sample.
- M6: add `"ampliseq"` to `_DEDICATED_METRIC_ASSAYS`; keep it registered in
  `_RULE_PACKS` (existing test `test_rule_pack_for_ampliseq_returns_the_ampliseq_pack`
  must stay green).
- Realistic hand-authored DADA2 `overall_summary.tsv` + ASV-table fixtures;
  unit + gate tests; `[Unreleased]` CHANGELOG line.

## Out of scope

mag firing; band re-calibration; MultiQC aliasing; any change to other assays'
paths, slug names, or bands.

## Acceptance criteria (testable)

- **B1.** A healthy `overall_summary.tsv` + ASV table → non-UNVERIFIED
  `dada2_read_retention:<s>`, `asv_count:<s>`, `sample_read_depth:<s>`.
- **B2.** A grossly-failed sample (retention below `fail_below` 20.0, or reads below
  1000) → FAIL on that check.
- **B3.** A sample located but yielding zero usable metrics → one explicit
  `ampliseq_qc:<sample>` UNVERIFIED. No artifact at all → silent skip, no crash.
- **B4.** Partial: only `overall_summary.tsv` present (no ASV table) → retention +
  read-depth evaluate; `asv_count` simply absent; no whole-sample UNVERIFIED.
- **B5.** Multi-sample file → each sample keyed separately; no cross-sample bleed.
- **B6.** No double-emit with a MultiQC carrying a matching slug (gate is sole
  source). `rule_pack_for("ampliseq")` still returns the pack.
- **B7.** Gate not applied to any other assay.

## Dependencies & sequencing

Parsers → gate + M6 → fixture + docs. No new runtime dep; stdlib only; no real
nf-core run in CI. The multi-sample parser shape is the notable difference from
methylseq — get `{sample: {...}}` return signatures right.
