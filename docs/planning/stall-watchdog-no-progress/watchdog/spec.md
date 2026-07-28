# Aspect spec — `watchdog`

The whole slice is one aspect: the heartbeat watchdog plus the `no_progress` class it makes
reachable. They ship together because neither is useful alone — a detector branch with no
emitter classifies text Contig never writes; a watchdog with no branch produces a run that
misclassifies as `tool_crash`.

Parent PRD: [`../prd.md`](../prd.md).

## Problem slice and user outcome

A hung run is invisible to Contig (`default_executor` blocks in `subprocess.run`,
`runner.py:602`). With `--detect-stalls`, a run that goes silent on every observable surface for
the configured window is terminated, diagnosed `no_progress`, and retried with `-resume`;
otherwise it ends in an honest `gave_up`. Off by default, so no existing user is affected.

## In scope

1. A pure stall decision over heartbeat fingerprints, with an injected clock.
2. A heartbeat observer over `trace.txt`, `.nextflow.log`, and `run.log` that cannot itself hang
   the watchdog.
3. A watchdog executor factory preserving `Executor = Callable[[list[str], Path], int]`.
4. Process-group-safe termination (SIGTERM → grace → SIGKILL) that keeps `contig cancel` working.
5. A `no_progress` branch in `diagnose_failure`, ahead of the OOM check.
6. A `no_progress` retry patch in `propose_patches` (`risk="safe"`).
7. `--detect-stalls` / `--stall-timeout` plumbed CLI → `_dispatch_run` → `self_heal_run`.
8. Corpus: a training case, a heal scenario, both baselines refrozen, dependent test literals moved.
9. Docs: `CAPABILITY_ROADMAP.md`, `FEATURES.md`, `CHANGELOG.md`, and the stale
   `heal-guard` docstring (`cli.py:2600-2607`).

## Out of scope

`qc_anomaly`; Snakemake support claims; on-by-default operation; timeout calibration; a
dashboard surface; per-task (rather than per-run) stall detection; stall-specific retry
escalation beyond `max_attempts`.

## Acceptance criteria (testable)

| # | Criterion |
|---|---|
| A1 | The pure decision returns *stalled* only after the full window with **all** surfaces silent; any single surface changing resets it. |
| A2 | A fingerprint sequence where only `.nextflow.log` changes is **never** stalled (the long-single-task case). |
| A3 | An observer whose read blocks does not block the watchdog; the blocked read counts as *no progress observed*, never as *alive*. |
| A4 | Contig's own stall message classifies as `no_progress`; so does the frozen `holdout-no-progress-1`; **both through the same phrase-level needles**. |
| A5 | A genuine OOM still classifies as `oom` — both the `exit == 137` path and the "out of memory" text path — when no stall sentinel is present. |
| A6 | A `no_progress` diagnosis proposes exactly one `risk="safe"` retry patch. |
| A7 | The watchdog terminates a real, long-running child process and returns a non-zero code; the run's stall message lands in `run.log`. |
| A8 | `contig cancel` still reaps the run with the watchdog enabled. |
| A9 | `--stall-timeout` without `--detect-stalls` exits non-zero naming the flag. |
| A10 | With the watchdog disabled, `default_executor` is used unchanged and the pre-existing suite passes untouched. |
| A11 | The new heal scenario reaches its declared outcome through the real `self_heal_run` loop. |
| A12 | `contig eval-guard` passes clean against the refrozen baseline at 12/13; `contig heal-guard` lists `no_progress` in `covered_classes`. |

## Dependencies and sequencing

Phases 1–2 (pure core + observer) are independent of 3 (detector/repair) and can run in
parallel. Phase 4 (executor) needs 1 and 2. Phase 5 (cancel) needs 4. Phase 6 (CLI) needs 4.
Phase 7 (corpus) needs 3 and 6. Phase 8 (docs) is last.

## Open questions carried in

- **O5 (decided in the plan):** the observer runs off-thread so a wedged filesystem cannot
  freeze the watchdog.
- **O2 (verify, do not assert):** what a SIGTERMed Nextflow returns and writes to its trace.
  Covered by the manual gate, not CI.
- **O4:** whether the watchdog settings round-trip through `LaunchManifest`. Plan proposes
  runtime-only.
