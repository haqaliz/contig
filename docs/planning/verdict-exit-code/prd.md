# PRD: verdict-exit-code

Make Contig's verified **FAIL** verdict enforceable at the CLI via an opt-in
`--fail-on-verdict` flag on `contig run` and `contig verify`.

- **Type / slug:** feat / `verdict-exit-code`
- **Branch:** `feat/verdict-exit-code/aliz`
- **Source:** inline brief (`_card/issue.md`) + dig (`_card/understanding.md`)
- **Capability:** C3 follow-on (the "CLI exit-code wiring" deferred repeatedly since
  v0.35.0; see `CHANGELOG.md:47-52`, `CAPABILITY_ROADMAP.md:469-472`)

## Problem Statement

Contig computes a conservative, honest run verdict (`PASS` / `WARN` / `FAIL` /
`UNVERIFIED`) and renders it everywhere — the report, `contig show`, the dashboard.
But **no verdict, not even FAIL, changes the CLI exit code today.** Verified in code:

- `contig run` exits non-zero **only** when the pipeline itself didn't complete
  (`cli.py:618-620`, keyed on `RunSummary...succeeded`).
- `contig verify` exits non-zero **only** on output drift or a signature mismatch
  (`cli.py:957-971`); it never consults the QC verdict.

So a run that **completes** but whose science is broken — a structural FAIL (missing/
corrupt required output) or the germline biological-plausibility FAIL bands shipped in
v0.35.0 (noise-level Ti/Tv, grossly-off het/hom, empty call set) — still returns **exit
0**. Any researcher who wires `contig run`/`contig verify` into a shell script or CI
step gets a green result on a FAILed analysis.

This directly blunts Contig's headline differentiator. The verified verdict is *the*
moat (`FEATURES.md:36-38`, MARKET_ANALYSIS §4: "incumbents own infrastructure and
observability, not intelligence"); a verdict that automation can't act on is cosmetic in
exactly the context — unattended pipelines — where trust matters most. CLAUDE.md #2 is
"make every verdict harder to fool"; a verdict with no teeth is trivially ignored.

**Evidence it's real:** the gap is named as an explicit, deferred follow-on in the
shipped v0.35.0 changelog and the capability roadmap, and confirmed by direct reading of
the two exit-decision sites above.

## Goals & Success Metrics

- **G1 — FAIL is enforceable.** With `--fail-on-verdict`, a completed run whose reduced
  verdict is `FAIL` exits non-zero (code `1`) from both `run` and `verify`.
  - *Measure:* new CLI tests: FAIL-verdict + flag ⇒ `exit_code != 0`; PASS/WARN/
    UNVERIFIED + flag ⇒ `exit_code == 0`.
- **G2 — Zero default regressions.** Without the flag, behavior is byte-identical to
  today for exit codes and `--json` payloads.
  - *Measure:* the full existing suite stays green with no assertion changes except the
    one reworded stale-contract comment (`test_run_qc.py:356-360`); a FAIL-verdict run
    **without** the flag asserts `exit_code == 0`.
- **G3 — No over-claim.** `UNVERIFIED` never exits non-zero (it is not a FAIL), so the
  flag never converts "we couldn't check" into "it failed."
  - *Measure:* UNVERIFIED + flag ⇒ `exit_code == 0` test.

## User Personas & Scenarios

- **A — lone computational biologist:** runs Contig in a nightly cron / Makefile over a
  cohort. Wants `contig run … --fail-on-verdict || alert` to page them when a completed
  run is scientifically broken, not just when Nextflow crashes.
- **C — core facility:** gates a batch-processing pipeline in CI; a FAILed verdict should
  stop the line and block promotion of a bad result, exactly like a failing test.
- **D — biotech researcher:** wants a defensible, scriptable "this run is trustworthy"
  signal — a zero exit under `--fail-on-verdict` is that signal.

Scenario: `contig verify <id> --fail-on-verdict` in a CI step. The run completed and
outputs haven't drifted, but the stored verdict is FAIL (e.g. empty germline call set).
Today: exit 0, CI green, bad result promoted. With this feature: exit 1, CI red, caught.

## Requirements

### Must-have (slice 1)

- **M1** — Add a boolean `--fail-on-verdict` option (default `False`) to `contig run`.
  When set and `record.verdict == "fail"`, exit non-zero (`1`) after rendering the
  report. Gate lives at `cli.py:618-620`. Because a non-completing run already exits 1
  regardless of the flag (and its verdict is `"fail"` too), the flag adds **only** the
  completed-but-QC-FAIL case.
- **M2** — Add the same `--fail-on-verdict` option (default `False`) to `contig verify`.
  When set and the **loaded** `record.verdict == "fail"`, exit non-zero (`1`) on **every**
  path (no-checksums and has-checksums, text and `--json`), composing with the existing
  drift/signature exit (any one of them non-zero ⇒ non-zero).
- **M3** — Severity policy: **only** `FAIL` triggers non-zero. `WARN`, `UNVERIFIED`,
  `PASS` all exit 0 under the flag.
- **M4** — Exit code is `1` (reuse the existing idiom; a FAIL verdict is not
  distinguished from a crash by code).
- **M5** — Default (flag absent) behavior is unchanged: same exit codes, same stdout,
  same `--json` payloads. No existing passing assertion changes (except reworded stale
  comment).
- **M6** — The gate reads the existing `record.verdict` computed property
  (`models.py:357-369`); no recomputation, no new verdict logic, no new model field.
- **M7** — Test-first (RED→GREEN) for every behavior in M1–M5.

### Should-have

- **S1** — Help text on both flags stating: opt-in; only a FAIL verdict exits non-zero;
  WARN/UNVERIFIED do not; composes with drift/signature on `verify`.
- **S2** — `CHANGELOG.md` Unreleased entry; reword the "never changes the exit code" /
  "exit decided by pipeline success only" language in `CAPABILITY_ROADMAP.md` and
  `FEATURES.md` to "…by default; opt-in via `--fail-on-verdict`."

### Nice-to-have (explicitly deferred, not in slice 1)

- **N1** — `verify --json` gains a `"verdict"` key when the flag is set (kept out to
  guarantee payload stability; revisit if users want the code *and* the reason in JSON).
- **N2** — `--fail-on-warn` / a `--fail-on={fail,warn}` level. Deferred; slice 1 is
  FAIL-only. (No structural commitment made to ease this — a future flag can be added
  additively without breaking `--fail-on-verdict`.)
- **N3** — A distinct exit code (`2`) for science-FAIL vs crash. Rejected for slice 1 in
  favor of the code-1 idiom.
- **N4** — Wiring the flag through the dashboard "Run test profile" launch path.

## Technical Considerations

- **Single source of truth:** `RunRecord.verdict` (`models.py:357-369`) already reduces
  to `pass|warn|fail|unverified`, never raises, and is already rendered by
  `render_run_report` (`report.py:90`). Both commands hold the record in scope, so the
  gate is a 1–2 line conditional per command — no new module.
- **`run` gate** (`cli.py:618-620`): after `typer.echo(render_run_report(record))`, add
  `if fail_on_verdict and record.verdict == "fail": raise typer.Exit(code=1)`. Keep the
  existing `.succeeded` gate as-is (it fires first for crashes). `run` has **no `--json`**,
  so only the flag param + one branch.
- **`verify` gate** (`cli.py:868-971`): compute `verdict_fail = fail_on_verdict and
  record.verdict == "fail"` once after `load_run` (`cli.py:893`), then OR it into each
  exit decision (`sig_bad`, `not result["ok"]`) across the four sub-paths. Care: the
  no-checksums branch currently `return`s 0 — it must exit non-zero when `verdict_fail`.
  Preferred shape: a single consolidated exit decision near the end rather than four
  scattered edits, to avoid missing a path.
- **`_dispatch_run` plumbing:** `run` delegates to `_dispatch_run` (`cli.py:327`). The new
  flag must be threaded from `run()` into wherever the exit decision lives (the
  `render_run_report`/exit block runs inside `_dispatch_run` at :618-620, so the param is
  added to `_dispatch_run`'s signature and defaulted for its other callers `rerun`/`resume`
  — verify those callers don't regress).
- **Reproducibility / verification impact:** none to the run record or bundle — this is a
  read-only consumer of the already-serialized verdict. No new persisted field, no
  reproduce-contract change, no signature-input change.
- **No new dependency, no raw-read egress.**

## Risks & Open Questions

- **R1 — Missing a `verify` exit path.** `verify` has 4 return/exit sub-paths; a scattered
  edit could leave one path exiting 0 on a FAIL verdict. *Mitigation:* consolidate the
  exit decision; test all four paths (no-checksums text, no-checksums `--json`,
  has-checksums text, has-checksums `--json`) with a FAIL-verdict record.
- **R2 — `_dispatch_run` shared by `rerun`/`resume`.** Adding a param there could change
  their behavior. *Mitigation:* default the param `False`; assert `rerun`/`resume` exit
  codes unchanged.
- **R3 — Interaction with self-heal `run` where a healed run completes with a residual
  FAIL verdict.** That is the *intended* trigger (completed, but verdict FAIL). Confirm no
  test asserts a healed-but-FAIL run exits 0 (the dig found none). *Open:* none blocking.
- **Open Q:** should `verify --json` echo the verdict when the flag is on? Deferred to N1;
  slice 1 keeps the payload identical.

## Out of Scope

- Changing the **default** exit behavior of any command (the flag is strictly opt-in).
- Any new verdict computation, band, or QC check — this enforces the *existing* verdict.
- `--fail-on-warn`, a level argument, or a distinct exit code (N2/N3).
- `verify --json` verdict key (N1).
- Dashboard / launch-form wiring (N4).
- FAIL severity for the somatic / RNA-seq / annotation plausibility packs (separate,
  calibration-gated work).

## Acceptance Criteria (testable, test-first)

1. `run --fail-on-verdict` on a **completed** run with a FAIL QC verdict ⇒ `exit_code != 0`.
2. `run --fail-on-verdict` with PASS / WARN / UNVERIFIED ⇒ `exit_code == 0`.
3. `run` **without** the flag on the same FAIL run ⇒ `exit_code == 0` (default unchanged).
4. `run --fail-on-verdict` on a non-completing run ⇒ `exit_code != 0` (as today; verdict
   is FAIL, and the `.succeeded` gate already fires).
5. `verify --fail-on-verdict` on a loaded FAIL-verdict record ⇒ `exit_code != 0` on all
   four sub-paths (incl. no-outputs / no-checksums).
6. `verify --fail-on-verdict` with a PASS/WARN/UNVERIFIED record and no drift ⇒
   `exit_code == 0`.
7. `verify` **without** the flag on a FAIL-verdict record, no drift ⇒ `exit_code == 0`.
8. `verify --fail-on-verdict --json` still emits the current payload and applies the exit
   code (payload unchanged from today).
9. Full existing suite green; the only text change is the reworded stale contract comment
   at `test_run_qc.py:356-360`.
