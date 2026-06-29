# Aspect spec: detect-and-gate

Parent PRD: `../prd.md`. Single aspect for this slice (small, cohesive).

## Problem slice & user outcome

A `contig run` on real data with an explicit `--fasta`/`--gtf` whose contig-naming
schemes are **disjoint** is refused at pre-flight with the exact mismatch named,
before any compute is spent — unless the user passes `--allow-reference-mismatch`.
Legitimate references (any shared contig, incl. partial/subset) launch unchanged.

## In scope

1. A pure parsing+rule module (`src/contig/reference_check.py`):
   - `fasta_contigs(path) -> set[str]` and `gtf_contigs(path) -> set[str]`,
     gzip-transparent, streamed, tolerant of garbage/blank lines.
   - `check_reference_consistency(fasta, gtf) -> list[str]` implementing the
     **disjoint-only** rule with a **deterministic** message.
2. CLI gate in `cli.py:_dispatch_run()` after `resolve_reference` (explicit mode
   only; iGenomes skipped for free), refusing with `typer.Exit(1)` on a problem.
3. `--allow-reference-mismatch` flag on `run` (and honored on `rerun`), recorded in
   `LaunchManifest` so reproduce is faithful.

## Out of scope

Corpus / `FailureClass`; sample-vs-reference; dashboard/report UI; known-sites/BED;
GTF version; the C2 repair. (See PRD "Out of Scope".)

## Acceptance criteria (testable)

- **AC1** Disjoint FASTA(`chr1,chr2`)/GTF(`1,2`) → `check_reference_consistency`
  returns one problem string naming both sides and the `chr`-prefix asymmetry.
- **AC2** Shared (`chr1,chr2` / `chr1`) and subset/partial overlap → returns `[]`.
- **AC3** Either file empty/unparseable (no contigs) → returns `[]` (uncomparable,
  never a false refuse).
- **AC4** Gzipped `.fa.gz` / `.gtf.gz` inputs parse identically to plain.
- **AC5** Message is deterministic (stable sorted sample of contigs) — assertable.
- **AC6** Gate: a `contig run --input … --fasta … --gtf …` with a disjoint pair
  exits non-zero and writes **no** `launch.json` / never calls `self_heal_run`.
- **AC7** `--allow-reference-mismatch` converts the refuse into a proceed (warning
  printed), and the flag is persisted in `launch.json`; `rerun` of such a manifest
  stays bypassed (faithful reproduce).
- **AC8** Suite stays green (baseline 847 passed, 1 skipped); no network/tool exec.

## Dependencies & sequencing

Phase 1 (module) before Phase 2 (CLI wiring). No external deps.

## Risks specific to this aspect

- Message determinism → fix via sorted sampling (see plan Phase 1).
- `rerun` faithfulness → fix via a manifest field (see plan Phase 2).
- `chr`-prefix hint is message-only; the decision is pure set-disjointness, so a
  stray decoy contig can't cause a wrong refuse.
