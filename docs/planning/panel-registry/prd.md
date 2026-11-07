# PRD — Panel builder and registry (M3)

Feature slug: `panel-registry` · Type: feat · Owner: aliz
Branch: `feat/panel-registry/aliz` · Capability: **M3 (Beyond Genomist)**
Status: drafted 2026-11-07

## Problem Statement

M1 and M2 take a BED, but a lab needs a trustworthy way to define that BED: a
gene list, an HGNC-normalized symbol set, or an existing BED. Today the user
writes coordinates by hand or exports a panel from a vendor tool, with no
checksum, version, or record of how it was made.

M3 adds a **panel builder and registry**: resolve gene symbols, build a
canonical exon BED from a GTF, validate an uploaded BED, checksum it, and store
it with metadata. The resulting BED is directly usable by `contig variants` and
`contig readiness`.

This is a research-use panel definition, not a clinical panel certification.

## Goals & Success Metrics

- **G1 — Gene list → canonical BED.** Resolve HGNC symbols/aliases, select
  MANE Select exons (or all protein-coding transcripts), and write a sorted,
  checksummed BED.
- **G2 — BED → validated BED.** Accept BED3/BED4, normalize chromosome names,
  validate coordinates, sort/dedupe, and checksum.
- **G3 — Registry.** Store `<id>.bed` + `<id>.json` with name, genes, source,
  build, transcript policy, checksum, and creation time.
- **G4 — Reuse.** The BED output plugs into M1/M2 unchanged; `panel-list` and
  `panel-show` make the registry inspectable.
- **Success metric:** a user can go from a gene list to a reusable, checksummed
  panel BED in one command, and the same inputs produce the same BED.

## Requirements

### Must-have (v1)

- `contig panel-build --name NAME --genes BRCA1,BRCA2 --gtf annotation.gtf.gz
  [--hgnc hgnc_complete_set.txt] [--build GRCh38] [--out-dir panels]`
- `contig panel-build --name NAME --bed panel.bed [--build GRCh38]`
- HGNC validation when `--hgnc` is supplied: approved symbol, alias, or previous
  symbol; unknown symbols fail with a clear list.
- MANE Select preference when the GTF tags it; `--transcripts all` keeps all
  protein-coding transcripts.
- BED validation: 0-based half-open, `start < end`, normalized `chr` prefix,
  sorted/deduped output.
- Metadata JSON: id, name, build, source, genes, transcripts, method, checksum,
  created_at, Contig version, notes.
- `contig panel-list --dir panels` and `contig panel-show --dir panels ID`.
- Tests: synthetic HGNC/GTF/BED fixtures; no large files in CI.

### Should-have (later slices)

- Panel versioning/archival and a `--version` label.
- Transcript-level selection (specific transcript IDs).
- A panel diff between two versions.
- Coverage expectations attached to a panel.
- A dashboard panel view.

### Nice-to-have / explicit non-goals

- Clinical panel certification or regulatory claims.
- A hosted/community marketplace.
- A CNV/CNVkit panel designer.
- Model training.

## Technical Considerations

- **No new dependencies.** HGNC/GTF/BED parsing is stdlib.
- **HGNC optional.** Without the file, symbols are kept uppercase with a note;
  with it, aliases/previous symbols normalize to the approved symbol.
- **Determinism.** The panel id is a slug plus a short SHA-256 of the canonical
  BED; the same input yields the same id. Timestamps live in metadata only.
- **BED semantics.** BED is 0-based half-open; GTF is 1-based inclusive. Convert
  explicitly.
- **Attribution.** HGNC and GENCODE remain external sources; metadata records the
  paths and checksums used.

## Risks & Open Questions

- **R1 — HGNC version drift.** Mitigation: record the HGNC path/checksum and a
  `hgnc_version` note; a missing alias is a clear error, not a guess.
- **R2 — MANE ambiguity.** Mitigation: prefer MANE Select when tagged; otherwise
  keep all protein-coding transcripts and say so in metadata.
- **R3 — BED contig mismatch.** Mitigation: normalize `chr` prefixes; do not
  silently map unknown contigs.
- **Open:** should a panel carry expected coverage thresholds? (v1: no; it is a
  BED + metadata.)

## Out of Scope

- Clinical certification, diagnosis, treatment advice.
- Panel versioning/archival, transcript-level selection, dashboard (v1).
- Model training.

## Acceptance

- A gene-list build writes a sorted BED and metadata with a checksum; an alias
  resolves to the approved symbol; an unknown symbol fails.
- A BED build normalizes, sorts, dedupes, and checksums.
- `panel-list` and `panel-show` read the registry.
- The output BED works as `--bed` for `contig variants`/`contig readiness`.
