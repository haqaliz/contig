# Evidence gate — second run (M10 semantic filter)

Date: 2026-09-21. Follow-on to `evidence-gate-20260921.md` (value-only: 0/20
binds). Same subject repo (`ritvikK05/rnaseq-reanalysis-htt`, same shallow
clone), same reviewed 20-claim draft, same throwaway gate script — now passing
the M10 `metrics` map (the simulation's METRICS) to the **shipped module**
(commits 73fce8e + b8b4bf0). Shipped chain only: unchanged `sweep_repo`,
unchanged `load_claims`, unchanged `_value_matches`/exactly-one/dual-scale/M9,
new semantic subsetting + `semantic_match`, independent wrong-bind
re-resolution through the real resolvers.

## Results (actual, shipped module)

- `sweep_repo`: 330,081 candidates, 0 skips (unchanged).
- `match_claims(..., metrics=METRICS)`: **6 bound / 7 ambiguous / 3 refused /
  4 no_candidates** out of 20.
- Wrong-bind check: **6/6 bound locators re-resolve to exactly the claim
  value at the claimed precision; 0 wrong, 0 unresolvable.**

| Claim | Value | Outcome | Semantic path | Site count |
|---|---|---|---|---|
| called_deg_count | 2252 | **bound** | n_deg (pool also drew Count, n_deg_mapped) | 1 |
| recovery_rate | 68.2 | **bound** | recovery | 1 |
| na_padj_count | 2326 | **bound** | n_na_padj (pool also drew padj, padj_ref) | 1 |
| filtering_off_deg | 2226 | **bound** | n_deg | 1 |
| drop_ko4_deg | 2826 | **bound** | n_deg | 1 |
| drop_ko4_recovery | 62.6 | **bound** | recovery | 1 |
| ref_deg_count | 1464 | no_candidates | n_deg, n_deg_mapped (value absent) | 0 |
| recovery_of_testable | 81.8 | no_candidates | recovery (value absent) | 0 |
| go_top_padj | 2.5e-27 | no_candidates | n_na_padj, padj, padj_ref (value absent; see sensitivity) | 0 |
| unmapped_ref_deg | 244 | no_candidates | n_deg, n_deg_mapped (value absent) | 0 |
| called_by_both | 998 | ambiguous | value-only fallback (no header matches) | 11 |
| spearman_rho | 0.896 | ambiguous | value-only fallback | 160 |
| go_terms | 256 | ambiguous | value-only fallback | 45 |
| jaccard_drop_ko4 | 0.662 | ambiguous | value-only fallback | 144 |
| htt_l2fc_this | 1.44 | ambiguous | l2fc_raw, l2fc_ref, l2fc_shrunk | 86 |
| htt_l2fc_ref | 1.34 | ambiguous | l2fc_raw, l2fc_ref, l2fc_shrunk | 83 |
| true_disagree | 108 | ambiguous | value-only fallback | 188 |
| sign_agreement | 100.0 | refused | M9 deny-list | 0 |
| filtering_off_recovery | 68.0 | refused | M9 sig-digit rule (68.0 is int-valued, 2 sig digits) | 0 |
| near_miss_count | 72 | refused | M9 sig-digit rule | 0 |

## Expectation vs actual (recorded honestly)

The manual simulation predicted ≈7 binds; the module produced **6**. The
difference is exactly `filtering_off_recovery` (68.0): the simulation omitted
M9, and the module refuses it (68.0 is an integer-valued float with 2
significant digits — M9 by design). The module is correct per spec; the
simulation was known to skip M9. Every other claim matches the simulation's
verdict, and every bind re-resolves correctly — including `recovery`/`n_deg`/
`n_na_padj` binding to the exact baseline/filtering-off/drop-KO4 rows they
name in `05_sensitivity_summary.csv`.

## Vocabulary sensitivity, now measured twice (both were predicted)

1. **"called by both" vs `n_recovered`**: words ["both","called"] match no
   header → value-only fallback → ambiguous (11 sites). The value 998 lives in
   the `n_recovered` column; a metric word "recovered" (⊂ "n_recovered") would
   bind it. The paper's phrasing ≠ the repo's header; the human review step is
   the documented fix, and the sidecar names the count either way.
2. **"padj" vs `p.adjust`**: the word "padj" matches `padj`, `n_na_padj`,
   `padj_ref` — but NOT `p.adjust` (the dot breaks the raw-lowercase
   substring). The GO claims' true home (`p.adjust` in `04_go_*.csv`) is
   excluded from the semantic pool. Harmless for `go_top_padj` (the value
   2.5e-27 is not in the repo anyway — the closest is 2.36e-27, and
   sci-notation compares exactly), but the `semantic_match` line naming
   unrelated columns for a "padj"-worded claim is real noise, documented as a
   known sensitivity of the containment rule.

## Gate verdict (PRD rule applied)

**The narrowed design ships.** The semantic filter restores meaningful,
verifiable recall on the canonical repo shape: 0/20 → 6/20, every bind
re-resolved correct, 0 wrong; every non-bind degrades honestly (ambiguous with
the count named, refused with the reason, no_candidates with the semantic
column named). The residual limits are named and human-review-shaped, not
silent: metric-vocabulary ↔ header-vocabulary mismatches (two measured cases),
multi-column semantic pools (`l2fc_raw`/`l2fc_ref`/`l2fc_shrunk` still
ambiguous at value level — the semantic filter narrows but does not
disambiguate dense per-gene tables), and M9's intentional refusal of
round-percentage claims (100.0, 68.0). Aspect 3 (the CLI) is unblocked to ship
narrowed: `extract-claims` → human review (add/reject metric words per claim)
→ `infer-locators` → `reproduce`, with the sidecar as the review surface.

## Honesty scope (same voice as the first gate)

One repo, one gate run, shallow clone at a moving `main`; the paper text was
the repo's own README; the reviewed draft and the METRICS map are the
author-of-record's reading (a second human reviewer could pick different
words — the sensitivity cases show how much that matters). No real run
performed (R6 still read from the scripts, still absent). The expectation
discrepancy (68.0) is disclosed above, not hidden. Nothing touched the shipped
modules during the run; the suite stayed green (3179 passed / 1 skipped).