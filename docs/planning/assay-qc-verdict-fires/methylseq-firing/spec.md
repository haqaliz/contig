# Aspect spec — methylseq-firing

Parent PRD: `../prd.md`. This is the **first slice** of `assay-qc-verdict-fires`;
ampliseq and mag are out of scope here (separate fast-follow slices on this seam).

## Problem slice & user outcome

Make the `methylseq` biological QC verdict actually fire by ingesting Bismark's own
on-disk report artifacts, and make any can't-compute outcome an explicit UNVERIFIED
breadcrumb — never a silent no-op. A researcher running nf-core/methylseq gets a
real PASS/WARN/FAIL on mapping efficiency and duplication (and bisulfite conversion
when a control is present), or an honest UNVERIFIED.

## In scope

- New `verification/methylseq_metrics.py` pure parsers → `{canonical_slug: float}`.
- A dedicated `assay == "methylseq"` gate in `runner._discover_qc` mirroring the
  scrnaseq gate, with `_locate_methylseq_qc` + `_sample_from_bismark` helpers.
- M6 single-authoritative-source: remove `methylseq` from `_RULE_PACKS` so the
  generic MultiQC pack path skips it; the gate imports `METHYLSEQ_RULE_PACK`
  directly (as scrnaseq's gate imports `SCRNASEQ_RULE_PACK`).
- A realistic hand-authored Bismark report fixture set; unit + gate tests.
- `[Unreleased]` CHANGELOG entry.

## Out of scope

- ampliseq / mag firing. Band re-calibration / FAIL-severity tuning. MultiQC
  slug-aliasing. Any change to scrnaseq/rnaseq/variant paths. Dashboard changes
  beyond what the existing QC panel already renders.

## Acceptance criteria (testable)

- **A1.** A healthy Bismark alignment+dedup report set → methylseq biological
  `QCResult`s include a non-UNVERIFIED `mapping_efficiency:<sample>` and
  `duplication_rate:<sample>`.
- **A2.** A grossly-failed run (mapping efficiency below `fail_below` 30.0) → a FAIL
  `mapping_efficiency:<sample>`.
- **A3.** A sample whose only located artifact yields **zero** usable metrics → one
  explicit `methylseq_qc:<sample>` UNVERIFIED. No artifact at all → no methylseq
  metric result (silent skip), no crash.
- **A4.** A sample with only the alignment report (no dedup, no conversion control)
  → PASS/WARN on mapping efficiency, and **no** whole-sample UNVERIFIED (R4/M3).
- **A5.** `percent_bs_conversion` is emitted only when a recognizable conversion/
  control line is present; a standard report without one omits it (no result for
  that check), never a guessed value.
- **A6.** The gate is the single source: a methylseq run whose MultiQC happened to
  carry a matching slug does not double-emit any check (M6). `rule_pack_for(
  "methylseq")` no longer returns a pack; any test asserting otherwise is updated.
- **A7.** The methylseq gate is not applied to any other assay (gate-scope test).

## Dependencies & sequencing

Parsers (Phase 1) → gate + M6 wiring (Phase 2) → fixture + integration + docs
(Phase 3). No new runtime dependency; stdlib only; no real nf-core run in CI.

## Open questions / risks (aspect-specific)

- Exact Bismark report filename globs and the precise field labels
  ("Mapping efficiency:", "duplicated alignments removed:") — pin against a realistic
  fixture during Phase 1; the explicit-UNVERIFIED breadcrumb makes a wrong label
  fail loudly, not silently.
- Removing methylseq from `_RULE_PACKS` may touch an existing test — grep and update
  under TDD.
