# PRD: self-heal-eval-guard (held-out outcome-match guard for the self-heal loop)

Status: reviewed, ready for tech-plan. Owner: aliz. Branch: `feat/self-heal-eval-guard/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff, 2026-07-07),
`docs/planning/_card/understanding.md` (Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md`
C6. Capability: **C6 (eval flywheel), slice 2 — the labelable half.**

Decisions settled at the review gate (2026-07-07): headline guard metric =
**outcome-match** (not raw recovery rate); a scenario matches iff the loop diagnoses
the **correct `failure_class` AND** reaches the **declared terminal outcome**; coverage
= the **7-scenario Core mix**; `--history` **deferred**.

## Problem Statement

Contig's moat is the self-heal loop (detect → diagnose → patch → retry) and the
verified verdict. We ship a regression guard for the **detector's classification
accuracy** — `contig eval-guard` (v0.17.0) fails the build if `diagnose_failure`
mislabels held-out failures below a committed baseline. But that guards only whether
Contig *diagnoses* a failure correctly. **Nothing measures or guards whether the loop
actually behaves correctly end to end** — whether a detected+diagnosed failure is
patched and retried to a healed run, or correctly given up on when it is unrecoverable.

That is the moat's biggest measurement gap. Whole-loop behavior is the headline
reliability surface: the Phase 1→2 gate is "≥70% unattended completion on the core
pipeline" (`docs/ROADMAP.md:109`) and the Phase 3 flywheel target is "measurable
improvement in self-heal" (`docs/ROADMAP.md:161`). A refactor of `self_heal.py`,
`propose_patches`, `apply_patch`, or the resource-sizing logic could silently change
loop behavior with every unit test still green — the tests assert individual scenarios,
but no single number tracks whether the loop, run end to end over a frozen set, still
diagnoses and resolves each failure as intended, and nothing fails CI when it drifts.

`CAPABILITY_ROADMAP.md:497-501` names this as C6's deferred next slice ("repair-loop
(whole self-heal) accuracy into one number"). Its C1/C3 half is blocked on a labeling
design (concordance/plausibility signals carry no ground-truth labels). **Self-heal
outcomes are cleanly labelable** (each scenario has a declared expected outcome), so
this slice carves off the unblocked half.

**Evidence it's real and buildable:** every seam a benchmark needs is already
injectable on `self_heal_run` (`self_heal.py:793`: `executor`, `index_builder`,
`poll`, `propose`, `auto_approve`, `resource_ceiling`, `max_attempts`), and
`tests/test_self_heal.py` already drives ~15 scripted fail-then-succeed scenarios
through exactly these seams. The scoring/guard/baseline machinery exists in
`holdout.py` + `compare_to_baseline` and needs a loop-scoped analogue. No incumbent
(Galaxy, Terra, Seqera, …) issues a self-heal correctness verdict at all, let alone
guards it (`FEATURES.md:61-74`).

## Goals & Success Metrics

- **G1 — Measure whole-loop behavior on a frozen set.** A new `contig heal-guard`
  runs a frozen set of synthetic injected-failure scenarios through the **real**
  `self_heal_run` and computes `outcome_match_rate = matched / total`, where a
  scenario **matches** iff the loop (a) diagnoses the scenario's `expected_class` and
  (b) reaches the declared terminal state — `recovered == expected_recovered` **and**
  the last `RepairStep.outcome == expected_outcome`. It also reports an informational
  `recovery_rate = healed / total` sub-metric and a per-`FailureClass` matched/total
  table. *Metric:* the command prints both rates + the table; a test asserts the
  computed `outcome_match_rate` equals the known scenario outcomes exactly.
- **G2 — Guard against regression.** `heal-guard` fails the build (`exit 1`,
  `REGRESSION: …`) when `outcome_match_rate` drops below the committed baseline
  (`heal_baseline.json`) minus a float tolerance, naming the deviating scenario(s).
  *Metric:* a test where one scenario is perturbed to deviate exits non-zero and names
  it; the unperturbed set exits zero.
- **G3 — Deliberate refreeze.** `--update-baseline` (re)writes the baseline as a
  reviewed act, never an automatic side effect of running the guard. *Metric:* a test
  shows the guard alone never mutates the baseline; `--update-baseline` does.
- **G4 — Honest labeling.** The scenario set carries `source="holdout:synthetic"`;
  the command output and the committed baseline both state the covered `FailureClass`es
  and the scenario count, and never render the number as a real-world/field recovery
  rate. *Metric:* review + a test asserting `covered_classes` is surfaced in the JSON
  output and the human summary says "synthetic".
- **G5 — No regression, deterministic, no network, no real pipeline.** The full suite
  (baseline **1176 passed, 1 skipped**) stays green; every scenario runs through
  injected seams — no nf-core run, no subprocess, no network. *Metric:* suite green;
  `heal-guard` runs in CI in <5s.

**Baseline honesty:** the committed `outcome_match_rate` is expected to be **1.0** (the
loop behaves as declared on every shipped scenario) — unlike `eval-guard`'s 0.833,
because a *correct give-up* is a **match**, not a miss. So the guard's job is to catch
any *drift from correct behavior*, and any single scenario deviating drops the rate and
fails CI. `recovery_rate` (≈0.57 for the Core mix, since 3 of 7 scenarios give up by
design) is **informational only** and is never guarded — it exists to show the
healed/gave-up split honestly.

## User Personas & Scenarios

The direct user is the **maintainer / CI** (the founder's own build workflow), not an
end researcher:

- **Maintainer refactoring the self-heal loop:** changes `propose_patches` or the
  resource-sizing math; `heal-guard` in CI catches a behavior drift (a scenario that
  now misdiagnoses, or heals where it should give up, or vice versa) that the
  per-scenario unit tests — each still green in isolation — do not surface as a single
  guarded number.
- **Buyer-facing trust signal (indirect, asserted not validated):** the committed
  baseline is evidence the self-heal loop is measured end to end and guarded against
  regression — moat #2 made concrete for the reliability surface, the way `eval-guard`
  is for diagnosis.

## Requirements

### Must-have (this slice)

- **R1 — `HealScenario` declarative schema (frozen JSONL).** A Pydantic model
  describing one injected-failure scenario as **data** (no Python callables):
  - `scenario_id: str`, `description: str`, `source: str` (`"holdout:synthetic"`),
    `expected_class: FailureClass` (the class the loop must diagnose),
  - `attempts: list[AttemptSpec]` — ordered per-attempt outcomes; each `AttemptSpec`
    carries a **single-task** trace row (`status`, `exit`) and the `log_text` the
    scripted executor writes on that attempt. (Single-task traces match
    `test_self_heal.py`; multi-task trace richness is deferred — see nice-to-have.)
  - seam config: `auto_approve: bool = False`, `poll_decision: "approve" | "reject" |
    "timeout" | None = None`, `resource_ceiling: dict[str,int] | None = None`,
    `index_builder_result: "success" | "fail" | None = None`, `max_attempts: int = 3`,
    `assay: str = "rnaseq"`,
  - expected terminal: `expected_recovered: bool`, `expected_outcome: str` (the terminal
    `RepairStep.outcome`).
- **R2 — Generic scenario driver over the REAL loop.** A function
  `run_heal_scenario(scenario, tmp_dir) -> HealScenarioResult` that synthesizes a
  scripted `executor(cmd, trace_path)` (and, when the scenario needs them,
  `index_builder` and `poll`) from the declarative `attempts`/seam config, then invokes
  the **real** `self_heal_run` with those seams. **`propose` (→ `propose_patches`) and
  the detector `diagnose_failure` are left at their defaults, never stubbed** — only
  `executor`/`index_builder`/`poll` are synthesized; stubbing the patcher or detector
  would gut the guard's value and is prohibited. It reads terminal state from the
  returned `RunRecord`: `recovered = RunSummary.from_events(record.events).succeeded`,
  the last `RepairStep.outcome`, and the diagnosed `failure_class` (from
  `record.repair_history`). It must catch the trace-less `PipelineExecutionError`
  (record `None`) and treat it as `recovered=False` with a sentinel outcome — never a
  crash.
- **R3 — `evaluate_heal(scenarios) -> HealEvalReport`.** Mirrors `evaluate_detector`:
  runs every scenario via R2, and for each computes `matched = (diagnosed_class ==
  expected_class) and (recovered == expected_recovered) and (actual_outcome ==
  expected_outcome)`. Tallies `total`, `matched`, `outcome_match_rate = matched/total`,
  `healed`, `recovery_rate = healed/total`, a per-class `matched/total` table
  (`HealClassScore`), and a `mismatches` list — each mismatch names the scenario and
  which of {class, recovered, outcome} diverged and how (expected vs actual).
- **R4 — `HealSnapshot` + `HealGuardResult` models + `heal.py` guard module.** New
  loop-named models mirroring `EvalSnapshot`/`HoldoutGuardResult` (do **not** overload
  the detector-named models — settled):
  - `HealSnapshot`: `timestamp, scenario_count, corpus_sha, outcome_match_rate,
    recovery_rate, per_class: dict[str, HealClassScore], covered_classes: list[str],
    contig_version`.
  - `HealGuardResult`: `scenario_count, outcome_match_rate, baseline_match_rate, delta,
    tolerance, regressed, improved, recovery_rate, corpus_sha, baseline_sha,
    sha_mismatch, has_baseline, mismatches`.
  - `src/contig/heal.py` with `default_heal_scenarios_path()`,
    `default_heal_baseline_path()`, `load_heal_scenarios()`, `evaluate_heal()` (or a
    sibling module), `save_heal_baseline()`, `load_heal_baseline()`,
    `compare_heal_to_baseline(...)` — the loop analogue of `holdout.py`, keeping the
    compare a **pure function** (delta / regressed / improved / sha_mismatch flags; the
    CLI decides exit).
- **R5 — Frozen scenario set + committed baseline.** `src/contig/data/
  heal_scenarios.jsonl` (the 7 Core-mix scenarios, R7) and `src/contig/data/
  heal_baseline.json` (one pretty `HealSnapshot`), following the `save_baseline`
  serialization idiom (`model_dump_json(indent=2) + "\n"`). The scenarios file is
  **never** the default of any training-corpus command (like the detector holdout).
- **R6 — `contig heal-guard` command.** Mirrors `eval-guard` (`cli.py:1579`): options
  `--scenarios`, `--baseline`, `--tolerance`, `--update-baseline`, `--json`. Behavior:
  load scenarios → `evaluate_heal` → sha the scenarios file → `--update-baseline`
  refreezes and returns 0 (`Baseline updated: outcome-match 100% over 7 synthetic
  scenarios; recovery 4/7; covered: <classes>`); else `compare_heal_to_baseline` →
  print human summary (`Heal-guard: outcome-match X% vs baseline Y% (delta ±Z.Zpp) over
  N synthetic scenarios; recovery M/N; covered: <classes>`) + any mismatch lines
  (scenario + what diverged) → **`regressed` → stderr `REGRESSION:` + `Exit(1)`**;
  `sha_mismatch` → loud non-failing warning; `improved` (rate rose above baseline, only
  possible after a prior below-1.0 baseline) → nudge `consider --update-baseline`,
  return 0; no baseline → nudge + `Exit(1)`. `--json` echoes
  `HealGuardResult.model_dump_json()`.
- **R7 — Core-mix coverage (7 scenarios, confirmed).** Spans both terminal outcomes and
  the reachable, injectable classes; every one asserts class + outcome:
  1. `oom` — attempt-1 `exit 137` + OOM log, attempt-2 success → **healed**
     (`patched_and_retried`).
  2. `time_limit` — attempt-1 walltime-kill trace/log, attempt-2 success → **healed**
     (`patched_and_retried`).
  3. `missing_index` (buildable) — `index_builder_result="success"`, build then
     success → **healed** (`built_index_and_retried`).
  4. `missing_index` (unresolvable) — unparseable index path → **gave-up**
     (`index_unresolvable`).
  5. `tool_crash` — `exit 1` segfault log, no patch → **gave-up** (`gave_up`).
  6. approval-gated **healed** — a gated patch, `auto_approve=True` →
     **healed** (`approved_and_retried`).
  7. approval-gated **gave-up** — `poll_decision="timeout"` → **gave-up**
     (`approval_timed_out`).
  `covered_classes = {oom, time_limit, missing_index, tool_crash}` (plus the
  approval-path outcomes) is enumerated in the baseline. Deferred classes (Out of
  Scope) are listed in `heal-guard --help` and the docs.
- **R8 — Tests-first, real seams via `tmp_path`.** No mocking of `self_heal_run`,
  `propose_patches`, or `diagnose_failure` — the driver invokes the real loop with
  synthesized `executor`/`index_builder`/`poll` only. Cover: each scenario's expected
  class + recovered + outcome; the aggregate `outcome_match_rate` and `recovery_rate`
  math; the guard regressed/improved/no-baseline branches; a perturbed scenario forcing
  a named `REGRESSION` exit 1; `--update-baseline` refreeze (and that the plain guard
  never mutates the baseline); sha-mismatch warning; and a determinism check (same
  scenarios → identical rates twice).
- **R9 — CI wiring.** Add `- run: uv run contig heal-guard` to
  `.github/workflows/ci.yml` immediately after the `eval-guard` step (`ci.yml:23`).

### Should-have

- `heal-guard --help` states plainly the number is over **synthetic** scenarios and
  lists covered + deferred classes.
- `contig_version` recorded in the baseline (as `holdout_baseline.json` does), so a
  drop is attributable to a code vs scenario-set change.

### Nice-to-have (explicitly later, not now)

- `heal-guard --history` trend over versions (`heal_history.jsonl`), and folding the
  outcome-match/recovery numbers into the shared eval history — **deferred** (settled).
- Multi-task trace fidelity in scenarios (sibling rows, per-process peaks).
- Coverage of more `FailureClass`es (see Out of Scope) as follow-on scenarios.

## Technical Considerations

- **Chokepoints / reuse:** new `src/contig/heal.py` (guard I/O + compare + driver +
  `evaluate_heal`, mirrors `holdout.py`/`corpus.py`); new models appended to
  `src/contig/models.py` next to `EvalSnapshot`/`HoldoutGuardResult`; the command in
  `cli.py` next to `eval-guard`; the CI step next to the `eval-guard` step.
- **The real loop is invoked, not mocked** (R2) — so the guard exercises
  `diagnose_failure`, `propose_patches`, `apply_patch`, resource-sizing, and the retry
  budget end to end. This is what makes it a *loop* guard rather than a second detector
  guard, and it is why the class-match check (settled) is meaningful: a scenario fails
  if the real detector misdiagnoses even when the terminal outcome coincidentally lands.
- **Reading the outcome:** `self_heal_run` returns a `RunRecord` with **no top-level
  status**. Recovery = `RunSummary.from_events(record.events).succeeded`; give-up =
  `record.verdict == "fail"` + last `RepairStep.outcome`; diagnosed class from
  `record.repair_history[*].diagnosis`. Trace-less failures raise
  `PipelineExecutionError(1, None)` — caught in R2.
- **Determinism / reproducibility:** scenarios are pure data; the driver is
  deterministic; the scenarios file is sha'd into the baseline (`corpus_sha`) exactly
  as the detector holdout is. No `Date.now()`/randomness in the scored path (timestamps
  stamped only at `--update-baseline`, as the detector baseline does).
- **No raw-read egress; no over-claiming:** synthetic fixtures only; the guard makes no
  correctness claim about biology, only about the loop's behavior on known scenarios.

## Data Model / Artifact Contracts

- **New models** (`models.py`, all additive): `AttemptSpec`, `HealScenario`,
  `HealClassScore` (`matched:int, total:int, rate:float`), `HealScenarioResult`
  (`scenario_id, diagnosed_class, recovered, actual_outcome, matched, divergence`),
  `HealEvalReport` (`total, matched, outcome_match_rate, healed, recovery_rate,
  per_class, mismatches`), `HealSnapshot`, `HealGuardResult`.
- **New data files** (`src/contig/data/`): `heal_scenarios.jsonl` (frozen, never a
  training-command default) and `heal_baseline.json` (single pretty `HealSnapshot`).
- **No change** to `RunRecord`, `RepairStep`, `FailureCase`, `EvalSnapshot`,
  `HoldoutGuardResult`, or the detector corpus.

## Risks & Open Questions

- **R-risk-1 (headline honesty):** a synthetic number can be misread as field
  reliability. *Mitigation:* `source="holdout:synthetic"`, "synthetic" in every output
  line + help text, `covered_classes` always surfaced, and the headline is
  *outcome-match* (behavioral correctness) not a "recovery %" that invites the
  misreading. Non-negotiable (G4).
- **R-risk-2 (coupling to loop-internal outcome strings):** scenarios encode expected
  terminal `outcome` strings (`patched_and_retried`, `index_unresolvable`,
  `approval_timed_out`, …). If those are renamed, scenarios must update. *Accepted:*
  they are already asserted verbatim in `test_self_heal.py`, so this is existing,
  contained coupling — and catching such a rename *is* a legitimate guard signal.
- **R-risk-3 (a real behavior change masquerading as a scenario break):** because the
  guard is outcome-match, a genuine intended behavior change (e.g. a new patch strategy
  that heals a previously-gave-up class) will fail the guard until the baseline is
  refreshed — by design. `--update-baseline` is the deliberate acknowledgement, and the
  diff in `covered`/rate is the review artifact.
- **Open — none blocking.** All review-gate decisions are settled (outcome-match,
  class+outcome, 7-scenario Core mix, history deferred).

## Out of Scope

- Folding the **unlabeled** C1 concordance / C3 plausibility signals into the guard
  (deferred — needs a labeling design; the roadmap's "one number" fold).
- Any **real-run / field** recovery metric or telemetry aggregation across real bundles
  (the separate "repair success-rate analytics" dashboard item, on real data).
- `heal-guard --history` and shared-eval-history folding (deferred — settled).
- `FailureClass`es not reachable by `diagnose_failure` today (`qc_anomaly`,
  `no_progress`).
- Failure kinds with **no injectable seam** in CI beyond `executor`/`index_builder`/
  `poll` (enumerated as deferred, not silently omitted): `bad_param`,
  `container_pull_failed`, `download_failed`, `disk_full`, `permission_denied`,
  `conda_solve_failed`, etc. — future scenarios.
- Any dashboard surface (`eval-guard`/`holdout` have none; CLI + CI only).
- Any Layer-1 (NL → workflow) surface.
