# Understanding — germline-variant-count-plausibility (Phase 2 dig)

## What the work is really asking

Add ONE WARN-capped germline plausibility check: the total variant count from a
`variant_calling` run's primary VCF, in a deliberately wide band, so the verdict catches a
run that completed but produced a near-empty (failed calling) or absurd call set. It is the
last unbuilt item on the C3 germline build list (`CAPABILITY_ROADMAP.md:~421`), symmetric to
the shipped somatic `somatic_variant_count`.

## Verified shipped/absent state (in code)

- **Germline has no count band today.** `VariantMetrics` (`variant_metrics.py:36-48`) carries
  only `ts_tv` and `het_hom`. `variant_count` exists ONLY in `somatic_plausibility.py` and
  `y_variant_count` in `sex_plausibility.py`. Confirmed by grep.
- **No `graphify-out/` graph in this worktree** — dig navigated source directly.

## The seams to reuse (no new machinery)

- **Germline VCF reader:** `concordance.parse_vcf` (`concordance.py:87-110`) — gzip-transparent,
  streamed, returns a dict keyed by `(CHROM,POS,REF,ALT)` → first-sample GT. `variant_metrics()`
  **already calls it once** (`variant_metrics.py:114`). ts_tv/het_hom are derived from that parse.
- **Gate:** `runner._discover_qc`, germline block at `runner.py:287-292`:
  ```python
  if assay == "variant_calling":
      pattern = manifest_for("variant_calling").required[0]  # "*.vcf.gz"
      vcfs = sorted(p for p in run_dir.rglob(pattern) if p.is_file())
      if vcfs:
          results.extend(evaluate_variant_plausibility(vcfs[0]))
          results.extend(evaluate_sex_plausibility(vcfs[0]))
  ```
  A count band added to `evaluate_variant_plausibility`/`VARIANT_RULE_PACK` **rides along with
  no gate edit** (this is the elegant part).
- **Rule-pack mechanics:** rules are `list[dict]` with `warn_below`/`warn_above`/`fail_*`/`message`,
  read via `.get()` in `_status_for` (`rule_pack.py:410-429`); WARN-only = omit `fail_*`.
  Germline's existing WARN-capped rules (`ts_tv_ratio`, `het_hom_ratio`) live in the **registered**
  `VARIANT_RULE_PACK` (`rule_pack.py:49-75`) and are selected by `_rule_by_check`
  (`variant_metrics.py:129-134`) — the germline-native precedent to follow.
- **Provenance:** somatic count is **verdict-only, no RunRecord provenance** (no `SomaticInference`
  exists). Sex-check attaches `SexInference`, but the count band is symmetric to *somatic count*, so
  **verdict-only, no new provenance model.**
- **Tests:** inline VCF strings → `tmp_path`. `tests/verification/test_variant_metrics.py` (helpers
  `_HEADER`/`_vcf_line`/`_write_vcf`, band tests `test_plausibility_in_band_passes` /
  `_out_of_band_warns_never_fails` / `_uncomputable_is_unverified`) is the direct template;
  `test_somatic_plausibility.py` (`test_variant_count_in_band_passes`/`_out_of_band_warns`) shows the
  count-band assertions.

## Recommended design (reuse-first, germline-native) — "Design A"

1. Add `variant_count: int` to `VariantMetrics`, computed as `len(sites)` from the **already-parsed**
   `parse_vcf` result in `variant_metrics()` — **no second parse, no new reader/module/gate**.
2. Add a `variant_count` rule to the registered `VARIANT_RULE_PACK`, **WARN-only**, wide band.
3. Select it in `evaluate_variant_plausibility` via the existing `_rule_by_check` idiom.
4. Tests mirror `test_variant_metrics.py`.

No new `FailureClass`, model, persisted-record, dependency, or exit-code change — additive to the
verdict only. This is the smallest possible C3 slice and mirrors how germline ts_tv/het_hom already work.

**Considered alternative — "Design B" (mechanical somatic mirror):** a new
`variant_count_plausibility.py` + unregistered pack + new evaluator + new gate line. Rejected: more
code, a second VCF parse, and it ignores germline's own established structure.

## The one real semantic choice (flag to PRD)

`len(parse_vcf())` counts **distinct variant sites of the primary sample** — it dedups identical site
keys and treats a multiallelic record as ONE comma-ALT key; it does NOT PASS-filter (matches somatic).
This is **not byte-identical** to somatic's "biallelic streamed record count." For a wide WARN-only
gross-failure band the difference is negligible (a few %), so the recommendation is: **define the
metric honestly as "distinct germline variant sites (primary sample)" via the existing parse** rather
than adding a raw record counter. Decide + document in the PRD.

## Band calibration note (flag to PRD)

Germline counts span orders of magnitude by capture: WGS ~4–5M, WES ~20–50k, targeted panel ~hundreds.
Somatic used `[10, 100000]`; germline needs a **much wider** upper bound (e.g. `warn_above` ~2e7) and a
low `warn_below` (~10) to catch only near-total-failure and absurd counts. Deliberately loose,
uncalibrated, WARN-only; FAIL + real-data calibration deferred (matches every prior C3 slice).

## Zero-count handling (flag to PRD)

`variant_count` is always an int, so it never hits the UNVERIFIED branch; a genuinely-empty/unparseable
VCF → count 0 → **WARN below band** (honest, never a false pass). No VCF at all → the gate never fires
(silent skip; structural QC owns a genuinely-missing output). Symmetric to somatic. Recommend NOT adding
a special UNVERIFIED-on-zero case for slice 1.

## Guardrail check (CLAUDE.md) — clean

Layer-2 verify-only; reads a VCF already on the user's compute (no raw-read egress); research-use sanity
signal, never a clinical judgement; WARN-capped, UNVERIFIED-never-PASS; test-first, synthetic fixtures,
no real nf-core/sarek in CI.
