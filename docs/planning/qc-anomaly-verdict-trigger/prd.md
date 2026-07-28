# PRD — `qc_anomaly` verdict trigger

**Slug:** `qc-anomaly-verdict-trigger` · **Branch:** `feat/qc-anomaly-verdict-trigger/aliz`
**Capability:** C6 (eval flywheel) × C2 (self-heal breadth) — the verify↔self-heal link
**Date:** 2026-07-28 · **Status:** ✅ SHIPPED — merged to `master` 2026-07-29 (`0901362`)
**Inputs:** `docs/planning/_card/issue.md` (brief), `understanding.md` (Phase-2 dig, 4 agents)

---

## Problem Statement

**`qc_anomaly` is a failure class that cannot happen.** It is one of 18 `FailureClass`
literals (`models.py:279`), but nothing in the product can produce it: no branch in
`detect.py` emits it, no branch in `repair.py` patches it, it appears in **0 of 25**
training-corpus cases, and its one held-out case has been misclassified in **all seven**
recorded trend points (`data/holdout_history.jsonl` — `predicted: 0`, `recall: 0.0`, v0.22.0 →
v0.48.0). `cli.py:2683` documents it as structurally unreachable. It is the **last** such
class: `no_progress`, its sibling, was closed in the stall-watchdog slice.

**The underlying product gap it names is real.** `diagnose_failure` is called from exactly one
place — the `except PipelineExecutionError` branch (`self_heal.py:993`) — so **the self-heal
loop only ever reacts to a non-zero exit.** A run that completes with every task green, and
whose QC then reduces to **FAIL**, returns through `self_heal.py:984` straight into
`_finalize` at `:985` with nothing in between. It is never diagnosed, never enters
`repair_history`, and never becomes a corpus case. The verdict is an **output only**; it is
never an **input**.

That shape is now reachable in practice, not hypothetical: FAIL-severity QC shipped for
germline Ti/Tv, het/hom and `variant_count` (`CAPABILITY_ROADMAP.md:585`) and for somatic
`somatic_variant_count fail_below: 1` (`:871`). A truncated caller yielding an empty call set
is precisely a green run with a FAIL verdict.

**Evidence — measured, not asserted.** All 17 `run_record.json` bundles recorded on the
development machine were scanned against the exact R1 trigger condition:

| Result | Count |
|---|---|
| `run_record.json` found | 17 |
| `events_ok=False` (crashed — the existing loop already handles these) | 5 |
| Green with `qc_verdict` ∈ {pass, warn, no-qc} | 11 |
| **Green with `qc_verdict == "fail"` — would trip** | **1** |

The tripping run is `runs/variant-bad`: an `nf-core/sarek` germline record where
`NFCORE_SAREK:HAPLOTYPECALLER (S1)` **COMPLETED with exit 0**, the recorded `ts_tv_ratio:S1`
carries `status: "fail"`, `mean_coverage` and `het_hom_ratio` both PASS — and `repair_history`
is **`[]`**. That is the gap this PRD describes, sitting in a real bundle on disk, and it becomes
the slice's regression fixture rather than a synthetic one.

**⚠️ Correction (2026-07-28, found during Phase 1 mutation testing — this cuts against the
slice and is recorded rather than smoothed).** An earlier draft of this section claimed
`ts_tv = 3.5` "**FAILs** the germline plausibility band". **That is false under today's bands.**
`VARIANT_RULE_PACK`'s `ts_tv_ratio` is `warn_above: 2.4`, `fail_above: 3.6`
(`verification/rule_pack.py:57-64`), so **3.5 evaluates to WARN**. The bundle records
`status: "fail"` with `expected_range: [1.8, 2.4]` from a **`contig_version: 0.0.1`** evaluation
that predates the current bands.

The trigger still fires on it, and legitimately so — it reduces the **recorded** `qc_results`
via `overall_verdict` and does not re-evaluate bands. But the honest reading of the measurement
changes:

- **Literally true:** 1 of 17 recorded bundles trips the trigger.
- **What that 1 actually is:** a stale v0.0.1 recorded status, not a current-band FAIL.
- **Under today's bands, re-evaluated: 0 of 17.**

**So the measurement proves the shape is producible and representable — not that it occurs.**
Combined with the fact that the run was plainly *authored* to be bad, and that 5 of the 17
crashed outright (which the existing loop already diagnoses), **organic frequency is 0 of 17 on
either reading**, and the stricter reading is the one to quote. This is **push, not
demand-pull**, and it makes the committed revisit trigger below load-bearing rather than
ceremonial.

### ⚠️ Correction to the inherited rationale

The `no_progress` PRD and `CAPABILITY_ROADMAP.md:1074` defer this work because *"its honest
trigger is the verdict object, not log text (**QC runs at `_finalize`, not as a pipeline
step**)"*. The parenthetical is **false**, verified twice independently:

- `_finalize` (`self_heal.py:1244-1323`) never calls `_discover_qc` or `evaluate_run_qc`,
  directly or transitively. It only *appends* a conditional `reference_harmonized` breadcrumb
  to an already-populated list (`:1307`).
- QC is computed inside `run_pipeline` at `runner.py:1223`, gated only on
  `artifact_path.exists()`, **before** the `returncode != 0` check at `:1230` — on **every**
  attempt, success and failure alike.

The correct reason the `no_progress` mechanism does not transfer is that **the success path has
no diagnosis call at all**, not that QC runs too late to see. **R11** corrects the doc.

---

## Goals & Success Metrics

| Goal | Metric | Measured by |
|---|---|---|
| `qc_anomaly` becomes producible | A test constructs a green-run-with-FAIL-QC record and asserts a `qc_anomaly` `Diagnosis` reaches `repair_history` | `uv run pytest` |
| The loop's guarded coverage widens | `heal-guard` `covered_classes` **6 → 7**, `outcome_match_rate` stays **1.0** | `uv run contig heal-guard` |
| The failure becomes eval data | A QC-FAIL-on-green run writes a pending-corpus `FailureCase` where it previously wrote none | test + `contig corpus` inspection |
| Nothing else moves | exit code, lifecycle event, and `record.verdict` byte-identical on every existing path | regression tests |

### Explicit non-goal: `eval-guard` does not move

**`eval-guard` stays at 0.923 (12/13) and that is correct.** The held-out fixture
`holdout-qc-anomaly-1` is *pipeline-step* shaped (a FAILED `MULTIQC_QC_GATE` event plus
third-party QC-gate log text) and would only classify via a **log-text needle branch**. Those
needles would be phrases **Contig never emits**, so the justification the `no_progress` slice
relied on — *"what generalizes the branch is that our own wording is ordinary English"*
(`detect.py:39-54`) — is **unavailable** here. Per **D1** we decline that trade. Any future
claim that this slice "improved detector accuracy" would be false.

---

## Users & Scenario

**Primary: the lone computational biologist** running germline or somatic variant calling on
their own compute. Their sarek run finishes green. Every task succeeded. The call set is
empty because a caller step silently truncated, so `somatic_variant_count fail_below: 1`
FAILs the verdict.

- **Today:** the report and dashboard show FAIL (so they are *not* unaware), the run exits 0
  unless they passed `--fail-on-verdict`, and `repair_history` is **empty** — the engine has
  no record that anything was ever wrong. Nothing enters the corpus.
- **After:** the same FAIL, the same exit code, the same lifecycle event — plus one diagnosed
  `qc_anomaly` step naming which checks failed and stating that no repair was attempted
  because none can work, and one corpus case.

**Honest framing of the benefit: this is diagnosis and telemetry, not rescue.** The slice
recovers nothing, by design (see *Requirements → R4*).

---

## Requirements

### Must-have

**R1 — Trigger, precisely scoped.** After `run_pipeline` returns normally in `self_heal_run`
(i.e. `returncode == 0`), fire **only** when all three hold:

1. `RunSummary.from_events(record.events).succeeded is True`
2. `record.qc_results` is non-empty
3. `overall_verdict(record.qc_results) == "fail"`

Condition 1 is load-bearing, not redundant: `RunRecord.verdict` (`models.py:373-385`) returns
`"fail"` for a **failed task event** before it ever consults QC, so keying on
`record.verdict == "fail"` alone would misattribute an event-driven failure as a QC anomaly. A
test must pin that an event-FAIL run with returncode 0 does **not** produce `qc_anomaly`.
Condition 2 is likewise load-bearing: empty `qc_results` reduces to `"unverified"`, never
`"fail"`, and must stay a silent skip.

**R2 — Synthesize the `Diagnosis` in `self_heal.py`; leave `detect.py` untouched.** The
`Detector` type is `Callable[[list[TaskEvent], str], Diagnosis]` (`detect.py:20`); widening it
would touch the LLM detector and every injection site to carry a value that is not log text.
The diagnosis is a **deterministic structural read of our own verdict object**, not an
inference over evidence:

- `failure_class="qc_anomaly"`
- `root_cause` naming the count of FAILed non-informational checks
- `evidence` = the failing check names and their statuses, drawn from `record.qc_results`
- `confidence = 1.0` — see **D6**

**R3 — Insertion point.** Between `self_heal.py:984` and `:985`, which are adjacent today. The
check lives in `self_heal_run`, **not** in `run_pipeline`, keeping the blast radius to the
self-heal loop (any other `run_pipeline` caller is unaffected — noted as **O3**).

**R4 — No repair is attempted, and the reason is provable.** A bare `-resume` retry of a
QC-FAIL run is **provably useless**, verified:

- `-resume` is appended with **no cache invalidation** (`runner.py:1116-1117`); grep for
  work-dir clearing / `.nextflow/cache` logic returns **zero hits** — Contig has no mechanism
  of its own to invalidate Nextflow's task cache.
- Every task exited 0 by definition of the trigger, so every task is cache-valid.
- Therefore nothing re-executes, outputs are byte-identical, and `overall_verdict` re-derives
  **identically**.

This is the sharp contrast with `no_progress`, whose retry is defensible despite an all-hit
cache because a stall's cause (a wedged mount, a transient hang) is plausibly gone next
attempt. Here the cause is **in the data**. A `kind="retry"` patch would be a dressed-up
recovery and **must not be written**. `propose_patches` gains **no** `qc_anomaly` branch, and a
test pins its absence so nobody adds one without revisiting this reasoning.

**R5 — A new outcome literal, because `gave_up` would be dishonest** (**D4**).
`outcome="qc_verdict_flagged"`. `gave_up` means "we tried and lost"; nothing was tried here,
and reusing it would make this path indistinguishable in the corpus from the shipped
`tool-crash-giveup`. `RepairStep.outcome` is a plain `str` (`models.py:313`) with no enum, so
this costs no type change. `RepairStep.detail` carries the field instrument: which checks
failed, and the explicit statement that no repair was attempted because a retry is 100%
cache-hit and re-derives an identical verdict.

**R6 — Always on** (**D5**). No flag. The trigger changes no exit code, no lifecycle event, no
verdict, and spends no compute — unlike `--detect-stalls`, which gates a real side effect
(it SIGKILLs the pipeline). An opt-in gate would also mean the corpus only ever sees
volunteers. Consequently **no** `rerun`/`resume` flag-forwarding follow-up is needed.

**R7 — Contract invariants, each pinned by a test.**

- **Exit code unchanged.** `cli.py:743-744` exits 1 when events fail (unconditional);
  `cli.py:745-747` exits 1 on a FAIL verdict **only** under `--fail-on-verdict` (v0.36.0). A
  QC-only FAIL must continue to exit **0** by default.
- **Lifecycle event unchanged.** `_finalize` emits `finished`/`failed` from
  `RunSummary.from_events(...).succeeded`; a QC-only FAIL stays **`finished`**. Recording a
  give-up-shaped step must not flip it to `failed`.
- **Verdict unchanged.** `record.verdict` is a computed field already returning `"fail"`. This
  slice adds no QC check, band, threshold, or biological claim.
- **`_finalize` still runs exactly once** and stays terminal.

**R8 — Runtime corpus capture** (**D3**). Write a pending `FailureCase` for the QC-FAIL run.
Today the capture at `self_heal.py:997-1007` sits on the exception path only, so this class of
failure cannot enter the corpus at all. This is the moat-#2 justification for the slice.

**R9 — The committed detector corpora are NOT touched, and this is forced, not chosen.** Both
corpora score `expected_class` from `(events, log_text)` only. A zero-exit structural case
cannot be represented, and adding one while `detect.py` is untouched would **misclassify and
lower `eval-detector` accuracy**. No case is added to `detector_corpus.jsonl` or
`detector_corpus_holdout.jsonl`; `holdout_baseline.json` is **not** refrozen.

**R10 — `heal-guard` coverage, exercising the REAL QC path** (**D2**; **O1 resolved
empirically — see below**). `HealScenario`/`AttemptSpec` (`models.py:533-560`) replay only
`status`/`exit`/`log_text`, so today `_discover_qc` finds nothing in the scripted harness and
any scenario reduces to `"unverified"`, never `"fail"`. **O1 is now settled: the scripted
harness can drive the real, unmodified `_discover_qc` to a FAIL verdict with one tiny
artifact** — no seam that bypasses QC, and therefore R10 keeps its rationale.

The proven minimal fixture (run against `runner._discover_qc` directly, no mocking):

- **one file**, any name ending `.vcf.gz`, anywhere under the run dir (root is fine)
- **content**: an empty gzip stream — `gzip.open(p, "wt").write("")`, **33 bytes on disk**. A
  113-byte realistic header (`##fileformat=VCFv4.2` + `#CHROM…`) behaves identically and is
  preferable if the fixture should look plausible.
- **`assay="variant_calling"`**

Mechanism: `parse_vcf` opens a `.gz` name with stdlib `gzip` (**plain gzip, not real bgzip** —
`verification/concordance.py:87-110`), yields zero data rows, so `variant_metrics` returns
`variant_count=0` with both ratios `None`; `VARIANT_RULE_PACK`'s `variant_count fail_below: 1`
(`verification/rule_pack.py:84-89`) makes 0 a **FAIL** — by explicit design
(`variant_metrics.py:165-167`: *"a real 0 (empty call set) rides the band as a FAIL … and never
routes into the unverified branch"*). Observed result: `variant_count:sample → fail`, four
sibling checks `unverified`, `overall_verdict == "fail"`. No MultiQC file, no BAM and no
annotated VCF are needed, so no other gate fires to pollute the set.

**Consequently the models change is much smaller than first costed:** `_discover_qc` takes only
`(run_dir, assay)` and globs relative to the run dir with no `results/`-vs-`work/` preference
and no absolute-path dependency, so the harness needs only a small directive to drop that one
artifact — **not** an injectable `qc_results` field. The scenario's single attempt is
`status="COMPLETED", exit=0` (so `RunSummary.succeeded` is true and R1's condition 1 holds
rather than short-circuiting on the events branch), `assay="variant_calling"`,
`expected_outcome="qc_verdict_flagged"`, `expected_recovered=false`. Every existing scenario
already writes a trace row, so that half is precedented.

Refreeze discipline: `heal_scenarios.jsonl` + `heal_baseline.json` via
`heal-guard --update-baseline`, and the hardcoded literals in `tests/test_heal_scenarios.py`
(`scenario_count`, `corpus_sha`, recovery counts) updated in the same commit.

**R11 — Correct the stale rationale in the docs.** `CAPABILITY_ROADMAP.md:1074` and the
`cli.py:2683` docstring both state or imply that `qc_anomaly` is unreachable and that QC runs
at `_finalize`. Update: the class is now reachable, and the parenthetical mechanism claim is
wrong (see *Correction* above). `cli.py:2683`'s "Not covered" list must move `qc_anomaly` into
the covered set — the same care the `no_progress` slice took not to conflate the two classes.

### Should-have

**R12 — The `detail` string as a field instrument.** Because real-world frequency is
unmeasured (see *Honest Limits*), `RepairStep.detail` should record enough to answer later
"how often does this fire, and on which checks?" without new telemetry: the failing check
names, their count, and the assay. One consistent, greppable message stem.

### Nice-to-have

**R13 — A dashboard surface** for the diagnosed QC verdict. Deferred; `repair_progress.jsonl`
already receives the step (`_record_attempt`, `self_heal.py:237-250`), so a live view gets it
for free without UI work in this slice.

---

## Decisions

| # | Decision | Rationale |
|---|---|---|
| **D1** | **Door B only** — structural trigger; `detect.py` untouched | Door A's needles would be text Contig never emits, so the `no_progress` generalization defence is unavailable. `eval-guard` stays 0.923; the eval number must not drive a detector rule. |
| **D2** | `heal-guard` coverage **in scope** | Otherwise the loop behaviour is asserted in unit tests but never replayed through the real loop. |
| **D3** | Runtime corpus capture **in scope** | The moat-#2 output; without it the slice's only lasting artifact is one bundle field. |
| **D4** | New outcome literal `qc_verdict_flagged` | `gave_up` implies an attempt; nothing was attempted, and reuse would make it indistinguishable from a real give-up. |
| **D5** | **Always on**, no flag | No side effect to gate; an opt-in corpus sees only volunteers. |
| **D6** | `confidence = 1.0` | A deterministic read of our own verdict object, not an inference. Existing confidences (0.2–0.95) grade *guesses from log text*; this is not a guess. Note `diagnose_failure_strict` (`detect.py:420-453`) demotes weak guesses but never sees this path. |

---

## Technical Considerations

**Architecture fit.** Purely additive wiring in the orchestration layer. Reuses
`overall_verdict` (`models.py:85-111`) — which already excludes `informational=True` results
from the severity reduction, so a verdict-neutral check can never trip the trigger — plus
`_record_attempt` (`self_heal.py:237-250`) and the existing `RepairStep`/`Diagnosis` models
unchanged.

**Files expected to change:** `src/contig/self_heal.py` (trigger + capture),
`src/contig/models.py` (**one optional `HealScenario` field** directing the harness to drop the
QC artifact — not an injectable QC-results structure, per **O1**), `src/contig/heal.py`
(write that artifact in `_scripted_executor`), `src/contig/cli.py` (docstring), `src/contig/data/heal_scenarios.jsonl` +
`heal_baseline.json` + `heal_history.jsonl` (refreeze), `tests/` (new + updated literals),
`CHANGELOG.md`, `FEATURES.md`, `docs/technical/CAPABILITY_ROADMAP.md`.
**Explicitly NOT changed:** `detect.py`, `repair.py`, `runner.py`,
`detector_corpus*.jsonl`, `holdout_baseline.json`.

**Reproducibility impact: none.** No change to `LaunchManifest`, the reproduce bundle, or
signing. `RepairStep` is already part of `repair_history` and already round-trips.
`canonical_record_bytes` covers `repair_history` today, so **existing signatures over runs that
previously had an empty `repair_history` remain valid** — this slice adds a step only to runs
that would newly trip the trigger, never retroactively. No signature-break disclosure is
expected; the plan must **verify** this rather than assume it (**O4**).

**Verification impact.** The verdict itself is unchanged. What changes is that a FAIL verdict
becomes a *diagnosed* event. No new check, band, or threshold; no clinical or biological claim.

**Dependencies:** none blocking. Builds on shipped `overall_verdict`, `_record_attempt`, the
heal-scenario driver, and the FAIL-severity packs that make the trigger reachable.

---

## Risks & Open Questions

| # | Open question | Recommendation |
|---|---|---|
| ~~**O1**~~ | ~~How does the scripted heal harness produce a **real** FAIL verdict?~~ | **RESOLVED empirically (2026-07-28): option (b), and it is cheap.** One 33-byte empty-gzip `.vcf.gz` + `assay="variant_calling"` drives the real `_discover_qc` to `overall_verdict == "fail"`. Verified by calling the unmodified function directly — no seam, no mocking. Full fixture in **R10**. |
| **O2** | Does adding a `RepairStep` to an otherwise-successful run break a downstream assumption (`repair_history` non-empty ⇒ the run had failures) in the report renderer, HTML panel, or dashboard? | Grep and test all consumers before implementing. A real regression risk, cheap to check. |
| **O3** | Callers of `run_pipeline` outside `self_heal_run` (if any) get no diagnosis. | Enumerate them; if the only production caller is the loop, record it as scoped-by-design. |
| **O4** | Confirm empirically that no existing signed bundle's canonical bytes change. | Assert, don't assume — three C8 slices have shipped signature-break disclosures. |
| **O5** | Should the trigger also fire on `warn`? | **No.** Out of scope — WARN is the normal corroboration tier and would fire constantly. |

| # | Risk | Mitigation |
|---|---|---|
| **RISK-1** | **Dead code:** real QC-FAIL-on-green runs may be vanishingly rare, so the path never fires in the field. | **Partly measured, and the measurement is not reassuring:** 1 of 17 recorded runs trips the trigger, and that one was deliberately authored to be bad — **organic frequency is 0 of 17** (see *Problem Statement*). Accepted knowingly; R12's `detail` string is the instrument that would later replace the guess with data. The single tripping bundle at least gives the slice a real fixture. |
| **RISK-2** | **Over-claiming.** A reader could take "closed the last unreachable class" as "detector accuracy improved" or "self-heal got stronger". Neither is true. | The non-goal is stated in this PRD, and must be restated in CHANGELOG/roadmap: `eval-guard` unchanged, nothing recovered. |
| **RISK-3** | **Partly self-graded**, as with `no_progress`. | Here the exposure is *smaller*, because we decline the corpus/accuracy move entirely (**D1**/**R9**). The `heal-guard` scenario is still one we author — disclosed. |
| **RISK-4** | The new outcome literal is unenforced (`outcome: str`, no enum), so a typo would silently diverge from the heal scenario's `expected_outcome`. | One shared module-level constant referenced by both the production path and the scenario assertion. |

---

## Out of Scope

- **Any `detect.py` needle branch** for third-party QC-gate log text (**D1**) — and therefore
  any `eval-guard` / `holdout_baseline.json` movement (**R9**).
- **Any actual repair** for `qc_anomaly`. A remediation that changes something Nextflow's cache
  keys on (e.g. adjusting a QC-threshold parameter) is a much larger design question and a
  separate slice.
- Firing on `warn` or `unverified` verdicts (**O5**).
- New QC checks, bands, thresholds, or calibration of any existing band.
- A dashboard card (**R13**).
- Folding C1/C3 corroboration signals into one eval number — blocked on a labeling design
  (`CAPABILITY_ROADMAP.md:1024`).
- The dead-looking `verification/run_qc.py::run_qc` (nothing in `src/contig` calls it; only
  `evaluate_run_qc` is live) — flagged by the dig, cleanup is unrelated debt.
- Any Layer-1 (NL→workflow) surface.

### Filed follow-up — `wasRepaired` still overclaims, and `OUTCOME_META` is thirteen short

Found during Phase 3.5 review; **deliberately not fixed here** (founder decision, 2026-07-28).

This slice changes the dashboard's `wasRepaired` from `repair_history.length > 0` to
`some(s => s.patch !== null)`. That is **strictly better** — it fixes the new
`qc_verdict_flagged` case and the pre-existing no-patch `gave_up` case — but it means **"a patch
was *proposed*"**, not applied. `apply_patch` runs at only two sites (`self_heal.py:879`,
`:1266`), and **five** paths record a non-null patch and return before either:

| Site | Outcome | Patch |
|---|---|---|
| `:1102` | `gave_up` (attempt budget exhausted) | `gated` |
| `:1183` | `rejected_by_user` / `invalid_choice_rejected` / `approval_timed_out` | `gated` |
| `:1234` | `rejected_by_user` / `approval_timed_out` | `gated` |
| `:1246` | `gave_up` (attempt budget exhausted) | `safe` |
| `:1257` | `gave_up_at_ceiling` | `safe` |

The sharpest case: **a user who rejects a patch at the approval gate is told their run was
`Repaired`.** Pre-existing (today's `length > 0` does the same), so this slice makes nothing
worse — but it does not deliver the "a patch was applied" semantics its own decision claims.

**The durable fix is a structured field, not more string matching.** A TypeScript allowlist
would have to track **15** Python outcome literals that `RepairStep.outcome` does not
type-constrain (it is a bare `str`, `models.py:313`): `patched_and_retried`,
`approved_and_retried`, `chose_and_retried`, `built_index_and_retried`,
`recompressed_reference_and_retried`, `gave_up`, `gave_up_at_ceiling`, `rejected_by_user`,
`approval_timed_out`, `invalid_choice_rejected`, `index_build_failed`, `index_unresolvable`,
`reference_recompress_failed`, `reference_recompress_unresolvable`, `qc_verdict_flagged`.

`OUTCOME_META` maps three keys, but one (`stopped_for_confirmation`) **appears nowhere in
`src/`** — it is dead. So it maps **2 real literals of 15**, and `rejected_by_user`,
`approval_timed_out`, `gave_up_at_ceiling` and ten others **already render today** as mangled
snake_case dressed in give-up styling. A user who rejected a patch already sees something that
looks like a give-up.

**Follow-up slice:** add `RepairStep.patch_applied: bool`, drive the badge off it, and map the
unmapped literals.

> ⚠️ **Do NOT set the flag "wherever `apply_patch` returns"** — that naive rule reproduces the
> very bug this follow-up exists to kill. `_apply_patch_and_maybe_build` calls `apply_patch` on
> its **first line** (`:879`), before it knows whether the build or recompress succeeded, and the
> code says so itself at `:876`: *"The build IS the fix (apply_patch is a no-op for
> build_index)."* Under that rule `index_build_failed`, `index_unresolvable`,
> `reference_recompress_failed`, and `reference_recompress_unresolvable` would all be stamped
> `patch_applied=True` despite nothing effective having happened — and hardened into the
> **signed** record, where it is far more expensive to correct than a dashboard predicate.
>
> **Use the signal that already exists:** `_apply_patch_and_maybe_build` returns a 5-tuple whose
> last element is `continue_` (`-> tuple[..., bool]`, `:849`), documented as "the loop should
> retry" — i.e. *something effective happened*. It is `True` exactly for the
> applied-and-proceeding cases and `False` for all four failures above. Drive `patch_applied`
> off that boolean, plus `True` at the `:1266` site. Derived from control flow, not from a
> hand-maintained literal list — which is the entire reason to prefer a structured field.

It touches the **signed** `RunRecord` shape, so it must re-verify the signature safety this
slice's Phase 0 established — which is exactly why it is its own slice and not a two-file
phase's side effect.

---

## Honest Limits (to carry verbatim into CHANGELOG / roadmap)

1. **Push, not demand-pull.** No design partner asked for this. It closes a documented
   taxonomy gap; the **frequency of real QC-FAIL-on-green runs is unmeasured**, and nothing
   here claims otherwise.
2. **It recovers nothing, by design.** The slice adds diagnosis and telemetry. Calling it a
   self-heal improvement would be false — R4 proves a retry cannot work.
3. **`eval-guard` does not move**, deliberately. The 13/13 held-out score was available only
   through a needle branch on foreign text, and we declined it.
4. **The `heal-guard` gain is authored by us.** `covered_classes` 6 → 7 reflects a scenario we
   wrote for a class we made reachable — evidence that a taxonomy gap closed, not that a user
   was helped.
5. **No real nf-core run in CI.** The trigger is exercised against synthetic records and the
   scripted heal harness; whether a real sarek truncation lands exactly on
   `events-succeeded + QC-FAIL` is **reasoned**, not observed, and belongs to the manual gate.

## Revisit trigger (committed)

The `no_progress` slice committed a revisit trigger in both directions; this one must too, or it
is unfalsifiable — the pointed question the self-critique raised. **Adopted by default** (author's
choice at the review gate, not the founder's, and open to revision):

- **Against:** if the trigger fires on **zero non-authored runs across the next 20 real runs**,
  the diagnosis path is **removed** and the behaviour reduced to a report-only note. The
  `RepairStep.detail` instrument (**R12**) is what makes that countable without new telemetry —
  grep `repair_progress.jsonl` for the message stem.
- **For:** if it fires on real runs and the diagnosed check names cluster (e.g. repeatedly
  `variant_count` on truncated callers), that cluster is the demand signal for the **actual
  remediation** this slice deliberately declines to build (a patch that changes something
  Nextflow's cache keys on) — at which point `qc_anomaly` earns a real `propose_patches` branch
  and **R4**'s reasoning is revisited on evidence rather than repealed on taste.
