# Aspect Spec: alias-map

**Feature:** contig-alias-harmonization · **Aspect:** the single build aspect (general
per-contig rename map + alias table + CLI/provenance integration).

## Problem slice & user outcome

Widen the v0.9.0 chr-prefix harmonizer to an **equivalence-group rename map** so a
UCSC↔Ensembl contig-naming mismatch (mito `chrM`↔`MT`, and tabled scaffolds) auto-harmonizes
at pre-flight — including the residual case where the autosomes already match — while a
genuine wrong-assembly still refuses, and any contig left unmatched is surfaced (not
silently dropped).

## In scope

- A data-driven **alias equivalence table** (mito universal in code; GRCh38 scaffolds in a
  bundled, extensible data file) + loader.
- `plan_harmonization` rewritten to compute a concrete `{gtf_name: fasta_name}` rename map
  by matching each GTF contig's prefix-variant + alias-group candidates **against the actual
  FASTA contig set** (satisfies M9 FASTA-lookup), with a residual-mismatch trigger (M3) and
  the refuse-on-disjoint invariant (M4).
- `harmonize_gtf` rewritten to apply a rename map (not a single direction).
- CLI `_dispatch_run` integration (post-check, params swap, provenance), reproduce
  re-derivation unchanged.
- WARN `reference_harmonized` breadcrumb enumerates still-unmatched GTF contigs (M8).
- Docs + CHANGELOG.

## Out of scope

- New `reference_mismatch` FailureClass / detector-corpus case (provenance-only, M5).
- Network fetch of UCSC chromAlias; FASTA rewrite; assembly-signature comparison; exhaustive
  per-assembly table completeness.

## Acceptance criteria (testable)

1. `plan_harmonization({chr1,chr2,chrM}, {1,2,MT})` → rename map sends `MT→chrM`, `1→chr1`,
   `2→chr2`; `direction` label reflects add_chr + alias; no unmatched.
2. Residual case `plan_harmonization({chr1,chr2,chrM}, {chr1,chr2,MT})` (autosomes match) →
   rename map sends `MT→chrM`; triggers despite non-disjoint input.
3. Pure-alias `{chr1,chrM}` vs `{chr1,chrMT}` → `chrMT→chrM`.
4. Wrong-assembly (scaffold fixture, disjoint after mapping) → `None` → CLI exit 1;
   `--allow-reference-mismatch` proceeds + persists.
5. A tabled GRCh38 scaffold alias harmonizes; an **un-tabled** contig left unmatched appears
   in the WARN breadcrumb message.
6. `harmonize_gtf` applies the map with byte fidelity (line-endings, comments, gz) preserved.
7. `_finalize` records the harmonization in `ReferenceIdentity` + WARN breadcrumb; verdict
   capped at WARN; `rerun`/`resume` re-derive from the original GTF.
8. **No regression:** the full existing suite stays green (no false-refusals).

## Dependencies & sequencing

Alias table (P1) → planner (P2) → rewriter (P3) → CLI (P4) → breadcrumb (P5) → docs (P6).
P1 is independent new files; P2–P5 are sequential (shared `reference_harmonize.py`/`cli.py`).

## Open risks

- Whether `_finalize` can recompute unmatched from `record.parameters` (harmonized gtf path)
  or must thread it from `_dispatch_run` — resolved empirically by the P5 RED test.
