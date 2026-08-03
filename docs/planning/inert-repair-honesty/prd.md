# PRD — inert-repair-honesty (C2)

- **Slug:** `inert-repair-honesty` · **Branch:** `feat/inert-repair-honesty/aliz` · **Owner:** aliz
- **Capability:** C2 (self-heal breadth), filed against C2 by the C6 catalog-coverage slice
- **Inputs:** [`../_card/issue.md`](../_card/issue.md), [`understanding.md`](understanding.md)
- **Status:** drafted 2026-08-03, pending review gate

---

## Problem Statement

`propose_patches` (`repair.py:14-175`) emits a patch for five failure classes whose stated
operation is performed by nothing. The loop then records propose → "apply" →
`patch_applied=True` → retry, and every surface renders that as a repair Contig performed.

**The over-claim starts at the approval gate, not at the report.** `_write_pending_approval`
(`self_heal.py:319-348`) serializes both the `rationale` and the `operation` dict into
`pending_approval.json` (`:342-343`), and `repair-timeline.tsx:258-274` dumps
`JSON.stringify(patch.operation)` verbatim. So a human is shown `{"clean_work_dir": true}`
next to an Approve button. Four of the five are `risk="needs_confirmation"`, so this gate is
on their only path. For `platform_unsupported` the screen is self-refuting: the rationale
says *"Re-running here won't help: run on an x86_64 host or a cloud backend"*
(`repair.py:110-114`) beside a button whose entire effect is to re-run here.

**`patch_applied` is not the bug.** `models.py:315-320` defines it as "enacted and the loop
proceeded to retry", explicitly not "the configuration was mutated". By that definition
`True` is correct. The defect is one level down: for `kind="env"`, **enactment is defined as
a no-op**. `apply_patch` (`self_heal.py:583-586`) merges the whole operation dict,
string-coerced, into `target.backend_options`; `nfconfig.py:71-98` reads exactly six keys
(`queue`, `region`, `partition`, `account`, `qos`, `time`) by named `.get()` and never
iterates the dict. On `backend == "local"` — the heal path's backend — it is never consulted
at all. `continue_=False` is structurally unreachable for an `env` or `retry` patch, so
`patch_applied=True` is guaranteed, not incidental.

This is **one layer below** the bug v0.49.0's `patch_applied` slice fixed: the flag is now
honest about enactment, but enacting a no-op still renders as a repair everywhere.

### Evidence it is real

- Verified live: `clean_work_dir`, `fix_permissions`, `relax_or_pin_env`,
  `use_native_arch_backend` appear in `src/contig/` **only** at their `repair.py` emit site
  plus the `cli.py:2692-2709` honest-scope docstring. `container_unavailable`'s
  `wait_seconds: 15` never reaches `backend_options` at all — `apply_patch` is a documented
  no-op for `kind="retry"` (`self_heal.py:549`) — and **there is no `sleep` or backoff
  anywhere in the retry path** (`self_heal.py:1350`, `:1173-1174`).
- The repo ranks this itself in two files: `FEATURES.md:251` ("**the highest-value C2 item
  outstanding**") and `CAPABILITY_ROADMAP.md:453`.
- The code says so out loud in three places: `repair.py:167-168` ("only a human can decide
  and do that safely"), `detect.py:124-125` ("a human must fix the path/ownership; retrying
  on the same host will not help"), `repair.py:112-113` ("Re-running here won't help").

### Evidence about who is harmed, stated against our own interest

**No user has ever hit any of these five.** Measured, not assumed:

- **Pending corpus: 0 of 20.** `runs/pending_corpus.jsonl` exists, is **0 bytes**, and its
  mtime (2026-07-29) postdates every real run (2026-06-21→23) by five weeks.
- **Real runs: 0 of 15.** Six carry a non-empty `repair_history`; the only classes ever
  assigned in the field are `oom`, `tool_crash`, `missing_index`, `unknown`.
- **Holdout support: 3 of 5 have none**, so `eval-guard`'s 92.3% carries no information about
  `conda_solve_failed`, `platform_unsupported`, or `container_unavailable`.
- **`platform_unsupported` is the sharpest case.** Its training case is sourced
  `live:realtest (2026-06-20)` and its `log_text` is byte-identical to a real `.command.err`
  — but the real run was diagnosed **`tool_crash`, `gave_up`**. The case's `events: [{exit:
  null}]`, which `detect.py:353` requires, was **authored**.

So this is **push, not demand-pull**, and now demonstrably so. The honest phrasing is that
organic frequency is unmeasured *because the instrument has recorded nothing* — not because
it was never installed. The harm today is to the integrity of the record and the corpus, not
to a person. That is a real harm (moat #2 is accumulated evaluation data), but it must not be
dressed as a user-facing win.

---

## Goals & Success Metrics

**G1 — No surface claims an enactment that did not happen.** Measured: for each of the four
advisory classes, an end-to-end test asserts `patch_applied is False`, `recovered is False`,
and that no surface renders "applied"/"Repaired".

**G2 — The one sound premise is genuinely enacted.** Measured: a test proves
`container_unavailable`'s retry waits the patch's `wait_seconds` through an injected clock,
and a `heal-guard` scenario asserts it through the real loop.

**G3 — The gate stops showing an operation dict for work Contig will not do.** Measured: a
test asserts `pending_approval.json` for an advisory carries guidance and evidence and **no**
`operation` promising machine action.

**G4 — `heal-guard` covers the classes honestly.** Target `covered_classes` **11 → 15**
(all five except `platform_unsupported`, which the driver cannot reach — see R-Open-2).
Guarded `outcome_match_rate` **stays 1.0**.

**G5 — A committed revisit trigger, because every metric above is self-referential.** G1–G4 all
reduce to "a test we wrote asserts behaviour we defined"; none distinguishes *made the record
honest* from *made the record differently-shaped*. Following the `no_progress` and `qc_anomaly`
precedent, this slice commits its own trigger in both directions:
- **(a)** If the **next 20 diagnosed failures** appended to the pending corpus contain **no**
  case in any of the five classes, the advisory abstraction is restated as taxonomy-only, and
  no further breadth is built for these classes on push alone. Counter: group
  `runs/pending_corpus.jsonl` by `failure_class` — no new instrumentation.
- **(b)** If `container_unavailable` fires and the enacted wait **does not** recover it, the
  wait is removed rather than lengthened — a longer guess would be the same unvalidated
  reasoning at a bigger number.

**Explicitly NOT a goal, and any claim otherwise would be false:**

- `eval-guard` **cannot move** and must be asserted unmoved at **92.3%**. Nothing here touches
  `detect.py` or any corpus; further, the pending-corpus append (`self_heal.py:1096`) happens
  **before** `propose` (`:1106`), so proposer changes write zero bytes to the corpus.
- **The recovery rate does not improve.** `recovery_rate` will move on **corpus composition**
  (new scenarios), not on loop behaviour, and it is informational-only and never guarded. It
  must be disclosed as composition, exactly as the catalog-coverage slice disclosed its own.
- **This recovers nothing new for a user** except a transient Docker-daemon blip.

---

## Users & Scenarios

Contig's ICP (lone computational biologist; wet-lab scientist who cannot code). The scenario
that matters is the **approval gate**, because that is where a human is asked to act on a
false promise:

> A run fails on a full disk. Contig pauses and shows: *"Out of disk; clean the work directory
> to reclaim space, then retry"* with `{"clean_work_dir": true}` and an Approve button. The
> user approves, believing Contig will reclaim space. Contig reclaims nothing, re-runs, fails
> identically — and the run page then reports the attempt as a repair that was **applied**.

The wet-lab persona is precisely the one who cannot tell that the second failure is the same
failure. That is the cost of the status quo, and it does not require the class to be common
to be worth fixing — it requires only that it be reachable.

---

## Requirements

### Must have

**R1 — A new `Patch.kind = "advisory"`.** Widens the Literal at `models.py:300`. An advisory
is a diagnosis plus human-executable guidance; it is **not** machine-applicable. Chosen over
adding a field because a new *field* on `Patch`/`RepairStep` is a **fifth signature break**,
while a new *enum member* is not (see T3).

**R2 — Four classes become advisory**, keeping their rationales (which were always advice):
`disk_full`, `permission_denied`, `conda_solve_failed`, `platform_unsupported`. Their inert
operations (`clean_work_dir`, `fix_permissions`, `relax_or_pin_env`,
`use_native_arch_backend`) are removed, not reassigned.

**R3 — An advisory can never be recorded as enacted.** `apply_patch` gains an explicit
advisory branch, and `_apply_patch_and_maybe_build` returns `continue_=False` — a return that
is *currently unreachable* for `env`/`retry`. Because `patch_applied` is sourced solely from
`continue_` (`self_heal.py:1164-1165`, `:1208`, `:1264-1268`), `patch_applied=False` then
holds **by construction, not by review** — the same standard the v0.49.0 slice set for itself.

**R4 — The advisory gate still pauses, and records an honest outcome.** The human reads the
guidance, fixes the problem themselves, approves, and the retry runs.
- New outcome literal `advisory_acknowledged_and_retried`: Contig observed an acknowledgement
  and a retry, and enacted nothing. **The name is deliberately observational.** An earlier
  draft used `retried_after_manual_fix`, which asserts a fact Contig cannot verify — it never
  observes whether the human fixed anything. Every other honest literal here is observational
  (`approval_timed_out`, `rejected_by_user`, `gave_up_at_ceiling`, `qc_verdict_flagged`); this
  one must be too, or we replace one unverifiable claim with another.
- `patch_applied=False`, therefore `recovered=False` (`heal.py:186-187`) — the recovery is
  attributed to the human, which is what actually happened.
- Reject/timeout paths unchanged (`rejected_by_user` / `approval_timed_out`).
- Precedent: `qc_verdict_flagged` was deliberately **not** folded into `gave_up`, because
  `gave_up` means "we tried a fix and lost" (`self_heal.py:77-82`). Same argument here.

**R5 — The gate stops promising machine action.** `_write_pending_approval` must not serialize
an `operation` for an advisory, and `repair-timeline.tsx:258-274` must not render one. The
human sees the diagnosis, the evidence, and what *they* need to do.

**R6 — `container_unavailable` genuinely waits.** `wait_seconds` becomes load-bearing: the
retry sleeps through an **injected clock seam** so CI never really sleeps. Direct in-repo
precedent: the stall watchdog already takes `sleeper: Callable[[float], None] = time.sleep`
(`runner.py:673`). The seam must be threaded through `self_heal_run` **and** `heal.py`'s
evaluator (`:105-116`, wired `:174`), or no scenario can cover it. Risk stays `safe`; no gate
change. Its diagnosis stays distinct from `container_pull_failed` — the two detector branches
have disjoint needles and separate fixtures (`detect.py:136-167`, `tests/test_detect.py:43-55`).

**R7 — Correct the two false statements**, independent of everything above:
- `self_heal.py:547-548` — "string-coerced so it rides into the generated config" is false for
  every backend.
- `tests/test_self_heal.py:1219-1223` — the same falsehood in a comment; the assertion beneath
  it is correct.

**R8 — Rewrite the pinning guard honestly, in the same commit.**
`tests/test_repair.py:230-282` fires in both directions by design, and its own docstring
forbids deleting it for green. After this work `_INERT_OPERATIONS` is empty — four operations
withdrawn (assertion 2) and `wait_seconds` consumed (assertion 3) — so the guard becomes
vacuous and must be **retired deliberately**, with `cli.py:2692-2709` corrected in the same
commit. Replace it with a guard that pins the *new* contract: advisory patches carry no
machine-applicable operation, and `wait_seconds` **is** consumed.

**R9 — Both dashboard repair surfaces move together.** They currently disagree on source of
truth: `wasRepaired` reads `patch_applied` (`derive.ts:40-42` → `runs-table.tsx:196-203`, the
only user-visible "Repaired" badge in the product), while the timeline reads only the outcome
literal (`repair-timeline.tsx:177`). Fixing one and not the other leaves the runs table and the
run page telling different stories about the same step.

**R10 — Satisfy the pinned dashboard outcome contract.** `repair-truthfulness.spec.ts` asserts
`LIVE_OUTCOMES.length === 18` (`:112`) and that `OUTCOME_META` keys equal `LIVE_OUTCOMES`
exactly (`:121`), with underscore-free labels (`:116`) and a declared family (`:140-142`);
`:144-148` forbids reusing `qc_verdict_flagged`'s amber. Adding `retried_after_manual_fix`
requires the map entry, the family list at `:48-77`, and the count 18 → 19 — together.

### Should have

**R11 — `heal-guard` scenarios for the four reachable classes**, driven through the real loop:
`disk_full`, `permission_denied`, `conda_solve_failed` (advisory-approved →
`retried_after_manual_fix`, `patch_applied=false`, `recovered=false`) and
`container_unavailable` (enacted wait). Refreeze `heal_baseline.json` as a deliberate act
(`--update-baseline`, never a hand-edit), disclosing that `recovery_rate` moved on composition.

**R12 — Record that withdrawing changes provenance.** The four inert operations are currently
written into `record.target.backend_options` and pinned by `tests/test_self_heal.py:1231`.
Removing them is a **bundle content change**, not only a proposer change, and must be stated.

### Nice to have

**R13 — File the two incidental defects found in the dig, without fixing them here:**
(a) `read_task_errors` hardcodes `Path(run_dir)/"work"` (`runner.py:1070`) while Nextflow is
given `target.work_dir` (`nfconfig.py:100`), so **the detector goes blind on a custom
`--work-dir`**; (b) `risk="destructive"` is a **no-op to the engine** — no code branches on it
and `--auto-approve` has no carve-out, so only the dashboard honors it.

---

## Technical Considerations

**T1 — Architecture fit.** Layer 2 (self-heal honesty). Nothing authors pipelines from
English; no wet-lab, clinical, or proprietary-data dependency. Consistent with `CLAUDE.md`.
It also repairs a contract violation: `Patch`'s own docstring calls it "a typed,
**machine-applicable** candidate fix" (`models.py:293-298`), and `ARCHITECTURE.md:417` says
patches are "typed operations … not free-text". The four env patches are neither.

**T2 — The enactment pattern `container_unavailable` must follow** (extracted from
`missing_reference`, `_recompress_reference`, the `IndexBuilder` family): a `Callable` type
alias with a shelling-out default, injected as a keyword arg and threaded through
`self_heal_run` *and* `heal.py`; run-scoped scratch so user files are never touched; wipe
scratch before each attempt; redirect rather than mutate; bound to one per run; an honest
branch table returning `(target, params, outcome, detail, cont)` where `cont` is the sole
source of `patch_applied`. For a sleep only the **seam and threading** obligations apply.

**T3 — Signature exposure: none, if we add no field.** `signing.py:55-64` signs
`record.model_dump(mode="json")` with no allow-list, so *every* field is signed. A new
**outcome string value** or a new **`kind` enum member** changes only future canonical bytes;
records already signed re-serialize identically and still verify. A new **field** on
`RepairStep`/`Patch` would be a fifth break. **R1/R4 are deliberately designed to avoid one.**
This must be verified by test, not assumed.

**T4 — Reproducibility.** `LaunchManifest` carries no `params` and no `backend_options`
(`models.py:401-432`), so nothing here perturbs replay. Removing the inert keys from
`record.target.backend_options` changes bundle *content* (R12) but not re-runnability.

**T5 — Engine scope.** Nextflow is the tested scope. On Snakemake, `backend_options` is never
read and `params` are ignored entirely (`snakemake.py:26-46`), so the advisory change is inert
there in the same way every `set_param` repair already is — worth stating, not fixing.

---

## Risks & Open Questions

**R-Risk-1 — This is push, not demand-pull, and the metrics that could flatter it cannot
move.** 0/20 and 0/15. `eval-guard` cannot move; `recovery_rate` moves only on composition.
The only defensible claims are: an over-claim is removed, one real fix is enacted, and
`heal-guard` gains honest coverage. Anything stronger is false.

**R-Risk-2 — We are building an abstraction for classes that never fire.** A new `Patch.kind`,
a new outcome literal, a pinned dashboard contract churned, four `repair.py` branches
rewritten — for five classes with zero field occurrences. Accepted knowingly: the repo ranks
it #1 for C2, the guard forces the decision eventually, and the cost is bounded by adding no
new field and no new risk tier.

**R-Risk-3 — `retried_after_manual_fix` is unfalsifiable from inside the loop.** Contig cannot
verify the human actually fixed anything; it only knows the human approved and the retry ran.
The literal must be worded and documented as *what Contig observed*, never as a claim about
what the human did.

**R-Risk-4 — Self-graded, again.** We author the scenarios for the classes we then grade, and
no real nf-core run happens in CI. Same disclosure as the `no_progress`, `qc_anomaly` and
catalog-coverage slices.

**R-Risk-5 — `container_unavailable`'s wait is unvalidated.** Whether 15s recovers a downed
Docker daemon is an empirical question the repo has no data on. We are enacting the *stated*
fix, not proving it works. Its `expected_signal` remains unverified by Contig.

**🔴 R-Open-0 — `--auto-approve` recreates the lie by another door. MUST be closed before
implementation.** `self_heal.py:1146-1174` applies the best-ranked gated patch with **no human
at all**, and has no carve-out for any risk tier. Under R4 as drafted, an advisory under
`--auto-approve` would be auto-"approved", the retry would run, and the loop would record
`advisory_acknowledged_and_retried` — when nobody acknowledged anything and nothing was fixed.
That is the same false claim this PRD exists to remove, re-entering through the unattended
path. It is also the path CI and any non-interactive user takes. Candidate resolutions:
- **(a) Auto-approve skips advisories.** An advisory is not applicable, so there is nothing to
  auto-apply; the loop gives up with the guidance recorded. Most honest; changes unattended
  behaviour for four classes (today they retry, wastefully).
- **(b) A distinct unattended literal**, e.g. `advisory_unattended`, recording that guidance was
  emitted with no human in the loop and no retry claimed.
- **(c) Advisory still retries under auto-approve**, but the outcome says only that a retry
  happened, asserting no acknowledgement.

**R-Open-1 — What does an advisory `Patch.operation` contain?** `operation` is a required
`dict[str, object]` (`models.py:301`). Options: `{}`, or a non-actionable descriptor. Must not
be shaped like a machine operation. *Decide in tech-plan.*

**R-Open-2 — `platform_unsupported` cannot be driven through `heal-guard`.** `detect.py:353`
requires a failed event with `exit is None`, while `AttemptSpec.exit` is a required `int`
(`models.py:543`) used both as the trace column and the executor return code (`heal.py:62`,
`:82`). Covering it needs an additive model/driver change, which prior slices treat as a
mechanism change requiring its own justification. **Proposed: leave it uncovered and record
the reason** (hence `covered_classes` 15, not 16). *Confirm in tech-plan.*

**R-Open-3 — Does the advisory gate need new dashboard copy?** `approval-gate.tsx:163` reads
"A safe fix was not available, so Contig is holding the run until you approve or reject this
repair. Nothing risky is applied without your say." For an advisory, *nothing at all* is
applied — the copy is misleading. Also `approval-gate.tsx:29-45` has its own `FAILURE_LABELS`
missing `disk_full` and `permission_denied`.

**R-Open-4 — The dashboard's `FAILURE_CLASSES` mirror is already stale** (`derive.ts:278-292`
omits `disk_full`, `permission_denied`, `download_failed`, `reference_not_bgzf`,
`missing_dependency`) and **no test pins it**. In scope to fix, or file separately?

---

## Out of Scope

- **Enacting `clean_work_dir`, `fix_permissions`, `relax_or_pin_env`, or
  `use_native_arch_backend`.** Each was assessed and rejected on evidence: `disk_full` has no
  free-space observer (no `statvfs` anywhere) and deleting the work dir destroys the
  `-resume` cache the retry depends on *and* regresses the shipped `contig resume`
  (`cli.py:2203`); `permission_denied`'s denied paths lie outside the run dir (both fixtures
  point at `/results`), so no redirect shape applies and the operation is unbounded and
  likely unprivileged; `relax_or_pin_env` has no Contig-side file to edit (nf-core owns the
  env YAMLs) and conda is never the default profile (`cli.py:672`); `use_native_arch_backend`
  cannot be expressed at all — `ExecutionTarget` has no host/architecture field, and a
  heal-time backend switch raises `ConfigGenerationError` where nothing catches it.
- **Changing any detector rule.** `detect.py` is untouched, so `eval-guard` cannot move. The
  soundness of `platform_unsupported`'s rule (`detect.py:411` concedes it "rests on a warning
  that appears on healthy tasks too") and the loose `conda`+`solve` heuristic
  (`detect.py:191-203`) are **filed, not fixed**.
- **Fixing the `destructive` risk-tier gap** or the `read_task_errors` work-dir bug (R13).
- **Any new `Patch` or `RepairStep` field** — deliberately avoided to prevent a fifth
  signature break.
- **Making `--auto-approve` destructive-aware.**

---

## Acceptance (test-first)

1. Each of the four advisory classes: `propose_patches` returns a `kind="advisory"` patch with
   no machine-applicable operation; through the **real** loop, approval yields
   `retried_after_manual_fix`, `patch_applied False`, `recovered False`.
2. `container_unavailable`: the retry sleeps the patch's `wait_seconds` via an injected clock
   (asserted, never really slept); a `heal-guard` scenario covers it.
3. `pending_approval.json` for an advisory carries guidance and evidence and no promising
   `operation`.
4. A pre-change signed record still verifies (no fifth signature break).
5. `eval-guard` asserted **unmoved at 92.3%**; `heal-guard` `outcome_match_rate` **1.0**,
   `covered_classes` 11 → 15, with the `recovery_rate` move disclosed as composition.
6. The retired inertness guard is replaced by one pinning the new contract.
