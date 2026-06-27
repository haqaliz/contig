# Aspect spec: fai-build (build a missing `.fai`, then retry)

Single aspect of the `self-heal-missing-index` PRD
(`docs/planning/self-heal-missing-index/prd.md`). The PRD is small enough to be one
aspect; this spec is the buildable slice.

## Problem slice & user outcome

Today a `missing_index` failure is detected and a `build_index` patch is proposed,
but applying it does nothing (`self_heal.py:274-330`), so the retry fails the same
way. Outcome: a missing FASTA index (`.fai`) is **recovered autonomously** — Contig
builds it with `samtools faidx`, retries the same pipeline, and records an auditable
"built the index, then re-ran" repair step. A build that itself fails ends in an
honest FAIL, never a false PASS.

## In scope

- A new injected `IndexBuilder` seam (mirrors the `Executor` seam) with a
  shelling-out default and a test fake.
- Loop-level logic in `self_heal_run` that, when a `build_index` patch is applied,
  parses the missing `.fai` path from `diagnosis.evidence`, runs the builder, and
  branches the recorded outcome (`built_index_and_retried` / `index_build_failed` /
  `index_unresolvable`).
- One shared apply-and-build helper used at every gated apply site (the patch is
  `needs_confirmation`).
- **Corpus note:** a golden `missing_index` case already exists
  (`src/contig/data/detector_corpus.jsonl` line 6, `case_id="missing-index"`), so
  PRD M6's "seed a golden case" is **already satisfied** — no new corpus seed is
  required. This aspect only verifies the corpus/detector tests stay green and that
  pending-corpus capture still labels the first failure `missing_index`.

## Out of scope

- Other index kinds (`.bai`, `.tbi/.csi`, `.dict`, STAR/BWA) — follow-on on the same
  seam via a path-extension→command table.
- Pipeline-regenerate (config-mutation) route; stale-index detection; any change to
  `detect.py`'s `missing_index` rule; risk-tier change to the patch; dashboard
  rendering; re-entering the approval gate after a failed build (one
  approve→build→retry is the ceiling).

## Acceptance criteria (testable)

1. **Heals a missing `.fai`** — `self_heal_run` with `auto_approve=True`, a fake
   executor that fails attempt 1 with a missing-`.fai` log then succeeds attempt 2,
   and a fake `IndexBuilder` that creates the `.fai` and returns 0, produces a
   succeeded run whose last `RepairStep.outcome == "built_index_and_retried"` and
   whose `patch.operation == {"build_index": True}`.
2. **Builder is actually invoked with the right command** — the fake builder records
   its argv; the test asserts it is `["samtools", "faidx", "<fasta>"]` where
   `<fasta>` is the evidence path minus the `.fai` suffix.
3. **Failed build → honest FAIL** — fake builder returns non-zero; the run finalizes
   with `outcome == "index_build_failed"`, `detail` naming the `.fai` path,
   `verdict == "fail"`, and **no further retry attempt** is made (builder/executor
   call counts asserted).
4. **Unparseable evidence → honest FAIL** — a `missing_index` diagnosis whose
   evidence has no parseable `.fai` token finalizes with
   `outcome == "index_unresolvable"` and `verdict == "fail"`; the builder is never
   called.
5. **`-resume` re-runs the failed process** — attempt 2 actually re-executes (the
   fake executor's call count reaches 2) and succeeds once the `.fai` exists.
6. **`apply_patch` unchanged** — `test_apply_patch_reference_build_index_is_rerun_only`
   still passes (the build is loop-level, not in `apply_patch`).
7. **Corpus stays green** — the existing golden `missing_index` case (line 6) loads
   and the detector eval / corpus tests pass; pending-corpus capture on the first
   failure still labels the case `missing_index`. (No new golden case to add.)
8. **Suite green** — `uv run pytest` passes.

## Dependencies & sequencing

1. Seam + pure parse helpers (no loop changes) → 2. Loop wiring via shared helper →
3. Golden corpus seed. Each is independently testable; (2) depends on (1).

## Open questions / risks (this aspect)

- Path parsing must handle absolute and relative `.fai` tokens and degrade to
  `index_unresolvable` when none is found (AC4).
- Builder cwd: run with the run/work dir as cwd; revisit if real runs show path
  mismatches (PRD R2).
- Interactive gate + failed build ends FAIL with no second gate (PRD R6) — accepted
  for this slice.
