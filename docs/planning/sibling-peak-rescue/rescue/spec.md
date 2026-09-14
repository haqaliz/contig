# Spec: sibling-peak-rescue / rescue

Status: **SHIPPED (Unreleased, 2026-09-13).** Landed on
`feat/sibling-peak-rescue/aliz` as `bbaf8f6` (parser prerequisite), `857f1eb`
(sibling sizer rung, flipping the no-rescue pin), `da926b7` (heal-site wiring +
telemetry), and the docs commit (changelog/roadmap corrections). Acceptance
criteria AC1-AC7 passed; the guards were re-run and unmoved.

Single aspect for the PRD (`docs/planning/sibling-peak-rescue/prd.md`). Mirrors
the parent slices' `sizing/` single-aspect pattern
(`peak-rss-resource-scaling/sizing/spec.md`).

## Problem slice

Complete the C2 OOM-sizing ladder with the deferred same-process sibling rung:
when no OOM'd task has a usable own `peak_rss`, size the retry from the max
observed peak among same-coarse-`process` rows — **only when that strictly
exceeds the current limit** (else blind `× 2`, never a no-op retry) — and record
the tier + borrowed evidence in `RepairStep.detail`. Prerequisite: the trace
parser must expose the coarse `process` column it currently aliases to `name`.

## In scope

1. `events.py` — both parsers read `process` by header name, `or name or ""`
   fallback; docstring column list corrected.
2. `resource_sizing.py` — `peak_informed_memory_gb` gains `current_gb` and the
   sibling rung; `PeakSizing` gains `source_name` (defaulted); tiers
   `"sibling_peak"` / `"sibling_dominated"`; module docstring (`:9-11`) updated.
3. `self_heal.py::_oom_memory_sizing` — current-limit read, `current_gb` pass,
   two new detail strings; call site and `apply_patch` untouched.
4. Tests, RED first: flipped `test_same_process_sibling_is_not_rescued` +
   dominated/no-sibling/coarse-column parser tests + fake-executor integration
   test (sibling-sized retry config + detail wording; dominated → blind detail).
5. Changelog + `CAPABILITY_ROADMAP.md` corrections (walltime blocker claim,
   C2 marker), `contig-next`-style honest-scope writeup.

## Out of scope

- Walltime branch code; FailureCase corpus fold-in; Snakemake;
  verdict/exit-code/`FailureClass`; tier-`"oom_task"` behavior; heal-guard
  scenarios; calibration; dashboard.

## Acceptance criteria (test-first, no real Nextflow in CI)

- AC1 Parser: trace with both columns → `process` = coarse value on both models;
  trace without the column → `name` fallback, all existing tests unchanged.
- AC2 Sizer: censored OOM'd row + sibling peak with `ceil(peak×1.5) > current`
  → tier `sibling_peak`, correct target, `source_name` set.
- AC3 Sizer: same but candidate `≤ current` → tier `sibling_dominated`,
  `target_gb None`; caller detail says blind fallback.
- AC4 Sizer: no sibling and no own peak → tier `unavailable` (byte-identical
  behavior); own peak present → `oom_task` unchanged; multi-OOM max unchanged.
- AC5 `apply_patch` seam + ceiling/never-shrink/gave-up tests pass unchanged.
- AC6 Integration: fake executor writes a partial trace with a `process` column
  and a sibling row → retry config sized from the sibling peak, detail carries
  `sibling_peak` and the borrowed name; dominated case → blind `× 2` config,
  detail carries `sibling_dominated`.
- AC7 Guards unmoved, **verified not assumed**: run `contig heal-guard` and
  `contig eval-guard` before the first commit and after the last — baselines
  must be byte-identical (no refreeze); the `oom` heal scenario's trace has no
  `process`/peak column, so it must stay on the blind path. No
  FailureClass/corpus change anywhere in the slice.

## Dependencies and sequencing

1. Parser fix (AC1) — must land before the sizer change; both parser edits in
   one commit (the join key breaks if only one lands).
2. Sizer rung (AC2-AC4) — depends on 1.
3. Heal-site wiring + integration (AC5-AC6) — depends on 2.
4. Changelog + roadmap corrections (AC7) — last.

## Open questions / risks

- Trace accumulation across attempts is unmodeled (all rows read, matching
  tier a today) — accepted, noted in the PRD.
- The flipped shipped test is a deliberate contract change; the PRD's
  "disclosed like the `qc_anomaly` `recovered` flip" wording must appear in the
  changelog.
- If `PeakSizing.source_name` complicates the NamedTuple equality in existing
  tests, drop it (Should-have #5) rather than widen the diff — the tier and
  value carry the evidence either way.