# PRD: eval-holdout-guard (C6 slice 1 — held-out split + regression guard)

Status: draft for review. Owner: aliz. Branch: `feat/eval-holdout-guard/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff brief), `_card/understanding.md`
(Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md` §C6 (lines 390-414), `docs/ROADMAP.md:168`.
Capability: **C6 — eval flywheel as a continuous loop, slice 1 of N.**

## Problem Statement

Contig's diagnosis detector (`diagnose_failure`, the `rules` detector) is the front of the
self-heal loop: it classifies a failure into a `FailureClass`, which drives every downstream
repair. Its quality is measured by `contig eval-detector`, which scores the detector against
the **entire** labeled corpus (`src/contig/data/detector_corpus.jsonl`, 23 `FailureCase`s) and
reports an exact-match accuracy (`corpus.py:50-104`, `cli.py:1485-1553`).

Two gaps make that measurement unable to *protect* accuracy over time:

1. **No held-out set.** Every case the detector is scored on is also a case an author can look
   at while tuning the rules, so the accuracy number can be inflated by fitting to the same
   cases it is judged on. There is no reserved set the detector has not been tuned against.
   (Confirmed: "held-out" exists only as a to-build in `CAPABILITY_ROADMAP.md:404-407` and
   `ROADMAP.md:168`; no split/tag/exclusion anywhere in `corpus.py`/`cli.py`.)
2. **No regression guard.** Nothing fails a build when a corpus edit or a detector change
   *lowers* accuracy. A well-meant rule tweak that fixes one class while breaking another can
   ship silently. `CLAUDE.md`'s "moat #2" — accumulated evaluation data that compounds — stays
   an assertion, not a measured, defended invariant.

**Evidence it's real & why it's the moat.** `CLAUDE.md`: the moat is "execution / verification
/ reproducibility infrastructure **+ accumulated workflow-evaluation data**." C6 is that data
turned into a measured loop so every shipped verdict compounds instead of drifting. It is
strictly **Layer 2**, inside the founder's engineering edge, and gets *better* as base models
improve — the pluggable detector registry (`rules`/`rules-strict`/`llm`, `detect.py:585-614`)
plus a held-out benchmark is exactly what lets a better diagnoser be **proven** better rather
than asserted (`CLAUDE.md` constraint #3; model-swap harness already shipped, `FEATURES.md:225`).

## Goals & Success Metrics

- **G1 — A frozen, non-leaking held-out set exists.** A new committed
  `src/contig/data/detector_corpus_holdout.jsonl` of newly authored synthetic cases, distinct
  from the training corpus. *Metric:* a test asserts the held-out `case_id`s and the training
  `case_id`s are disjoint, and that no existing whole-corpus command reads the held-out file.
- **G2 — A guard command scores the current detector against the held-out set.** *Metric:* a
  test invokes the command and gets a `DetectorEvalReport`-backed accuracy over exactly the
  held-out cases (reusing `evaluate_detector`, not a reimplementation).
- **G3 — The guard flags a regression (non-zero exit).** Given a committed baseline accuracy,
  the guard exits non-zero when the current detector scores **below** baseline (minus a small
  float tolerance), and exits zero when it meets/exceeds baseline. *Metric:* the roadmap's
  test-first acceptance verbatim (`CAPABILITY_ROADMAP.md:409-411`): a frozen held-out set; a
  known-good detector (`rules`) scores above the threshold → exit 0; a deliberately worse
  detector → exit 1 flagged as a regression.
- **G4 — Reuse, not rebuild; no regression, no network.** The guard calls the existing
  `evaluate_detector` / `get_detector` / `EvalSnapshot` machinery. The full suite stays green;
  the guard is pure local file parsing on deterministic detectors (never `llm` by default).

## User Personas & Scenarios

- **The maintainer (founder, persona A-adjacent — the developer of Contig):** edits a detector
  rule or promotes a new corpus case, runs the guard (locally and in CI), and is told
  immediately if diagnosis accuracy on the reserved set dropped — before it ships to a design
  partner's real runs.
- **A design partner / buyer (persona C/D, indirectly):** benefits because the guard is a trust
  signal — "our failure-diagnosis accuracy is measured against a held-out benchmark and cannot
  silently regress." It is not a surface they operate directly in this slice.

## Requirements

### Must-have (this slice)

- **R1 — Frozen held-out corpus file.** `src/contig/data/detector_corpus_holdout.jsonl`, same
  `FailureCase` schema (`models.py:358-366`), newly authored synthetic cases covering the major
  failure classes present in the training corpus (at minimum: `oom`, `time_limit`,
  `missing_index`, `bad_param`, `container_pull_failed`, `tool_crash`, `qc_anomaly` — the
  classes with live repair paths). `source` prefix = `holdout:` (a new source-kind, parallel to
  `synthetic:`/`live:`/`confirmed:`), so provenance is self-describing and greppable.
- **R2 — Held-out loader.** A thin helper that loads the held-out file via the existing
  `load_corpus` (`corpus.py:40-47`) from a `default_holdout_path()` (mirrors
  `default_corpus_path`, `corpus.py:28-30`). No new parsing.
- **R3 — Committed baseline.** A committed baseline artifact recording the held-out accuracy
  the guard defends, plus the held-out corpus sha and the detector it was measured with — so a
  drop is attributable to a detector change vs a held-out-set change. Prefer reusing the
  `EvalSnapshot` shape (`models.py:397-414`, already carries `accuracy`, `corpus_sha`,
  `per_class`, `detector`, `contig_version`) written to a single committed
  `src/contig/data/holdout_baseline.json` (one snapshot, not a JSONL trend).
- **R4 — Guard command.** A new Typer command (working name `contig eval-guard`) that: loads
  the held-out set, resolves the detector (`get_detector`, default `rules`), runs
  `evaluate_detector`, compares accuracy to the baseline (fail if `accuracy < baseline - tol`),
  prints a clear PASS/REGRESSION line naming the delta and any newly-missed classes, and
  **exits non-zero on regression**. Mirrors the option/guard/render style of the sibling
  `eval-detector`/`coverage`/`clusters` commands (`cli.py:1485,1556,1590`). Options at least:
  `--detector`, `--holdout` (path override), `--baseline` (path override), `--tolerance`,
  `--json`.
- **R5 — Baseline (re)freeze path.** An explicit, opt-in way to (re)write the baseline after an
  intentional, reviewed accuracy change (e.g. `--update-baseline`), so freezing is a deliberate
  committed act, never an automatic side effect of running the guard.
- **R6 — Determinism & leakage safety.** The held-out file is loaded **only** by the guard;
  `eval-detector`/`coverage`/`clusters` continue to load only the training corpus (a test pins
  this). Guard runs on deterministic detectors; `llm` is never the default and requires explicit
  opt-in. No network in tests.

### Should-have

- **S1 — Per-detector baselines.** Allow a baseline per detector name (so `rules` vs
  `rules-strict` each have a defended number) rather than a single global baseline. Slice-1 may
  ship a single-detector baseline (`rules`) and treat multi-detector as a fast follow.
- **S2 — Guard wired into the project check surface** (CI / a `make`-style target) so it
  actually runs on every change — otherwise it's a guard nobody invokes (see Risk R-b).

### Nice-to-have

- **N1 — Per-class regression detail** in the output (which class's recall fell), beyond the
  headline accuracy delta.
- **N2 — A `--snapshot` of each guard run** appended to a held-out history, mirroring
  `eval-detector --snapshot`, to trend held-out accuracy over time.

### Explicitly out of scope

- **Folding in C1 concordance / C3 plausibility outcomes.** Those are WARN-capped corroboration
  signals **without ground truth**; they cannot enter a classification-accuracy guard. The
  roadmap's "one accuracy number over C1–C5" (`CAPABILITY_ROADMAP.md:402`) is a **later slice**
  needing its own labeling design. This slice scores the **labeled failure-class detector
  corpus only.**
- **Self-heal (end-to-end repair) accuracy.** The guard measures **detector classification**
  accuracy, not whole-loop repair success. Repair-outcome scoring is future C6 work.
- **Auto-refreshing / auto-growing the held-out set** from live runs. The held-out set is
  hand-frozen this slice; promotion of real cases into it is future work (and must preserve the
  no-leak invariant).
- Any Layer-1 workflow-authoring surface (guardrail, `CLAUDE.md`).

## Technical Considerations

- **Reuse map (do not rebuild):** `load_corpus`/`default_corpus_path` (`corpus.py:28-47`),
  `evaluate_detector` → `DetectorEvalReport` (`corpus.py:50-104`, `models.py:387-394`),
  `get_detector`/`DETECTORS` (`detect.py:585-614`), `EvalSnapshot` +
  `snapshot_from_report`/`append_snapshot`/`load_history` (`models.py:397-414`,
  `eval_history.py:22-66`), `sha256_file` (`models.py:17`), Typer command patterns
  (`cli.py:1441-1553`).
- **New source-kind `holdout:`** must be handled by `_source_kind` (`corpus.py:282-288`) so
  coverage/provenance tooling classifies held-out cases correctly if ever surfaced.
- **Back-compat:** no new required field on `FailureCase`. The chosen design (separate file,
  not a marker field) means the shipped `detector_corpus.jsonl` is untouched — zero migration.
- **Reproducibility/verification impact:** the baseline pins `corpus_sha` of the held-out file
  (`sha256_file`), so "accuracy dropped" is attributable to detector vs held-out change; the
  guard is deterministic and re-runs identically. This deepens moat #2 without touching the
  run/verify path a user sees.
- **CLI naming:** confirm `eval-guard` vs `eval-detector --guard` in tech-plan; leaning to a
  distinct command because a guard's defining behavior (non-zero exit for CI) differs from the
  reporting `eval-detector`.

## Risks & Open Questions

- **R-a — Tiny/imbalanced held-out set → noisy accuracy.** Mitigation: author enough cases to
  cover the live-repair classes with ≥1 each and enough total that a single miss is a
  meaningful, intended signal; document the intended count in the plan.
- **R-b — A guard nobody runs.** If not wired into CI/a check target (S2), it won't defend
  anything. Open question: is wiring into CI in-scope for this slice or a fast follow? (Leaning:
  land the command + tests this slice, wire CI as S2 within the same PR if cheap.)
- **R-c — Baseline staleness / who freezes it.** The `--update-baseline` act must be deliberate
  and reviewed (it's committed data). Open question: should the guard *warn* when the held-out
  sha differs from the baseline's recorded sha (set changed but baseline not refreshed)?
  (Leaning: yes — a mismatched sha should be a loud warning, not a silent pass.)
- **R-d — Per-detector baseline (S1).** Single global baseline is simplest but conflates
  detectors. Decide in tech-plan whether slice-1 ships single (`rules`) or per-detector.

## Out of Scope

See "Explicitly out of scope" above. In one line: no unlabeled-signal folding, no repair-loop
accuracy, no auto-growing the set, no Layer 1.
