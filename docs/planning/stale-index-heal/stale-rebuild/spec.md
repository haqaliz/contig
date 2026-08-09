# Aspect Spec: stale-rebuild

**Slug:** `stale-index-heal` / aspect `stale-rebuild`
**Boundary:** the whole slice as one coherent unit — detector branch → path parse →
scratch build → atomic replace → retry → corpus/guards → docs. Sized for one engineer
(agent) per task; tasks are sequential-ish (detector before repair before guards).

## Problem slice and user outcome

A run whose single-file index (`.fai`/`.bai`/`.tbi`/`.csi`) is older than the data it
indexes fails with htslib's "The index file is older than the data file" and today dies
as an undiagnosed `tool_crash`. Outcome: the engine detects it, rebuilds the index from
the run's resolved source, replaces the stale sidecar atomically, and retries —
recording `built_index_and_retried` with mtime evidence, bounded to one rebuild per path.

## In-scope requirements (from PRD M1–M8, S1–S2)

- M1 detector branch (freshness AND-guard, ordered before the generic `missing_index`
  branch)
- M2 stale-index path parse; honest `index_unresolvable`
- M3 rebuild via the shipped `_INDEX_BUILD` table (source = index-minus-suffix)
- M4 scratch build (`<run_id>/healed_index/<name>`) + atomic replace; user's file
  untouched on failed build; `built_paths` build-once
- M5 `built_index_and_retried` reuse; mtime/argv evidence in `RepairStep.detail`;
  `risk="needs_confirmation"` unchanged
- M6 one golden corpus case + one heal-guard scenario; `heal_baseline.json` refrozen in
  the same commit; `heal_history.jsonl` appended
- M7 RED-first tests (detector per kind + ordering collisions; repair success/failure/
  give-ups/cross-device)
- M8 `CAPABILITY_ROADMAP.md` C2 record + CHANGELOG entry in the same commit wave
- S1 golden cases for `.bai`/`.tbi`/`.csi` (beyond the M6 minimum)
- S2 heal-guard variant with a failed build → honest `index_build_failed` give-up

## Out-of-scope boundaries

- Wrong-reference index flavor; `.dict`; directory-shaped indexes; pre-flight
  freshness stat; classic-BWA/bwa-mem2 build-redirect; new outcome literal or
  FailureClass; dashboard changes; signature-affecting model changes.

## Acceptance criteria (testable)

1. A stale `.fai`/`.bai`/`.tbi`/`.csi` log line (htslib freshness wording) classifies
   `missing_index` via the new branch — and absence-phrased lines still classify via
   the generic branch (both directions pinned).
2. Repair: attempt 1 fails with the stale line → build argv from `_INDEX_BUILD` for the
   kind → user's sidecar is replaced **only after a successful build** (failed build:
   file byte-identical) → retry succeeds → `RepairStep` records
   `built_index_and_retried`, `patch_applied=True`, detail carries old/new mtime + argv.
3. Build-once: a second stale failure on the same path gives `index_build_failed`
   ("Already rebuilt …"), never a loop.
4. Give-ups: unparseable path → `index_unresolvable`; builder rc ≠ 0 → `index_build_failed`.
5. Guards: training corpus 100%; `eval-guard` 92.3% unmoved (CI assertion); `heal-guard`
   outcome-match 1.0 over the refrozen set including the new scenario; no signature break
   (pre-existing bundle still verifies).
6. No real nf-core/samtools run in CI (injected executor + injected builder only).

## Dependencies and sequencing

1. Detector branch + tests (M1, M7-detector) — no other code depends on it yet.
2. Parse + rebuild + replace + record (M2–M5) — depends on 1.
3. Corpus case + heal scenario + refreeze + guard assertions (M6, S1, S2) — depends on 2.
4. Docs + roadmap + CHANGELOG (M8) — depends on 3.

`heal_baseline.json` refreeze lands in the same commit as the scenario (R6). The
cross-device replace fallback decision (PRD R5) is resolved inside task 2 with the
recommendation (same-dir temp + rename) unless the implementing agent finds a reason
against it and says so in the task report.

## Open questions / risks

- R5 (cross-device replace) mechanics — recommended same-dir temp fallback.
- R2 wording drift: keep the needle set minimal; non-matching stale text degrades to
  `tool_crash` (no regression).
- R7 wrong-reference masquerade stays out of scope; N2 reference-identity-in-detail is
  the honest follow-on, not built here.
