# Understanding: reproduce-eval-fold-in

**Status:** dig note for PRD (Phase 2 of `cbf feat reproduce-eval-fold-in`).
**Source:** inline brief — `docs/planning/_card/issue.md` (no GitHub issue filed).

## What the work is really asking

Fold the reproduce track (C8) into the C6 eval flywheel in two halves:

1. **`contig reproduce-guard`** — a fourth regression guard, sibling of the
   shipped `eval-guard` / `heal-guard` / `verify-guard`: replay frozen reproduce
   scenarios through the **real** `run_reproduction` loop (claims loader,
   locators, freshness guard, env-resurrection — seams injected, code never
   stubbed) and guard a per-claim **verdict-match rate** against a committed
   baseline, wired into CI.
2. **A capture channel** — reproduce outcomes become pending corpus cases
   (sidecar append; the signed `ReproduceRecord`/`signature.json` untouched),
   promoted by a human via a `*-promote` CLI, mirroring the shipped
   `pending_verify_corpus.jsonl` + `contig verify-case-promote` pattern.

## Affected areas (from graphify-first dig)

### The three guards (the pattern to copy)
- `verify-guard` is the closest model: `src/contig/verify_corpus.py` (scorer +
  corpus/baseline/history I/O + pure comparator) + thin CLI
  `src/contig/cli.py:2920-3068`. Siblings: `src/contig/holdout.py` (eval-guard),
  `src/contig/heal.py` (heal-guard).
- Layout invariants: baseline = **single pretty-printed snapshot JSON**;
  history = **JSONL of snapshots**; corpus = **JSONL of models**; all under
  `src/contig/data/` via `default_*_path()` functions; `--update-baseline` /
  `--snapshot` / `--history` / `--history-file` / `--tolerance` flags; exit 1 on
  regression; `sha_mismatch`/`detector_mismatch` are informational warnings.
- CI: `.github/workflows/ci.yml` runs each guard as a bare `- run: uv run contig
  <guard>` step (eval-guard, heal-guard, verify-guard already there; a
  reproduce-guard step slots in beside them).
- Baseline models: `EvalSnapshot`, `HealSnapshot`, `VerifySnapshot` in
  `models.py`; `sha256_file` at `models.py:17`.

### The reproduce machinery to replay (never stub)
- `verification/reproduce.py` (1467 lines): `load_claims` (strict
  `ClaimsError`), `classify` (exact ≤1e-9 → REPRODUCED, rel-delta ≤ tolerance →
  WITHIN-TOLERANCE, else DIVERGED; non-finite/missing → UNVERIFIED, never a
  false pass), `run_reproduction(repo, run_command, claims, *, executor,
  claims_sha256, results_path, created_at, run_started_at, reproduce_id,
  allow_install, installer)` (`:838-851`), `reduce_reproduction` (per-status
  counts), all four locator families + flat `--results` + `_require_fresh`
  freshness guard (`run_started_at=None` raises — the guard must stamp a real
  `time.time()`).
- Seams: `default_command_executor` → `(exit_code, combined_output)` tuple;
  `Installer` seam for env-resurrection; both injectable via kwargs (unit) or
  monkeypatch (CLI e2e). The guard needs **scripted executors that write
  artifacts with mtime ≥ the run stamp** (or stdout-mode `PatternLocator`
  claims, exempt by construction).
- No frozen reproduce scenario JSONL exists today — the guard defines a new
  `ReproduceScenario` format. Replay template: `_ScriptedExecutor` /
  `_ScriptedInstaller` in `tests/test_reproduce_env_resurrection.py:80-126`
  (multi-call scripted shape already covers install-retry).

### The capture channel (the pattern to copy)
- `pending_verify_corpus.jsonl` + `should_capture_verification` gate
  (`verify_corpus.py:445-462`) + `verification_case_from_run`
  (`:465-489`) + `contig verify-case-promote` (`cli.py:2434-2492`,
  dedupe against golden, `pending:` → `confirmed:`, auto-snapshot history).
- Self-heal's `pending_corpus.jsonl` append precedent
  (`self_heal.py:1290-1325`) shows the sidecar-write pattern that never
  touches the signed record.
- The C8 eval-data promise: "every reproduction attempt (the environment-repair
  chain, the per-claim diff outcome) is a labeled corpus case"
  (CAPABILITY_ROADMAP.md C8) — the capture must include the repair chain
  (`ReproduceRecord.repair_history`), not just per-claim verdicts.

## Ambiguities / open questions (for the requirements interview)

1. **Match semantics of the guarded metric.** Exact per-claim status equality
   (REPRODUCED/WITHIN-TOLERANCE/DIVERGED/UNVERIFIED) is the strongest and most
   honest (the verdict contract treats UNVERIFIED as never-a-pass), but
   `reduce_reproduction`'s four buckets suggest a coarser "matched vs
   diverged-vs-unverified" tier is possible. Recommend exact status equality,
   per-scenario rate + aggregate guarded rate.
2. **Capture gating.** `should_capture_verification` captures only
   WARN/FAIL verdict runs. For reproduce: capture **every** run (cheap, local,
   and the corpus is the point), or gate on non-reproduced/repair cases?
3. **Scenario format.** Inline claims/scripted executors in the JSONL (like
   `HealScenario.attempts` inline) vs referencing fixture files. Recommend
   inline — keeps `corpus_sha` self-contained like the sibling corpora.
4. **Anti-tautology control.** verify-guard keeps a deliberate `known_miss` to
   hold the baseline < 1.0 and prove the guard is live. reproduce-guard needs
   the equivalent — a deliberately-drifting scenario (e.g. a DIVERGED expected
   verdict that stays DIVERGED only if classify really re-derives) plus a
   mutation control pin.
5. **Naming.** `reproduce_scenarios.jsonl` / `reproduce_baseline.json` /
   `reproduce_history.jsonl`, `ReproduceSnapshot`, `ReproduceScenario`,
   `ReproduceCase` (pending), `contig reproduce-guard`, `contig
   reproduce-case-promote` — all consistent with the sibling vocabulary.

## Strategic check

Layer-2 only (reproduce/verify/eval machinery — no Layer-1, no clinical, no
proprietary data). Deepens moat #2 (the corpus compounds) and the C8 acquisition
channel's trust story. Does not collide with the in-flight
`feat/reproduce-local-tree-hash` worktree (that slice's local-path hashing is
orthogonal; it will land before or after this one). Push, not demand-pull —
honest scope must be recorded in the roadmap/CHANGELOG per house style.
