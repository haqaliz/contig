# Phase 5 report — docs & changelog sync (C7 M2 + M3)

- **Slug/aspect:** `annotation-plausibility` / `verify`
- **Plan:** `docs/planning/annotation-plausibility/verify/plan_20260710.md` → "Phase 5"
- **Scope:** docs only — `CHANGELOG.md`, `docs/technical/CAPABILITY_ROADMAP.md`. No code touched.

## What was done

1. **`CHANGELOG.md`** — added an `### Added` subheading under `## [Unreleased]` (previously
   empty) with one entry covering both M2 (somatic `default_params` widened to
   `strelka,mutect2,vep`; M1 structural verifier + `AnnotationProvenance` capture gated to
   the new `VARIANT_ASSAYS` constant; provenance capture at `_finalize` now conditional,
   with the never-drop-for-a-real-variant-run fallback) and M3 (new
   `verification/annotation_plausibility.py`, CSQ `Format:`-resolved vs. fixed-ANN index
   parsing, `real_consequence_fraction`/`intergenic_fraction`, the new WARN-capped
   `ANNOTATION_PLAUSIBILITY_PACK` and its two checks, single-VCF-feeds-both-verifiers). Called
   out uncalibrated/loose bands, WARN-cap/no-FAIL, UNVERIFIED-never-false-pass, the carried
   live-cache caveat, no real VEP/SnpEff/sarek in CI, and the M4/M5/FAIL-calibration deferrals.
2. **`docs/technical/CAPABILITY_ROADMAP.md`** — updated the C7 section header (line 577) and
   the sequencing-summary C7 row (line 654) to `M1 + M2 + M3 SHIPPED (Unreleased)`, M4/M5 still
   pending. Added a "Shipped (M2 slice, Unreleased)" and a "Shipped (M3 slice, Unreleased)"
   paragraph mirroring the M1 shipped paragraph's structure/tone, and appended "SHIPPED
   (Unreleased)" to the M2/M3 bullets in the milestone list. No other capability's SHIPPED/
   pending marker was touched.
3. **`FEATURES.md`** — checked (`grep -n -i "C7\|annotation" FEATURES.md`): zero matches. The
   file has no C7-milestone or annotation-row granularity at all, so it was left untouched per
   the task's conditional instruction.
4. **Verification:** `uv run pytest -q` → all tests pass (docs-only change, suite unaffected).
5. Re-read the CHANGELOG entry against the facts supplied in the task brief before committing;
   no discrepancies found (registry default_params, `VARIANT_ASSAYS` constant name/location,
   `_finalize` gating + fallback, `ANNOTATION_PLAUSIBILITY_PACK` non-registration, band
   thresholds 0.10/0.95, and the single-VCF-feeds-both-verifiers wiring were all cross-checked
   directly against `src/contig/registry.py`, `src/contig/runner.py`,
   `src/contig/self_heal.py`, and `src/contig/verification/rule_pack.py`).

## Commit

`docs(verify): changelog + roadmap sync for annotation somatic gate + plausibility [C7 M2 M3]`
