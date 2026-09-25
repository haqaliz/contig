# Card: feat rocrate-reference-identity

- **Type:** feat
- **Id:** rocrate-reference-identity (no GitHub issue; inline brief)
- **Branch:** `feat/rocrate-reference-identity/aliz`
- **Source:** `/contig-next` pick, 2026-09-25

## Brief

Map the run's `ReferenceIdentity` (mode, iGenomes `genome` key, `fasta`/`gtf` paths with
their sha256, harmonization, and `known_sites`) into the RO-Crate export produced by
`to_rocrate` in `src/contig/provenance.py`. This closes the C5 follow-on deferred in
`docs/planning/reference-identity-provenance/prd.md:188` ("a follow-on can map the
identity into the crate"); the C5 row in `CAPABILITY_ROADMAP.md:2475` still lists
RO-Crate as pending.

Constraints and caveats:
- RO-Crate 1.1 has no standard term for a reference genome, so pick and document a
  vocabulary.
- Where a checksum is unavailable (iGenomes mode, unhashable file), emit the entity
  without one rather than faking it (the current `_file_entity` requires a `sha256` str).
- Never emit `annotation_version` while it is null.
- Records with no `reference_identity` (Snakemake, older runs) must produce a
  byte-identical crate; check existing rocrate tests first.
- Offline, stdlib-only, no signed-field change.
- Optionally fold in `AnnotationProvenance` (C7) if it fits the same shape.
