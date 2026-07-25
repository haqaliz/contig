# Understanding — feat stall-watchdog-no-progress (Phase 2 dig)

## What the work is really asking

Contig can only diagnose a run that **exits**. A run that **hangs** — a deadlocked tool, a
wedged network mount, a container that never makes progress — is invisible: `default_executor`
(`src/contig/runner.py:602`) is a blocking `subprocess.run`, so nothing observes a run in
flight, and the process sits there burning the user's compute until a human notices.

This slice adds the missing observer: a **heartbeat watchdog** that watches the run's own
`trace.txt` while it runs, terminates the run when it has made no forward progress for a
configured period, writes an honest stall message to `run.log`, and lets the existing
detect → diagnose → patch → retry loop classify it as `no_progress` and retry with `-resume`.

`no_progress` is the **last designed-but-unbuilt entry in the detector taxonomy**:
`docs/technical/ARCHITECTURE.md:203` specifies it ("heartbeat watchdog: no new tasks for N
minutes"), the `FailureClass` literal exists (`src/contig/models.py:278`), the frozen held-out
corpus already contains a case for it (`detector_corpus_holdout.jsonl:12`) — and no branch of
`diagnose_failure` has ever emitted it (`src/contig/cli.py:2603` says so in as many words).

---

## Affected areas (mapped)

### The execution path — where the watchdog goes

`run_pipeline` (`runner.py:879`) builds the command and calls the seam:

```python
cmd, artifact_path, parse_events = _build_engine_run(...)   # runner.py:894
returncode = executor(cmd, artifact_path)                   # runner.py:901
```

**The key finding: `artifact_path` IS `run_dir/trace.txt`** for Nextflow (`runner.py:842-846`),
and `-with-trace <artifact_path>` is already on the argv (`runner.py:793-806`). So the executor
seam **already receives the heartbeat file the watchdog needs**. `Executor =
Callable[[list[str], Path], int]` (`runner.py:567`) does **not** have to change — the stall
timeout can be bound by a **factory** that returns an `Executor` closure, exactly the way tests
already inject fakes.

After the executor returns, everything downstream already works for a terminated run:
`run_pipeline` captures the partial trace into a `RunRecord` and raises
`PipelineExecutionError` on a non-zero exit (`runner.py:903-928`), and `self_heal_run` catches
it and calls `diagnose_failure(events, log_text)` where `log_text` is `run.log` +
task errors (`self_heal.py:997-999`). **A watchdog-terminated run needs no new plumbing to
reach the detector** — it just has to leave a message in `run.log`.

### Retry semantics — already correct

`self_heal.py:981` passes `resume=resume or attempt > 1`, so **every retry already gets
Nextflow `-resume`**. A stall retry therefore resumes cached completed tasks instead of
restarting from zero. This makes retry-on-stall cheap and makes `risk="safe"` defensible.

### Process termination — precedent exists

`src/contig/lifecycle.py:69-90` `_terminate_process_group(pid, wait_seconds)` already does
SIGTERM → wait → SIGKILL over a process group, used by `cancel_run`. The comment
(`lifecycle.py:72-74`) notes runs are spawned detached so `pgid == pid`, and that killing the
group "reaps the Nextflow launcher and its Java/tool children together".

**Open question (see below):** the watchdog holds a `Popen` handle, not a detached pid. Killing
only the launcher risks orphaning Nextflow's Java/tool children. Spawning with
`start_new_session=True` and reusing `killpg` is the likely answer, but it changes Ctrl-C
signal delivery for the foreground case, and that trade needs a decision.

### Live progress reading — reusable

`src/contig/progress.py` already reads a **live, in-flight** run's `trace.txt` for `contig
status` / `contig watch`: `read_progress()` returns a `ProgressSnapshot` with
`tasks_completed`, `tasks_running`, `submitted` (`progress.py:118-166`). It keys on
`COMPLETED` / `RUNNING` statuses, which proves Nextflow's trace carries in-flight rows, not
just terminal ones. The stall fingerprint should be derived the same way rather than inventing
a second trace reader. `parse_trace_file` / `parse_resource_usage_file`
(`src/contig/events.py:101,140`) are the existing parsers; the peak-RSS slice established the
precedent of parsing the run's **own partial trace** at heal-decision time.

### Configuration precedent

`--approval-timeout` (`cli.py:321`, a `float` of seconds, default 1800) plumbs
CLI → `_dispatch_run` (`cli.py:414`) → `self_heal_run` (`self_heal.py:943`). A `--stall-timeout`
mirrors it exactly. Resource ceilings (`CEILING_MEMORY_GB` / `CEILING_TIME_H`, threaded as
`resource_ceiling`, `self_heal.py:959`) are the precedent for a bounded, overridable constant.

### The detector

`propose_patches` (`src/contig/repair.py:14`) needs a `no_progress` branch. The closest
precedents are `container_pull_failed` and `download_failed`, both `kind="retry"`,
`operation={"retry": True}`, `risk="safe"` (`repair.py:36-55,127-136`) — transient failures
where re-running is the fix.

---

## ⚠️ The load-bearing hazard: detector branch shadowing

This is the finding that most shapes the design.

`diagnose_failure` (`detect.py:39`) checks **OOM first, deliberately and unconditionally**:

```python
oom_exit = any(e.exit == 137 for e in events)
oom_lines = _matching_lines(log_text, ("out of memory", "outofmemoryerror", "killed", "oom"))
if oom_exit or oom_lines:      # detect.py:41-47
```

Two independent ways a naive watchdog gets **misclassified as `oom`**:

1. **The word "killed"** appearing anywhere in `run.log`. A message like "watchdog killed the
   stalled run" is classified OOM, not `no_progress`.
2. **`exit == 137` on any trace row.** If the watchdog SIGKILLs and a child tool's task lands
   in the trace with exit 137, the OOM branch fires on the events alone — *regardless of what
   the log says*.

So the slice must: (a) word the stall message to avoid `killed`/`oom`/`out of memory`/`time
limit`; (b) prefer SIGTERM (exit 143) over SIGKILL wherever possible and verify what the trace
records; and (c) decide where the `no_progress` branch sits. Placing it **before** OOM is
arguably correct — Contig's own watchdog message is a first-party fact about what Contig did,
strictly more reliable than a text heuristic over third-party tool output — but it reverses a
deliberate "OOM wins outright" comment, so it is a decision that must be made explicitly and
tested both ways.

The fallback today is `tool_crash` when any task failed (`detect.py:341-350`), which is exactly
what `holdout-no-progress-1` currently scores as.

---

## The honesty problem: false-positive stalls

A stall is **indistinguishable from a legitimately long single task** by trace inactivity
alone. STAR `genomeGenerate`, a large WGS alignment, or a slow container pull can each emit no
new trace row for hours. If the timeout is too aggressive, the watchdog kills real work.

Mitigations to settle in the PRD:

- The timeout must be **generous by default** and user-configurable.
- **Whether it is on at all by default** is the central product decision. Off-by-default
  (opt-in `--stall-timeout`) can never destroy legitimate work but delivers no unattended
  benefit unless asked for; on-by-default with a very large timeout raises unattended
  completion but risks terminating a legitimate long-running task. Note the mitigating fact
  that a retry `-resume`s, so the cost of a false positive is bounded (lost work on the
  in-flight task only) rather than catastrophic.
- The fingerprint should count **all** trace activity (row count, status transitions, mtime),
  not just newly-COMPLETED tasks, so a run that is slowly progressing through a long task is
  less likely to look dead.
- Retrying a *deterministic* hang just re-hangs; the bounded `max_attempts` budget (default 3)
  and an honest `gave_up` outcome must be the backstop. A stall that recurs is not "recovered".

---

### Executor seam blast radius — small

There is exactly **one production wiring site**: `cli.py:661` (`executor=default_executor` in
`_dispatch_run`). The other references are `self_heal.py:979` (pass-through),
`heal.py:122` (`_scripted_executor`, the heal-guard's scripted seam), and
`cli.py:1003` (`default_command_executor`, the unrelated `reproduce` seam). Tests inject
executors in **38 places**, all fakes — none of which break if the seam signature is preserved
and the watchdog is introduced as a factory returning an `Executor`.

## Eval / corpus blast radius

- `src/contig/data/detector_corpus_holdout.jsonl:12` — `holdout-no-progress-1` currently
  MISSES as `tool_crash`. Making the class reachable should flip it.
- `src/contig/data/holdout_history.jsonl` — held-out accuracy has been **flat at 0.846 (11/13)
  across 6 recorded points, v0.22.0 → v0.48.0**. This slice should move it to ~0.923, leaving
  only `qc_anomaly` unreachable. The committed baseline must be **deliberately refrozen**.
- `src/contig/data/heal_scenarios.jsonl` — 7 scenarios over 5 classes. Schema confirmed
  (verbatim `oom-heal`): `scenario_id`, `description`, `source`, `expected_class`, `attempts[]`
  (`{status, exit, log_text}` per attempt), `auto_approve`, `poll_decision`,
  `resource_ceiling`, `index_builder_result`, `max_attempts`, `assay`, `expected_recovered`,
  `expected_outcome`. A `no_progress` scenario is straightforward — **but its first attempt
  must not use `exit: 137` nor an OOM-flavoured `log_text`**, or it will be classified `oom`
  (the `oom-heal` scenario uses exactly `exit 137` + `"Process killed: out of memory"`).
- `src/contig/cli.py:2603` — the heal-guard docstring names `no_progress` as structurally
  unreachable; it must be updated when this ships, or the docs lie.
- **Both baselines pin a `corpus_sha`** — `holdout_baseline.json` (`corpus_size: 13`,
  `accuracy: 0.8461…`, `contig_version: 0.22.0`) and `heal_baseline.json` (`scenario_count: 7`,
  `outcome_match_rate: 1.0`, `recovery_rate: 0.571…`, `covered_classes` array of 5,
  `contig_version: 0.21.0`). Adding a scenario changes the sha → a loud mismatch warning until
  the baseline is deliberately refrozen with `--update-baseline`. `covered_classes` must gain
  `no_progress`.
- **Tests that will move:** `tests/test_eval_holdout.py`, `tests/test_heal_scenarios.py`,
  `tests/test_heal_guard.py`, `tests/test_cli_heal_guard.py`, `tests/test_guard_trend.py`,
  `tests/test_snapshot_history.py` — plus `tests/test_detect.py` and `tests/test_repair.py` for
  the new branch. The detector-corpus training set (`detector_corpus.jsonl`) should gain a
  `no_progress` case too, seeded like every prior class.
- **Release procedure (`RELEASING.md:10-20`):** the trend is grown deliberately at release
  time via `contig eval-guard --snapshot` / `heal-guard --snapshot`, whose updated
  `*_history.jsonl` files ride the release commit; CI never writes history. So the order is:
  ship the code → refreeze the baselines as a deliberate act in this PR → snapshot at release.

---

## Ambiguities / open questions for the PRD

1. **Default on or off?** (the central product decision — see above.)
2. **What is the default timeout?** ARCHITECTURE says "N minutes"; real bioinformatics tasks
   run for hours. A default in minutes would be wrong.
3. **SIGTERM vs SIGKILL, and process-group handling.** Does the watchdog `Popen` need
   `start_new_session=True` to reap Nextflow's children, and what does that cost for Ctrl-C?
   What exit code does a SIGTERMed Nextflow actually return, and what does it write into the
   trace? (Cannot be observed in CI — see below.)
4. **Is retry-on-stall `safe` or `needs_confirmation`?** Retry is cheap because of `-resume`,
   which argues `safe`; but a hang may be deterministic, which argues for a human.
5. **Does this apply to Snakemake?** `_build_engine_run` (`runner.py:812`) has a second engine
   path whose artifact is `stats.json`, not `trace.txt`. Nextflow-only is the honest scope
   (matching the peak-RSS and walltime slices, both Nextflow-only), but it must be stated.
6. **Where does the watchdog decision live?** A pure function (the `resource_sizing.py` mould)
   is required for CI testability; the `Popen` + poll loop around it cannot be exercised in CI.
7. **Does the stall message belong in `run.log` only, or also on the `RepairStep.detail`?**
   The walltime slice's "field instrument" precedent suggests recording the observed idle time
   so the default timeout can later be calibrated against real runs.

## Honest limits this slice will have to state

- **No real Nextflow in CI.** The watchdog's decision function can be fully unit-tested with an
  injected clock and on-disk trace fixtures, but the `Popen`/terminate path — and therefore the
  *actual* exit code and trace contents of a SIGTERMed Nextflow run — is **reasoned, not
  observed**, and needs a manual gate. This is the same posture as the `Fetcher`/`Installer`
  seams (`runner.py:567-586`).
- A watchdog proves **inactivity**, not **deadlock**. It cannot distinguish a hung tool from a
  slow one; it only enforces a policy the user configured.

## Strategic check (CLAUDE.md)

Squarely **Layer 2** — run / self-heal, the execution-reliability moat. No Layer-1 workflow
authoring, no wet-lab or clinical dependency, no new runtime dependency (stdlib `subprocess`,
`time`, `os`). It raises the ROADMAP Phase 1 headline metric (unattended completion,
`docs/ROADMAP.md:109`) and adds a labeled corpus class, which is moat #2.
