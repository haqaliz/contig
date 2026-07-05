# Understanding — feat/eval-holdout-guard (C6 slice 1: held-out split + regression guard)

Fast-track Phase-2 dig. Grounded in a full code map (path:line cited inline), from direct
reads plus a code-mapping agent pass. No `graphify-out/` graph exists in this worktree.

## What the work is really asking

The first concrete slice of C6 (`CAPABILITY_ROADMAP.md:390-414`): stop scoring the detector
over the *whole* corpus and instead (1) freeze a **held-out** set, (2) score the current
detector against it, and (3) add a **regression guard** — a command that exits non-zero when a
corpus or detector change lowers held-out accuracy, so a regression is caught *before it ships*.
This is moat #2 (accumulated eval data) turned into a measured loop.

## The machinery to reuse (do NOT rebuild)

- **Corpus:** `src/contig/data/detector_corpus.jsonl` — 23 `FailureCase` lines
  (`models.py:358-366`: `case_id, description, source, events, log_text, expected_class`).
  Loaded by `load_corpus` (`corpus.py:40-47`). Confirmed/live/synthetic is carried in the
  `source` prefix (`corpus.py:282-288`), not a field. **No split/held-out field exists.**
- **Eval:** `evaluate_detector(cases, detector) -> DetectorEvalReport` (`corpus.py:50-104`);
  accuracy = exact-match rate of predicted vs `expected_class` over ALL cases handed in
  (`corpus.py:71,101`). Report fields: `total, correct, accuracy, mismatches, per_class`
  (`models.py:387-394`).
- **Detector registry:** `get_detector(name)` → `rules` / `rules-strict` (pure) / `llm`
  (env-gated) (`detect.py:585-614`). Guard default must be a deterministic detector.
- **History:** `EvalSnapshot` (`models.py:397-414`: `timestamp, corpus_size, corpus_sha,
  accuracy, per_class, contig_version, detector`), `snapshot_from_report` + `append_snapshot`
  + `load_history` (`eval_history.py:22-66`), committed at `data/eval_history.jsonl`.
- **CLI:** `eval-detector` Typer command (`cli.py:1485-1553`); siblings `coverage`, `clusters`,
  `corpus-promote` share the exact option/guard/render style a new command must mirror.
  `sha256_file` at `models.py:17`.

## Affected areas (likely touch points)

- `src/contig/corpus.py` — held-out load/split helper.
- `src/contig/cli.py` — a new guard command (or flags on `eval-detector`).
- Possibly `src/contig/models.py` — only if a marker field is chosen over a separate file.
- `src/contig/data/` — the frozen held-out artifact + a committed baseline.
- `tests/test_eval_holdout.py` (new) — mirror `test_corpus.py` / `test_cli.py:1797-1936`.

## The three real design decisions (for the interview / PRD)

1. **Split mechanism — separate frozen file vs. a marker field.** The card and the leakage
   gotcha (`issue.md:57-63`; agent gotcha #1) favor a **physically separate frozen file**
   (`detector_corpus_holdout.jsonl`) because the existing whole-corpus path
   (`cli.py:1527,1570,1604`) can never accidentally score it. A `split`/`held_out` field on
   `FailureCase` is back-compat-safe (default) but requires filtering at *every* corpus load
   site or held-out cases leak. **Leaning: separate file.**
2. **How the held-out set is populated given only 23 cases.** Carving cases out of the tiny,
   class-imbalanced corpus (`missing_index`=9, most classes =1; gotcha #6) shrinks training/eval
   and can empty whole classes. Options: (a) curate a *distinct* held-out set of new/reserved
   cases; (b) reserve a documented subset by `case_id`. Must not assume balanced per-class support.
3. **What "regression" means — the guard's comparison basis.** Roadmap acceptance names both a
   **threshold floor** ("scores above a threshold") and a **delta** ("a change that *lowers*
   accuracy"). Likely a committed baseline (floor number and/or a baseline snapshot) that the
   guard compares against, with a non-zero exit + clear message on drop. Decide: floor only,
   delta-vs-baseline only, or both; and the tolerance.

## Guardrails honored / scope flags

- **Layer 2** (verification/eval infra), founder's-edge engineering — no drift toward Layer 1.
- **Honest scope:** this slice scores the **labeled failure-class detector corpus only**.
  Folding in the WARN-capped, unlabeled C1 concordance / C3 plausibility signals is a **later
  slice** needing its own labeling design — explicitly out of scope here (`issue.md:46-64`).
- Deterministic, local, no network in tests; committed eval data stays reproducible
  (snapshots pin `corpus_sha`).

## Contradiction / caveat surfaced

The roadmap prose ("fold C1–C5 outcomes into one accuracy number", `CAPABILITY_ROADMAP.md:402`)
over-reaches: concordance/plausibility are corroboration signals with no ground truth, so they
cannot enter a classification-accuracy guard. The PRD must scope to the labeled corpus and name
the unified-number version as future work — not paper over the gap.
