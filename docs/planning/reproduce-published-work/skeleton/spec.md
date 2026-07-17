# Aspect spec — `skeleton` (reproduce-published-work, slice 1)

The single aspect of the C8 first slice: the `contig reproduce` walking skeleton.
Parent PRD: `../prd.md`. Approved at the review gate as "walking skeleton as-is".

## Problem slice & user outcome

A reviewer/biotech user points `contig reproduce` at a local repo + a claims file, the repo's
script runs and writes a `results.json`, and they get an honest per-claim verdict
(`REPRODUCED`/`WITHIN-TOLERANCE`/`DIVERGED`/`UNVERIFIED`) plus a signed, re-runnable record — with
`UNVERIFIED` never rendered as reproduced.

## In scope

- `contig reproduce <repo> --run "<cmd>" --claims <file> [--results results.json] [--runs-dir]
  [--tolerance 0.1] [--fail-on-diverged]`.
- Claims file loader/validator (JSON list `{id, value, tolerance?}`).
- Execute `--run` in the repo via the injected `Executor` seam; non-zero exit → all claims
  `UNVERIFIED`.
- Bind regenerated values from the repo's `results.json`.
- Per-claim comparator reusing `benchmark._relative_delta`, tight-epsilon classification + the M5
  boundary rules.
- `ClaimStatus` / `ClaimResult` / `ReproduceRecord` models + `reduce_reproduction`.
- Signed record (reuse generic signing) + `reproduce.json` manifest; render + exit code.

## Out of scope (this aspect)

Env-resurrection (slice 2); paper-parsing; the output-locator (slice 1.5); figures/plots/tables;
remote `<doi|url>`; dashboard; C6 eval fold-in; conclusions verdicts.

## Acceptance criteria (testable — all RED first)

1. Concordant repo (results match claims) → every claim `REPRODUCED`; summary says all reproduced.
2. A claim within tolerance but not epsilon-exact → `WITHIN-TOLERANCE` with delta named.
3. A claim outside tolerance → `DIVERGED` naming observed vs stated + delta.
4. Missing claim key in `results.json`, non-numeric observed, `NaN`/`inf` → `UNVERIFIED` (never a
   false pass), one per affected claim.
5. Non-zero script exit → all claims `UNVERIFIED`; command still exits per M8 (0 by default).
6. Malformed claims file / duplicate id / negative-or-zero tolerance / non-numeric claim value →
   clear error, non-zero exit, no record written.
7. Zero-claim edge: claimed `0` vs observed `0` → `REPRODUCED`; claimed `0` vs nonzero observed →
   classified via absolute delta vs tolerance (documented).
8. `CONTIG_SIGNING_KEY` set → `signature.json` written and `verify_signature` returns True; record
   round-trips.
9. The `reproduce.json` manifest captures repo + command + claims sha256 so the invocation is
   re-derivable.
10. `--fail-on-diverged` → exit non-zero iff any claim `DIVERGED`; default exit unchanged.
11. `pyproject.toml` runtime deps unchanged; full suite runs offline.

## Dependencies & sequencing

Models → reproduce module → bundle/signing wiring → CLI. Each phase green before the next.

## Risks specific to this aspect

Boundary correctness in the comparator (AC 4, 7) is the highest-risk area — write those RED first.
`ReproduceRecord` must stay off `RunRecord`; confirm signing is generic during the bundle phase.
