# PRD — `repair-success-analytics` (`contig repair-stats`)

Phase 3/4 output. Inputs: `docs/planning/_card/issue.md` (brief) and
`docs/planning/repair-success-analytics/understanding.md` (dig, verified first-hand
against the code and the 15 real run records). Every factual claim below carries a
`file:line`; nothing is asserted from memory.

---

## Problem Statement

`docs/ROADMAP.md:109` makes **"≥70% unattended completion on the core pipeline"** a
Phase 1 → Phase 2 exit gate, and `docs/ROADMAP.md:101` repeats it as a success metric.
`CAPABILITY_ROADMAP.md` (C2) calls unattended-completion rate "the headline reliability
metric". **No command in the CLI can compute it.** `contig clusters` (`cli.py:3673`) and
`contig coverage` (`cli.py:3707`) aggregate the *labeled failure corpus*; nothing
aggregates `repair_history` across runs.

`FEATURES.md:216` names the gap precisely — *"Repair success-rate analytics … Built data
(the `patch_applied` slice supplied the missing field …); **cross-run aggregation still
to build**"*.

Several recent slices also committed to **revisit triggers that are counted by hand**
today — e.g. `CAPABILITY_ROADMAP.md:617`: *"counted by grouping
`runs/pending_corpus.jsonl` by `failure_class`, **no new instrumentation**"*. This slice
makes those triggers checkable with a command instead of a Python one-liner.

**Who has the problem:** the founder/maintainer, sequencing the roadmap and honouring
committed revisit triggers. This is **not** an end-user feature, and the PRD does not
pretend otherwise.

## Goals & Success Metrics

1. `contig repair-stats` reports, across a runs directory: per-outcome-family counts,
   per-failure-class counts, and an **unattended-completion rate** with its denominator
   stated.
2. The command is **correct on today's data** — meaning it does not report the two real
   `patched_and_retried` steps as "not applied" (the naive failure, see R1), and does not
   count the vacuously-green zero-event run as an unattended success (see R3).
3. Every number is accompanied by enough context to be discarded: derived-vs-read counts
   separated, not-analyzable runs disclosed, thin-data flagged.

**Non-metric:** this slice does not aim to *move* the unattended-completion number. It
recovers nothing for a user. It makes an existing, unmeasured number legible.

## Scope decisions taken in the interview

| Decision | Chosen |
|---|---|
| Legacy `patch_applied` | **Three-state, derive legacy** from the outcome literal, counted separately |
| Headline output | **Breakdown + guarded rate**, zero-event runs excluded as not-analyzable |
| Fixture/scratch runs | **Count all, classify + disclose** — no name-based policy invented |
| Command name | **`contig repair-stats`** |

## Requirements

### Must-have

- **R1 — Three-state applied, read from raw JSON.**
  `models.py:322` declares `patch_applied: bool = False` (**not** `bool | None`), so
  pydantic fills `False` for every pre-v0.49.0 record and the loaded model cannot
  distinguish *absent* from *false*. Measured: **0 of 7** real repair steps carry the key,
  including two `patched_and_retried` steps that are definitionally enacted.
  The classifier therefore inspects **key presence in `run_record.json`**, yielding
  `applied` / `not_applied` / `legacy_derived`, and never collapses the three into one
  percentage.
  - For a `legacy_derived` step, applied-ness is derived from the outcome literal using
    the shipped family map (R2). The pre-field record set is **frozen**, so the map cannot
    silently rot — which is why the `patch-applied-field` slice's objection to a derived
    map (`CHANGELOG.md:869-876`: a hand-maintained map "would silently default a later
    literal to not-applied") does not apply here. State that reasoning in the code.
  - Derived counts are reported **separately from** read counts in both text and JSON.

- **R2 — Agree with the shipped five-family grouping, not the prose.**
  `FEATURES.md:216` says "auto-healed vs paused vs gave-up" (three) and
  `docs/planning/repair-patch-applied/dashboard-repair-surface/spec.md` says three. The
  **shipped** dashboard (`dashboard/components/run/repair-timeline.tsx:86-192`) has
  **five** families over 19 literals: `APPLIED` (7), `DECLINED` (3), `GAVE_UP` (7),
  `FLAGGED` (1 — `qc_verdict_flagged`), `ACKNOWLEDGED` (1 —
  `advisory_acknowledged_and_retried`). The CLI mirrors the shipped five.

- **R3 — Two orthogonal axes, never collapsed.** *(Surfaced during drafting; this is the
  requirement most likely to have shipped as a bug.)*
  "Was the patch **enacted**?" and "did a **human** have to act?" are different questions.
  `approved_and_retried` (`self_heal.py:1449`, reached only after `_write_pending_approval`
  at `:1397` and a `poll` returning approve at `:1406`) and `chose_and_retried` (after
  `_write_pending_choice`, `:369`) are both **APPLIED** *and* **attended**.
  - **Attended outcome set (6):** `approved_and_retried`, `chose_and_retried`,
    `rejected_by_user`, `approval_timed_out`, `invalid_choice_rejected`,
    `advisory_acknowledged_and_retried`.
  - `advisory_acknowledged_and_retried` is attended by design — the inert-repairs slice
    attributes that recovery to the human, not the engine.
  - **Unattended completion** = run is analyzable **AND** `RunSummary.succeeded` **AND**
    no attended outcome anywhere in its `repair_history`.

- **R4 — Analyzable-run gate, because green is vacuous at zero events.**
  `models.py:156-158`: `succeeded = (failed_tasks == 0)`, so an empty event list is
  `succeeded=True`. Real example: `testpass` has **0 events**, derives `succeeded=True`,
  and its only repair step is `gave_up`. A run with **no task events** is
  **not analyzable**: excluded from the rate's numerator and denominator, counted in its
  own bucket, and the exclusion stated in the output. No name-based filtering of `_*` or
  `test-*` bundles — that would invent policy the codebase does not define.

- **R5 — Unknown bucket for unmapped literals.**
  `stopped_for_confirmation` is present in real data (`realtest2`), is emitted **nowhere**
  in `src/`, and was **deleted** from the dashboard
  (`repair-timeline.tsx:56`; asserted absent at `dashboard/e2e/repair-truthfulness.spec.ts:128`).
  It must resolve to `unknown`, never be folded into `GAVE_UP` and never be derived to an
  applied-ness. Follow the dashboard's own stated principle
  (`repair-timeline.tsx:194-203`): an unmapped literal "is genuinely unknown to this
  build, so the honest rendering is the raw literal … rather than a guess at which family
  it is."

- **R6 — House shape: pure core + thin Typer shell + text/JSON.**
  Mirror `corpus.py:291 coverage_report(...) -> dict` (a plain dict) with a thin command,
  as `clusters`/`coverage` do. `--runs-dir` (default `"runs"`, matching `cli.py:2717`) and
  `--json`. Enumerate via `workspace.py:39 list_run_ids` / `:26 load_run` — do not re-roll
  directory walking.

- **R7 — Thin-data flag.** Follow `corpus.py:309`'s `_THIN_THRESHOLD` precedent: flag
  classes/families with too little support rather than presenting a rate as settled.

- **R8 — Naming disambiguation is a requirement, not a nicety.**
  `heal.py:250-252` defines `recovered = summary.succeeded and any(s.patch_applied)` and
  `:309-311` turns it into `recovery_rate` — **over synthetic `HealScenario` replays for
  `heal-guard`, never over real runs**, and `CHANGELOG.md:897-901` warns its trend points
  are non-comparable across a definition change. The command's help text and output must
  make clear this is **real runs**, not that number.

### Should-have

- **S1 — Per-failure-class breakdown** keyed on `step.diagnosis.failure_class`, **not**
  `step.failure_class` (absent/None in all 15 real records). Observed today: `oom` ×2,
  `tool_crash` ×3, `missing_index` ×1, `unknown` ×1.
- **S2 — Last-step-wins** for a run's terminal outcome, mirroring `heal.py:253-256` and
  the env-alias-map guard convention.
- **S3 — Honest empty/degenerate output**: a missing runs dir yields `[]` from
  `list_run_ids` (`workspace.py:44`); say "no runs", not "0%".

### Nice-to-have (explicitly deferred)

- `--snapshot` / `--history` trend JSONL. Every recent guard ships one, but those read a
  **frozen committed corpus**; this reads a mutable runs directory, so a trend point is
  not reproducible from committed data. Deferred with that reason recorded.
- A dashboard card.
- Aligning `report.py`'s binary renderer with the new three-state (see Risks).

## Technical Considerations

- **New pure module** `src/contig/repair_stats.py`. `corpus.py` is the wrong home: it
  operates on `FailureCase` corpora (`corpus.py:40,107,247,291`), not `RunRecord`s.
- **Reads raw JSON *and* the validated model.** Unusual for this codebase and worth a
  comment: the model is used for events/diagnosis/outcome, the raw dict **only** for
  `patch_applied` key presence. `bundle.py:67 load_bundle` is
  `RunRecord.model_validate_json`, so the raw read is a second, deliberate read of the
  same file.
- **No model change, no signed-payload change, no new dependency, no signature break.**
  Read-only over existing artifacts — consistent with the "no new instrumentation"
  wording of the revisit trigger this serves.
- **Verified**: all 15 real records load through `workspace.load_run` without a
  `ValidationError`. Malformed-record handling is still required (skip + disclose), but no
  such record exists today.
- **Reproducibility impact: none.** Nothing enters the bundle or the signed payload.

## Risks & Open Questions

- **R-Risk-1 — The first run of this command will look underwhelming, and that is the
  correct behaviour.** With `heal.py`'s formula, today's corpus yields **0 recoveries over
  15 runs**, because `mvp` — the one genuine `patched_and_retried` success — carries no
  `patch_applied` key. R1's derivation is what turns that into a truthful non-zero number.
  The output must be legible enough that a reader sees rigour, not breakage.
- **R-Risk-2 — Deliberate inconsistency with `report.py`.** `report.py:93-101
  _applied_word` reads `patch_applied` **verbatim** and is binary by design ("both states
  are spelled out because silence would read as 'applied' to anyone skimming"). After this
  slice a legacy step reads `not applied` in `contig show` and `legacy (derived: applied)`
  in `repair-stats`. **Position: accept the divergence for now.** The failure modes
  genuinely differ — a single record under-claiming is harmless, a *rate* built on the
  same default is wrong. Aligning `report.py` is filed as nice-to-have, not silently left.
- **R-Risk-3 — Derivation is a reinterpretation of stored data.** Mitigated by: the legacy
  set is frozen; derived counts are always reported separately; unmapped literals stay
  unknown. If a reader disagrees with the derivation they can subtract it.
- **R-Risk-4 — Push, not demand-pull; n=15 and self-observed.** No design partner asked
  for this. The corpus is the founder's own dev/proof runs. Say so in the CHANGELOG in the
  house "Honest scope" style rather than implying field measurement.
- **R-Risk-5 — Contradiction in `FEATURES.md:216`.** It implies the analytic is unblocked
  because `patch_applied` shipped. It is unblocked **only for runs produced after
  v0.49.0**, and there are currently **zero** such runs. The PRD states this; the
  CHANGELOG must too.
- **Open — revisit trigger.** Proposed, following house practice: once **20 post-v0.49.0
  runs** exist, re-run `repair-stats`; if the `legacy_derived` bucket is still the
  majority, the derivation stays permanent rather than transitional and should be
  documented as such.

## Out of Scope

- Any change to `models.py`, the signed payload, or `patch_applied`'s default.
- Backfilling `patch_applied` into existing bundles (would rewrite signed records).
- A dashboard surface.
- Trend/snapshot history (deferred above, with reason).
- Anything that moves the unattended-completion number rather than measuring it.
- The C8 M8 real-repo smoke — a separate, unrelated act.

## Acceptance (test-first)

Pure core (`tests/test_repair_stats.py`):
1. A step whose raw JSON **omits** `patch_applied` and whose outcome is
   `patched_and_retried` classifies `legacy_derived → applied`, **not** `not_applied`.
2. A step that **carries** `patch_applied: false` classifies `not_applied` — distinct
   from (1). *This is the anti-regression pin for R1.*
3. `stopped_for_confirmation` classifies `unknown`; it is neither derived nor bucketed as
   `GAVE_UP`.
4. `approved_and_retried` is simultaneously `APPLIED` **and** attended; a run whose only
   step is `approved_and_retried` and which succeeded is **excluded** from unattended
   completion. *Pin for R3.*
5. A zero-event run is `not_analyzable` and appears in neither the numerator nor the
   denominator of the rate.
6. All five shipped families are exercised; a family-key enumeration pin fails if
   `repair-timeline.tsx`'s literal set and the Python map diverge.

CLI (`tests/test_cli_repair_stats.py`):
7. `--json` emits the documented keys; text mode names the rate's denominator.
8. A missing runs dir reports "no runs", never `0%`.
9. Help/flags asserted by **introspecting Typer params, never Rich-rendered `--help`
   text** (house rule — that flakes in CI's no-TTY).

Deterministic, synthetic fixtures, no real Nextflow run in CI.

---

## Addendum — gaps closed by the Phase-4 self-critique

### A. The derivation map, stated explicitly (was implicit, and derivable wrongly)

R1 said "derive from the outcome literal using the shipped family map" without saying
what the map *is*. A reader could reasonably derive applied-ness from "the literal ends
in `_and_retried`", which is **wrong**: `advisory_acknowledged_and_retried` ends that way
and records `patch_applied=False` (`CHANGELOG.md:648`).

Verified literal by literal against every `patch_applied=` site
(`self_heal.py:1273-1644`, `verification/reproduce.py:1261-1296`) — notably
`patched_and_retried` is unconditionally `True` (`self_heal.py:1637-1644`) and the
`approved` / `chose` / index-build / recompress sites take it from the control-flow
`cont`, true only on the `*_and_retried` paths:

| literal | family | applied | attended |
|---|---|---|---|
| `patched_and_retried` | APPLIED | ✅ | — |
| `approved_and_retried` | APPLIED | ✅ | **✅** |
| `chose_and_retried` | APPLIED | ✅ | **✅** |
| `built_index_and_retried` | APPLIED | ✅ | — |
| `recompressed_reference_and_retried` | APPLIED | ✅ | — |
| `installed_and_retried` | APPLIED | ✅ | — |
| `retry_failed` | APPLIED | ✅ (install ran; retry then failed) | — |
| `rejected_by_user` | DECLINED | ❌ | **✅** |
| `approval_timed_out` | DECLINED | ❌ | **✅** |
| `invalid_choice_rejected` | DECLINED | ❌ | **✅** |
| `gave_up` / `gave_up_at_ceiling` | GAVE_UP | ❌ | — |
| `index_build_failed` / `index_unresolvable` | GAVE_UP | ❌ | — |
| `reference_recompress_failed` / `reference_recompress_unresolvable` | GAVE_UP | ❌ | — |
| `install_failed` | GAVE_UP | ❌ | — |
| `qc_verdict_flagged` | FLAGGED | ❌ (nothing was tried, `self_heal.py:84-88`) | — |
| `advisory_acknowledged_and_retried` | ACKNOWLEDGED | ❌ | **✅** |
| *`stopped_for_confirmation`* | *unmapped* | **unknown** | **unknown** |

**Verified equivalence: `applied` ⟺ membership of the APPLIED family** — which holds only
because the shipped dashboard split `ACKNOWLEDGED` and `FLAGGED` out of `APPLIED`. Derive
from the **family**, and pin that equivalence with a test so a future literal added to
APPLIED with `patch_applied=False` reddens rather than silently mis-derives.

**`qc_verdict_flagged` on the attended axis:** unattended (no human acted), so a
`qc_verdict_flagged` run that succeeded *does* count as an unattended completion. Noted
explicitly because it is the one case where "completed unattended" and "came out well"
diverge — the run is green with a failing QC verdict. The rate measures the former; the
`FLAGGED` count sitting beside it is what stops that being misread.

### B. Unit of counting — per-step vs per-run (was genuinely ambiguous)

The PRD mixed the two. `realtest4` proves it matters: two steps,
`patched_and_retried` **then** `gave_up`. Resolved, and to be stated in the output
itself:

- **Family and failure-class breakdowns are per STEP.** Each attempt is a real event;
  collapsing a 2-attempt run to one row discards the first attempt.
- **The unattended-completion rate is per RUN**, and a run is attended if **any** step in
  its history carries an attended outcome — not just the last one. A human who approved
  attempt 1 was still a human in the loop even if attempt 2 ran clean.
- **`last-step-wins` (S2) applies only to a run's terminal outcome label**, mirroring
  `heal.py:253-256` — never to the attended test.
- Totals in the output are labelled `runs` or `steps` at every site. No unlabelled number.

### C. Expected output on today's corpus (a pin the PRD lacked)

Success criteria were behavioural with no target. Since `runs/` is gitignored, this
cannot be a CI test, but it is a **manual post-merge verification** with a predicted
result — recorded now so a surprise is visible as a surprise:

Predicted for the 15 real records: **15 runs**, of which **1** (`testpass`, 0 events) is
`not_analyzable`; **7 steps** across 6 runs, **all 7 `legacy_derived`** (0 carry the key);
derived families APPLIED ×2, GAVE_UP ×4, unknown ×1 (`stopped_for_confirmation`);
failure classes `tool_crash` ×3, `oom` ×2, `missing_index` ×1, `unknown` ×1; **0 steps
read from the field**, and the thin-data flag raised on every class. If the command
prints anything else, the discrepancy is the finding.

### D. Effort

`FEATURES.md:216` sizes this **M**. Concretely: one pure module (~150 lines), one Typer
command, two test files. No model, signature, dependency, or dashboard change.

### Remaining 🟡 at the gate

- **Stakeholder alignment** is trivially the founder — no external approver. Stated, not
  padded.
- **R-Risk-4 stands**: push, not demand-pull; n=15, self-observed, founder's own dev runs.
  Nothing in this slice changes that, and the CHANGELOG must say so plainly.

---

## Addendum 2 — corrections from the Phase-2 agent reports

The three dig agents' reports arrived after the PRD was drafted. They confirm the findings
above and correct **one load-bearing error** and two smaller ones.

### 🔴 CORRECTION to R3 — `approved_and_retried` is NOT unconditionally attended

R3 and the Addendum-A table classify `approved_and_retried` and `chose_and_retried` as
attended, on the reasoning that they are reached only through the approval gate. **That is
wrong.** Both literals also fire under `--auto-approve`, where the engine decides per
policy and **no human is involved** (`self_heal.py:1449`, `:1497`, `:1553` — auto-approve
auto-*decides* a gated patch; it does not remove the patch from the gated-outcome
vocabulary).

**And the record cannot disambiguate them.** `auto_approve` is a CLI flag
(`cli.py:413`) threaded into `self_heal_run` (`cli.py:452`, `:814`) and **never
persisted**. The only `auto_approve` field in `models.py` is at `:569`, on
**`HealScenario`** — the synthetic scenario model, not `RunRecord`. Verified against the
full `RunRecord` field list; there is no such field, and no `ExecutionTarget` equivalent.

**Resolution — a third attendance state, exactly parallel to R1's three-state applied.**
The record under-determines the answer, so the command must not invent one:

| attendance | outcomes |
|---|---|
| `attended` | `rejected_by_user`, `approval_timed_out`, `invalid_choice_rejected`, `advisory_acknowledged_and_retried` |
| **`attendance_unknown`** | **`approved_and_retried`, `chose_and_retried`** — a human *or* `--auto-approve`; unknowable from the record |
| `unattended` | everything else (`patched_and_retried`, `gave_up*`, `qc_verdict_flagged`, the index/recompress fan-out, and all three `reproduce.py` literals — that loop has **no** approval gate at all) |

A run containing an `attendance_unknown` step is reported in its own bucket and excluded
from both the numerator and the denominator of the unattended-completion rate, with the
exclusion counted and stated — the same discipline R4 applies to zero-event runs.

**Impact on today's numbers: none.** The real corpus contains only
`patched_and_retried`, `gave_up`, and `stopped_for_confirmation`, so no step is
`attendance_unknown` yet. This is a design correction, not a data correction — and it is
precisely the kind of thing that would otherwise have shipped as a silent overcount of
"attended".

**Filed as a finding against the engine, not fixed here:** a run record cannot say whether
a human was in the loop, because `auto_approve` is not captured. That is a genuine
provenance gap of the same shape as the C2 deferral items. Persisting it (on
`LaunchManifest` or `ExecutionTarget`) would collapse `attendance_unknown` to empty and is
the natural follow-on slice. Out of scope here: it is a model/signature change, and this
slice is read-only by design.

### 🟡 Correction to AC#9 — there is no `--help` testing convention to follow

AC#9 said to assert flags by "introspecting Typer params, never Rich-rendered `--help`".
The first half is unsupported: **no test in the repo asserts on `--help` output at all,
and none introspects Click/Typer params either.** The only `--help` string in `tests/` is
an unrelated parametrize value (`tests/test_paper_intake.py:64`). Restated: **do not test
`--help`.** Assert exit codes, parsed JSON, and plain-echo substrings, matching
`tests/test_cli_insight.py`. (The standing rule against asserting on Rich-rendered
`--help` still holds — it simply never comes up here, because this family renders with
plain `typer.echo` and no Rich tables.)

### 🟡 Refinement — `RunRecord.verdict` exists and is persisted

The PRD said `RunRecord` has no status field. True, but incomplete: there is a
`@computed_field verdict` (`models.py:389-401`, `Literal["pass","warn","fail","unverified"]`)
that **is** serialized into `run_record.json`. It is not a substitute for the completion
signal — it returns `"fail"` when `RunSummary.from_events(...).succeeded` is False but
otherwise reports the *QC* verdict, conflating completion with quality. **Keep
`RunSummary.from_events(record.events).succeeded` as the completion signal** (mirroring
`heal.py:249-252`), and treat `verdict` as an available extra dimension, not the gate.

### Confirmations (no change required)

- Empty `repair_history` unambiguously means a clean first-attempt success:
  `repair_history` is freshly `[]` per `self_heal_run` invocation (`self_heal.py:1199`),
  one call site (`cli.py:792`), no merge/resume-across-invocations path.
- `stopped_for_confirmation` is dead in `src/`, removed from `OUTCOME_META`, and locked
  absent by `dashboard/e2e/repair-truthfulness.spec.ts:128` — R5 stands.
- The 19-literal set and the five dashboard families match `src/` 1:1, no orphans either
  direction — R2 and the Addendum-A table stand (with the R3 correction above).
- `heal.py` and `reproduce_guard.py` are the only rate computations and are **both**
  over frozen synthetic scenarios; `report.py` has no aggregate logic at all — R8 stands,
  and the new command should not reuse `HealEvalReport`/`ReproduceGuardResult`, which are
  shaped around scenario expectation-matching.
- House rendering is plain `typer.echo`, no Rich tables, counts as raw ints always
  `sorted()` by key for determinism, `--json` dumping the pure function's dict verbatim,
  `_THIN_THRESHOLD = 3` (`corpus.py:279`) rendered as a literal `"  THIN"` suffix
  (`cli.py:3733`) — R6/R7 stand, and the new command should match that shape exactly.

---

## Addendum 3 — the prediction, checked (2026-09-05, `stats-core` complete)

Addendum C committed a predicted output over the 15 real records and said *"if the
command prints anything else, the discrepancy is the finding."* It printed something
else in two places. Both are the **code being right and the prediction being wrong**.

Actual, via `repair_stats_report(collect_runs("runs"))`:

```
runs:  total 15 | analyzable 14 | not_analyzable 1 | attendance_unknown 0
       rate_denominator 14 | unattended_completed 9
       unattended_completion_rate 0.6428571428571429
steps: total 7
       by_family        {applied: 2, gave_up: 4}
       by_failure_class {tool_crash: 3, oom: 2, missing_index: 1, unknown: 1}
       by_applied       {applied: 0, not_applied: 0, legacy_derived: 6, unknown: 1}
       by_attendance    {attended: 0, unattended: 6, attendance_unknown: 0, unknown: 1}
       legacy_derived_applied {applied: 2, not_applied: 4}
thin:  [missing_index, oom, unknown]
unmapped_outcomes: {stopped_for_confirmation: 1}
```

**Matched:** 15 runs; 1 `not_analyzable` (`testpass`, 0 events); 7 steps; families
APPLIED ×2 / GAVE_UP ×4; all four failure classes exactly; **0 steps read from the
field** — the central claim of R1 and R-Risk-5, confirmed against real data.

**Discrepancy 1 — "all 7 `legacy_derived`" was wrong; it is 6 + 1 `unknown`.** The
prediction was internally inconsistent: it also said `unknown ×1`. `stopped_for_confirmation`
is unmapped, so it is `unknown` on the applied axis and never derived — exactly R5. The
prediction, not the code, was sloppy.

**Discrepancy 2 — "the thin flag raised on every class" was wrong.** `tool_crash` has
**3** steps and the threshold is `< 3`, so it is not thin. Three of four classes are.
This also retires the concern raised during implementation that the flag "always fires
and carries no discriminating information" — at n=7 it already discriminates.

**The headline number: 64.3% unattended completion (9 of 14 analyzable runs).**
Read it honestly, against our own interest:

- It sits just under `ROADMAP.md:109`'s ≥70% gate, and **it must not be reported as
  progress toward that gate.** The denominator is 14 runs of which most are dev, proof
  and demo bundles (`_livetest2-proof`, `dash-livetest`, `test-2026-*`) that never failed.
  This is the "count all, classify + disclose" decision working as designed — the number
  is true for its stated denominator and worthless as a field measurement.
- It is high mostly because **most runs never failed at all.** "Unattended completion"
  counts clean runs; it is not a recovery rate. Applying `heal.py:250-252`'s recovery
  formula to the same corpus still yields **0**, because no step carries the field.
- `cli-surface` must therefore state the denominator, the `not_analyzable` exclusion, and
  the legacy-derived count **beside** the rate, never the rate alone. That requirement is
  now evidence-backed rather than anticipated.
