# Understanding — `repair-success-analytics`

Phase 2 dig note. Grounded in the Phase 1 card (`docs/planning/_card/issue.md`) and
first-hand verification against the code **and against the 15 real run records** in
`/Users/aliz/dev/at/contig/runs` (gitignored, so not in this worktree — read by
absolute path per the `contig-worktrees` skill). Every claim below was executed, not
inferred.

## What the work is really asking

Ship the **cross-run aggregation** half of `FEATURES.md:216` ("Repair success-rate
analytics … Built data … cross-run aggregation still to build"): a command that walks a
runs directory and reports, across all runs, **auto-healed vs human-declined vs gave-up,
by failure class** — the input to `docs/ROADMAP.md:109`'s Phase 1 → Phase 2 exit gate
("≥70% unattended completion on the core pipeline"), which today **cannot be computed by
any command in the CLI**.

It is a **read-only analytic over artifacts that already exist**. It adds no
instrumentation — deliberately, matching the wording of the revisit trigger it serves
(`CAPABILITY_ROADMAP.md:617`: "counted by grouping `runs/pending_corpus.jsonl` by
`failure_class`, **no new instrumentation**"). It recovers nothing new for a user; it
makes the self-heal loop's field performance legible.

## The house pattern this must follow (verified)

`contig clusters` (`cli.py:3673`) and `contig coverage` (`cli.py:3707`) are the two
precedents, and they are consistent:

- **Pure, testable core in a module; thin Typer shell in `cli.py`.**
  `corpus.py:247 cluster_failures(cases) -> list[dict]`, `corpus.py:291 coverage_report(...)`.
- **Both render text *and* `--json`** — `tests/test_cli_insight.py` has
  `test_clusters_json_lists_clusters_worst_first` / `test_coverage_json_reports_totals_and_thin`.
- **Tests split in two**: `tests/test_corpus_insight.py` (pure functions) +
  `tests/test_cli_insight.py` (CLI surface). The house term for this family of commands
  is "insight".
- **`coverage` already ships thin-data honesty** ("thin-coverage flags under 3 cases",
  `FEATURES.md`), which is the precedent for the small-n disclosure this command needs.

Runs-side enumeration is already solved and must be reused rather than re-rolled:
`workspace.py:39 list_run_ids(runs_dir)` (missing dir → `[]`), `workspace.py:26
load_run(runs_dir, run_id)` (raises the domain error `RunNotFoundError`, not
`FileNotFoundError`), `workspace.py:21 bundle_dir_for`. `contig list` (`cli.py:2716`)
establishes the option: `--runs-dir`, `typer.Option("runs", ...)`.

## The three findings that shape the design

### 1. `patch_applied` cannot be read from the loaded model. It must be read from the raw JSON.

`models.py:322` declares `patch_applied: bool = False` — **not** `bool | None`. Pydantic
therefore fills `False` for every record written before v0.49.0. Measured across the real
corpus (raw-JSON key presence vs the loaded model):

```
VIA PYDANTIC (outcome, patch_applied)   VIA RAW JSON (outcome, key_present)
  ('patched_and_retried', False) 2        ('patched_and_retried', False) 2
  ('gave_up',             False) 4        ('gave_up',             False) 4
  ('stopped_for_confirmation', False) 1   ('stopped_for_confirmation', False) 1
```

**0 of 7 real repair steps carry the key.** So a naive aggregator reading
`step.patch_applied` reports **0% applied across the entire real corpus** — including the
two `patched_and_retried` steps, an outcome that is *by definition* enacted (the applied
family, per the `patch-applied-field` slice). The model's own comment sanctions the
default as an under-claim *for a single record* ("Defaults False so a pre-field bundle
under-claims rather than over-claims", `models.py:318-322`) — but an aggregate **rate**
built on it is not conservative, it is wrong, and it would report 0% for the number that
gates Phase 2.

**Consequence:** the classification is **three-state — applied / not-applied /
unknown-legacy** — and the third state is only detectable by inspecting the raw
`run_record.json` for **key presence**, not by reading the validated model. Counts for
the three states must be reported separately and never collapsed into one percentage.

### 2. The legacy fallback (derive applied-ness from the outcome literal) has a real hole.

For a legacy step the honest recovery is to derive applied-ness from the outcome literal
— the `patch-applied-field` slice notes such a map "is currently total" over the 18 live
literals (`CHANGELOG.md:869-876`), though it rejected the map *for the model field*
because a hand-maintained map silently defaults new literals to "not applied". Using it
**only for records that predate the field** is a different proposition: that set is
frozen and cannot grow.

But the real corpus contains `stopped_for_confirmation` (run `realtest2`) — a literal
emitted **nowhere in `src/`** and **deleted from the dashboard**
(`dashboard/components/run/repair-timeline.tsx:56`, asserted absent at
`dashboard/e2e/repair-truthfulness.spec.ts:128`). So the derived map has a live
counter-example in the data on day one. It must resolve to **unknown**, not to a guess.

### 3. The denominator is a trap: `succeeded` is derived from events, and zero events is vacuously green.

`RunRecord` has **no `status` and no `summary` field** (fields verified:
`run_id, pipeline, pipeline_revision, target, input_checksums, parameters,
container_digests, nextflow_version, contig_version, events, qc_results,
output_checksums, repair_history, resource_usage, reference_identity,
annotation_identity, harmonized_reference_direction, assay, sex_inference,
verification_inputs`). Success is derived: `models.py:156-158`

```python
failed = sum(1 for e in events if e.is_failure)
return cls(total_tasks=len(events), failed_tasks=failed, succeeded=failed == 0)
```

**`succeeded = (failed == 0)`, so an empty event list is `succeeded=True`.** This is the
same "green by construction" artifact the `patch_applied` slice called out for
heal-guard's old `recovered` (`CHANGELOG.md:889-896`). The real corpus, measured:

| run | succeeded | events | steps | outcomes |
|---|---|---|---|---|
| `_livetest2-proof` | True | 90 | 0 | — |
| `_slurm-livetest-proof` | True | 234 | 0 | — |
| `_x86-livetest-proof` | True | 92 | 0 | — |
| `dash-livetest` | True | 234 | 0 | — |
| `first-real` | False | 41 | 0 | — |
| `mvp` | True | **2** | 1 | `patched_and_retried` |
| `realdata-demo` | True | **2** | 0 | — |
| `realtest` | False | 5 | 1 | `gave_up` |
| `realtest2` | False | 5 | 1 | `stopped_for_confirmation` |
| `realtest3` | False | 5 | 1 | `gave_up` |
| `realtest4` | False | 5 | 2 | `patched_and_retried`, `gave_up` |
| `test-2026-06-21T21-29-17-491Z` | True | 234 | 0 | — |
| `test-2026-06-21T22-18-14-239Z` | True | 234 | 0 | — |
| `testpass` | True | **0** | 1 | `gave_up` |
| `variant-ok` | True | **1** | 0 | — |

Note `testpass`: **0 events → `succeeded=True`, while its only repair step is
`gave_up`.** A naive unattended-completion rate counts that as a success. Note also that
the directory mixes genuine runs with dev/demo/proof fixtures (`_*-proof`,
`dash-livetest`, `test-*`), so 9/15 = 60% is not a scientific completion rate by any
reading.

**Consequence:** the command must not print a bare headline percentage. Either the
denominator is explicitly defined and disclosed, or the output leads with counts and a
thin-data flag. This is the single biggest honesty risk in the slice, and it is the
question the PRD must settle.

## Affected areas

- **New pure module** (name TBD in the PRD; `corpus.py` is the wrong home — it operates
  on `FailureCase` corpora, not `RunRecord`s). Reuses `workspace.list_run_ids`/`load_run`
  plus a raw-JSON read for key presence.
- `src/contig/cli.py` — one new command in the "insight" family, `--runs-dir` +
  `--json`, mirroring `clusters`/`coverage`.
- `tests/test_cli_insight.py` + `tests/test_corpus_insight.py` — or new siblings named
  for this command; follow whichever the PRD picks.
- **No model change, no signed-payload change, no new dependency.** Read-only.

## Ambiguities / open questions for the interview

1. **Denominator.** What exactly is "unattended completion"? Candidates: (a) succeeded
   with an empty `repair_history`; (b) succeeded with no human-decision outcome in the
   history; (c) succeeded AND `any(patch_applied)` (heal-guard's `recovered`, which is
   about *recovery*, not *completion* — a different axis). And does a zero-event run
   count at all, or is it excluded as vacuous?
2. **Legacy derivation: do it, or refuse it?** Derive applied-ness from the outcome
   literal for pre-field records (disclosed as derived), or report them flatly as
   `unknown` and let the number be small but unimpeachable? The second is more honest and
   makes the real corpus report ~nothing.
3. **Should the command filter the runs directory at all** (excluding `_*`-prefixed
   proof/demo bundles), or count everything and disclose? Filtering invents policy;
   not filtering makes the first real number misleading.
4. **`stopped_for_confirmation`** and any other dead literal: `unknown`, or a named
   "legacy literal" bucket?
5. **Command name.** `contig repair-stats`? `contig heal-rate`? It must not be confusable
   with `heal-guard`'s `recovery_rate`, which is over **synthetic** scenarios
   (`CHANGELOG.md:897-901` explicitly warns its trend points are non-comparable).
6. **Grouping key.** `failure_class` lives on `step.diagnosis.failure_class`, **not** on
   the step (the step's own key is absent in all real records). Confirm the group-by is
   the diagnosis class. Observed in the real corpus: `oom` ×2, `tool_crash` ×3,
   `missing_index` ×1, `unknown` ×1.
7. **Trend/snapshot.** Every recent guard ships `--snapshot`/`--history` into an
   append-only JSONL. In scope, or a follow-on? (Leaning follow-on: this reads runs, not
   a frozen corpus, so a trend point is not reproducible from committed data.)

## Contradiction surfaced (not papered over)

`FEATURES.md:216` says the `patch_applied` slice "supplied the missing field", implying
the analytic is now unblocked. **It is unblocked only for runs produced after v0.49.0** —
and there are currently **zero** such runs on disk. So the feature as specified would, on
today's data, produce a report whose applied/not-applied axis is entirely `unknown`. That
is a true and useful thing to report, but it is not what the FEATURES.md row implies, and
the PRD must state it rather than let the first run of the command be a surprise.

## Guardrails check (`CLAUDE.md`)

Layer 2 — telemetry of the run/self-heal loop ✓. Not Layer 1 ✓. No wet-lab/clinical/
proprietary data ✓. Deepens moat #2 by making accumulated evaluation data legible ✓.
No correctness over-claim — the whole slice turns on refusing to over-claim
(three-state applied, disclosed denominator, thin-data flag) ✓. Test-first, synthetic
fixtures, no nf-core run in CI ✓. Not blocker-deferred work ✓.

## Addendum — two more findings that change the spec

### 4. The shipped outcome grouping is FIVE families, not the three `FEATURES.md` names.

`FEATURES.md:216` describes the analytic as "auto-healed vs **paused** vs gave-up", and
the older `docs/planning/repair-patch-applied/dashboard-repair-surface/spec.md` groups
into three. The **shipped** dashboard
(`dashboard/components/run/repair-timeline.tsx:86-192`) has five, over 19 literals:

| family | literals |
|---|---|
| `APPLIED` (7) | `patched_and_retried`, `approved_and_retried`, `chose_and_retried`, `built_index_and_retried`, `recompressed_reference_and_retried`, `installed_and_retried`, `retry_failed` |
| `DECLINED` (3) | `rejected_by_user`, `approval_timed_out`, `invalid_choice_rejected` |
| `GAVE_UP` (7) | `gave_up`, `gave_up_at_ceiling`, `index_build_failed`, `index_unresolvable`, `reference_recompress_failed`, `reference_recompress_unresolvable`, `install_failed` |
| `FLAGGED` (1) | `qc_verdict_flagged` |
| `ACKNOWLEDGED` (1) | `advisory_acknowledged_and_retried` — the inert-repairs slice's outcome, which attributes recovery to the **human**, not the engine |

The CLI should agree with the **shipped five**, not with the prose. `ACKNOWLEDGED` is
the interesting one for an *unattended*-completion metric: it is a retry that only
happened because a human acted outside Contig, so it belongs on the attended side of the
line even though its literal ends in `_and_retried`.

The dashboard's fallback is also the right precedent for the unmapped case
(`repair-timeline.tsx:194-203`): *"If one reaches here it is genuinely unknown to this
build, so the honest rendering is the raw literal in give-up styling rather than a guess
at which family it is."* `stopped_for_confirmation` — present in `realtest2` — hits
exactly this path. The CLI needs an **unknown** bucket, not a silent fold into gave-up.

### 5. A consistency tension with `report.py` that the PRD must name, not discover in review.

`report.py:93-101 _applied_word` renders one step as `applied` / `not applied` and its
docstring says it *"Reads RepairStep.patch_applied verbatim"* — deliberately binary, with
both states spelled out "because silence would read as 'applied' to anyone skimming".

If this slice introduces a third `unknown-legacy` state, **two surfaces will disagree**:
a legacy step reads `not applied` in `contig show`'s report and `unknown` in the new
aggregate. That is defensible — the failure modes differ (one record under-claims
harmlessly; a rate built on the same default is simply wrong) — but it must be an
explicit, argued decision in the PRD, with a stated position on whether `report.py`
follows later or stays binary by design.

### Precedent for the formula

`heal.py:250-252` is the house definition of a recovery, and it is worth mirroring
exactly rather than inventing a second one:

```python
summary = RunSummary.from_events(record.events)
patch_applied = any(s.patch_applied for s in record.repair_history)
recovered = summary.succeeded and patch_applied
```

`heal.py:309-311` turns that into `recovery_rate = healed / total`. **It runs over
synthetic `HealScenario` replays for `heal-guard`, never over real runs** — and
`CHANGELOG.md:897-901` explicitly warns its trend points are non-comparable across a
definition change. The new command must be named and documented so the two numbers are
never mistaken for each other.

Applying that same formula to the real corpus today yields **0 recoveries out of 15
runs** — because `mvp`, the one genuine `patched_and_retried` success, carries no
`patch_applied` key. This is finding #1 restated as a number, and it is the single fact
most likely to make the first run of this command look broken when it is in fact
reporting honestly.

## Note on method

The Phase-2 fan-out was dispatched (three read-only agents: models, CLI precedent,
outcome taxonomy). Their reports did not come back, so every finding above was verified
first-hand in this session by reading the code and by executing against the 15 real run
records. Nothing here is agent-sourced or unverified.
