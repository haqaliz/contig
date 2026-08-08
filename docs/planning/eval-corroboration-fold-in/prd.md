# PRD: Fold verification signals into the C6 eval loop (verify-guard)

- **Slug:** `eval-corroboration-fold-in`
- **Type:** feat — `feat/eval-corroboration-fold-in/aliz`
- **Source:** docs/planning/_card/issue.md (contig-next handoff brief); understanding at
  docs/planning/eval-corroboration-fold-in/understanding.md
- **Status:** Draft (Phase 3/4 of contig-begin-fast) — pending review gate

---

## Problem Statement

The C6 eval flywheel ships two regression guards: `contig eval-guard` (held-out
detector-classification accuracy, baseline 0.923 over 13 cases) and `contig
heal-guard` (self-heal loop outcome-match rate, baseline 1.0 over 20 scenarios).
Both measure the *failure-and-fix* side of the moat. The **verification** side —
the C1 cross-tool concordance checks, the C3 biological-plausibility packs, the
structural and annotation checks — is produced into `RunRecord.qc_results` and
reduced to a verdict, but **nothing measures whether the verification rules are
right**, and nothing improves them.

The consequence is concrete, not abstract: **every C1/C3 slice ships its bands
as "uncalibrated engineering defaults" and defers calibration "until bands are
calibrated on real data"** (count_concordance.py thresholds, somatic site-overlap
band, germline WES-safe FAIL bands, sex-check bands, annotation plausibility
bands, rule-pack WARN bands — at least a dozen deferral sites). There is no
instrument that would make a band change *measurable*: no labeled corpus of
verification outcomes, no guarded accuracy number, no human-correction channel.
Calibration is deferred indefinitely by design.

The C6 fold-in — folding C1/C3/annotation corroboration signals into the eval
loop — has been the single capability the roadmap still marks pending, deferred
across five sites, all naming the same blocker: *"the signals carry no
ground-truth labels, so they need a labeling design"*
(CAPABILITY_ROADMAP.md C6; FEATURES.md C6 row;
docs/planning/eval-holdout-guard/prd.md:117-121;
docs/planning/self-heal-eval-guard/prd.md:32-36;
docs/planning/annotation-m5-surface/prd.md:240-243).

The dig (understanding.md) confirms the blocker is structural, not cosmetic:
`QCResult` (models.py:67-82) has no label field; the guards are
classification-shaped (corpus.py:76, heal.py:216-238); and no ground truth for
verification signals exists anywhere in the repo. The one existing
verdict→corpus bridge (`qc_verdict_flagged`, self_heal.py:1041-1110) is lossy
(QC summary flattened to prose) and unreachable by concordance (WARN-capped by
contract, can never FAIL).

**This slice ships the labeling design and the instrument.** It does not claim
to calibrate anything; it makes calibration possible and regression-guarded.

## Goals & Success Metrics

1. **A labeled verification corpus exists** — a frozen holdout
   (`verify_corpus_holdout.jsonl`) seeded with synthetic cases spanning the
   signal families, each with an expected verdict label, plus a growing golden
   corpus fed by real runs through a human promote channel.
2. **A guarded number exists** — `contig verify-guard` re-derives each case's
   verdict under the *current* rules and guards the agreement rate against a
   committed baseline, wired into CI after eval-guard/heal-guard.
   - *Success metric:* guard passes on the committed seed baseline; a
     deliberately perturbed band must move the guarded number (mutation
     control), i.e. the guard is **band-sensitive** — this is what separates it
     from a tautology.
3. **A human-correction channel exists** — real WARN/FAIL runs capture pending
   verification cases; `contig verify-case-promote` confirms/corrects the
   expected verdict and moves them into the golden corpus.
   - *Success metric:* a promote round-trip works end to end (capture → promote
     → golden → guard corpus unchanged by design, training corpus grows), and
     the five historical deferral records are updated from "blocked on labeling
     design" to shipped.
4. **Incidental fix in scope** — dashboard `FAILURE_CLASSES` covers all 18
   `FailureClass` literals so the existing relabel UI can label every class.
   - *Success metric:* `FAILURE_CLASSES.length == 18`, relabel of
     `reference_not_bgzf` / `missing_dependency` / `disk_full` /
     `download_failed` / `permission_denied` succeeds through the UI route.
5. **The one countable outcome signal that exists pre-revenue:** the **first
   field-labeled case promoted through the channel** (a real run's WARN/FAIL
   verdict confirmed or corrected via `verify-case-promote`) is a named
   milestone within this slice. Everything else here is honestly a conformance
   assertion (guard passes, round-trip works) — this milestone is the single
   datapoint that makes the corpus non-tautological, and it is called out as
   such rather than buried.

## User Personas & Scenarios

- **The founder (only current user).** Pre-revenue; every eval slice so far is
  push, not demand-pull — this one is no exception and must say so. The persona
  is a full-stack engineer auditing whether the verification bands are sane and
  regress-guarding them before release.
  - Scenario: after a release that touches a rule pack, `verify-guard` in CI
    either passes (bands still agree with the labeled corpus) or names the
    drifted cases. Before, a band change was a silent judgement call.
- **Future reviewer (core-facility persona, later).** A WARN/FAIL run lands in
  pending verification cases; the reviewer confirms or corrects the verdict
  ("this FAIL was a broken run" vs "this FAIL was a false alarm — band too
  strict"). Each correction is a labeled datapoint that makes the next band
  change measurable.

## Requirements

### Must-have

**R1 — Labeling design (the "labeling design" the five deferrals name).**
A new `VerificationCase` model: `case_id`, `description`, `source`
(`"synthetic"` | `"pending:{run_id}"` | `"confirmed:{run_id}"`), `assay`,
`inputs` (the **pre-band** signal values the verdict was derived from — the
metric/check inputs, not the statuses), and `expected_verdict`
(`pass|warn|fail|unverified`) — the human-confirmed correct verdict.

- **Verdict-level labels** (confirmed with founder): a reviewer judges the
  *verdict*, not per-check statuses. Per-case `inputs` may name the driving
  check(s) for provenance, but the label is one verdict.
- **The threshold-sensitivity contract (anti-tautology).** The guard must
  re-derive statuses from `inputs` under the *current* bands, never from stored
  statuses. A case whose stored value crosses a changed band must flip status.
  Pinned by a mutation test in the guard's own suite.
- **Honest scope, stated on the model:** the first corpus is synthetic and
  self-graded (we author the fixtures we grade — same disclosure as every prior
  eval slice); the corpus only becomes non-tautological as real runs feed it.

**R2 — Seeded holdout corpus.** `src/contig/data/verify_corpus_holdout.jsonl`
with synthetic cases covering at least: germline plausibility (Ti/Tv, het/hom,
variant-count bands), RNA-seq plausibility + composition, somatic plausibility
(VAF/count/swap), single-cell cell-QC, annotation plausibility, concordance
status derivation (pass/warn/unverified boundaries), and verdict reduction
(an informational-only list reduces to unverified, a FAIL check drives FAIL).
Every case carries a description stating what it pins. `source="synthetic"`,
ids prefixed `verify-`, disjoint from any other corpus.

- **R2a — The corpus must contain at least one known-miss fixture**: a case
  whose expected verdict the *current* rules get wrong (eval-guard's
  `qc_anomaly` miss precedent, holdout_baseline 0.923 not 1.0). The committed
  `verdict_match_rate` baseline must therefore be **< 1.0**, and the guard's
  first demonstration of liveness is that it flags this case as a MISS. A 1.0
  baseline over self-authored fixtures would read as a frozen tautology
  regardless of intent.

**R3 — `contig verify-guard`.** Sibling of eval-guard/heal-guard, reusing the
holdout.py/heal.py/snapshot_history.py pattern:

- Scores the current verification rules over the frozen holdout by re-deriving
  each case's verdict from `inputs` and comparing to `expected_verdict`.
- Reports a **guarded** `verdict_match_rate` plus **informational** per-family
  rates (by assay / by signal kind) — informational never guarded.
- Committed baseline `src/contig/data/verify_baseline.json` (one object:
  timestamp, corpus_size, corpus_sha, verdict_match_rate, per-family,
  contig_version), `--update-baseline` (rewrite + append history),
  `--snapshot` (append only), `--history` (trend).
- Regression → exit 1 naming the diverging case ids; sha/detector-version
  mismatch → loud warnings, non-failing (eval-guard precedent).
- Wired into `.github/workflows/ci.yml` after `heal-guard`.

**R4 — Capture channel (real runs).** At finalize, a run whose verdict is
`fail` or `warn` (and only those — the signals a human can judge) appends a
pending `VerificationCase` to `<runs_dir>/pending_verify_corpus.jsonl`
(`source="pending:{run_id}"`, `expected_verdict=null` until promoted) built
from **pre-band metric inputs**, not from stored QC statuses.

- Always on, no flag (precedent: qc_anomaly corpus capture is always on —
  volunteers-only corpus, no side effect to gate).
- **R4a — Slice-1 capture is bounded to the metric-dict families** (the
  rule-pack plausibility evaluators + verdict reduction), whose pre-band input
  shapes already exist. **Concordance-family capture is deferred to a named
  follow-on**: the dig showed those evaluators act on matrices/VCFs and have no
  pre-band input shape today (a signal-level re-derivation seam would be a
  separate design). Stated here, not decided in the plan — so R4 cannot balloon.
- The pre-band inputs require an **additive, optional** capture seam on the run
  record (back-compat: old bundles load unchanged).

**R5 — `contig verify-case-promote`.** CLI sibling of `corpus-promote`:
confirm or correct `expected_verdict` on a pending case, dedupe against golden,
rewrite `source` `pending:` → `confirmed:`, append to
`src/contig/data/verify_corpus.jsonl` (golden), remove from pending, and
auto-snapshot a full-corpus score to `verify_history.jsonl` (corpus-promote
precedent, cli.py:2403-2416). Dashboard UI for verification review is out of
scope slice 1 (CLI-only).

**R6 — FAILURE_CLASSES completeness.** Add the five missing literals
(`reference_not_bgzf`, `missing_dependency`, `disk_full`, `download_failed`,
`permission_denied`) to `dashboard/lib/derive.ts` `FAILURE_CLASSES` so the
pending-review relabel route (route.ts validates against it) accepts all 18.
Tests pin `18` and a relabel round-trip for a previously-missing class.

### Should-have

**R7 — `contig verify-eval`** (informational): score the verification rules
over the *golden* corpus (not just the frozen holdout), reporting per-family
rates — the analogue of `eval-detector`. Never guarded.

**R8 — Deferral-record updates**: the five historical "blocked on labeling
design" sites (CAPABILITY_ROADMAP.md C6 summary + C7 M5 line, FEATURES.md C6
row, the two planning PRDs) restate the fold-in as shipped-with-honest-scope.

### Nice-to-have

**R9 — Dashboard trend card** for `verify_history.jsonl` under `/eval`
(holdout-history.tsx / heal-history.tsx precedent).

## Technical Considerations

- **Where it sits:** pure Python in `src/contig/` — a new module in the
  holdout/heal mould (e.g. `verification/verify_corpus.py` + CLI wiring in
  `contig.cli`), new models in `models.py` (additive/optional fields only),
  data files under `src/contig/data/`, capture at the `_finalize` /
  `_discover_qc` boundary in `runner.py` + `self_heal.py`.
- **Guard plumbing is copy-paste-ready** (holdout.py, heal.py,
  snapshot_history.py:21-39); snapshot history is already generic over the
  snapshot model. Follow the exact `--update-baseline` / `--snapshot` /
  `--history` semantics, sha pinning, and the "baseline backed by a recorded
  trend point" test pattern (test_snapshot_history.py:110/:144).
- **Back-compat invariants that must not break:** the 0.923 hard-pin
  (test_qc_anomaly_capture.py:165), bare-guard strings
  (test_guard_trend.py:187/:363), eval/holdout/heal baselines and histories
  byte-stable. A sibling guard must not touch them. New snapshot fields must
  default (the `detector`/`informational` back-compat idiom).
- **Reproducibility/verification impact:** the capture seam writes no signed
  bytes (pending corpora are never signed); golden `verify_corpus.jsonl` is a
  corpus data file, not a run bundle. No `RunRecord` signed-field change is
  intended; if one becomes necessary it must be flagged at review (signature
  break precedent).
- **No network, no real nf-core in CI.** Synthetic fixtures and injected
  seams only (standing rule).

## Risks & Open Questions

- **Tautology risk (the big one).** Verification checks are deterministic code;
  a corpus we write scored against our own bands is self-graded. Mitigations:
  (1) the threshold-sensitivity contract with a mutation control proves the
  guard is alive; (2) **R2a's known-miss fixture forces the committed baseline
  below 1.0**, so the guard demonstrably flags a real defect from day one;
  (3) the real-run capture channel is the only path to non-tautological data,
  and it is honest about being empty pre-revenue — the first promoted
  field-labeled case (metric 5) is the countable turning point; (4) the
  honest-scope statement on the model. If the slice cannot meet (1) or (2),
  the fallback is informational-only (recovery_rate precedent) — but the PRD
  commits to the full guard.
- **Per-family input-shape seam.** Bounded by R4a: slice-1 capture covers only
  the metric-dict families; concordance-family capture is a named follow-on.
  The guard's holdout corpus is unaffected (synthetic input shapes are authored
  with the fixtures).
- **Organic frequency pre-revenue.** Concordance flags only fire when a user
  passes the flags; plausibility fires on every run. Capture volume is tiny and
  the pending corpus will be mostly empty for a while — stated, not hidden.
- **Open:** should the pending verification corpus live under `runs/` (like
  `pending_corpus.jsonl`) or `src/contig/data/`? (Plan decision, default:
  `runs/` for pending, `src/contig/data/` for golden + holdout — matches the
  existing corpus split.)

## Out of Scope

- **Band calibration itself** — this slice builds the instrument; tuning bands
  against the corpus is future work (and the reason the instrument exists).
- **Per-check (signal-level) labels** — verdict-level only (confirmed with
  founder).
- **Dashboard pending-review UI for verification cases** — CLI-only promote in
  slice 1; R9 trend card is the only dashboard surface.
- **C1 "corroborated by" dashboard line** — the annotation one ships
  (annotation_surface.py); generalizing to C1 is a separate slice.
- **qc_anomaly remediation** — still a separate, larger design question
  (qc-anomaly-verdict-trigger/prd.md:340-342).
- **Layer 1, clinical claims, raw-read egress** — standing guardrails; this
  slice is pure eval machinery over existing verdict signals.

## Data Model (draft)

```python
class VerificationCase(BaseModel):
    case_id: str            # "verify-<n>" (synthetic) or "<run_id>-verify" (run)
    description: str        # honesty note: what the case pins
    source: str             # "synthetic" | "pending:<run_id>" | "confirmed:<run_id>"
    assay: str | None       # variant_calling | rnaseq | scrnaseq | somatic_variant_calling | ...
    inputs: dict            # pre-band signal values (per-family shape, defined in plan)
    expected_verdict: Literal["pass","warn","fail","unverified"] | None = None  # None until promoted
```

Snapshot: `VerifySnapshot` mirroring `EvalSnapshot`/`HealSnapshot` with
`verdict_match_rate` (guarded) + per-family rates (informational).

## Proposed Aspect Decomposition (for tech-plan)

1. `verify-core` — VerificationCase model, seed holdout corpus, re-derivation
   scorer (threshold-sensitivity contract + mutation control).
2. `verify-guard-command` — CLI guard, baseline/history/refreeze, CI wiring,
   back-compat tests.
3. `capture-promote` — run-record input capture seam, pending capture,
   `verify-case-promote`, golden corpus.
4. `failure-classes` — dashboard FAILURE_CLASSES 18/18 + tests (small, could
   fold into another aspect).

## Guardrails Check

Layer 2 (eval machinery over verify signals) ✓ · no Layer 1 ✓ · founder's edge
✓ · gets better as base models improve ✓ (better adjudication of disagreements
makes labels more accurate and bands better calibrated — never redundant) ·
push, not demand-pull — stated.
