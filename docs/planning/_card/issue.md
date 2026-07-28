# Card: feat / qc-anomaly-verdict-trigger

- **Type:** feat
- **Id/slug:** qc-anomaly-verdict-trigger
- **Owner:** aliz
- **Branch:** feat/qc-anomaly-verdict-trigger/aliz
- **Source:** inline brief (no GitHub issue — `gh issue list` returns "No Issues") — carried
  from the `/contig-next` recommendation (2026-07-28), the next slice after the somatic
  swapped-pair smell test merged.

## Brief

Close `qc_anomaly`, the last structurally unreachable `FailureClass` (it exists only in
`src/contig/models.py:279`, the held-out fixture, and a `src/contig/cli.py:2683` docstring —
**no `detect.py` branch, no `repair.py` branch**), by making the QC verdict an input to the
self-heal loop.

Today `self_heal_run` (`src/contig/self_heal.py:925`) only reacts to a **non-zero exit**, so
a run that completes green while `_finalize` reduces to **FAIL** — a real outcome since the
germline Ti/Tv, het/hom, variant-count and somatic empty-call-set FAIL floors shipped — is
never diagnosed, never enters the loop, and exits 0 unless `--fail-on-verdict`.

Dig carefully into the **two possible triggers** before choosing: the held-out fixture
`holdout-qc-anomaly-1` is *pipeline-step* shaped (a `MULTIQC_QC_GATE` FAILED event +
third-party "QC gate rejected the run" log text), while the product-real trigger is Contig's
own **verdict object** at `_finalize` — so scoring 13/13 on `eval-guard` needs a log-text
branch whose needles are foreign text nothing constrains, the same first-party-uniqueness
trade the `no_progress` slice took and recorded as residual risk.

Expect **no genuine repair** for most cases (an honest diagnosed give-up, not a dressed-up
recovery), guard against retrying a deterministic FAIL in a loop, change **no default exit
code**, and state plainly that any `eval-guard` move (0.923 → 1.0) is **partly self-graded**.

## Why (moat + shipped state)

- **The last structurally unreachable failure class, and the docs name it as needing its own
  slice.** `docs/technical/CAPABILITY_ROADMAP.md:1074` — *"`qc_anomaly` remains the one
  structurally unreachable class — this slice did not close it and must not be read as having
  done so; its honest trigger is the verdict object, not log text (QC runs at `_finalize`, not
  as a pipeline step), so it needs its own slice."*
- **It closes the one place where verify does not feed self-heal.** The verdict is today an
  output only. A run that finishes green while `_finalize` reduces to FAIL — real per the
  germline FAIL bands (`CAPABILITY_ROADMAP.md:585`) and the somatic empty-call-set floor
  (`:871`) — is never diagnosed. That silent-success shape is exactly what the moat exists to
  kill (`CLAUDE.md` constraint #2), and it makes the verdict an *input* to the loop.
- **Measurable against a frozen baseline.** `holdout-qc-anomaly-1` has been misclassified in
  **all seven** recorded trend points (`src/contig/data/holdout_history.jsonl` — `qc_anomaly`
  `predicted: 0`, `recall: 0.0`, v0.22.0 → v0.48.0). `eval-guard` would move 0.923 → 1.0
  (13/13); `heal-guard` `covered_classes` 6 → 7.

## KNOWN CAVEAT — two different doors, only one of them honest (pin FIRST in the dig)

The held-out fixture and the product-real trigger are **not the same thing**:

- `src/contig/data/detector_corpus_holdout.jsonl` → `holdout-qc-anomaly-1` is *pipeline-step*
  shaped: `events: [{process: "MULTIQC_QC_GATE", status: "FAILED"}]` plus
  `log_text: "QC gate rejected the run: MultiQC duplication-rate metric (92%) breached the
  assay's QC anomaly threshold."` — i.e. a **third-party QC gate inside someone else's
  workflow**.
- Contig's own trigger is the **verdict object** at `_finalize` — no log text, no failed
  process, exit code 0.

So **scoring 13/13 requires a log-text branch whose needles are foreign text nothing
constrains** — the exact first-party-uniqueness trade the `no_progress` slice took knowingly
and recorded as unenforced residual risk (`CAPABILITY_ROADMAP.md:370`). Decide deliberately
which door(s) this slice opens, and **do not let the eval number drive the detector rule**.

## Honest contract (constraints this slice must not break)

- **There is often no repair.** Bad biology is not retryable. The honest terminal outcome is a
  **diagnosed give-up**, mirroring the frozen `tool-crash-giveup` scenario — never a
  dressed-up recovery.
- **No retry loop over a deterministic FAIL.** A verdict that will re-derive identically must
  not be re-attempted; whatever bound is chosen must provably terminate.
- **No default exit-code change.** v0.36.0 made FAIL → exit 1 **opt-in** via
  `--fail-on-verdict` (`docs/planning/verdict-exit-code/`); this slice must not silently
  reroute that.
- **Partly self-graded, stated as such.** We would be making reachable a class whose held-out
  fixture we wrote ourselves — the same critique the `no_progress` slice recorded about
  itself. It evidences that a documented taxonomy gap closed; nothing more.
- Test-first, no real nf-core run in CI, no new dependency unless argued.

## Shipped precedents to mirror

- **`docs/planning/stall-watchdog-no-progress/`** — the closest precedent: the previous slice
  that made an unreachable class reachable (`no_progress`), including its detector-branch
  needle discipline, its ordering decision in `detect.py`, and its residual-risk record.
- **`docs/planning/verdict-exit-code/`** — the `--fail-on-verdict` opt-in exit-code wiring;
  the boundary this slice must respect.
- **`docs/planning/eval-holdout-guard/`** — `contig eval-guard`, the frozen held-out corpus,
  and the `--update-baseline` refreeze-as-a-deliberate-act convention.
- **`docs/planning/self-heal-eval-guard/`** — `contig heal-guard`, `heal_scenarios.jsonl`, and
  the outcome-match-vs-recovery-rate distinction.

## Deferred (name in PRD, out of scope unless the dig argues otherwise)

- Folding the unlabeled C1 concordance / C3 plausibility corroboration signals into one eval
  number (blocked on a labeling design — `CAPABILITY_ROADMAP.md:1024`).
- Any dashboard card for the new class.
- Band calibration of any QC threshold (this slice adds no new bands).
- Any Layer-1 (NL → workflow) surface.
