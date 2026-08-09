# Spec — detector (CRAM/BAM format-mismatch detection)

Aspect of `self-heal-cram-bam-conversion`. Scope per `prd.md`: **detector-only** — new
`FailureClass`, narrow branch, corpus/guard seeds, dashboard taxonomy sync. No conversion
repair (deferred behind the committed revisit trigger, PRD Out of Scope).

## Problem slice and user outcome

A tool killed by a CRAM-decode/format error is diagnosed `tool_crash` at confidence 0.4.
After this aspect: `alignment_format_mismatch` with a named root cause — and the class
exists in the taxonomy so a future pending case can be relabeled into it.

## In-scope requirements (PRD mapping)

- R1: `FailureClass` literal `alignment_format_mismatch` (models.py:262-281, 18 → 19).
- R2: narrow AND-guarded detector branch in `diagnose_failure` (after `reference_not_bgzf`
  :387-404, before `tool_crash` :408), confidence 0.85, CRAM→BAM flavor.
- R3: one golden corpus case + holdout twin written FIRST, independently framed (htslib vs
  GATK wording).
- R4: one heal-guard give-up scenario (`tool-crash-giveup` template), `covered_classes`
  15 → 16, `--update-baseline` refreeze.
- R5: no repair, no false pass, no signature break.
- R6: evidence lines carry the matched CRAM/format lines.
- R7: dashboard `FAILURE_CLASSES` sync (derive.ts + promote route validator + the e2e
  order pin), Python Literal order is source of truth.
- R8: changelog note recording the deferred repair + revisit trigger.

## Out-of-scope boundaries

- The conversion repair itself (samtools view into scratch, params redirect, retry).
- BAM→CRAM direction; the `.csi`-for-BAM/CRAM index kind; `--work-dir` blindness fix.
- Any verdict / exit-code / manifest / signed-record change.

## Acceptance criteria (testable)

1. `diagnose_failure` on the training-case log → `alignment_format_mismatch`, confidence
   0.85, root cause naming CRAM/format.
2. Control (i): a `stale-bai`-shaped log still → `missing_index` with the branch present.
   Control (ii): a CRAM error line containing an absence phrase/path token still →
   `alignment_format_mismatch`.
3. `eval-guard`: held-out baseline **unmoved** (92.3%) — holdout file not edited, only
   appended-to with the new twin? **No** — holdout appended-to WOULD change corpus_sha and
   the guard's number (12/13 → 13/14 if the twin classifies). The holdout append changes
   `corpus_sha` → guard reports `sha_mismatch` loudly → baseline must be refrozen with
   `--update-baseline` (deliberate act, documented). The accuracy must be **≥ the committed
   number (12/13) and honestly reported**; if the twin misclassifies, that is a deliberate
   known-miss to disclose, not a silent pass.
4. `heal-guard`: scenario `alignment-format-mismatch-give-up` → diagnosed class right,
   `gave_up`, `expected_recovered false`, `expected_patch_applied false`; `covered_classes`
   15 → 16; `--update-baseline` refreeze as a deliberate act; `outcome_match_rate` stays 1.0.
5. Dashboard: `FAILURE_CLASSES` in derive.ts lists all 19 literals in Python order; the e2e
   pin updated; promote route accepts `alignment_format_mismatch` (relabel round-trip).
6. Full suite green: `uv run pytest`; `npm test`/`npm run build` in dashboard/.
7. No signature-breaking test added; `verify` on an existing bundle unaffected.

## Dependencies and sequencing

- The bgzip-reference slice's branch (detect.py:387-404) and the `tool-crash-giveup`
  scenario are the templates; both exist at base b8b2092.
- Dashboard sync depends on the Python literal landing first (order pin).
- The baseline refreeze is the LAST step (after all corpus edits).

## Open questions / risks

- Exact needle set is an implementation decision; validated by the two control tests.
- The holdout append forces a baseline refreeze — the refreeze must be the deliberate,
  documented act (never a hand-edit; `--update-baseline` only).
