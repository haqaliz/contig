# Aspect spec: verify-guard-command

Slug: `eval-corroboration-fold-in` · Aspect: `verify-guard-command`

## Problem slice

The CLI surface: `contig verify-guard` (sibling of eval-guard/heal-guard) with
baseline/history/refreeze semantics, wired into CI, plus the RELEASING.md
snapshot step. Consumes aspect 1's scorer and models.

## In-scope

- `contig verify-guard` command in `contig.cli` mirroring `heal_guard`
  (cli.py:2659-2842) exactly: `--corpus`/`--baseline`/`--history-file`
  overrides, `--tolerance`, `--update-baseline` (rewrite baseline + append
  history, exit 0), `--snapshot` (append only), `--history` (trend print /
  `--json`), `--json` guard result, missing-baseline → exit 1 with hint,
  sha-mismatch loud warning, `REGRESSION:` exit 1 naming diverging case ids,
  `improved` nudge, `PASS:` line.
- Defaults: `src/contig/data/verify_corpus_holdout.jsonl`,
  `verify_baseline.json`, `verify_history.jsonl`.
- CI: `.github/workflows/ci.yml` gains `uv run contig verify-guard` after
  `heal-guard` with a comment.
- `RELEASING.md` snapshot step for the new guard.
- Guard tests mirroring the existing pins (bare default pass, regression on
  perturbed corpus, history trend, baseline↔trend consistency).

## Out-of-scope

- Capture/promote commands (aspect `capture-promote`); dashboard trend card
  (R9 nice-to-have, deferred).

## Acceptance criteria

1. `uv run contig verify-guard` (bare) exits 0 and prints `verify-guard PASS`
   with the committed baseline; `--json` emits a `VerifyGuardResult`.
2. Perturbing a committed holdout case (flip `expected_verdict`) makes the bare
   guard exit 1 and name the case id.
3. `--update-baseline` refreezes (baseline + history append, exit 0);
   `--history` prints the trend; `--snapshot` appends without touching baseline.
4. CI runs the guard; `test_releasing_doc_has_snapshot_step` still passes with
   the updated RELEASING.md.
5. Existing eval-guard/heal-guard pins (0.923, outcome-match 100%, trend
   strings) untouched and green.

## Dependencies / sequencing

Depends on aspect 1 (models + scorer + seed + baseline). The seed baseline
generation happens here (via the real command's `--update-baseline`).
