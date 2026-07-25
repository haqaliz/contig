# Card: feat stall-watchdog-no-progress (C2 self-heal breadth · C6 eval headroom)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/stall-watchdog-no-progress/aliz`

No GitHub issue — this unit of work came from `/contig-next` (cn), 2026-07-25. The
recommendation below is the source brief.

## Brief

Implement the heartbeat stall watchdog and the `no_progress` failure class — the last
designed-but-unbuilt entry in the detector taxonomy (`docs/technical/ARCHITECTURE.md:203`;
the `FailureClass` exists at `src/contig/models.py:278` but no `diagnose_failure` branch
emits it, per `src/contig/cli.py:2603`).

Scope:

- A pure, CI-testable stall decision function (in the `resource_sizing.py` mould) over the
  run's own partial `trace.txt` heartbeat.
- A `Popen`-based poll inside `default_executor` (`runner.py:602` is a blocking
  `subprocess.run` today — keep the `Executor` seam signature intact) that terminates a
  stalled run and writes an honest stall message to `run.log`.
- A narrow `detect.py` branch keyed on that message.
- A bounded retry-or-give-up repair with an honest give-up outcome.
- A seeded heal-scenario + corpus case.

**Caveat to dig on first:** the watchdog false-positives on legitimately long single tasks
(STAR `genomeGenerate`, large alignments emit no trace rows for hours), so the timeout must
be generous and configurable, and the detector branch must classify Contig's *own* emitted
message rather than being fitted to the frozen `holdout-no-progress-1` fixture.

No real Nextflow in CI — the subprocess path is manual-gated. Expect held-out detector
accuracy to move 0.846 → ~0.923 (`src/contig/data/holdout_history.jsonl` has been flat since
v0.22.0); refreeze the baseline deliberately.

## Why this was picked (from `/contig-next`)

- **The last designed-but-unbuilt entry in the detector taxonomy.** `ARCHITECTURE.md:203`
  specifies `no_progress` (heartbeat watchdog: no new tasks for N minutes);
  `models.py:278` carries the `FailureClass`; no branch in `detect.py` emits it.
  `cli.py:2603` states it: "qc_anomaly and no_progress are currently structurally
  unreachable".
- **The one C2 gap that is neither shipped nor blocked.** The other pending C2 items have
  documented blockers (`CAPABILITY_ROADMAP.md:326-336`): bwa-mem2 and classic-BWA
  build/redirect have no live trigger, CRAM↔BAM has no reachable trigger, corrupt/partial
  STAR is blocked. A hung task is the failure class that most directly burns a user's
  compute unattended — the ROADMAP Phase 1 headline metric (`docs/ROADMAP.md:109`, ≥70%
  unattended completion).
- **It moves a number that has not moved in six releases.**
  `src/contig/data/holdout_history.jsonl` pins held-out detector accuracy at 0.846 across
  v0.22.0 → v0.48.0, with `holdout-no-progress-1` missing as `tool_crash` every time;
  `CAPABILITY_ROADMAP.md:874` calls that "a deliberate gap that leaves headroom for the
  nudge to fire once those rules exist." One slice raises it to ~0.923, seeds a 6th
  heal-guard scenario class (`heal_baseline.json` covers 5), and reuses the `trace.txt`
  parser the peak-RSS slice already shipped.

## Alternates considered (not this card)

- `qc_anomaly`, the sibling structurally-unreachable class — the honest trigger is the
  verdict object, not log text (QC runs at `_finalize`, not as a pipeline step), and the
  natural repair is thin.
- C8 `contig reproduce` dashboard card — deferred in every C8 slice and unblocked, but
  surface work with thinner moat than a new recovered failure class.

## Related prior art in-repo

- `src/contig/resource_sizing.py` — the pure-decision-function pattern this slice mirrors
  (peak-RSS OOM sizing, walltime sizing).
- The peak-RSS memory-scaling slice (`CAPABILITY_ROADMAP.md:263-279`) — precedent for
  parsing the run's **own partial `trace.txt`** at heal-decision time.
- `src/contig/data/heal_scenarios.jsonl` / `heal_baseline.json` — the frozen heal-guard set
  (5 classes covered) this slice extends.
- `src/contig/data/detector_corpus_holdout.jsonl:12` — the frozen `holdout-no-progress-1`
  case that currently misses as `tool_crash`.
