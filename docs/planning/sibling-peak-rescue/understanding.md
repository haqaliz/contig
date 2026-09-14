# Understanding — sibling-peak-rescue

Phase 2 dig note. Grounded in the `contig-next` handoff brief
(`docs/planning/_card/issue.md`) and a two-agent code dig; every citation below was
verified by reading the file in this worktree (`feat/sibling-peak-rescue`, base
`7a8c0e3`), not from memory or the roadmap's prose.

## What the work is really asking

Complete the C2 resource-scaling ladder with its deliberately-cut rung: when an
OOM'd task's **own** observed peak is unusable (a signal-killed task writing `-`/0
to `peak_rss`), size the retry from the **max observed peak among same-coarse-process
siblings** instead of falling straight to the blind `× 2` bump — justified because
`process.resourceLimits` is process-global (`nfconfig.py:68`). The prerequisite is
the parser fix the parent slices deferred twice: `events.py:91` and `events.py:130`
both set `process = name or ""`, dropping Nextflow's coarse `process` column, so
sibling grouping is impossible today.

The shipped ladder lives in `src/contig/resource_sizing.py`:
`peak_informed_memory_gb` (42–66) joins `(e.process, e.name)` against exit-137
events (`:57–61`), takes `max` of the OOM'd tasks' own peaks (`:65`), and returns
`PeakSizing(target_gb, tier, observed_peak_mb)` (`:29–39`) — tier `"oom_task"` or
`"unavailable"`. `self_heal._oom_memory_sizing` (465–487) parses the run's partial
`trace.txt` at heal-decision time and the result flows into
`apply_patch(observed_target_gb=…)` (`self_heal.py:536–539`, `:596–605`), where the
ceiling clamp, never-shrink, and `gave_up_at_ceiling` (`:453–462`, `:1605–1614`)
stay unchanged. The memory detail string is built at `self_heal.py:480–487` and
recorded into `RepairStep.detail` at `:1633–1644`.

## Affected areas (all paths relative to the worktree root)

- `src/contig/events.py:87–97` (TaskEvent) and `:127–136` (TaskResource) — the two
  `process=name or ""` aliases. Both parsers are **header-driven**
  (`col = {name: i …}`, `:78` / `:118`), so the fix is a column-name lookup with an
  `or name or ""` fallback — no positional risk. Real traces already carry the
  coarse column: `build_nextflow_command` emits plain `-with-trace <path>` with no
  `trace.fields` override (`runner.py:1321–1322`).
- `src/contig/resource_sizing.py:42–67` — add the sibling rung between `oom_task`
  and `unavailable`; new tier literal; docstring `:9–11` (which names this exact
  follow-on) must be updated.
- `src/contig/self_heal.py:465–487` — detail builder gains the sibling tier's
  wording; `:1616–1617` call site unchanged.
- `tests/test_resource_sizing.py:65–79` — `test_same_process_sibling_is_not_rescued`
  **pins today's deliberate non-rescue** and flips in this slice; its docstring
  records the deferral rationale verbatim.
- `tests/test_events.py:68–78` — pins `process := name` for a trace with no
  `process` column; survives via the fallback, but needs a new sibling test with
  both columns present.
- Consumers of the `process` field (blast radius): `resource_sizing.py:57,61` (the
  join key — must stay correct), `progress.py:71,152` (display-only; now shows the
  coarse process, arguably the intended fix), `detect.py:621` (LLM-prompt text
  only; the rules detector never reads `process`). `stall.py` deliberately does not
  parse; `heal.py` writes traces but does not parse them.
- Dashboard: **no change** — `dashboard/lib/runs.ts:222,233–237` already reads the
  coarse `process` column by header name with a `|| name` fallback.

## Corpus fold-in (the optional half of the brief)

`FailureCase` (`models.py:469–477`) has five fields; it is **outside the signed
payload** (signing covers `RunRecord` only — `signing.py:22,55–64`), so an additive
defaulted field is not a signature break and old JSONL loads
(`FailureCase.model_validate_json`, `corpus.py:44`). The write site is
`self_heal.py:1322–1332` (exception path; the QC-verdict path at `:1290–1302` has
no events/peak), through `failure_case_from_run` (`corpus.py:107–129`).
**Ordering constraint:** the pending append runs at `:1322–1332`, *before* the
sizing computation at `:1616`, so threading the peak in requires either computing
the sizing earlier or parsing the (cheap) trace at capture time — a real plan
decision, not a detail. Today the observed peak rides only inside
`RepairStep.detail` (a string, inside the signed record).

## Contradictions surfaced (not papered over)

1. **The walltime "sibling rescue" is already shipped in superset form.**
   `realtime_informed_time_h` (`resource_sizing.py:92–118`) takes the max `realtime`
   across **all** usage rows (`:114`), not a same-process join — so the roadmap's
   "same-process sibling-`realtime` rescue (same `process == name` blocker as
   memory)" (`CAPABILITY_ROADMAP.md:299–301`) is inaccurate as written. There is no
   parser blocker on the time branch. Narrowing it to same-process would *reduce*
   the candidate set and is a behavior change with no demand — this slice leaves
   the time branch untouched and records the correction.
2. **The `process == name` aliasing exists in both parsers**, not just one; the
   join key in `resource_sizing.py` is only correct today because *both* sides
   alias identically. Fixing one parser without the other would silently break the
   own-peak tier — the plan must fix both in one commit.
3. **`progress.py`'s blast radius is smaller than the roadmap implies** — display
   only (`progress.py:71,152`). The more consequential consumer is the
   `(process, name)` join key itself.

## Open questions for the requirements interview

1. **Corpus fold-in in-scope or deferred?** The brief says "optionally". The dig
   shows it is additive, unsigned, and small — but it carries the append-ordering
   decision above and grows the slice.
2. **Walltime**: confirm "leave untouched + record the roadmap correction" (vs
   narrowing to same-process, which is a regression-risk behavior change).
3. **Name the borrowed sibling?** Recording *which* task the peak came from
   (`PeakSizing` gains an optional source name) strengthens the evidence line but
   widens the model change.

## Guardrails check (CLAUDE.md)

Layer 2 (self-heal breadth for the shipped C2 ladder) ✓. No Layer 1 ✓. No
raw-read egress ✓. No verdict/exit-code/`FailureClass` change ✓. No
wet-lab/clinical dependency ✓. Test-first with injected trace/executor fixtures;
no real Nextflow in CI ✓. Honest give-up paths unchanged ✓.
