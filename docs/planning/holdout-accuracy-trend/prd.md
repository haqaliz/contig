# PRD: holdout-accuracy-trend

Status: draft for review. Owner: aliz. Branch: `feat/holdout-accuracy-trend/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff brief),
`docs/planning/_card/understanding.md` (Phase-2 dig), `docs/technical/CAPABILITY_ROADMAP.md`
C6. Capability: **C6 (Eval flywheel as a continuous loop) — the unblocked half of its
stated-pending list** (a held-out-accuracy trend over versions; the C1/C3 fold-in is the
blocked half and is explicitly out of scope).

## Problem Statement

`contig eval-guard` (held-out **detector accuracy**) and `contig heal-guard` (self-heal
**outcome-match rate**) each compute a number and compare it to a single frozen baseline,
failing the CI build on regression (`cli.py:1870-1983`, `cli.py:1986-2101`). Neither keeps
any **history**, so there is no visible trajectory of whether the engine is getting better
over corpus / detector / release versions. The only over-time trend that exists is
`eval-detector --snapshot/--history` writing `eval_history.jsonl` (`eval_history.py`) — and
that trends the detector against the **training** corpus, not the frozen held-out set or the
self-heal loop.

The moat is "execution / verification / reproducibility infrastructure **+ accumulated
evaluation data**" (`CLAUDE.md` #2), and the product should "get BETTER as foundation models
improve" (`CLAUDE.md` #3). Today the "we improve over time, measured on a **frozen** held-out
set" claim — a more defensible trust signal than the training-corpus trend that already ships
as a dashboard "DIFFERENTIATOR" (`FEATURES.md:224`) — is asserted, never shown. A buyer (or
the founder) cannot see the held-out accuracy or the self-heal outcome-match rate move as the
detector/model is swapped.

**Evidence it's real, and honestly bounded:** `HealSnapshot`'s own docstring
(`models.py:597-615`) states "there is no history file … `--history` is explicitly deferred"
— the deferral is recorded in the code. `CAPABILITY_ROADMAP.md` C6 slice 2 lists "a
held-out-accuracy trend over corpus/loop versions" under "Still pending." This slice closes
that named gap.

## Goals & Success Metrics

- **G1 — Held-out detector-accuracy trend.** `contig eval-guard --snapshot` appends one
  `EvalSnapshot` (stamped with `corpus_sha` of the held-out set, `detector`,
  `contig_version`, UTC `timestamp`) to a committed `holdout_history.jsonl`; `contig
  eval-guard --history` renders the trajectory with a **per-version accuracy delta** column.
  *Metric:* a test appends N snapshots and asserts the rendered order + the delta of the last
  vs previous.
- **G2 — Self-heal outcome-match trend.** `contig heal-guard --snapshot` appends one
  `HealSnapshot` to a committed `heal_history.jsonl`; `contig heal-guard --history` renders
  the outcome-match-rate trajectory with per-version deltas (recovery-rate shown alongside,
  informational-only, matching the guard's existing honesty split). *Metric:* symmetric test
  to G1 on the heal history.
- **G3 — Deliberate persistence, no CI flood.** A trend point is written **only** on an
  explicit `--snapshot` **or** on `--update-baseline`; a bare `eval-guard`/`heal-guard`
  (the CI invocation) writes **nothing**. *Metric:* a test invoking the bare command asserts
  the history file is unchanged/absent; a `--snapshot` invocation asserts exactly one line
  appended; an `--update-baseline` invocation asserts both the baseline refroze **and** one
  line appended.
- **G4 — Dashboard trend series.** The `/eval` page renders a held-out-accuracy trend and a
  self-heal outcome-match trend (sparkline + per-version delta table, mirroring the shipped
  `eval-history.tsx`), reading the two new JSONL files via a `dashboard/lib` reader. Absent
  files degrade to an empty state, never an error. *Metric:* a Playwright spec over a fixture
  history renders the series; an absent-file case renders the empty state.
- **G5 — No regression, deterministic, no network.** The full suite (baseline **1601
  passed, 1 skipped**) stays green; `npm run build` + `npm test` in `dashboard/` stay green.
  Time/version are injected through the existing pure-builder seam, so tests are
  deterministic (no `datetime` monkeypatch).

## User Personas & Scenarios

- **The founder (primary).** Swaps the `rules` detector for an `llm` detector, or promotes
  new corpus cases, and wants to *see* whether held-out accuracy and self-heal outcome-match
  moved — the instrument that proves `CLAUDE.md` #3. Runs `contig eval-guard --history` /
  `heal-guard --history`, or opens `/eval`.
- **C, core facility / D, biotech buyer (trust signal).** Evaluating whether Contig's
  verification actually compounds. The dashboard held-out/heal trend is the "how Contig is
  learning" evidence (`FEATURES.md:130-132`) on the *frozen* set, harder to game than the
  training-corpus trend.

Personas A (lone comp-bio) and B (wet-lab non-coder) are not the audience for this internal
eval surface; no requirement targets them.

## Requirements

### Must-have (this slice)

- **R1 — Two committed history files, JSONL, append-only. [RESOLVED: two files]**
  `src/contig/data/holdout_history.jsonl` (one `EvalSnapshot` per line) and
  `src/contig/data/heal_history.jsonl` (one `HealSnapshot` per line). Separate files because
  the snapshot shapes differ **and** the held-out `corpus_sha` ≠ the training-corpus sha
  already in `eval_history.jsonl` — mixing would conflate two corpora. Each file ships
  **seeded with one point** derived from the current committed baseline
  (`holdout_baseline.json` / `heal_baseline.json`) so `--history` and the dashboard render
  non-empty on day one; the release hook (R10) accrues points thereafter.
- **R2 — Reuse the snapshot models via a generic JSONL helper. [RESOLVED: generic helper]**
  `EvalSnapshot` (`models.py:478-495`) for holdout — already the `holdout_baseline.json`
  shape and produced by `snapshot_from_report`. `HealSnapshot` (`models.py:597-615`) for heal
  — already the `heal_baseline.json` shape and produced by `snapshot_from_heal_report`. **No
  new model** is required. Add a small **generic** `append_jsonl(snapshot, path)` /
  `load_jsonl(model_cls, path)` (parametrized by the pydantic class, mirroring
  `eval_history.py:49-66`) rather than a copy-pasted `heal_history.py`: `mkdir(parents=True,
  exist_ok=True)`, append `model_dump_json() + "\n"`; a missing file loads to `[]`; **blank
  and malformed lines are skipped, never crash** (matches the shipped `load_history` and the
  dashboard reader). Timestamp/version are passed into the builders (existing injection seam).
- **R3 — `eval-guard --snapshot`.** Appends one `EvalSnapshot` for the current held-out run
  to `holdout_history.jsonl` (`corpus_sha = sha256_file(holdout_path)`, `detector`,
  `contig_version = _pkg_version("contig")`, UTC timestamp). Composable with the guard: the
  guard comparison/exit-code behavior is unchanged; `--snapshot` is an additional side effect.
- **R4 — `eval-guard --history`.** Loads `holdout_history.jsonl` and prints the accuracy
  trajectory oldest→newest, one line per snapshot (`timestamp  accuracy X.X%  (held-out N)
  [detector]  Δ +Z.Zpp`), where the delta is vs the previous snapshot (first row shows `—`).
  `--json` prints the array. An empty/absent history prints an honest "no snapshots yet"
  line, never an error.
- **R5 — `--update-baseline` also appends a trend point.** On `eval-guard --update-baseline`,
  after `save_baseline(...)`, also append the same `EvalSnapshot` to `holdout_history.jsonl`
  (a deliberate baseline move is a natural trend point). One snapshot object, written to both
  the baseline (refreeze) and the history (append).
- **R6 — heal-guard parity (R3–R5 for heal).** `heal-guard --snapshot`, `heal-guard
  --history`, and append-on-`--update-baseline`, over `heal_history.jsonl` with `HealSnapshot`.
  `--history` renders `outcome-match X.X%  (N scenarios)  Δ +Z.Zpp` with `recovery H/T`
  alongside as **informational-only** (never part of the delta headline — matches the guard's
  existing "recovery_rate reported, never guarded" honesty).
- **R7 — CI unchanged; no per-build snapshots.** `.github/workflows/ci.yml:23,27` stay bare
  (`uv run contig eval-guard` / `heal-guard`) — the guards keep failing the build on
  regression and write **no** history. History accrues only from deliberate `--snapshot` /
  `--update-baseline` runs.
- **R8 — Dashboard trend series.** A `dashboard/lib/runs.ts`-style reader for each new file
  (env-overridable path like `evalHistoryPath()`, `[]` when absent), TS type mirrors in
  `dashboard/lib/types.ts` (reuse `EvalSnapshot`; add a `HealSnapshot` mirror), and two
  trend cards on `/eval` mirroring `eval-history.tsx` (fixed y-domain `[0,1]` sparkline +
  per-version delta table). Absent files → empty state.
- **R9 — Tests-first, deterministic, no network.** Python: append/load round-trip,
  **blank/malformed-line tolerance (skip, never crash)**, delta render,
  bare-command-writes-nothing, `--snapshot` appends exactly one, `--update-baseline`
  refreezes-and-appends, empty-history render — all with `tmp_path` + literal injected
  `timestamp=`/`contig_version=` (no `datetime` monkeypatch), via `CliRunner`. Dashboard:
  a Playwright spec over a fixture history for each series + an absent-file empty state.
- **R10 — Release-time snapshot hook (accrual). [RESOLVED: add the hook]** So the trend
  actually accrues (CI stays bare per R7), the release flow gains a documented, low-friction
  step that runs `contig eval-guard --snapshot` and `contig heal-guard --snapshot` once per
  release — landing one held-out point and one heal point per version. `tech-plan` locates the
  existing release path (the `chore(release):` flow / any Makefile/justfile) and wires the two
  commands + a short doc note; the mechanism is a documented target/step, not new CI-on-push
  behavior.

### Should-have

- The `--history` renderer marks the latest row (e.g. a trailing `←latest`) so the current
  standing is obvious at a glance.
- `--history-file` override on both guards (mirroring `eval-detector --history-file`) so
  tests and the dashboard fixtures can point at a scratch file.

### Nice-to-have (explicitly later, not now)

- A combined "eval health" view unifying the three trends (detector-training, held-out,
  heal) on one dashboard panel.
- Sha/detector-mismatch annotations inline in the trend (e.g. flag the point where the
  held-out corpus sha changed), so a discontinuity is legible rather than silent.

## Technical Considerations

- **Chokepoints:** the two guard commands in `src/contig/cli.py` (`eval-guard`
  1870-1983, `heal-guard` 1986-2101). Both already build the right snapshot object in their
  `--update-baseline` branch — the new work threads that object to an append call and adds the
  `--snapshot`/`--history` options.
- **Writer/loader placement:** extend `eval_history.py` with generic-enough helpers, or add
  a small parallel `heal_history.py`. Decision deferred to `tech-plan`, but the `EvalSnapshot`
  append/load in `eval_history.py` is directly reusable for holdout; heal needs a
  `HealSnapshot` variant (different model). Prefer minimal duplication.
- **Default paths:** add `default_holdout_history_path()` / `default_heal_history_path()`
  next to `default_history_path()` (all under `src/contig/data/`).
- **Version + time:** `_pkg_version("contig")` (`cli.py:18`) and
  `datetime.now(timezone.utc).isoformat()` at the CLI call site, passed into the pure
  builders — the exact seam the shipped tests freeze.
- **Reproducibility / verification impact:** this is pure eval-machinery telemetry (moat #2);
  it does not touch a run's verdict, exit code, or reproduce bundle. No raw-read egress — it
  reads only committed corpus shas and eval numbers. The committed JSONL files are the durable
  artifact.
- **Dashboard:** mirror `eval-history.tsx` (sparkline `W=600 H=140`, y-domain `[0,1]`,
  `deltaPp()` for the delta column) and the `getEvalHistory()` reader shape
  (`runs.ts:894-928`). No new charting dependency.
- **Honesty (`CLAUDE.md`):** the committed numbers are shown as-is — held-out **0.833/0.846**
  (`holdout_baseline.json` is 0.846; the roadmap quotes 0.833) and heal **1.0 (7/7)**. The
  renderer never rounds a regression away; recovery-rate stays informational-only.

## Risks & Open Questions

- **R-risk-1 — History churn from `--update-baseline`.** Appending on every baseline refreeze
  could add near-duplicate points if the baseline is refrozen often. *Mitigated:* baseline
  refreezes are deliberate, rare acts; a duplicate point is honest (it records that a refreeze
  happened) and the `corpus_sha`/`timestamp` distinguish it. Not deduped in this slice.
- **R-risk-2 — Held-out `corpus_sha` vs training `corpus_sha` confusion.** Reusing
  `EvalSnapshot` for two different corpora. *Mitigated* by the two-file split (R1) and by
  labeling the dashboard cards ("held-out" vs the existing training-corpus trend).
- **R-risk-3 — Committing generated data churns the repo.** The two JSONL files are seeded
  (one line each, from the current baselines) and grow slowly. *Accepted:* same pattern as the
  already-committed `eval_history.jsonl`.
- **Resolved — writer factoring:** a generic `append_jsonl`/`load_jsonl` parametrized by the
  pydantic class (R2), not a per-type copy.
- **Resolved — seeding:** seed each file with one point from the current committed baseline
  (R1); the release hook (R10) accrues points thereafter.
- **Open (for `tech-plan`) — release-flow chokepoint:** exactly where R10's two `--snapshot`
  calls attach in the existing `chore(release):` flow (a Makefile/justfile target, a release
  script, or a documented manual step). Located during planning.

## Out of Scope (confirmed deferred)

- **The C1/C3 fold-in** — folding the unlabeled concordance/plausibility corroboration signals
  into one eval number. This is the **blocked** half of C6's pending list (needs a labeling
  design for unlabeled signals) and is explicitly not attempted here.
- **Any change to guard pass/fail logic, thresholds, exit codes, or the baselines' values.**
  This slice only *records and renders* the numbers the guards already compute.
- **`eval-detector` / `eval_history.jsonl`** — the training-corpus trend already ships;
  untouched except possibly a shared writer helper.
- **New failure classes, new scenarios, new held-out cases** — the corpora are frozen inputs.
- **Any clinical claim; any Layer-1 workflow authoring; any raw-read egress.**
