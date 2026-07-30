# PRD — heal-scenarios-catalog-coverage (C6: cover the honest half of the failure catalog)

Slice of **C6, Eval flywheel as a continuous loop** (`docs/technical/CAPABILITY_ROADMAP.md`
§C6). Follows slice 1 (`eval-guard`), slice 2 (`heal-guard`), the `no_progress` scenario, the
`qc_anomaly` scenario, and v0.49.0's `patch_applied` correction.

Inputs: `docs/planning/_card/issue.md` (brief), `understanding.md` (Phase 2 dig).

**Scope decision (review gate, 2026-07-30).** The brief asked for all nine uncovered classes.
The dig found that **five of the nine repairs are inert**, and that the honest fix for them
may be to stop proposing a patch at all rather than to implement one — which would flip every
expectation a scenario would freeze. Freezing five expectations we already suspect are wrong
is exactly what R16 forbids. So this slice covers the **four classes whose repair is honest**,
and the five inert ones are deferred to a C2 slice that must first decide propose-vs-don't.

---

## Problem Statement

`contig heal-guard` replays a frozen scenario set through the **real** `self_heal_run` loop
and fails CI when the loop's outcome-match rate regresses. It currently covers **7** failure
classes over 9 scenarios (`src/contig/data/heal_baseline.json`). `src/contig/repair.py`
proposes a patch for **14** classes.

So nine classes ship a live repair strategy that **nothing drives end to end**. The
`heal-guard` docstring already names exactly these nine as its honest-scope carve-out
(`src/contig/cli.py:2681-2695`), and the roadmap names the same gap
(`CAPABILITY_ROADMAP.md:1057`): *"the wider failure-class catalog (container, download, disk,
permission, missing-reference families) has no scenario yet."*

**Evidence the gap is real, not theoretical.** v0.49.0 shipped a correction to precisely this
kind of defect — five self-heal paths recorded a non-null patch and returned before
`apply_patch` ran, so a user who **rejected** a patch at the approval gate was told their run
was `Repaired` (`CHANGELOG.md:11-30`). That bug lived in loop paths no scenario exercised.

**And the Phase 2 dig found the next one before a line was written.** Five of the nine
repairs are **inert**, for two distinct reasons. Four are `kind="env"` patches whose
operation is merged into `target.backend_options` as a string (`self_heal.py:583-586`) and
read by nothing, because `nfconfig.py:71-98` consumes only
`queue`/`region`/`partition`/`account`/`qos`/`time`. The fifth is a `kind="retry"` patch, for
which `apply_patch` is a **documented** no-op, so its operation never reaches
`backend_options` at all.

| Class | Operation | Kind | Only occurrence | Consumed by |
|---|---|---|---|---|
| `disk_full` | `clean_work_dir` | `env` | `repair.py:145` | nothing — no work dir is deleted, no `statvfs` |
| `permission_denied` | `fix_permissions` | `env` | `repair.py:169` | nothing — no `chmod`/`chown` exists |
| `conda_solve_failed` | `relax_or_pin_env` | `env` | `repair.py:123` | nothing — no env spec is relaxed or pinned |
| `platform_unsupported` | `use_native_arch_backend` | `env` | `repair.py:109` | nothing — `target.backend` is unchanged, so the retry re-runs on the same host the patch's own rationale calls hopeless |
| `container_unavailable` | `wait_seconds: 15` | **`retry`** | `repair.py:50` | nothing — the loop never sleeps |

**`container_unavailable` is the weakest member of the five**, and the deferral rests on less
for it than for the other four: a bare retry is a legitimate fix for a transient runtime
outage, so only the decorative `wait_seconds` is dishonest, not the premise. On a stricter
reading it could have been covered alongside `container_pull_failed`. It is grouped with the
deferred five so the propose-vs-don't question is answered for the whole family at once.

The loop's story for these is propose → "apply" → `patch_applied=True` → retry → `Repaired`.
That is one layer below the bug v0.49.0 fixed: the flag is now honest about **enactment**, but
enacting a no-op still renders as a repair on every surface. `repair.py:166-168` already says
of `permission_denied` that *"only a human can decide and do that safely"* — so the open
question is whether these should propose a patch at all. **This slice does not answer it, and
therefore does not freeze it.**

### The four classes this slice covers

| Class | Patch | Why it is honest |
|---|---|---|
| `missing_reference` | `{"set_param": {"igenomes_ignore": True}}`, `needs_confirmation` (`repair.py:79-91`) | A real param mutation: merged at `self_heal.py:575-582`, reaches the re-run argv at `runner.py:1118-1119`, lands in `record.parameters`. |
| `reference_not_bgzf` | `{"recompress_reference": True}`, `needs_confirmation` (`repair.py:66-78`) | Really decompresses: `_recompress_reference` (`self_heal.py:754-835`) stream-decompresses to a scratch path and repoints `params["fasta"]`. |
| `container_pull_failed` | `{"retry": True}`, `safe` (`repair.py:36-45`) | An honest no-op patch where *the re-run itself is the fix*, documented as such at `self_heal.py:549`; the retry carries `-resume`. |
| `download_failed` | `{"retry": True}`, `safe` (`repair.py:129-138`) | Same shape, same honesty. |

## Who has this problem

Primarily **us** — engine-quality infrastructure, the moat per `CLAUDE.md` #2 ("accumulated
workflow-evaluation data"). It reaches users indirectly: every unguarded loop path is a path
where a future change can silently start lying about a repair, and the repair surface is what
a lone computational biologist reads to decide whether to trust an unattended run.

**Honest framing: this is push, not demand-pull.** No design partner asked. Organic frequency
of these classes in recorded runs is **unmeasured** (the `qc_anomaly` slice's precedent number
was 0 of 17 recorded runs under its bands).

## Goals & Success Metrics

| Goal | Metric | Target |
|---|---|---|
| Cover the classes whose repair is honest | `heal_baseline.json` `covered_classes` | **7 → 11** |
| Every remaining uncovered class has a recorded reason | classes with a `propose_patches` branch, no scenario, and no stated reason | **9 → 0** |
| No regression | guarded `outcome_match_rate` | stays **1.0** |
| Detector untouched | `eval-guard` held-out accuracy | **unmoved at 92.3%** |
| The finding is filed, not buried | named CHANGELOG finding + C2 follow-up for the 5 inert repairs | **1** |
| **Defects surfaced** | loop behaviors found by driving a previously-unguarded class that are wrong or inert, each recorded with a `path:line` and a disposition (fixed / filed / frozen-and-disclosed) | **≥ 1** (already met at PRD time: the 5 inert repairs) |

The last two rows carry the argument. `covered_classes` can be raised while learning nothing;
the justification for this slice is that untested paths hide defects (v0.49.0's precedent), so
the count of defects surfaced — not the count of classes — says whether it paid for itself. It
is already ≥ 1 before a line of code is written, and that finding is what narrowed the scope.

**Why 11 and not 16.** Of the 18 `FailureClass` values (`models.py:262-281`),
`missing_dependency` is reproduce-local and structurally outside this loop and `unknown` is a
non-target — both already declared out at `cli.py:2681-2695`. The five inert classes are
deferred with a stated reason. **No class is left uncovered without one.**

`recovery_rate` is informational-only and never guarded (`cli.py:2695`).

## Personas & Scenarios

- **Contig maintainer (primary).** Changes `self_heal.py` or `repair.py` and needs CI to say
  whether the change altered how a failure family is handled. Today CI is silent for nine of
  them; after this slice, for five — each with a reason a reader can check.
- **Lone computational biologist (indirect).** Runs unattended and reads "Repaired" on the
  dashboard. Whether that word is earned is decided in exactly these paths.

## Requirements

### Must-have

- **R1 — One frozen `HealScenario` per covered class** — `missing_reference`,
  `reference_not_bgzf`, `container_pull_failed`, `download_failed` — replayed through the
  **real** `self_heal_run` loop. The detector and `propose` are never stubbed (the standing
  contract, `heal.py:117-124`). Only executor / index-builder / poll are synthesized.
- **R2 — No seam may bypass the code under test.** The new field is a **named fixture
  directive**, never an injected result — the `qc_artifact` precedent (`models.py:563-569`:
  *"synthesizing the verdict would stop measuring the thing under test"*).
- **R3 — Additive and default-inert.** The new field defaults to `None`; the nine existing
  JSONL lines stay **byte-identical**; a back-compat test pins the default.
- **R4 — `HealScenario.fasta_artifact: Literal["plain_gzip"] | None = None`.** The driver
  writes a real plain-gzip (non-BGZF) FASTA and passes `params={"fasta": <path>}` to
  `self_heal_run`, so `reference_not_bgzf` reaches the **real** `_recompress_reference`
  (`self_heal.py:754-835`) instead of only its `reference_recompress_unresolvable` guard.
  This is the slice's only mechanism change.
  *(The `trace_exit` seam from the pre-gate draft is dropped with the class it served: it
  existed only to make `platform_unsupported` expressible, and a seam with no live consumer is
  the mistake the deferred bwa-mem2 index build already records.)*
- **R5 — Mutual discrimination.** Each new scenario must classify as its declared class
  against the real detector and must not steal, or be stolen by, any already-frozen line. A
  per-scenario test asserts `diagnosed_class`. Known thieves: the `oom` rule sits at position
  2 with bare `"killed"`/`"oom"` substrings (`detect.py:90`); `download_failed` (#8) is itself
  stolen by `container_pull_failed` (#7) if the log says `"failed to pull"`, and steals from
  `conda_solve_failed` (#9) on `Temporary failure in name resolution`; `missing_index` (#10)
  steals any absence line naming an index from `missing_reference` (#16); `missing_index`
  (#10) also nearly steals `reference_not_bgzf` (#19), which survives only because the real
  faidx log's `Could not build fai index` line carries none of #10's absence needles.
- **R6 — Every gated scenario sets `auto_approve` or `poll_decision`.** `missing_reference`
  and `reference_not_bgzf` are `needs_confirmation`; without one of these the driver falls
  back to the real file poll (`heal.py:101-115`) at the default `approval_timeout=1800`
  (`self_heal.py:959`) and the suite hangs for 30 minutes per scenario.
- **R7 — Refreeze is a deliberate act.** `uv run contig heal-guard --update-baseline`, never a
  hand-edit (`cli.py:2664`, `cli.py:2728-2743`). Guarded `outcome_match_rate` stays 1.0;
  expectations are never loosened to accommodate a scenario.
- **R8 — Correct the honest-scope docstring** (`cli.py:2681-2695`) with the code as ground
  truth: scenario count, covered list, and a not-covered list that now carries **a reason per
  class** — inert-repair (5), reproduce-local (`missing_dependency`), non-target (`unknown`).
- **R9 — Only `heal_*` data files move.** `detector_corpus.jsonl`,
  `detector_corpus_holdout.jsonl` and `holdout_baseline.json` stay untouched; `eval-guard`
  must be verified unmoved.
- **R10 — File the inert-repair finding as the reason for the narrowed scope.** A named
  CHANGELOG finding plus a C2 follow-up item whose first question is *propose-vs-don't*, not
  *how to implement*. Precedent: the `qc_anomaly` slice filed `patch_applied` against itself.
- **R11 — Triage rule for what a scenario exposes.** Expectations are derived by observing the
  loop, so "make it green" must never be the default response to a surprise. Every divergence
  between what the loop does and what it should do is classified before any expectation is
  written:
  - **Inert** (the operation is a no-op) → **do not cover the class in this slice**; record
    the reason and file it. This is the rule that produced the current scope.
  - **Wrong** (the loop mis-diagnoses, mis-records, or claims something contradicted by its
    own data — the v0.49.0 shape) → **stop**. Do not freeze it as expected. Either fix it here
    with the expectation corrected in the same commit (a guarded number is never laundered),
    or leave the class uncovered, record the reason, and file it.
  - **Merely surprising but defensible** → freeze, with the reasoning in the description.

### Should-have

- **R12 — Give-up variants** where the give-up is the sole honest terminal or is cheap
  (`rejected_by_user`, `approval_timed_out`, `gave_up` at budget exhaustion). Target corpus
  ~14-15 lines total.
- **R13 — Correct the stale trend prose.** `CAPABILITY_ROADMAP.md:1846` and `FEATURES.md:255`
  both call the held-out-accuracy trend pending; it shipped (`holdout_history.jsonl`,
  `heal_history.jsonl`, `--snapshot`/`--history`,
  `dashboard/components/eval/{holdout,heal}-history.tsx`).

### Nice-to-have

- **R14 — A gap-pinning test** asserting the five inert operations are consumed by nothing, so
  that implementing one turns the test red and forces the deferral reason to be revisited in
  the same commit.

## Technical Considerations

**Architecture fit.** Additive only. The loop, the detector, `propose`, `apply_patch`, the
guard's scoring, the baseline format, and the CLI contract are unchanged. One optional model
field and its driver wiring are the entire mechanism surface.

**Scriptability, established by the dig.** Three of the four classes are reachable from log
text alone — `missing_reference`, `container_pull_failed`, `download_failed`. The fourth,
`reference_not_bgzf`, is detected from log text but needs R4's fixture to get past
`_recompress_reference`'s first guard (`self_heal.py:783-810`), because `HealScenario` has no
`params` seam today and `heal.py:138` passes none.

**Unreachable here, deliberately.** `_is_ambiguous` is always False for these classes (single
candidate, confidence ≥ 0.85 — `self_heal.py:278-285`), so `chose_and_retried` and
`invalid_choice_rejected` cannot occur. `gave_up_at_ceiling` is `oom`/`time_limit`-only
(`self_heal.py:435-444`). `no_record` is unreachable through the driver (`heal.py:157-161`).

**Reproducibility / verification impact.** None to the run bundle, the signed record, or any
exit code. This slice touches evaluation machinery only. No signature break.

**Dependencies.** None new. Stdlib `gzip` for the R4 fixture.

**Effort shape.** One optional model field plus driver wiring (`models.py`, `heal.py`); ~5-6
new JSONL lines; ~7-9 new tests plus ~8 hardcoded literals to recompute in
`tests/test_heal_scenarios.py:437-486`; one baseline refreeze; the `cli.py:2681-2695`
docstring; and a docs commit. The three log-only classes are independent of each other and of
the R4 seam, so the work parallelizes cleanly. The schedule risk is not the code — it is R5's
discrimination check across ~14 lines, where a silent break to the guarded rate would come
from.

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Expectations are derived by observing the loop**, so the guard catches future drift, not present wrongness. | Inherent to a regression guard; stated plainly rather than mitigated. R11 is what keeps a known defect from being frozen — and it already cost this slice five classes. |
| 2 | A new line steals, or is stolen by, an existing one → guarded rate breaks. | R5 plus a per-scenario `diagnosed_class` assertion. Highest-risk step in the build. |
| 3 | R4's `params` wiring is a genuinely new driver capability (the driver has never passed params). | Keep it a fixture directive: the driver constructs the path, the scenario names only a shape. |
| 4 | `recovery_rate` moves again; the 7th trend point is not comparable (corpus composition changed). | Disclose, do not reset — `heal_history.jsonl` is append-only and no prior slice rewrote it. |
| 5 | Deferring five classes reads as the slice under-delivering against its brief. | It is the opposite, and the CHANGELOG must say so: the deferral is the finding. Covering them would have frozen five suspect expectations into CI. |

**Revisit trigger, both directions** (or the claim is unfalsifiable):

1. **If any of the five inert repairs is implemented or withdrawn**, R14's test turns red and
   the deferral reason must be revisited in that same commit — at which point those classes
   become coverable against corrected behavior.
2. **If the next 20 runs appended to the pending corpus contain no case whose diagnosed class
   is any of these nine**, the coverage claim is restated as *taxonomy* coverage only and no
   further breadth is added on push alone. The counter is the pending-corpus append the loop
   already performs on every diagnosed failure (`self_heal.py:1096`) — measurable today by
   grouping that file by `failure_class`, with **no new instrumentation**. Stated precisely
   because the `qc_anomaly` slice's "0 of 17 recorded runs" precedent shows the number is
   checkable after the fact and worth checking.

## Honest weaknesses in this PRD's own case

1. **Push, not demand-pull.** No user asked. The organic frequency of these classes is
   unmeasured.
2. **Synthetic throughout.** No real nf-core run, container registry, network, disk, or
   permission state in CI — consistent with every prior heal scenario, and no stronger.
3. **Self-graded.** We author the fixtures for the classes we grade, exactly as the
   `no_progress` and `qc_anomaly` slices disclosed of themselves.
4. **It recovers nothing new for a user.** It changes what CI *guards*, not what the engine
   *does*. The user-visible improvement is deferred to the C2 follow-up this slice files.
5. **`covered_classes: 11` still invites over-reading.** It means eleven classes have a frozen
   synthetic scenario. It does not mean the engine handles those failures well — and for the
   five it excludes, the engine demonstrably does not.
6. **The narrowed scope is a judgement, not a proof.** We suspect the five inert repairs
   should stop proposing rather than be implemented; we have not established it. If that
   suspicion is wrong, deferring them cost a release cycle of coverage.

## Out of Scope

- **The five inert classes** — `disk_full`, `permission_denied`, `conda_solve_failed`,
  `container_unavailable`, `platform_unsupported`. Deferred to the C2 follow-up (R10) that
  must first decide propose-vs-don't. Each carries its reason in `cli.py`'s docstring per R8.
- **Implementing or withdrawing any inert repair.** That is the follow-up, not this slice.
  This slice must not quietly become a mechanism slice.
- **The `trace_exit` seam.** Dropped with `platform_unsupported`; no live consumer.
- `missing_dependency` (reproduce-local, structurally outside this loop) and `unknown` (a
  non-target).
- Folding the unlabeled C1/C3 corroboration signals into one eval number — blocked on labeling
  design (`CAPABILITY_ROADMAP.md:1030`).
- Any change to the detector corpora, `holdout_baseline.json`, the signed record, the bundle,
  or any exit code.
- Real-world calibration of these classes' frequency.

## Acceptance (test-first)

1. Each new scenario, constructed in-code, replays through `run_heal_scenario` with
   `matched is True`, the expected `diagnosed_class`, `actual_outcome`, and `patch_applied` —
   no mocking of the detector, `propose`, or `apply_patch`.
2. `HealScenario.fasta_artifact` defaults to `None` and a scenario omitting it is unchanged in
   behavior; when `"plain_gzip"`, a real non-BGZF gzip FASTA exists on disk, `params["fasta"]`
   points at it, and the loop reaches `recompressed_reference_and_retried` through the real
   `_recompress_reference`.
3. Every shipped scenario still reproduces its declared outcome; `outcome_match_rate == 1.0`
   over the enlarged set.
4. `baseline.corpus_sha == sha256_file(scenarios_path)`, and `scenario_count` and the exact
   `len(baseline.covered_classes) == 11` match the refrozen baseline.
5. `uv run pytest && uv run contig eval-guard && uv run contig heal-guard` — CI-identical —
   passes, with `eval-guard` unmoved and the detector corpora untouched.

## Strategic check (`CLAUDE.md`)

Layer 2 throughout: this hardens the run/self-heal harness and its evaluation data, named in
constraint #2 as the moat. No Layer-1 workflow generation. No wet-lab, clinical, regulatory,
or proprietary-data dependency — inside the founder's edge. It gets better as base models
improve (a better detector is measured by exactly this guard), satisfying constraint #3.
