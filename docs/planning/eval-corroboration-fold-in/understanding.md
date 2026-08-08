# eval-corroboration-fold-in — Understanding (Phase 2 dig)

## What the work is really asking

Fold the C1/C3/annotation corroboration signals (concordance, plausibility,
structural, VEP-vs-SnpEff agreement) into the C6 eval loop so **verification
accuracy** — not just detector-classification and heal-loop outcome-match
accuracy — is measured and regression-guarded. The roadmap has marked this
pending across five deferral sites (CAPABILITY_ROADMAP.md C6; FEATURES.md C6 row;
eval-holdout-guard/prd.md:117-121; self-heal-eval-guard/prd.md:32-36;
annotation-m5-surface/prd.md:240-243), all naming the same blocker: **the
signals carry no ground-truth labels**, and a labeling design is required first.

## What the dig established (file:line grounded)

1. **The blocker is structural, not cosmetic.** `QCResult` (models.py:67-82) has
   no expected-value/label field; checks are self-assessments. Concordance is
   WARN-capped by contract everywhere ("corroboration, not ground truth") and
   plausibility bands are uncalibrated engineering defaults. The guard machinery
   is classification-shaped (`evaluate_detector` scores predicted ==
   expected_class, corpus.py:76; `evaluate_heal` scores declared expected_*
   fields, heal.py:216-238), and nothing records whether a verification signal
   was *right*.

2. **No QC-level ground truth exists anywhere.** detector_corpus.jsonl /
   detector_corpus_holdout.jsonl are failure-log detection data; FailureCase
   (models.py:446-454) carries no QC field; the demo bundle has no
   concordance/plausibility results. The only existing labeled QC-ish surface is
   dashboard e2e fixtures (corroboration-fixture etc.).

3. **The one existing verdict→corpus bridge is lossy.** `qc_verdict_flagged`
   (self_heal.py:1041-1110) captures QC-FAIL-on-green runs into
   pending_corpus.jsonl with the QC summary flattened to prose in `log_text`;
   structured qc_results are dropped. Concordance can never FAIL, so it can
   never ride this bridge.

4. **The guard plumbing is copy-paste-ready for a sibling.** holdout.py +
   heal.py + snapshot_history.py give the full pattern: frozen corpus, pure
   comparator, pretty-JSON baseline, JSONL trend, `--update-baseline` /
   `--snapshot` / `--history`, CI invocation (ci.yml:20-27). Test surface pins:
   baseline 0.923 hard-pin (test_qc_anomaly_capture.py:165), baseline↔trend
   consistency (test_snapshot_history.py:110/:144), no-leak invariants, bare
   guard strings in test_guard_trend.py.

5. **A run_id join channel already exists but is unused.** FailureCase.source =
   "pending:{run_id}" ↔ runs/<id>/run_record.json (persists qc_results).

## The design crux (what the PRD must decide)

Verification checks are **deterministic code, not a model** — scoring them
against fixtures is one step from a tautology (the repo's standing
self-graded/synthetic honesty applies). The non-tautological reading: the
**bands/thresholds are the uncalibrated "model"**, and every C1/C3 slice
defers band calibration on real data (e.g. count_concordance thresholds,
somatic overlap band). A labeled verification corpus + guard is precisely the
instrument those deferrals keep naming — it makes band changes *measurable and
regression-guarded* over versions, and it becomes genuinely valuable as real
runs feed it through a promote channel. Options to put to the user:

- **Option 1 (full)**: a frozen labeled verification corpus (per-signal expected
  status/verdict) + a guard scoring the verification rules against it, seeded
  synthetic, fed by a real-run capture+promote channel, trended, CI-guarded.
- **Option 2 (informational)**: verification-signal outcomes reported/trended
  but never guarded (the recovery_rate precedent).
- **Option 3 (declined-by-design)**: record why no honest labeling exists
  (inert-repair precedent) and close the deferral.

## Incidental finds (flag, don't paper over)

- **Dashboard FAILURE_CLASSES drift**: derive.ts:278-292 is missing 5 of 18
  FailureClass literals (`reference_not_bgzf`, `missing_dependency`, `disk_full`,
  `download_failed`, `permission_denied`), so the UI cannot relabel pending
  cases to classes v0.49-0.50 made reachable — a live blocker on the same
  human-correction channel this feature proposes to reuse (filed as C2 defect
  (d) in CAPABILITY_ROADMAP.md).
- No "corroborated by" line exists for C1 signals (only C7 M4 annotation has
  one, annotation_surface.py:61-94) — a possible small sibling slice, likely
  out of scope here.

## Open questions for the interview

1. Which option (1/2/3) is the slice's scope; what does the human label mean
   ("was this WARN/FAIL correct?") and who provides it pre-revenue?
2. Guard surface: new `contig verify-guard` (sibling of eval-guard/heal-guard)
   vs folded into eval-guard?
3. In scope: the FAILURE_CLASSES relabel fix (it blocks the promote channel this
   feature reuses)?
4. Seeding: synthetic fixtures across which checks (concordance WARN bands,
   plausibility bands, structural) for the first corpus?

## Guardrails check

Layer 2 (verify/eval machinery) ✓. No Layer 1 ✓. Founder's edge ✓ (no
credentials/regulatory). Gets better as base models improve ✓ (better
adjudication of disagreements makes labels more accurate and bands better
calibrated). Push, not demand-pull — must be stated in the PRD.
