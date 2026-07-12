# Aspect spec: variant-count-band

Parent PRD: [`../prd.md`](../prd.md). Single aspect (the whole feature).

## Problem slice & user outcome

A completed germline (`variant_calling`) run whose primary VCF has a grossly-off variant
count (near-zero from failed/truncated calling, or an absurd count) currently passes the
verdict silently. Outcome: the germline verdict gains a WARN-capped count-band axis so the
gross-failure surfaces to persona A/C without ever blocking a legitimate run.

## In-scope requirements

- Add `variant_count: int` to `VariantMetrics`, computed as `len(sites)` from the
  `parse_vcf` result `variant_metrics()` already produces (distinct primary-sample
  `(CHROM,POS,REF,ALT)` sites; multiallelic once; not PASS-filtered).
- Add one `variant_count` rule to the registered `VARIANT_RULE_PACK`: `warn_below: 10`,
  `warn_above: 20_000_000`, no `fail_*`; `warn_above` commented as a soft uncalibrated
  tripwire.
- Select the rule in `evaluate_variant_plausibility` by adding `"variant_count"` to
  `_PLAUSIBILITY_CHECKS` and `metrics.variant_count` to `by_metric`. Because the value is
  always an int, it flows through the shared `evaluate()` (never the unverified branch).
- No `runner._discover_qc` edit — the check rides the existing
  `evaluate_variant_plausibility(vcfs[0])` call at `runner.py:291`.

## Out-of-scope boundaries

FAIL severity; band calibration; capture-aware bands; per-sample multi-sample counts; any
new module, provenance record, `FailureClass`, persisted-record, or dashboard card; somatic
changes; real nf-core/sarek in CI.

## Acceptance criteria (testable)

1. In-band count → one `variant_count:<sample>` result, status `pass`.
2. Out-of-band-low count (e.g. 2) → status `warn`, never `fail`.
3. Count 0 (header-only VCF) → status `warn` (below band), **not `unverified`**.
4. Out-of-band-high count (> `warn_above`) → status `warn` (tripwire fires).
5. `check` key equals `variant_count:<sample>` and carries `expected_range` `[10, 20000000]`,
   grouped with the other germline plausibility rows.
6. Gzipped VCF parses; multi-sample VCF counts the primary sample's distinct sites.
7. `VariantMetrics.variant_count` holds the expected int.
8. Existing germline plausibility tests unchanged & green; full suite green (baseline 1479
   passed, 1 skipped); no exit-code change.

## Dependencies & sequencing

Metric field (Phase 1) → rule + wiring (Phase 2) → docs (Phase 3). Sequential; no external
dependencies. Reuses `concordance.parse_vcf`, `rule_pack.evaluate`/`_status_for`/`_expected_range`.

## Open questions / risks

- `QCResult.value` is populated with an int (existing rows use float) — confirm the model
  accepts an int (Phase 2 test 5 exercises it; if the field is `float | None`, an int is
  accepted; if strictly typed, cast in the rule path). Low risk.
- `warn_above` false-WARN on very large joint-called cohorts — accepted (soft tripwire,
  WARN-only).
