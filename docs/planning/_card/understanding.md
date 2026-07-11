# Understanding — germline-sex-check-plausibility (Phase 2 dig)

## What the work is really asking

Add a **germline biological-plausibility check** that infers karyotypic sex from
the run's own VCF and flags when the signal is internally inconsistent. It is a
pure C3 slice on the CI-exercised `variant_calling` assay, WARN-capped, that
degrades to UNVERIFIED (never a false pass) when sex can't be inferred. It reuses
the shipped VCF-reading path — **no new compute path, no new tool, no live-run
dependency.**

## Affected areas (confirmed by code dig)

- **New module:** `src/contig/verification/sex_plausibility.py` — mirror the shape of
  `verification/variant_metrics.py` (germline, VCF-derived, reuses `parse_vcf`):
  a pure compute fn → an `evaluate_sex_plausibility(vcf_path, sample=...)` wrapper →
  explicit `status="unverified"` QCResult when uncomputable. Name matches
  `somatic_plausibility.py` (it IS a plausibility evaluator with its own pack) and
  the branch slug.
- **New test:** `tests/verification/test_sex_plausibility.py` — `tmp_path` real VCFs
  via inline `_HEADER` + `_vcf_line` + `_write_vcf` helpers; assert pass / warn (and
  `!= "fail"`) / unverified / gzip round-trip. No mocks, no network.
- **New pack:** `SEX_PLAUSIBILITY_PACK` (or module-level threshold constants
  single-sourced) in `src/contig/verification/rule_pack.py`. **Not** registered in
  `_RULE_PACKS` (like `SOMATIC_PLAUSIBILITY_PACK` / `RNASEQ_PLAUSIBILITY_PACK` /
  `ANNOTATION_PLAUSIBILITY_PACK`) — imported directly by the new evaluator. A WARN
  cap = omit `fail_below`/`fail_above` entirely (`rule_pack.py:50-59`,`285-303`).
- **Wiring:** `src/contig/runner.py` `_discover_qc`, the existing germline block at
  **runner.py:254-264** (`if assay == "variant_calling"`), which already locates the
  VCF via `manifest_for("variant_calling").required[0]` rglob'd under the run dir and
  extends `evaluate_variant_plausibility(vcfs[0])`. Add
  `results.extend(evaluate_sex_plausibility(vcfs[0]))` beside it, plus the import
  beside runner.py:60. **Reuse the same `vcfs[0]`** — no second discovery.

## The load-bearing input (confirmed)

`concordance.parse_vcf(vcf_path)` → `dict[(CHROM,POS,REF,ALT), normalized_gt]`
(`concordance.py:87-110`):
- **CHROM is kept verbatim** — no `chr` stripping. So X/Y strings are whatever the
  VCF uses; we must match `chrX`/`X` and `chrY`/`Y` ourselves (case-insensitive).
- GT normalized to sorted `/`-joined tokens (`"0/1"`); **phased `0|1` handled**;
  missing (`.`, `./.`) → `None`; **first sample column only**.
- This gives us both signals we need: per-site GT (for X-het) and CHROM (for
  X-site selection and Y presence). Reuse it exactly as `variant_metrics.py` does.

## The verdict / exit-code contract (confirmed — cannot regress)

- `overall_verdict` (`models.py:78-96`): precedence `fail > warn > pass > unverified`.
  A WARN-capped check tops out at `warn`; `unverified` carries no severity and can
  only be the verdict when nothing else is present.
- `contig run` process exit is decided **only** by pipeline success
  (`cli.py:610-612`), never by the QC verdict. So a WARN/UNVERIFIED
  `sex_plausibility` result changes the printed verdict at most to `warn` and
  **never** changes the exit code.
- The check flows into the verdict through the **`run`** path
  (`_discover_qc` → `RunRecord.qc_results`), not `contig verify` (which only
  re-hashes outputs / runs concordance and does not re-run the QC packs).

## The science + the honest imperfection (the design core)

Two independent signals from one VCF:
- **X-heterozygosity ratio** = het fraction over biallelic X-chromosome genotypes.
  Bimodal: XY (male) → near 0 (hemizygous); XX (female) → substantial (~autosomal).
- **Y-variant presence** = count/fraction of called variants on the Y contig.

Key asymmetry to encode honestly: **Y-presence is informative, Y-absence is not.**
A female sample against a Y-containing reference AND a sample against a Y-less
reference both yield ~0 Y calls — indistinguishable from the VCF alone. So:
- Primary call comes from **X-het** (reliable when enough X sites exist).
- **Y-presence** is used only as **corroboration when present** (X says female but
  Y variants present → discordant → WARN: possible aneuploidy / contamination /
  sample swap). Y-absence never penalizes.
- Too few X biallelic sites, or no X contig, → **UNVERIFIED** (indeterminate).

This bimodality means a single `warn_below/warn_above` band does NOT fit
`evaluate()` (it can't say "0 fine, 0.5 fine, 0.25 suspicious"). So the derived
single `sex_plausibility` PASS/WARN/UNVERIFIED result is **hand-built in the
wrapper** (like `variant_metrics.py`'s unverified branch), with the raw
`x_het_ratio` optionally surfaced as an informational metric.

## Ambiguities / open questions for the PRD interview

1. **Check shape:** one derived `sex_plausibility` (PASS/WARN/UNVERIFIED) built in
   the wrapper, X-het primary + Y-presence corroboration — vs plain numeric band
   checks. (Recommend the derived single check; bands don't fit a bimodal signal.)
2. **PAR masking:** pseudoautosomal regions are diploid in males and inflate male
   X-het; masking them needs build-specific (GRCh37≠GRCh38) coordinates. Recommend
   **out of scope** for this slice (loose WARN-capped thresholds + the no-Y-penalty
   absorb it); note as a known imperfection.
3. **Thresholds:** uncalibrated engineering defaults, WARN-capped, no FAIL (as every
   other C3 slice). Need: min-X-sites floor, X-het low/high cutoffs, Y-present floor.
4. **Multi-sample VCFs:** `parse_vcf` reads first sample only → inherit the existing
   `variant_metrics.py` first-sample limitation; per-sample sex is a deferred
   follow-on. Confirm consistency.
5. **reported-vs-inferred concordance:** explicitly **out of scope** (no sample-sheet
   sex field today) — a named follow-on, per the brief. Do not add the field here.

## Moat / guardrail check (passes)

Layer-2 verification only; deepens "make every verdict harder to fool"; runs on the
VCF already on the user's compute (no raw-read egress); research-use sanity signal,
**never** a clinical sex/karyotype determination; WARN-capped honors "no correctness
over-claiming"; test-first with synthetic fixtures, no real nf-core run in CI. No
drift toward Layer 1.
