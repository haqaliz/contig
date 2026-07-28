# Aspect Spec — env-resurrection

**Parent PRD:** `../prd.md` (C8 slice 2). Single aspect for the whole slice (mirrors how
`reproduce-output-locator` used a single `locator` aspect).

## Problem slice & user outcome

`contig reproduce` dead-ends on the ~76%-of-failures case: a repo whose script exits non-zero on a
missing Python dependency. Outcome: with `--allow-install`, detect the missing module from the run's
own error output, install it, retry once, and re-classify — so the repo can reach a real per-claim
verdict instead of a blanket `UNVERIFIED`. Off by default; unresolved paths stay honestly
`UNVERIFIED`.

## In scope

- Widen the reproduce command-executor seam to return `(exit_code, combined_output)`.
- A pure, reproduce-local `detect_missing_module(output) -> str | None`.
- An injected `Installer` seam + `default_installer` (fixed, charset-guarded `pip install` argv).
- A bounded (one install + one retry) opt-in install-retry loop in `run_reproduction`.
- Additive `ReproduceRecord.repair_history: list[RepairStep]`; `exit_code` = final run's exit.
- A new `FailureClass` literal `missing_dependency`; `Patch(kind="env", …)` reuses the existing kind.
- CLI `--allow-install/--no-allow-install` (default off) + a one-line repair note in
  `render_reproduction`.

## Out of scope (this aspect)

Alias map, iterative multi-module, version pinning, venv/conda/R management, TSV/CSV locator,
paper-parsing, figures, remote fetch, dashboard card, C6 eval fold-in, auto-install-without-flag.
`detect_missing_module` is **not** wired into the shared `diagnose_failure` cascade (keeps the
detector corpus + C6 eval-guard untouched).

## Acceptance criteria (testable)

1. Executor seam is `Callable[[list[str], Path], tuple[int, str]]`; existing reproduce suite green
   after the migration (no behavior change without the flag).
2. `detect_missing_module` extracts the top-level package from `ModuleNotFoundError: No module named
   'X'` / `ImportError`; returns `None` on no match or an unsafe token.
3. With `--allow-install`: fail-then-succeed run heals → claims classify normally; one `RepairStep`
   recorded; installer called exactly once; retried run's exit recorded.
4. Every unresolved path (flag off, no module, install non-zero, retry non-zero) → all
   `unverified`, never a false reproduce.
5. `ReproduceRecord` with no `repair_history` (legacy bundle) loads with `[]`; a healed record
   round-trips through the signed bundle.
6. Runtime deps unchanged; no real pip/network in CI (scripted executor + installer).

## Dependencies & sequencing

Seam migration (Phase 0) must land atomically and green before any new behavior. Detector + installer
(Phases 1–2) are independent and can be built in parallel. Engine loop (Phase 3) depends on 0–2. CLI
+ surface (Phase 4) depends on 3.

## Open questions / risks (this aspect)

- **R2 resolved:** add `missing_dependency` to `FailureClass`; keep the detector reproduce-local so
  the C6 eval-guard baseline is untouched (no corpus case, no `diagnose_failure` branch).
- **Stale results file:** the retried run must be classified against a fresh read of the results
  file, not a file left by the failed first run — assert with a fixture.
- **R4 accepted limit:** `default_installer` installs into `sys.executable`'s environment; no venv
  isolation this slice.
