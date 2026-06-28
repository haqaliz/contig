# Aspect Spec: capture-and-render

The single aspect of the `reference-identity-provenance` slice: capture reference
identity at finalize and render it in the methods paragraph and the HTML provenance
panel. See the parent [`../prd.md`](../prd.md).

## Problem slice & user outcome

A finished run's bundle should let a researcher/auditor (and the future C5/C2 engine
consumers) see exactly which genome assembly + annotation the run executed against,
with checksums where Contig can compute them. Outcome: reference identity is in
`run_record.json`, reproduces on re-run, and is visible in `contig methods` and the
HTML provenance panel.

## In-scope

- A typed `ReferenceIdentity` model and an optional `RunRecord.reference_identity`
  field (default `None`).
- A pure `compute_reference_identity(params)` helper deriving identity from a run's
  parameters (`genome` / `fasta` / `gtf`), hashing local files via `sha256_file`.
- Wiring the helper into `_finalize` (`self_heal.py`) so every finalized record
  carries it, read from `record.parameters` (no new argument threading — confirmed:
  `runner.py:293` sets `record.parameters = params or {}`, and `cli.py:380` puts the
  resolved reference into `params`).
- A reference clause in `render_methods` (`methods.py`).
- A reference-identity section in the HTML provenance panel (`report.py`).

## Out-of-scope (this aspect)

- Mismatch detection / any verdict or QC change (no `QCResult`, no exit-code change).
- Known-sites capture (deferred).
- Annotation/GTF version resolution (left `null`).
- RO-Crate export of the identity (deferred).
- Hashing files Nextflow downloads for an iGenomes key (out of Contig's namespace).

## Acceptance criteria (testable)

1. `compute_reference_identity` returns `mode="explicit"` with correct
   `sha256_file` checksums for `--fasta`/`--gtf` params pointing at real files.
2. With a `genome` key it returns `mode="igenomes"`, `genome` set, both checksums
   `None`; never reads a file.
3. With no reference keys (Snakemake/no-ref) it returns `None`.
4. A missing/unreadable explicit reference path yields that checksum `None` (no
   crash, no fabricated/zero hash).
5. The function is deterministic: hashing the same file twice yields the same digest
   (covers the re-run byte-stability guarantee).
6. A finalized record (via `_finalize`) has `reference_identity` populated from its
   `parameters`.
7. `render_methods` includes a reference clause when identity is present (naming the
   assembly/key, and checksums in explicit mode) and omits it cleanly when `None`.
8. The HTML provenance panel renders a reference-identity section when present
   (iGenomes shows the key labelled as pipeline-downloaded, not a blank hash) and
   omits it when `None`.

## Dependencies & sequencing

- Phase 1 (model) blocks everything.
- Phase 2 (helper) → Phase 3 (finalize wiring) is a sequential chain.
- Phases 4 (methods) and 5 (panel) depend only on Phase 1 and are independent of
  each other and of Phase 3 (they render whatever is on the record; tests use
  fixtures) → parallelizable.

## Open questions / risks

- Exact rendering wording for the methods clause and panel labels — agent picks
  phrasing consistent with existing `_provenance_clause` / `_provenance_rows`; not a
  blocker.
- None blocking; R1 (finalize seam) is resolved in this spec.
