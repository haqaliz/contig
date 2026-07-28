# Aspect spec: locator

Parent PRD: `../prd.md`. Single aspect for this slice (small, cohesive — one engineer/agent).

## Problem slice & user outcome

A `contig reproduce` claim can point at where its number lives in the repo's own **JSON** output
(`{"from": "out/summary.json", "path": "$.model.auc"}`) instead of requiring a Contig-shaped flat
`results.json`. Located claims resolve from that file at that path and classify with the existing
verdict; every resolution failure is `UNVERIFIED`; a claims file may mix located and flat claims;
back-compat with slice 1 is total.

## In scope

1. **Pure path walker** — `resolve_pointer(data, expr) -> object | None` in
   `src/contig/verification/reproduce.py` (or a small sibling helper it imports). Grammar: dotted
   segments + `[n]` list indices, leading `$.`/`$` tolerated and stripped. Walks nested `dict`/`list`.
   Any unresolved step (missing key, index range/type error, malformed expr) → `None`. No guessing,
   no partial match. Stdlib only.
2. **`Claim` + `load_claims` extension** (`reproduce.py:32-89`). `Claim` gains an optional locator on
   an aliased attribute (JSON key `"from"` — a keyword — maps to e.g. a small `Locator(source, path)`).
   `load_claims` validates: `from`/`path` all-or-nothing, both non-empty strings when present;
   violations raise `ClaimsError`. Stays **repo-agnostic** (no containment here).
3. **Located value-binding branch** in `run_reproduction` (`reproduce.py:181-237`). For a located
   claim on a completed run: read `repo/<from>` as JSON (cached per file within the run),
   `resolve_pointer`, require a finite non-`bool` number → `float` → `classify`. Any miss →
   per-claim `UNVERIFIED` with a specific message. Locator-less claims keep the flat `--results`
   lookup unchanged. Defensive: an escaping/absolute `from` reaching here → `UNVERIFIED`, file never
   read.
4. **CLI containment pre-check** in `reproduce` (`cli.py:713-806`). After `load_claims`, before the
   run: for each located claim, `(repo/from).resolve().relative_to(repo.resolve())` in
   `try/except ValueError`; on escape → `typer.echo(..., err=True)` + `raise typer.Exit(1)`, **no**
   record written (mirror the `--results` guard at `cli.py:745-753`). Clarify `--results` help as the
   locator-less fallback (S2).

## Out of scope

TSV/CSV row/column addressing; stdout/notebook/prose parsing; figures/plots; gzip on `from` files;
env-resurrection; paper-parsing; remote fetch; dashboard; C6 fold-in; any `ClaimResult`/
`ReproduceRecord` model change. (See PRD "Out of Scope".)

## Acceptance criteria (testable — write RED first)

- **AC1 (walker happy path)** `resolve_pointer({"model":{"auc":0.9}}, "$.model.auc") == 0.9`;
  `resolve_pointer({"samples":[{"n":5}]}, "samples[0].n") == 5`; leading `$`/`$.`/none equivalent.
- **AC2 (walker misses → None)** missing key, index out of range, `[0]` on a dict, `.k` on a list,
  malformed expr (`a..b`, `a[x]`, trailing `[`) each → `None`. Never raises.
- **AC3 (located REPRODUCED/DIVERGED)** a fixture repo whose script writes `out/summary.json`
  (non-Contig shape) yields `REPRODUCED` for a matching claim and `DIVERGED` (with observed-vs-stated
  + delta) for a drifted one, via `{"from","path"}`.
- **AC4 (located → UNVERIFIED, never false pass)** each of: `from` file missing; `from` unparseable
  JSON; `path` unresolved; target non-numeric; target **numeric string** (`"0.91"` — strict, not
  coerced); target `NaN`/`inf`; target `true` (bool) — → that claim `UNVERIFIED`, never
  `DIVERGED`/`REPRODUCED`, with a message naming the cause.
- **AC5 (all-or-nothing)** a claim with only `from` (or only `path`) → `ClaimsError`, exit non-zero,
  no record. Both non-empty strings required.
- **AC6 (mixed file)** one claims file with a located claim + a flat claim resolves each by its own
  path in a single run.
- **AC7 (safety, CLI)** a located claim with `"from": "../secret.json"` or an absolute `from` →
  CLI exits non-zero, **no** `reproduce_record.json` written (mirror `test_cli_reproduce.py:285,312`).
- **AC8 (safety, engine)** the same escaping `from` passed straight to `run_reproduction` → that
  claim `UNVERIFIED`, and the outside file is never opened.
- **AC9 (back-compat)** the full slice-1 reproduce suite (`test_reproduce.py`,
  `test_cli_reproduce.py`, `test_reproduce_models.py`, `test_reproduce_bundle.py`) stays green with
  no edits; a slice-1 claims file (no locator) is byte-identical in behavior.
- **AC10 (no new deps / offline)** `pyproject.toml` runtime deps unchanged; whole suite runs with a
  scripted executor + on-disk fixtures, no network.

## Dependencies & sequencing

Phase 1: pure `resolve_pointer` (AC1–AC2). Phase 2: `Claim`/`load_claims` (AC5). Phase 3:
`run_reproduction` branch (AC3–AC4, AC6, AC8). Phase 4: CLI containment pre-check + help (AC7).
Back-compat (AC9) and offline (AC10) asserted throughout. No external deps.

## Risks specific to this aspect

- **Walker tokenization** — pin exact rules (segment split, `[n]` parse, empty segment rejection) in
  the plan; a sloppy parser risks a silent wrong match. Tests AC2 lock the miss cases.
- **Engine-vs-CLI safety split** — containment rejects pre-run in the CLI (AC7); the engine keeps a
  defensive UNVERIFIED (AC8). Both must guarantee no read outside the repo.
- **`from` keyword aliasing** — do not name a Python attribute `from`; map the JSON key explicitly.
