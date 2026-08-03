# Understanding — inert-repair-honesty (C2)

Phase 2 deep-dig note. Grounded in a full read of `repair.py`, the relevant spans of
`self_heal.py`, `detect.py`, `nfconfig.py`, `models.py`, `cli.py`, plus measured corpus
evidence. `path:line` cited inline. Where a claim is inference rather than a read, it says so.

---

## What the work is really asking

`propose_patches` (`repair.py:14-175`) emits a patch for five failure classes whose stated
operation is performed by nothing. The loop then records propose → "apply" →
`patch_applied=True` → retry, and every surface renders that as a repair.

The brief (and `CAPABILITY_ROADMAP.md:453-479`) frames the decision as **propose-vs-don't**.
The dig says that framing is *nearly* right but is missing a third option, and that the five
do not form one class — they form **four different situations**.

---

## ⚠️ Finding 1: the over-claim starts at the approval gate, not at the report

The roadmap describes the harm as the record saying `Repaired`. That understates it, and it
is also imprecise: **there is no literal `"Repaired"` string in `src/`**. What actually
happens is worse, because it happens *before* the run is over and it involves the user:

`_write_pending_approval` (`self_heal.py:319-348`) serializes **both** the `rationale` **and**
the `operation` dict into `pending_approval.json` (`:342-343`). The human is shown
`{"clean_work_dir": true}` next to an Approve button. Four of the five are
`risk="needs_confirmation"`, so this gate is on their **only** path.

For `platform_unsupported` the result is self-refuting: the human is shown a rationale that
says *"Re-running here won't help: run on an x86_64 host or a cloud backend"*
(`repair.py:110-114`) beside an Approve button whose entire effect is to re-run here.

The downstream renders are then honest reports of a dishonest input:
`report.py:176-183` → `attempt 1: disk_full → env patch [applied] → approved_and_retried`;
`dashboard/components/run/repair-timeline.tsx:41` → `APPLIED`; `heal.py:186-187` →
`recovered = succeeded and any(step.patch_applied)`, counting it as a recovery.

## ⚠️ Finding 2: `patch_applied` is NOT the bug — it is correct by its own definition

`models.py:315-320` defines the field as *"enacted and the loop proceeded to retry"*, and
explicitly **not** "the configuration was mutated" and **not** "the patch worked".
`self_heal.py:1341-1345` repeats it. By that definition `True` is the right value.

The defect is one level down: for `kind="env"`, **enactment is defined as a no-op**.
`apply_patch` (`self_heal.py:583-586`) merges the whole operation dict, every key,
string-coerced, no whitelist, into `target.backend_options` — and `nfconfig.py:71-98` reads
exactly six keys (`queue`, `region`, `partition`, `account`, `qos`, `time`), each by a named
`.get()`. The dict is **never iterated**, so there is no unknown-key path at all: the merged
operation silently vanishes. On `backend == "local"` — the backend the heal loop uses —
`backend_options` is never consulted at all.

Confirmed structurally: `continue_=False` is **unreachable** for an `env` or `retry` patch
(every `False` return lives in the build/recompress helpers), so `patch_applied=True` is
guaranteed for these five, not incidental.

**Corollary:** any fix that only adjusts `patch_applied` would be wrong. The honest lever is
either (a) don't propose, or (b) make enactment real, or (c) stop calling this shape a patch.

## ⚠️ Finding 3: two shipped statements are false and must be corrected either way

- `self_heal.py:547-548` — `apply_patch`'s docstring: the operation is *"string-coerced so it
  rides into the generated config / re-run target"*. The "rides into the generated config"
  half is false for **every** backend.
- `tests/test_self_heal.py:1219-1223` — comment: *"it rides `backend_options` into the
  generated config"*. Same falsehood. The assertion beneath it (`:1231`) is correct; only the
  comment lies.

These are independent of the propose-vs-don't call and should be corrected regardless.

---

## The five are four different situations, not one

| Class | Risk | Gate | Why it is inert | Situation |
|---|---|---|---|---|
| `container_unavailable` | **`safe`** | **auto-applies, no human** | `kind="retry"`; `apply_patch` is a documented no-op (`self_heal.py:549`), so `wait_seconds: 15` is dropped | **A: premise right, enactment missing** |
| `disk_full` | `needs_confirmation` | pauses | `clean_work_dir` consumed by nothing | **B: enactment would fight `-resume`** |
| `permission_denied` | `needs_confirmation` | pauses | `fix_permissions` consumed by nothing | **C: advisory-shaped, code already says so** |
| `platform_unsupported` | `needs_confirmation` | pauses | `use_native_arch_backend` consumed by nothing | **C + inexpressible intent** |
| `conda_solve_failed` | `needs_confirmation` | pauses | `relax_or_pin_env` consumed by nothing | **D: near-unreachable trigger** |

### A. `container_unavailable` — the roadmap's assessment of this one is backwards

`CAPABILITY_ROADMAP.md:471-473` calls it *"the weakest member"*, on the grounds that only its
decorative field is dishonest. The detector says otherwise. Its needles (`detect.py:134-140`)
are `docker desktop is unable to start`, `cannot connect to the docker daemon`, `docker.sock`
— a **local container daemon that is down**, cleanly distinct from `container_pull_failed`'s
registry-pull failure. If the daemon is down, an *immediate* bare retry fails identically.
**The wait is the load-bearing part of the fix, and it is exactly the part that is dropped.**

This is also the only one of the five with a plausible local trigger: Docker Desktop
instability is a known issue on this development machine.

### B. `disk_full` — enactment is in direct conflict with `-resume`

Contig **does** know the work dir (`ExecutionTarget.work_dir`, `models.py:38`, written to the
config at `nfconfig.py:100`), and `shutil.rmtree` is already used elsewhere
(`self_heal.py:654`, `:813`). So deletion is expressible. But:

- Contig **never measures free space** — no `statvfs`, no `shutil.disk_usage` anywhere in
  `src/contig/`. It cannot verify the premise or the `expected_signal`
  (*"free disk space available"*).
- The loop retries with `-resume` (`self_heal.py:998`). The Nextflow work dir **is** the
  `-resume` cache. Deleting it guarantees the retry re-runs everything from scratch — on a
  volume that just ran out of space, having discarded the completed work.

`repair.py:143-144` already says this destroys data. Note also that `risk="needs_confirmation"`
rather than `"destructive"` — and the gate **never tests for `destructive`** (the literal
appears only in the `Patch.risk` union at `models.py:303`), so the two tiers are handled
identically today.

### C. `permission_denied` and `platform_unsupported` — the code already calls these human work

Both carry an in-code admission that the machine cannot fix them:

- `repair.py:167-168`: *"only a human can decide and do that safely"*.
- `detect.py:124-125`: *"a human must fix the path/ownership; retrying on the same host will
  not help."*
- `repair.py:112-113`: *"Re-running here won't help."*

For `platform_unsupported` the stated intent is additionally **inexpressible**. `target.backend`
is mutable (`ExecutionTarget` is unfrozen; `model_copy` already used at `self_heal.py:574`,
`:586`) and the plumbing to Nextflow exists (`runner.py:1155` re-renders per attempt;
`nfconfig.py:57` maps backend → executor). But the rationale offers *"an x86_64 host **or** a
cloud backend"*, and `ExecutionTarget` has **no host or architecture field** (`models.py:36-48`)
— there is no way to express "same `local` backend, different machine". Only the cloud half is
representable, and switching to `aws_batch`/`slurm` needs knobs the loop does not have
(`queue`+`region` / `partition`, `nfconfig.py:74-85`) plus an `s3://` work dir; missing knobs
raise `ConfigGenerationError`, a `ValueError` subclass that would **escape** the loop's
`except PipelineExecutionError` (`self_heal.py:1088`). *[inference — outer handler not traced.]*

### D. `conda_solve_failed` — the trigger is near-unreachable through a Contig-launched run

`cli.py:672`: `selected_profiles = profiles or ("docker" if input else "test,docker")`.
**Contig defaults to docker and never to conda.** `conda` is a legal `ContainerRuntime`
(`models.py:27`) and `nfconfig.py:41` can emit `conda.enabled = true`, so it is reachable only
if the user explicitly opts in. Contig also authors no conda env spec of its own — nf-core owns
those — so there is no Contig-side file for `relax_or_pin_env` to edit.

This is weaker than the bwa-mem2 "no live trigger" deferral (`CAPABILITY_ROADMAP.md:250-258`),
which is total; here it is opt-in-only. But the precedent for how to treat it is the same.

---

## Measured evidence for the "don't" side — no longer an assertion

Revisit trigger (b) at `CAPABILITY_ROADMAP.md:1287-1291` asks for the pending corpus grouped by
`failure_class`. Measured:

- **Pending corpus: 0 of 20.** `runs/pending_corpus.jsonl` exists, is **0 bytes**, and its mtime
  (2026-07-29) postdates every real run (2026-06-21→23) by five weeks. The counter has never had
  the opportunity to count. *(Blind spot worth recording: the append at `self_heal.py:1093-1105`
  is guarded by `if exc.record is not None`, so a trace-less failure is never counted — the
  roadmap's "no new instrumentation" counter does not mention this.)*
- **Real runs: 0 of 15.** Six of fifteen carry a non-empty `repair_history`; the only classes
  ever assigned in the field are `oom`, `tool_crash`, `missing_index`, `unknown`.
- **Holdout support: 3 of the 5 have none.** `conda_solve_failed`, `platform_unsupported` and
  `container_unavailable` have zero holdout cases, so `eval-guard`'s 92.3% carries **no
  information** about them.
- **`platform_unsupported` is the sharpest case.** Its training case is the rare one sourced
  `live:realtest (2026-06-20)` and its `log_text` is byte-identical to a real
  `.command.err`. But the real run was diagnosed **`tool_crash`, `gave_up`** — the case's
  `events: [{exit: null}]`, which `detect.py:355` requires, was **authored**. `detect.py:411`
  already concedes the rule *"rests on a warning that appears on healthy tasks too"*, and
  `diagnose_failure_strict` (`detect.py:431`) demotes it unconditionally.

So: this remains **push, not demand-pull**, and now demonstrably so. The honest phrasing is
that organic frequency is unmeasured *because the instrument has recorded nothing* — not
because it was never installed.

---

## The precedent for the honest fix already exists in this codebase

`qc_verdict_flagged` (`self_heal.py:77-82`) was deliberately **not** folded into `gave_up`,
because `gave_up` means *"we tried a fix and lost"* and reusing it would make the two
indistinguishable in the corpus. That is precisely the argument shape a withdrawn class needs.

Mechanically this is cheap: `RepairStep.outcome` is a plain `str` (`models.py:313`) with no
enum — `self_heal.py:79-82` notes this outright, which is why the constant exists.
`HealScenario.expected_outcome` is also `str` (`models.py:580`). **A new outcome literal needs
no Literal widening anywhere.** A new `Patch.kind` or `risk` tier *would* widen a Literal
(`models.py:300`, `:303`).

Also relevant: the loop's "recovery" outcomes `patched_and_retried` / `approved_and_retried` /
`chose_and_retried` are **default** outcomes reached by any patch that isn't a build or
recompress. Only `built_index_and_retried` and `recompressed_reference_and_retried` are earned
by work the loop actually performed.

---

## The third option the brief's framing omits

"Propose-vs-don't" is a binary over *whether a patch is emitted*. But four of the five are
`needs_confirmation`, i.e. they exist to **put a rationale in front of a human**. That has real
value — telling a user "you are out of disk, here is the evidence" is useful even when Contig
cannot fix it. What is dishonest is dressing that advisory as a machine-applicable `operation`
and then recording enactment.

So there are three candidate resolutions per class, not two:

1. **Enact** — build the real operation on the existing seam pattern.
2. **Withdraw** — stop proposing; give up with an honest, distinct outcome literal.
3. **Reclassify as advisory** — keep surfacing the diagnosis and its guidance to the human, but
   stop representing it as an applicable patch, and never record enactment or recovery.

Option 3 is what `permission_denied` and `platform_unsupported` look like they already *are*,
badly typed. It costs a `Patch.kind`/`risk` widening or a separate advisory shape — a real
design decision, and the main thing to settle in the PRD.

---

## Open questions for the PRD (decisions, not research)

1. **Per class, which of the three resolutions?** My reading of the evidence, offered as a
   starting position and not as a settled call:
   - `container_unavailable` → **enact** (a real bounded wait; premise is sound, cheap, and the
     one class with a plausible local trigger).
   - `disk_full` → **advisory** (measurable premise is absent and enactment fights `-resume`).
   - `permission_denied` → **advisory** (the code already says only a human can do it).
   - `platform_unsupported` → **advisory or withdraw**; its detection is separately suspect.
   - `conda_solve_failed` → **withdraw** (no Contig-side artifact to edit, near-unreachable
     trigger).
2. **Does the advisory shape need a new `Patch.kind`/`risk`, or a non-`Patch` channel?** This
   determines whether we widen a Literal and whether the gate must learn a new state.
3. **What does the gate do for an advisory?** Today every non-`safe` patch pauses for
   approve/reject. An advisory has nothing to approve. Does it still pause (useful: the human
   fixes the thing and then approves the retry), or does it become a give-up with guidance?
   If it still pauses, what is the honest outcome literal when the human approves — the retry
   *did* happen, but Contig repaired nothing.
4. **Signature exposure.** A new outcome value is a value change, not a schema change — but
   whether it perturbs `canonical_record_bytes` for signing users must be checked, not assumed
   (four disclosed breaks precede this). *Pending the surfaces dig.*
5. **How does the pinning test get updated honestly?** `tests/test_repair.py:230` is an
   AST-based guard asserting each operation is still emitted and referenced nowhere else. It
   goes RED by design the moment any of the five moves; it must be rewritten to pin the *new*
   contract per class, not deleted for green.
6. **Do the five then get `heal-guard` scenarios?** That was the stated downstream unlock
   (`CAPABILITY_ROADMAP.md:474-476`). Note `platform_unsupported` cannot be driven through the
   existing driver — `detect.py:355` needs `exit is None` while `AttemptSpec.exit` is a required
   `int` (`models.py:543`) — so covering it needs an additive driver change, which prior slices
   treat as a mechanism change requiring its own justification.

## Guardrail check

Squarely **Layer 2** (self-heal honesty). No wet-lab, clinical, or proprietary-data dependency.
Nothing here authors pipelines from English. Consistent with `CLAUDE.md`.

The moat argument is honest but should not be oversold: this **recovers nothing new for a
user**. It makes the engine stop claiming recoveries it did not perform, and — for
`container_unavailable` — enacts one small fix it currently only promises. The eval-data value
is that `heal-guard` can then cover these classes against behavior we believe.
