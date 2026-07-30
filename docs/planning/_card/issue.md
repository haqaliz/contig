# Card: feat / heal-scenarios-catalog-coverage

- **Type:** feat
- **Id/slug:** `heal-scenarios-catalog-coverage`
- **Owner:** aliz
- **Branch:** `feat/heal-scenarios-catalog-coverage/aliz`
- **Source:** inline brief (no GitHub issue — the tracker returns "No Issues"; confirmed on
  the prior card) — carried from the `/contig-next` recommendation (2026-07-30), the next
  slice after `repair-patch-applied` merged as v0.49.0.

## Brief

Extend C6's heal-guard corpus to the failure-class families that have never been driven
through the real self-heal loop. `src/contig/data/heal_baseline.json` covers 7 classes over 9
scenarios, while `src/contig/repair.py` proposes patches for 14 — so `missing_reference`,
`reference_not_bgzf`, `container_pull_failed`, `container_unavailable`, `conda_solve_failed`,
`download_failed`, `disk_full`, `permission_denied` and `platform_unsupported` all ship live
repair strategies that nothing exercises end-to-end (the roadmap names this gap at
`docs/technical/CAPABILITY_ROADMAP.md:1057`).

Add one frozen `HealScenario` per family through the **real** `self_heal_run` loop — the
detector and `propose` never stubbed (heal-guard PRD R2) — each declaring its terminal
outcome and `expected_patch_applied`, then refreeze `heal_baseline.json` as a deliberate act.

Two caveats to dig on first:

1. `outcome_match_rate` may legitimately fall below 1.0 if the loop misbehaves on a new
   family. Fix the loop or commit an honest baseline — do **not** quietly refreeze.
2. `disk_full` / `permission_denied` / `platform_unsupported` may not be scriptable through
   the existing executor / index-builder / poll seams, in which case drop them with the
   reason recorded rather than adding a seam that bypasses real behavior.

Also note: the held-out-accuracy trend is already shipped despite
`docs/technical/CAPABILITY_ROADMAP.md:1846` and `FEATURES.md:255` still calling it pending —
correct that prose as part of this work.

## Grounding gathered at pick time (`/contig-next`)

- `docs/technical/CAPABILITY_ROADMAP.md:1057` — C6 slice 2 honest scope, verbatim: *"the
  wider failure-class catalog (container, download, disk, permission, missing-reference
  families) has no scenario yet."*
- `docs/technical/CAPABILITY_ROADMAP.md:1030` — the other C6 leftover (folding the unlabeled
  C1/C3 corroboration signals into one eval number) is blocked on labeling design. Not this
  work.
- `src/contig/data/heal_baseline.json` — 9 scenarios, `covered_classes` = 7 (`bad_param`,
  `missing_index`, `no_progress`, `oom`, `qc_anomaly`, `time_limit`, `tool_crash`),
  `outcome_match_rate` 1.0, `recovery_rate` 0.5555…, `contig_version` 0.48.0.
- `src/contig/repair.py` — `propose_patches` branches for 14 classes: the 7 covered above
  (minus `qc_anomaly`, which proposes nothing by design) plus `container_pull_failed`,
  `container_unavailable`, `conda_solve_failed`, `download_failed`, `disk_full`,
  `permission_denied`, `platform_unsupported`, `missing_reference`, `reference_not_bgzf`.
- `CHANGELOG.md` v0.49.0 — the `patch_applied` bug (a **rejected** patch reported as
  `Repaired`) is the precedent for the kind of defect that hides in untested loop paths.
- Stale prose to correct: `docs/technical/CAPABILITY_ROADMAP.md:1846` and `FEATURES.md:255`
  both call the held-out-accuracy trend pending; it ships today as `holdout_history.jsonl` /
  `heal_history.jsonl`, `--snapshot`/`--history`, and
  `dashboard/components/eval/{holdout,heal}-history.tsx`.
