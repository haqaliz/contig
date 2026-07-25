# PRD — Heartbeat stall watchdog and the `no_progress` failure class

**Slug:** `stall-watchdog-no-progress` · **Branch:** `feat/stall-watchdog-no-progress/aliz`
**Capability:** C2 (self-heal breadth) with C6 (eval flywheel) headroom
**Status:** drafted 2026-07-25, pending review gate

---

## Problem Statement

**Contig can only diagnose a run that exits.** `default_executor` (`src/contig/runner.py:602`)
is a blocking `subprocess.run`, so nothing observes a run while it is in flight. A run that
**hangs** — a deadlocked tool, a wedged network mount, a container stuck on a socket — never
returns, never raises `PipelineExecutionError`, and never reaches the detector. It sits there
consuming the user's compute until a human notices.

This is the failure mode most directly opposed to the product's core promise. The ROADMAP's
Phase 1 headline metric is **≥70% unattended completion** (`docs/ROADMAP.md:109`); a hang is
precisely the case where "unattended" fails worst, because the run neither succeeds nor fails —
it consumes budget silently.

The gap is **designed and documented, never built**:

- `docs/technical/ARCHITECTURE.md:203` specifies the mechanism in the failure taxonomy:
  `no_progress` (heartbeat watchdog: no new tasks for N minutes).
- `src/contig/models.py:278` carries `no_progress` in the `FailureClass` literal.
- `src/contig/data/detector_corpus_holdout.jsonl:12` holds a frozen held-out case for it.
- **No branch of `diagnose_failure` has ever emitted it.** `src/contig/cli.py:2603` states it
  outright: "qc_anomaly and no_progress are currently structurally unreachable".

Consequence: held-out detector accuracy has been **frozen at 0.846 (11/13) across six recorded
trend points, v0.22.0 → v0.48.0** (`src/contig/data/holdout_history.jsonl`), with
`holdout-no-progress-1` misclassified as `tool_crash` every single time.

### Who has this problem

The Contig ICP running long pipelines on their own compute: the lone computational biologist
running sarek/rnaseq overnight on a lab workstation or an HPC allocation, and the core facility
running batches unattended. Both are exactly the users who cannot babysit a run — and both pay
for the hang in wall-clock time or cloud spend.

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| `no_progress` becomes reachable by the detector | `holdout-no-progress-1` classifies correctly; held-out accuracy moves **0.846 → ~0.923** (12/13), leaving only `qc_anomaly` unreachable |
| The self-heal loop can recover a stalled run | A new frozen heal scenario reaches its declared terminal outcome; `heal_baseline.json` `covered_classes` grows from 5 to 6 |
| A stalled run ends honestly, never silently | A terminated run yields a `no_progress` diagnosis with the observed idle time named — never a false success, never a misclassified `oom` |
| Zero regression when disabled | With the watchdog off (the default), behavior is **byte-identical** to today; the full existing suite passes untouched |

**Explicit non-metric:** we are **not** claiming a field recovery rate. No real hung Nextflow
run is exercised in CI (see Risks).

---

## User Personas & Scenarios

**Scenario A — the overnight hang (primary).** A researcher launches a sarek run at 18:00 with
`--detect-stalls`. At 22:00 a tool wedges on a stuck NFS read. By 23:00 the run has been
silent for an hour on every surface; the watchdog terminates it, records the stall, and the
self-heal loop retries with `-resume` — cached tasks are reused, so the retry picks up where
the run stopped. The researcher finds either a completed run or an honest
`no_progress` → `gave_up` verdict in the morning, instead of a process still hanging at 09:00.

**Scenario B — the false positive we must not cause.** A researcher runs a 14-hour WGS
alignment. The run is healthy but slow. **The watchdog must not touch it.** This is why the
heartbeat is composite (below) and why the feature is off by default.

---

## Requirements

### Must-have

**R1 — A pure, CI-testable stall decision.**
A pure function in the `src/contig/resource_sizing.py` mould decides "stalled or not" from an
injected clock plus an observed heartbeat fingerprint. No subprocess, no sleeping, no
filesystem coupling in the decision itself. This is the only part of the feature that CI can
honestly exercise, so it must carry the logic.

**R2 — A composite heartbeat fingerprint.**
A run is considered alive if **any** of these has changed since the last observation:

- `trace.txt` — mtime and size (the task-level signal `ARCHITECTURE.md:203` names),
- `.nextflow.log` — mtime and size (Nextflow's own executor polling; keeps writing during a
  single long task),
- `run.log` — size (Nextflow's periodic progress output).

A stall requires **all** surfaces silent for the full window. Rationale: a trace-only signal
goes dark for the entire duration of any one long task, which would make Scenario B a false
positive. The fingerprint must record **which** surfaces were silent, so the real idle-time
distribution can be calibrated later rather than guessed at again.

**R3 — A watchdog executor that preserves the `Executor` seam.**
`Executor = Callable[[list[str], Path], int]` (`runner.py:567`) does **not** change. The
watchdog is introduced as a **factory** returning an `Executor` closure that binds the timeout
and poll interval. Justification: there is exactly **one** production wiring site
(`cli.py:661`) but **38** test injection sites, all fakes — every one of which keeps working
untouched. `default_executor` remains as-is for the disabled path.

**R4 — Honest, bounded termination.**
On a stall: SIGTERM the run, wait a grace period, then SIGKILL if it has not exited, reusing
the semantics already proven in `lifecycle._terminate_process_group` (`lifecycle.py:69-90`).
The watchdog must reap **Nextflow's children** (Java + tool processes), not just the launcher —
requiring a process-group spawn. Termination happens **at most once per run attempt**.

**R5 — An honest stall message in `run.log`, worded to survive the detector.**
The message names the observed idle duration, the configured window, and which surfaces were
silent. It **must not contain** `killed`, `oom`, `out of memory`, or `time limit` — see R6.

**R6 — A `no_progress` branch in `diagnose_failure`, placed ahead of the OOM check.**
This is the load-bearing correctness requirement, and the dig resolved a real tension in it.

`detect.py:40-53` checks OOM **first and unconditionally**, matching the bare word `"killed"`
anywhere in the log **or** `any(e.exit == 137)` in the events. Two independent
misclassification paths exist: a stall message containing "killed", and a SIGKILLed child
leaving an exit-137 trace row. **The exit-137 path cannot be fixed by branch ordering below
OOM** — OOM wins outright on the events alone, whatever the log says.

**It must nevertheless be a text branch, not a new `diagnose_failure` parameter.** The frozen
held-out scorer calls the detector with exactly two arguments —
`detector(case.events, case.log_text)` (`corpus.py:50-104`) — and `holdout-no-progress-1`
carries **only** log text plus a `FAILED`/`exit: null` event. A stall flag threaded in from the
caller could never score that case, so it could never move the metric this slice exists to
move. The `Detector = Callable[[list[TaskEvent], str], Diagnosis]` signature (`detect.py:20`),
shared with the LLM detector, is fixed for the same reason.

So the branch must:
- **sit before the OOM check**, so a stall is classified on Contig's own first-party statement
  rather than on an incidental exit code. This reverses a deliberate "OOM wins outright"
  comment and is therefore an **explicit, tested decision**: the accompanying test must prove a
  genuine OOM (both the exit-137 and the "out of memory" text paths) still classifies as `oom`
  when no stall sentinel is present;
- key on a **narrow, first-party sentinel** that Contig alone emits, so no third-party tool
  output can trip it;
- classify **both** Contig's own emitted message **and** the frozen `holdout-no-progress-1`
  case, whose wording ("no new output or trace update", "terminated it as stalled", "no forward
  progress") the needles must generalize over. **The branch must not be fitted to the fixture
  string**: the test that matters is that our emitted message and the fixture classify through
  the same phrase-level needles;
- belong to the **`rules` detector**, which is what `self_heal_run` hardcodes
  (`self_heal.py:993`) — note the LLM detector could already emit `no_progress` today (it
  enumerates `get_args(FailureClass)`) but is never reached from the loop;
- leave every other class's classification **unchanged** (the held-out per-class table is the
  regression check). Under `diagnose_failure_strict` (`detect.py:374-407`) a `no_progress`
  diagnosis passes through undemoted — an explicit choice to confirm, not inherit silently.

**R14 — Do not break `contig cancel`.** *(New; from the dig, and the highest-risk finding.)*
`lifecycle.py:70-74` claims "runs are spawned detached, so the process group id equals the
pid" — **no code in `src/` actually detaches anything.** There is no `start_new_session`,
`preexec_fn`, or `setsid` anywhere; `default_executor` uses plain `subprocess.run`, so Nextflow
inherits the CLI's process group. `cancel_run` works today only because `status.json` records
`os.getpid()` — the **Contig process's own** pid (`self_heal.py:229`) — and `killpg` on that
shared group happens to reap the whole tree, Contig included.

Two consequences the implementation must handle:

1. A watchdog living **inside** that same process cannot `killpg` its own group — it would kill
   Contig itself. It must therefore spawn Nextflow into its **own** process group
   (`start_new_session=True`) and signal that group.
2. Doing so **removes Nextflow from the group `contig cancel` reaps**, so enabling the watchdog
   would silently break cancellation, orphaning a live Nextflow. The child's process-group id
   must therefore be recorded (e.g. into `status.json` alongside `pid`) and `cancel_run` taught
   to reap it, **or** an equivalent mechanism chosen — with a test proving cancel still works
   with the watchdog enabled.

This is a **pre-existing latent inconsistency** (the docstring already describes behavior the
code does not implement) that this slice is the first to actually collide with. Fixing the
docstring is in scope; re-architecting cancellation is not.

**R7 — A `no_progress` repair proposal.**
`propose_patches` (`repair.py:14`) gains a `no_progress` branch: `kind="retry"`,
`operation={"retry": True}`, **`risk="safe"`** — mirroring `container_pull_failed` /
`download_failed`. Auto-retry is defensible here because `self_heal.py:981` already passes
`resume=resume or attempt > 1`, so a retry **`-resume`s** and reuses completed tasks. Bounded
by `--max-attempts` (default 3), after which the loop records an honest `gave_up`. A
deterministic hang therefore costs at most N windows, then stops.

**R8 — Opt-in CLI surface, plumbed like `--approval-timeout`.**
- `--detect-stalls` (bool, **default `False`**) enables the watchdog.
- `--stall-timeout` (float seconds, **default `3600`** — one hour) sets the silence window.

Plumbed CLI → `_dispatch_run` (`cli.py:414`) → `self_heal_run` (`self_heal.py:943`) →
`run_pipeline`, exactly as `--approval-timeout` is today (`cli.py:321` → `cli.py:357` →
`self_heal.py:943`). `--stall-timeout` passed **without** `--detect-stalls` is **refused, not
silently ignored** (the repo's established posture, per the slice-7 `--rev` precedent).

**R9 — Off by default means byte-identical.**
With `--detect-stalls` absent, the executor is the unmodified `default_executor` and no new
code path executes. The entire existing test suite must pass **unmodified**.

**R10 — Eval corpus and baselines, refrozen deliberately.**
- A `no_progress` case joins the **training** corpus (`detector_corpus.jsonl`), as every prior
  class did.
- A `no-progress-heal` scenario joins `heal_scenarios.jsonl`. Its first attempt must use a
  **non-137 exit** and a **non-OOM-flavoured `log_text`**, or the scenario would classify as
  `oom` (the shipped `oom-heal` scenario is exactly `exit: 137` +
  `"Process killed: out of memory (exit 137)"`).
- `holdout_baseline.json` and `heal_baseline.json` are refrozen via `--update-baseline` as a
  **deliberate act in this PR**. Precisely (per the dig): the **held-out file is not edited**,
  so its `corpus_sha` is unchanged and the guard will report *improved*, not *regressed* — but
  the committed `accuracy`/`per_class` become stale, so `eval-guard --update-baseline` is
  required to lock in 12/13 and flip `no_progress` to `support=1/predicted=1/correct=1`. The
  **heal scenarios file is edited**, so its sha *does* change and
  `heal-guard --update-baseline` is mandatory; `covered_classes` gains `no_progress`.
- **Hardcoded test literals that must move** (they will fail otherwise):
  `tests/test_heal_scenarios.py:285-300` (`report.total == 7`, `report.healed == 4`,
  `recovery_rate == 4/7`) and `tests/test_heal_scenarios.py:303-319`
  (`baseline.scenario_count == 7`, plus a `corpus_sha == sha256_file(...)` assertion that fails
  immediately on any scenario edit until refrozen).
  `tests/test_eval_holdout.py:342-353` asserts the committed baseline passes with **no
  "changed" warning**, which is the mechanism that forces the refreeze discipline.
- `cli.py:2600-2607`'s docstring, which currently states `no_progress` is structurally
  unreachable, is corrected — otherwise the shipped docs lie. **`qc_anomaly` stays unreachable
  and must not be conflated with it** in that edit.
- The trend snapshot itself is **not** taken here: `RELEASING.md:10-20` grows
  `holdout_history.jsonl` deliberately at release time via `eval-guard --snapshot`. (Note
  `--update-baseline` also appends a history point, so it is a superset of `--snapshot` for the
  one run.)

**R11 — Nextflow is the supported and tested scope; the mechanism is engine-agnostic.**
The `Executor` seam sits **above** the engine branch in `_build_engine_run` (`runner.py:813`),
so a watchdog there applies to Snakemake for free. But the signals differ: `run.log` is written
identically by `default_executor` for both engines, while `trace.txt` is Nextflow-only and
Snakemake's `stats.json` is written **only at completion** (`snakemake.py:26-46`), giving no
mid-run progress signal at all.

Therefore: the fingerprint reads whichever surfaces exist and degrades naturally; we **claim
and test Nextflow only** (matching the peak-RSS and walltime slices). A Snakemake run with the
watchdog enabled falls back to `run.log` liveness alone — which must be **stated as untested**,
not advertised as support and not silently refused.

### Should-have

**R12 — Telemetry as a field instrument.**
Record the observed idle seconds, the configured window, and which surfaces were silent into
`RepairStep.detail`, following the walltime slice's explicit "field instrument" precedent. The
1-hour default is **reasoned, not calibrated**; this is the mechanism by which it can later be
calibrated against real runs rather than re-guessed.

### Nice-to-have (this slice or the next)

**R13 — A committed revisit trigger.** State in the shipped record what would change the
default posture: the first real report of a false positive (loosen/keep off), or N real stalls
recovered (consider on-by-default).

---

## Technical Considerations

### Architecture fit — the plumbing already exists

`run_pipeline` (`runner.py:879`) passes `artifact_path` — which **is** `run_dir/trace.txt` for
Nextflow (`runner.py:842-846`) — directly into the executor seam (`runner.py:901`). The
watchdog therefore already receives the heartbeat file it needs, with no signature change.

Downstream needs **no new plumbing at all**: a terminated run exits non-zero, `run_pipeline`
captures the partial trace into a `RunRecord` and raises `PipelineExecutionError`
(`runner.py:903-928`), and `self_heal_run` catches it and calls
`diagnose_failure(events, log_text)` with `log_text` = `run.log` + task errors
(`self_heal.py:997-999`). The watchdog only has to leave its message in `run.log`.

### Reproducibility and verification impact

**None by design.** No `models.py` change is required for the core (`RepairStep.detail` is a
free-text field that already exists). No verdict, QC, exit-code, or signing contract changes.
The launch manifest gains at most the watchdog settings; the watchdog **must not** bake a
scratch path or a runtime-derived value into `launch.json` in a way that breaks
`rerun`/`resume` re-derivation — the standing contract from the STAR-index and
GTF-harmonization slices.

### Dependencies

Stdlib only (`subprocess`, `os`, `signal`, `time`, `pathlib`). No new runtime dependency —
consistent with the repo's deliberate `pydantic`/`typer`/`cryptography`-only contract.

### Prior art reused

| Reuse | Where |
|---|---|
| SIGTERM → grace → SIGKILL over a process group | `lifecycle.py:69-90` |
| Live in-flight trace reading | `progress.py:118-166` (`read_progress`) |
| Pure decision function + injected observation | `resource_sizing.py` (peak-RSS / walltime slices) |
| Injected seam, real path manual-gated | `Installer` / `Fetcher` (`runner.py:567-586`) |
| Timeout plumbed CLI → loop | `--approval-timeout` (`cli.py:321`, `self_heal.py:943`) |
| Opt-in flag gating a side effect | `--allow-install`, `--allow-fetch` |

---

## Risks & Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| **False positive kills legitimate work.** A slow task is indistinguishable from a hang by inactivity alone. | High | Off by default (opt-in); composite heartbeat so a healthy long task still looks alive; retry `-resume`s, bounding the loss to the in-flight task. **Accepted, eyes open**, with the first real report as the revisit trigger. |
| **OOM branch shadowing.** `"killed"` in the log or an exit-137 trace row misclassifies a stall as `oom`. | High | R5 message wording + R6 branch placement, each with its own test. Prefer SIGTERM; treat SIGKILL's trace footprint as an explicit test case. |
| **No real Nextflow in CI.** The `Popen`/terminate path — and therefore the *actual* exit code and trace contents of a SIGTERMed Nextflow run — is **reasoned, not observed**. | High | Pure decision function fully unit-tested with an injected clock and on-disk fixtures; the subprocess path asserted for shape only and covered by a **manual pre-merge gate**. Same posture as `Fetcher`/`Installer`. **This limit must be stated in the shipped record, not softened.** |
| **The 1-hour default is uncalibrated.** No measurement of real inter-heartbeat gaps exists. | Medium | Off by default, so no user is exposed unasked; R12 telemetry exists precisely to replace the guess with data. |
| **Process-group spawn changes signal delivery.** `start_new_session=True` detaches the child from the terminal's process group, altering Ctrl-C behavior for a foreground `contig run`. | Medium | **Open question O1.** |
| **A deterministic hang re-hangs on retry**, burning the attempt budget. | Low | Bounded by `--max-attempts`; terminal `gave_up` is honest, not dressed as recovery. |
| **The watchdog can hang on the very failure it detects.** `stat()` against a hard-mounted, unresponsive NFS path blocks in uninterruptible sleep — and "wedged network mount" is a headline stall cause. A naive poll loop that `stat()`s `trace.txt` on that mount **freezes with the run**, detecting nothing. | High | **Open question O5.** Options: keep the observation off the run's own filesystem where possible, treat a blocked observation as its own signal, or accept and document the limit. Must not be discovered after shipping. |
| **`-resume` correctness after a hard kill.** A SIGKILLed task may leave a partially-written output in the work dir; the retry's `-resume` must not treat it as cached-complete. | Medium | Nextflow's `.exitcode`-based caching is believed to reject a task with no valid exit code, so a killed task should re-run — **an assumption to verify, not assert** (part of the manual gate, O2). |
| **Enabling the watchdog silently breaks `contig cancel`.** Detaching Nextflow into its own process group (required so the watchdog does not kill Contig itself) removes it from the group `cancel_run` reaps — orphaning a live Nextflow after a "successful" cancel. | **High** | **R14.** Record the child's pgid and teach `cancel_run` to reap it; test cancel with the watchdog enabled. Rests on a **pre-existing** inconsistency: `lifecycle.py:70-74` documents detached spawning that no code performs. |
| **Race with `contig cancel`.** A human cancelling while the watchdog is mid-termination could produce two terminal states or a confusing status. | Low | Termination is at-most-once per attempt (R4); the interaction needs one explicit test. |
| **Stall retries are bounded only by `max_attempts`.** Unlike index builds (`built_paths`, `self_heal.py:966`), nothing stops a stall from re-stalling up to 3 times — each costing a **full stall window** of wall clock (3 × 1h by default). | Medium | Accepted and documented; `gave_up` is honest. A stall-specific escalation (widen the window per attempt, or give up after two stalls at the same point) has **no precedent to reuse** and is deferred unless the plan finds it cheap. |

### Open questions

- **O1 — Ctrl-C semantics.** Does the watchdog's `Popen` need `start_new_session=True` to reap
  Nextflow's Java/tool children, and what does that cost for interactive Ctrl-C? Needs a
  decision in `tech-plan`, with the chosen trade documented.
- **O2 — What does a SIGTERMed Nextflow actually write?** Its exit code (143 expected) and what
  the partial trace records for in-flight tasks are **unobserved**. Drives R6's exit-137 test.
- **O3 — Poll interval.** Not user-facing, but it sets the granularity of the idle measurement
  and the cost of the watchdog loop. Propose a constant, not a flag.
- **O4 — Does `--detect-stalls` belong on `rerun`/`resume` too**, or only `run`? Consistency
  with how `_dispatch_run` is shared by `run` and `rerun` (`cli.py:414`). Related: `max_attempts`
  is persisted into `LaunchManifest` (`cli.py:643`) so `reproduce` replays it — decide whether
  the watchdog settings round-trip the same way, or are deliberately a **runtime-only** knob
  (defensible: a stall is an environment property, not a property of the analysis, and baking a
  timeout into a reproducible manifest would make replay depend on the original machine's
  I/O speed).
- **O5 — Can the watchdog observe a run whose filesystem is wedged?** See the risk table. This
  is the sharpest technical question in the slice: the most-cited stall cause (a hung mount) is
  also the one that can block the observer. A decision is required before implementation, and
  "we did not think about it" is not an acceptable shipped state.

### Honest weaknesses in this PRD's own case

Recorded rather than argued away, because the review gate should see them:

- **This is push, not demand-pull.** No design partner asked for it; **no real Contig run has
  ever been observed to hang.** The problem is real *in general* for long-running pipelines, and
  the architectural gap is documented — but the frequency is **unmeasured**, and this PRD does
  not claim otherwise. The `contig-next` ranking rule prefers demand-pull for new *assays*; this
  is a capability gap in the shipped taxonomy, which is why it still ranks — but the absence of
  a field report is a real weakness, not a footnote.
- **The headline metric is partly self-graded.** Moving held-out accuracy 0.846 → 0.923 means
  making a class reachable that we ourselves wrote the fixture for. It is a legitimate signal
  that a documented gap closed; it is **not** evidence that the watchdog helps a real user. The
  shipped record must not conflate the two.
- **Off by default plus no field reports means the code path may stay cold.** The value that is
  *unconditional* is the detector/corpus half: `no_progress` becomes classifiable, and a stall
  reported by any future run is diagnosed instead of mislabelled `tool_crash`. The watchdog is
  what makes that class *producible* by Contig itself. If the watchdog were dropped, the
  detector branch would only fire on stall text Contig never emits — which is why they ship
  together, and why R13's revisit trigger matters.

---

## Out of Scope

- **`qc_anomaly`**, the sibling structurally-unreachable class. Its honest trigger is the
  verdict object, not log text (QC runs at `_finalize`, not as a pipeline step). Separate slice.
- **Snakemake.** Nextflow-only (R11).
- **Calibrating the timeout on real data.** R12 ships the instrument; the calibration is a
  later slice with real runs behind it.
- **Distinguishing a hang from a slow task.** The watchdog enforces a user-configured policy;
  it does not and cannot detect deadlock.
- **A dashboard surface** for stalls.
- **Per-task stall detection** (killing one wedged task rather than the run). Nextflow owns
  task-level retry; Contig's seam is the run.
- **On-by-default operation.** Explicitly deferred pending field data (R13).
- **The C6 "fold C1/C3 signals into one eval number"** work — unrelated and blocked on its own
  labeling design.

---

## Acceptance (test-first)

1. **Pure decision:** given an injected clock and a sequence of heartbeat fingerprints, the
   decision function returns "stalled" only after the full window of silence across **all**
   surfaces, and "alive" if **any** surface changed. Deterministic, no sleeping.
2. **No false positive:** a fingerprint sequence where only `.nextflow.log` changes (the
   long-single-task case) is **never** stalled.
3. **Detector:** Contig's own emitted stall message classifies as `no_progress`; the frozen
   `holdout-no-progress-1` case classifies as `no_progress`; **an actual OOM still classifies as
   `oom`** (both the exit-137 and the "out of memory" text paths).
4. **Repair:** a `no_progress` diagnosis proposes a `safe` retry patch.
5. **Loop:** the new frozen heal scenario reaches its declared terminal outcome through the
   **real** `self_heal_run` loop (detector and `propose` never stubbed, per the heal-guard's
   standing contract).
6. **Disabled path:** with `--detect-stalls` absent, the executor is unchanged and the existing
   suite passes untouched.
7. **Refusal:** `--stall-timeout` without `--detect-stalls` exits non-zero naming the flag.
8. **Guards:** `contig eval-guard` reports ~0.923 against the refrozen baseline;
   `contig heal-guard` reports `no_progress` among `covered_classes`.

---

## Strategic check (`CLAUDE.md`)

Squarely **Layer 2** — run and self-heal, the execution-reliability moat. No Layer-1 workflow
authoring. No wet-lab, clinical, or proprietary-data dependency. No new runtime dependency. It
raises the ROADMAP Phase 1 unattended-completion metric and makes a labeled failure class
reachable for the first time, which is moat #2 (accumulated evaluation data). A better base
model makes the diagnosis of *why* a run stalled better; it never makes the watchdog redundant.
