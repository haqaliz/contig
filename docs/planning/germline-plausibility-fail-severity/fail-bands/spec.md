# Aspect spec: fail-bands

Parent PRD: `../prd.md`. Single aspect — this feature is one buildable unit.

## Problem slice & user outcome

Give the three germline biological-plausibility checks (`ts_tv_ratio`, `het_hom_ratio`,
`variant_count`) their first FAIL severity, so a grossly-implausible germline call set
drives `record.verdict` → FAIL instead of a easy-to-miss WARN. Verdict-only (no CLI
exit-code change). WES-safe, gross-only bands.

## In scope

- Add `fail_*` bands to the three germline rule dicts in
  `src/contig/verification/rule_pack.py` (`VARIANT_RULE_PACK`):
  - `ts_tv_ratio`: `fail_below: 1.2`, `fail_above: 3.6` (keep `warn_below: 1.8`,
    `warn_above: 2.4`).
  - `het_hom_ratio`: `fail_below: 1.0`, `fail_above: 3.0` (keep `warn_below: 1.4`,
    `warn_above: 2.5`).
  - `variant_count`: `fail_below: 1` (keep `warn_below: 10`, `warn_above: 20_000_000`;
    **no `fail_above`**).
- Update the WARN-only comments in `rule_pack.py` and docstrings in `variant_metrics.py`.
- Update the tests that assert germline plausibility is WARN-only; add new FAIL/boundary
  tests, the empty-call-set combined-result test (R7), and the band-ordering invariant
  test (R8).
- Sync docs: `CHANGELOG.md` (Unreleased), `CAPABILITY_ROADMAP.md` C3 germline rows,
  `FEATURES.md`.

## Out of scope

- CLI exit-code wiring (`contig verify`/`run`) — cross-cutting, deferred.
- Somatic / RNA-seq / RNA-composition / annotation / sex-check plausibility packs.
- Capture-type-aware bands; any clinical claim.

## Acceptance criteria (testable)

1. `ts_tv=0.5` → `status="fail"`; `ts_tv=2.0` (WGS) and `ts_tv=3.3` (WES) → not fail;
   `ts_tv=3.7` → fail; `ts_tv=1.15` → fail.
2. `het_hom=0.8` → fail; `het_hom=1.5` → not fail; `het_hom=3.1` → fail.
3. `variant_count=0` → fail (`fail_below: 1`); `variant_count=5` → warn (below `warn_below`
   but ≥ `fail_below`); `variant_count=25_000_000` → warn (soft ceiling, **not** fail).
4. Empty germline VCF → `variant_count` FAIL + `ts_tv`/`het_hom` UNVERIFIED →
   `overall_verdict(...) == "fail"` (R7).
5. Band-ordering invariant holds for every germline rule:
   `fail_below ≤ warn_below ≤ warn_above ≤ fail_above` where present (R8).
6. `uv run pytest` → green (baseline 1479 passed, 1 skipped; count may rise with new tests).

## Dependencies & sequencing

None external. Scorer (`_status_for`), evaluator, reducer, CLI all unchanged (verified in
the Phase-2 dig). Pure data + tests + docs. Tests written first (RED) per repo TDD.

## Risks specific to this aspect

- Contract-reversal churn across tests/comments/docs — mitigated by the Phase-2 file:line
  inventory in `_card/understanding.md`.
- A stray existing test that asserts empty-VCF → WARN (now FAIL) — expected to update, not
  a regression.
