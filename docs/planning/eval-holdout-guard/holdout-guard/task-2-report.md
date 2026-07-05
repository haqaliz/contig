# Task 2 (Phase C) report — `contig eval-guard` CLI command

Date: 2026-07-05 · Branch: `feat/eval-holdout-guard/aliz`

## Scope

Implemented Phase C only from `plan_20260705.md`: the `contig eval-guard` Typer command plus its
CLI tests. Did not touch Phase D/E (no `holdout_baseline.json` created/committed, no
CHANGELOG/CAPABILITY_ROADMAP/FEATURES edits).

## Files modified

- `src/contig/cli.py`:
  - Added import block `from contig.holdout import (compare_to_baseline, default_baseline_path,
    default_holdout_path, load_baseline, save_baseline)` next to the existing `eval_history`
    import.
  - Added `@app.command(name="eval-guard")` / `eval_guard(...)`, inserted directly after
    `eval_detector` and before `clusters`, per the plan's file-by-file build order. Reused
    `get_detector`, `load_corpus`, `evaluate_detector`, `sha256_file`, `snapshot_from_report`,
    `_pkg_version`, `datetime`/`timezone` — all already imported in `cli.py`; no new top-level
    imports beyond the `contig.holdout` block. Copied the `KeyError`→`Exit(1)` and
    `FileNotFoundError`→`Exit(1)` handling verbatim from `eval_detector`.
- `tests/test_eval_holdout.py`: appended the Phase C section (`# --- Phase C: eval-guard CLI
  command ---`) with a module-level `runner = CliRunner()` and `from contig.cli import app`,
  mirroring `tests/test_cli.py`'s `eval-detector` tests. Added `shutil` and `save_corpus` imports.

No Phase A/B file (`src/contig/holdout.py`, `src/contig/models.py`,
`src/contig/data/detector_corpus_holdout.jsonl`) was modified — only imported/reused.

## Command flow implemented (matches plan step list 1–6)

1. Resolve `holdout_path`/`baseline_path` (default to `default_holdout_path()` /
   `default_baseline_path()` when the flags are omitted).
2. `get_detector(detector)` — `KeyError` → stderr + `Exit(1)`.
3. `load_corpus(holdout_path)` — `FileNotFoundError` → stderr + `Exit(1)`.
4. `evaluate_detector(cases, detector_fn)`; `sha256_file(holdout_path)`.
5. `--update-baseline`: build `EvalSnapshot` via `snapshot_from_report(...)`, `save_baseline(...)`,
   echo "Baseline updated: ...", return (exit 0). Never fails.
6. Else: `load_baseline` + `compare_to_baseline`; emit JSON first if `--json` (kept clean — the
   "Guard:"/MISS text render, the improved nudge, and "Guard PASS" are all gated on `not
   json_out` so `--json` stdout stays parseable; the sha/detector-mismatch warnings and the
   REGRESSION line are written with `err=True` so they never land on stdout regardless of
   `--json`); no-baseline → stderr + `Exit(1)`; sha/detector mismatch → loud stderr warnings,
   non-failing; regression → stderr "REGRESSION: ..." + `Exit(1)`; improved → stdout nudge, exit
   0; else → stdout "Guard PASS: ...", exit 0.

## `get_detector` name resolution / worse-stub registration

Confirmed `get_detector` (`src/contig/detect.py:599-614`) resolves any name other than `"llm"`
via `DETECTORS[name]` (a module-level dict). Registered the stub with
`monkeypatch.setitem(contig.detect.DETECTORS, "worse", _worse)` — this mutates the shared dict
object in place, so `get_detector("worse")` (called from `cli.py`, which only imports the
`get_detector` function, not the dict) resolves it correctly without touching `contig.cli` at
all. No fallback `monkeypatch.setattr(contig.cli, "get_detector", ...)` was needed.

## stderr-capture convention used

This repo's `typer` version (0.26.7) vendors its own Click and its `typer.testing.CliRunner`
always separates streams: `Result.output` is stdout+stderr mixed, and `Result.stderr` is a
distinct decoded property (see `typer/testing.py` `StreamMixer`/`Result.stderr`) — no
`mix_stderr` constructor argument exists or is needed. Matched the existing `tests/test_cli.py`
convention of a bare `CliRunner()` and used `result.stderr` for the sha-mismatch-warning and
no-baseline assertions (asserting on the dedicated stream keeps the JSON test unambiguous too),
and `result.output` for the general PASS/REGRESSION text checks (some of which are stdout-only
anyway).

## Tests added (all in `tests/test_eval_holdout.py`, Phase C section)

1. `test_guard_update_then_pass` — freeze via `--update-baseline` into a tmp baseline (exit 0,
   "Baseline updated"), then guard against the same tmp baseline (exit 0, "Guard PASS").
2. `test_guard_regression_worse_detector` — freezes with `--detector rules`, registers the
   `"worse"` stub via `monkeypatch.setitem`, guards with `--detector worse` → exit 1,
   "REGRESSION" in output.
3. `test_guard_no_baseline` — `--baseline` pointing at a nonexistent tmp path → exit 1,
   "No held-out baseline" on `result.stderr`.
4. `test_guard_sha_mismatch_warns` — freezes against a tmp copy of the shipped held-out set, then
   guards against a second tmp copy with one duplicated case appended (different sha, same
   detector) → exit 0, and both "changed" and "sha" present (case-insensitive) on `result.stderr`.
5. `test_guard_json` — `--json` after a fresh freeze emits parseable JSON with `"regressed"` and
   `has_baseline: true`.

Every invocation passes `--baseline <tmp_path>/...`; the two tests that write a baseline via
`--update-baseline` also pass `--holdout <tmp copy>` where the plan called for it (sha-mismatch
test) or rely on the shipped read-only holdout file (update-then-pass, regression tests, since
those never write to `--holdout`). No committed file (`detector_corpus_holdout.jsonl`,
`holdout_baseline.json`) was ever written to by a test.

## Commands run + tail output

```
$ uv run pytest tests/test_eval_holdout.py -v
============================== 21 passed in 0.26s ==============================

$ uv run pytest
1092 passed, 1 skipped in 10.82s
```

(1092 = the 1087-baseline the task named + the 5 new Phase C CLI tests; Phase A/B's 16 tests from
Task 1 were already included in that 1087 baseline since Task 1 was merged on this branch before
Task 2 started.)

Manual smoke check (no committed files touched):
```
$ uv run contig eval-guard
No held-out baseline at .../src/contig/data/holdout_baseline.json; run 'contig eval-guard --update-baseline' to freeze one.
exit=1
```
Confirms Phase D's `holdout_baseline.json` still does not exist and the command fails closed
rather than crashing.

## Concerns

None blocking. Two judgment calls worth flagging for reviewer awareness:

- The plan's bullet list for the guard branch reads as a flat list of behaviors rather than a
  strict if/elif/else; I implemented `regressed` and `improved` as effectively mutually exclusive
  branches (guaranteed by `compare_to_baseline`'s tolerance-band semantics — they cannot both be
  true for the same comparison), with a final `else` branch printing "Guard PASS" only when
  neither fired. This matches all five new tests and the plan's stated per-branch messages.
- I gated the "Guard:"/MISS text render, the improved nudge, and the final "Guard PASS" line
  behind `not json_out` (not explicit in the plan's prose for the improved-nudge case) so that
  `--json` output stays a single parseable JSON line on stdout; sha/detector-mismatch warnings and
  the REGRESSION line stay on stderr unconditionally since the plan explicitly scoped those to
  stderr already, so they don't interfere with stdout JSON either way.
