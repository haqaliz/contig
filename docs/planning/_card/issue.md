# feat eval-corroboration-fold-in

## Brief

Fold the C1/C3/annotation corroboration signals (concordance WARN/PASS, plausibility outcomes, VEP-vs-SnpEff agreement) into the C6 eval loop so verification accuracy — not just detector/heal-loop accuracy — is measured and regression-guarded. This is the single capability the roadmap still marks pending (CAPABILITY_ROADMAP.md C6; FEATURES.md C6 row; C7 M5 deferral). Caveat to dig first: the docs name a blocker across four deferrals — these signals carry no ground-truth labels, so slice 1 is the labeling design itself, probably reusing the shipped pending-review/corpus-promote channel; if the dig concludes no honest labeling exists, the correct outcome is a declined-by-design record (inert-repair precedent), which still settles the deferral. Build test-first, CI-observable, no network, and state honestly in the PRD that this is push, not demand-pull.

## Source

Picked by `contig-next` (2026-08-09) from the repo's own planning files; not filed as a GitHub issue. No `gh` fetch performed.
