# Understanding: verdict-exit-code

Phase 2 dig output. Source: `_card/issue.md` + read-only code map of `src/contig/`
and `tests/` (worktree `feat-verdict-exit-code`).

## What the work is really asking

Make Contig's already-computed **FAIL verdict** able to fail the process, so a
researcher can gate a script or CI step on it — without changing today's default
behavior. The verdict is rendered and printed today but never consulted for the exit
code. This is enforcement plumbing, not new science.

## Key finding: the verdict is already a single, safe source of truth

`RunRecord.verdict` (`models.py:357-369`) is a `@computed_field` property that:

- returns `"fail"` if the pipeline didn't complete (`RunSummary...succeeded` is false),
- returns `"unverified"` if the run completed but has **no** QC results,
- else returns `overall_verdict(self.qc_results)` — `"fail"` dominates `"warn"`
  dominates `"pass"` (`models.py:78-96`).

It **never raises** (the `ValueError` in `overall_verdict` on an empty list is guarded
by the `not self.qc_results` branch). `render_run_report` already prints it
(`report.py:90`). So both commands can gate on `record.verdict == "fail"` with **no
new computation and no new loading** — the record is already in hand.

Vocabulary: `Verdict = Literal["pass","warn","fail","unverified"]` (`models.py:58`).

## Affected areas

### `contig run` — `cli.py` (`run` at :237, real work in `_dispatch_run` at :327)
- Exit is decided **only** by pipeline success at `cli.py:618-620`:
  ```python
  typer.echo(render_run_report(record))
  if not RunSummary.from_events(record.events).succeeded:
      raise typer.Exit(code=1)
  ```
- `record` (a `RunRecord`) is in scope; `record.verdict` is available and already
  printed. **No `--json` option on `run`.**
- Slice: add an opt-in check right here — `if fail_on_verdict and record.verdict ==
  "fail": raise typer.Exit(...)`. Because a non-completing run already exits 1
  unconditionally (and its verdict is `"fail"` too), the flag is a **strict superset**
  that adds only the *completed-but-QC-FAIL* case. Flag off ⇒ byte-identical to today.

### `contig verify` — `cli.py` (`verify` at :754, body :868-971)
- Loads the record: `record = load_run(runs_dir, run_id)` (`cli.py:893`). `record.verdict`
  is available but **never consulted** today.
- Exit is decided **only** by output drift (`result["ok"]` from `verify_outputs`) and
  signature mismatch (`sig_bad`). Concordance is at-most-WARN, never exits.
- Multiple return/exit paths: no-checksums branch (`:929-945`) and has-checksums branch
  (`:947-971`), each with a `--json` sub-path and a text sub-path.
- Slice: fold a `verdict_fail = fail_on_verdict and record.verdict == "fail"` into the
  exit decision **on every path** (including no-checksums — a run with a FAIL verdict but
  no captured outputs must still fail under the flag). `verify` reads the **stored**
  verdict; it does not recompute QC.
- `--json` payload (`result` dict) keys today: `ok`, `changed`, `missing`, `signed`,
  `signature_ok`, optional `concordance`. Open question: whether to surface `verdict` in
  the payload when the flag is on (default-off path must stay identical).

## Contract this reverses, and what must move

The repo currently documents "exit decided by pipeline success only" / "concordance
never changes the exit code." The flag is **opt-in**, so those statements stay true by
default. The one written pin that becomes stale is the docstring/comment at
`tests/verification/test_run_qc.py:356-360` ("cli.py's exit-decided-by-pipeline-
success-only contract") — reword to "…by default; `--fail-on-verdict` opts in."

Tests to respect (all remain GREEN because the flag defaults off and only acts on the
QC verdict, never on concordance):
- `tests/test_cli.py` concordance-exit-0 tests (`:1438, 1473, 1550, 1586, 1732, 1768,
  1930, 2138, 2406, 2557` and comments) — concordance still never changes exit.
- `tests/test_cli.py:131-144` — `run` PASS→exit 0, non-completing→exit≠0 (unchanged; the
  non-completing case exits via the existing `.succeeded` gate regardless of the flag).

New tests needed (no existing CLI test covers completed-but-FAIL-QC):
- `run` + `--fail-on-verdict`: a completed run whose QC verdict is FAIL exits non-zero;
  WARN/PASS/UNVERIFIED exit 0; **without** the flag the same FAIL run exits 0.
- `verify` + `--fail-on-verdict`: same matrix, on a loaded record; plus the no-checksums
  branch (FAIL verdict, no outputs) fails under the flag; `--json` still emits and the
  exit code still applies.

## Test idioms to reuse
- `typer.testing.CliRunner` (`tests/test_cli.py:4,20`), `from contig.cli import app`.
- `_fake_run_executor(trace_text, mqc_json)` (`tests/test_cli.py:57-65`) + fixtures
  `TRACE_OK`/`TRACE_FAIL`, `GOOD_MQC`/`VARIANT_MQC` drive `run` success + verdict.
- `_record_with(qc_results, pipeline=..., revision=...)` (`tests/verification/test_run_qc.py:162-171`)
  builds a completed `RunRecord` with arbitrary `QCResult`s — the idiomatic way to mint a
  FAIL-verdict record for `verify` (pass a `QCResult(status="fail", ...)`), then `_write_run`
  (`tests/test_cli.py:45-54`) to persist a bundle for `verify` to load.

## Ambiguities / open questions (for the interview)
1. **Flag name & surface:** `--fail-on-verdict` on both `run` and `verify` (recommended,
   parallel + discoverable), vs a shared `--strict`, vs an env var. Recommend a
   per-command bool flag, same name on both.
2. **Scope of slice 1:** both `run` and `verify` (recommended — the caveat names both),
   vs `verify`-first.
3. **Exit code value:** reuse `1` (recommended — matches every other `typer.Exit(code=1)`
   and pipeline-failure), vs a distinct code (e.g. `2`) to disambiguate "FAIL verdict"
   from "crash/bad args." A distinct code is friendlier for CI branching but diverges
   from the existing idiom.
4. **WARN handling:** slice 1 = only FAIL → non-zero; WARN/UNVERIFIED stay 0 (per brief).
   Confirm no `--fail-on-warn` in this slice.
5. **`--json` on `verify`:** keep payload identical by default; when the flag is on, may
   add a `"verdict"` key. Decide whether that's in-scope for slice 1.
6. **Docs:** update `CHANGELOG.md` (Unreleased), and reword the WARN-only / "never changes
   the exit code" language in `CAPABILITY_ROADMAP.md` / `FEATURES.md` to "by default;
   opt-in via `--fail-on-verdict`."

## Guardrail check (CLAUDE.md)
- **Layer 2, on-thesis** — hardens the verify surface; makes the verified verdict
  enforceable. Not Layer 1. ✓
- **No over-claiming** — enforces the *existing* verdict; adds no new science, no new
  band, no clinical claim. UNVERIFIED still never treated as PASS (it exits 0, correctly —
  it is not a FAIL). ✓
- **No new dependency, no raw-read egress.** ✓
