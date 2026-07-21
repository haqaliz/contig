# Card: feat reproduce-stdout-log-locator (C8 slice 4)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-stdout-log-locator/aliz`

No GitHub issue — this unit of work came from `/contig-next` (cn), 2026-07-21. The
recommendation below is the source brief.

## Brief

C8 slice 4 for `contig reproduce`: add a **third claim-locator addressing mode** that binds a
claim's observed value by **regex capture over the run's captured combined output**, and/or over a
repo-relative **log/text file** — siblings of the shipped JSON `resolve_pointer` (slice 1.5) and
TSV/CSV `resolve_cell` (slice 3) locators in `src/contig/verification/reproduce.py`.

The input is already there and unused: the slice-2 executor seam returns `(exit_code, output)`
and `run_output` today only feeds `detect_missing_module`
(`src/contig/verification/reproduce.py:687,721`). Stdlib-only (`re`), no `models.py` change,
classification through the **unchanged** `classify`, full back-compat when no locator is present.

## Why this was picked (from /contig-next)

- The only remaining C8 deferral with **no** feasibility blocker: figure/plot & table-image claims
  are hard-blocked (no plot-hash; adding perceptual hashing would break the stdlib-only dependency
  contract), paper-parsing needs its own parser/model design, remote `<doi|url>` needs network.
- Closes the "uncooperative repo" story C8 exists for: many published scripts print their headline
  numbers to stdout or a `.log` and write no JSON and no table at all — today every such claim
  degrades to UNVERIFIED.

## Caveats to settle in the dig, not late

1. **Ambiguity.** A pattern matching **0 or >1** times must degrade to UNVERIFIED with the match
   count named — never an arbitrary first-match pick. Mirrors the shipped `row`-key 0-or-many rule.
2. **Regex safety.** User-supplied patterns are a ReDoS / catastrophic-backtracking surface, so
   `load_claims` must compile/validate them **pre-run** (bad pattern ⇒ `ClaimsError`, exit
   non-zero, nothing written), and matching should be input-length-bounded.
3. **Which run's output.** Under `--allow-install` the bound output must be the **retried** run's
   — that is the run whose numbers are real.
4. **Containment.** A file-based `from` must flow through the existing `.source` containment guard
   unchanged (CLI pre-run refusal + the engine's defense-in-depth guard).
5. **Numeric-string rule.** Decide and state it explicitly: a regex capture is a string by
   construction (like a table cell), so it should follow the **slice-3** rule (parse it), not the
   slice-1.5 strict-UNVERIFIED JSON rule.

## Honesty contract (inherited, non-negotiable)

- Every unresolved / ambiguous / non-numeric / non-finite address degrades to **UNVERIFIED**,
  never `DIVERGED`, never a false reproduce.
- An escaping / absolute `from` is refused **pre-run** (exit non-zero, no record).
- `classify` / `ClaimResult` / `ReproduceRecord` / bundle / signing / `--fail-on-diverged`
  are reused as-is.

## Constraints

- Layer-2 only (run/verify/reproduce). Not Layer 1. Research-use, no raw-read egress.
- Stdlib-only runtime dependency contract (`pydantic`/`typer`/`cryptography`) must hold; `re` is
  stdlib.
- Test-first (strict TDD): pure extractor → `load_claims` validation → engine dispatch → CLI e2e.
  Deterministic. **No real repo, network, or pip in CI.**

## Prior art in-repo (starting points for the dig)

- `src/contig/verification/reproduce.py` — `resolve_pointer`/`_parse_path` (JSON walker, slice
  1.5), `_read_table`/`resolve_cell`/`_resolve_delimiter` (table reader, slice 3),
  `detect_missing_module` (slice 2), `load_claims`, `classify`, `run_reproduction`,
  `_observe_located`, `_observe_table_located`, `reduce_reproduction`.
- `benchmark._relative_delta` — the reused float-tolerance comparison.
- Slice planning: `docs/planning/reproduce-published-work/` (slice 1),
  `docs/planning/reproduce-output-locator/` (1.5),
  `docs/planning/reproduce-env-resurrection/` (2),
  `docs/planning/reproduce-tsv-csv-locator/` (3).
- Roadmap: `docs/technical/CAPABILITY_ROADMAP.md` → C8.
