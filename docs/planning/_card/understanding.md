# Understanding — feat somatic-swapped-pair (C4 tumor/normal swap smell test)

Phase-2 deep-dig note. Grounded in a full code map (path:line cited inline), verified by
reading `src/contig/verification/somatic_plausibility.py`, `strelka_vaf.py`,
`somatic_concordance.py`, `rule_pack.py`, `runner.py`, and the somatic test fixtures.

## What the work is really asking

Today the somatic verdict's biological axis reads VAF **only from the tumor column** of the
Mutect2 VCF. A tumor/normal **sample swap** (or a mislabeled pair, or heavy tumor-in-normal
contamination) completes, passes structural + tumor-VAF QC, and returns a biologically
inverted result — the researcher reports the normal's germline as the tumor's somatic
mutations. This slice adds one WARN-capped plausibility metric that reads the **normal
column** and fires when it carries a signal it shouldn't, catching the swap before the
result is trusted.

## The central design fork (resolve in the PRD interview)

The map shows the tumor half is a clean template, but the *shape of the smell metric* is a
real decision:

- **(A — recommended) `normal_median_vaf` with a `warn_above` band only.** Median VAF over
  the **normal** column at the same biallelic Mutect2 records the tumor metric already
  scans. In a correct pair the normal VAF at somatic sites is ~0; an implausibly high normal
  VAF is exactly the swap / mislabel / contamination smell. **Why this shape:** it mirrors
  the shipped `median_vaf` machinery verbatim (reuse `_vaf_from_sample` on the normal index),
  needs **no lower bound** (a low normal VAF is the healthy expected case — no warn_below),
  degrades to UNVERIFIED cleanly when the normal column can't be resolved, and avoids the
  division-by-~0 edge a ratio has (the *healthy* case has normal median ≈ 0, so a
  tumor/normal ratio blows up precisely when everything is fine). One metric, uncalibrated
  `warn_above`, honest.
- **(B) A directional `tumor_vs_normal` delta/ratio.** WARN when normal median VAF ≥ tumor
  median VAF (inverted). More explicitly "a swap," but the ratio/delta is calibration-
  sensitive and has the div-by-0 edge above; the inversion it catches is a strict subset of
  what (A)'s warn_above catches. Higher complexity, not obviously more catch.

Recommendation to carry into the interview: **(A)**. It's the minimal, honest, WARN-capped
signal that reuses the shipped pattern and needs the least calibration.

The brief also mentions "a tumor column that looks germline-clonal at ~0.5/1.0." Note the
shipped `median_vaf` rule already has `warn_above: 0.95` (`rule_pack.py:300-305`), so a
tumor VAF near 1.0 is *already* flagged; a ~0.5 clonal tumor is legitimately common and not
a reliable swap signal. So the net-new, defensible signal is the **normal-column VAF**, not
a new tumor-side rule.

## Affected code (confirmed by the map)

- **New parser needed — `##normal_sample=` resolver.** No `src/` code parses
  `##normal_sample=` today (grep: every somatic hit reads only `##tumor_sample=` /
  literal `TUMOR`). Must add a `_normal_column_index()` mirroring
  `somatic_plausibility.py:_tumor_column_index` (`:59-78`) and `_tumor_sample_name`
  (`:191-196`), with the **same never-guess→UNVERIFIED discipline**: no `##normal_sample=`
  header or no matching `#CHROM` column → `None` → one honest `unverified` QCResult, never a
  positional guess.
- **VAF derivation reused as-is.** `_vaf_from_sample()` (`somatic_plausibility.py:86-119`,
  FORMAT `AF` else `AD_alt/DP`) and `_biallelic()` (`:81-83`) apply unchanged to the normal
  column — only the column index differs. `_read_somatic` (`:122-163`) can be generalized or
  a sibling reader added for the normal index.
- **New rule on the existing pack.** Add `normal_median_vaf` to `SOMATIC_PLAUSIBILITY_PACK`
  (`rule_pack.py:296-328`), `warn_above` only (uncalibrated default, e.g. 0.30 — flag as
  uncalibrated), **no `fail_*`**, no `warn_below`. Pack stays unregistered in `_RULE_PACKS`.
- **Emit via the `by_metric` trick (v0.34.0 Strelka precedent).** New evaluator
  `evaluate_swap_plausibility(vcf, sample=None)` builds `by_metric = {"normal_median_vaf":
  value}` and calls shared `evaluate(...)` so ONLY that rule fires — the existing
  `median_vaf`/`somatic_variant_count`/`strelka_median_vaf` rules are never re-emitted
  (`evaluate()` skips absent metric keys, `rule_pack.py:474-475`; pattern:
  `strelka_vaf.py:244-252`). Emits `normal_median_vaf:<NORMAL>`.
- **Runner wiring.** Slot the new evaluator into the existing
  `if assay == "somatic_variant_calling":` block (`runner.py:337-407`), after the Mutect2
  plausibility call (`:354`), on the **already-globbed** `mutect2` VCF. Reuse
  `select_caller_vcfs(run_dir, vcfs)` (`somatic_concordance.py:164-211`, already called at
  `runner.py:387`) — do not re-glob.
- **UNVERIFIED-vs-skip.** "Cannot compute" (no normal column, no derivable normal VAF) →
  `QCResult(status="unverified", value=None, kind="metric")` (never a skip that reads as
  pass, `somatic_plausibility.py:264-276`). No Mutect2 VCF at all → silent skip (structural
  QC owns a missing output; matches the `if vcfs:` gate at `runner.py:340`).

## The one real risk to pin FIRST (the caveat)

**`##normal_sample=` is unverified in this codebase.** Real GATK Mutect2 emits it symmetric
to `##tumor_sample=`, but no code and no fixture here confirms the exact spelling. First dig
task: confirm the header spelling against a real sarek 3.5.1 Mutect2 header (or the
`##normal_sample=` GATK doc). The honest fallback (UNVERIFIED when the header/column is
absent or unparseable) absorbs a wrong guess — a stripped/re-headed VCF simply degrades,
never false-passes. `_pon_status` (`:199-221`) already models this degradation posture.

## Test approach (fixtures already model NORMAL)

`tests/verification/test_somatic_plausibility.py` helpers already write a NORMAL-then-TUMOR
`#CHROM` column with a fully-populated normal FORMAT (`_header`/`_rec`/`_write`, `:21-41`;
`_rec` default `normal_fmt="0/0:0.0:10,0:10"`). The only gap: `_header` writes
`##tumor_sample=` but not `##normal_sample=` — extend it (or use the existing `extra=()`
hook) to inject the normal header. Inline-VCF-to-`tmp_path` pattern, `.gz` supported
(`test_gzip_supported`, `:166-173`). No mocks, no tool exec, no real sarek run in CI.

## Guardrail check (CLAUDE.md)

Squarely Layer 2 (verify) — "make every verdict harder to fool." Reads a small VCF already
on the user's compute (no raw-read egress). WARN-capped, research-use corroboration, never a
clinical/cancer verdict. No new dependency, `FailureClass`, model, or reproduce-contract
change. Gets better as models adjudicate ambiguous swap cases. No Layer-1 drift.

## Open questions for the interview

1. Metric shape: confirm **(A) `normal_median_vaf` warn_above-only** vs (B) a directional
   ratio. (Recommend A.)
2. The uncalibrated `warn_above` default value (0.30? — flag as an engineering default, not
   validated).
3. Metric/label naming: `normal_median_vaf:<NORMAL>` — confirm.
4. Reader: generalize `_read_somatic` to take a column index, or add a sibling normal reader?
   (Implementation detail — likely generalize.)
