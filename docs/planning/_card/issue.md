# reference-identity-provenance (capture reference identity into run provenance)

- **Type:** feat
- **Id/slug:** reference-identity-provenance
- **Owner:** aliz
- **Branch:** feat/reference-identity-provenance/aliz
- **Source:** inline brief (no GitHub issue; handed off from `contig-next`)

## Brief

Ship the **first slice of capability C5** (reference & input-data integrity):
capture **reference identity** into the run's provenance.

Today `RunRecord` carries `genome` / `fasta` / `gtf` as bare **paths/keys**
(`src/contig/models.py:294-296`) with no checksums, no annotation/GTF version, and
no known-sites. So a run cannot prove *which* genome assembly and annotation it
actually ran against — the manifest pins tools and params, but not the **data they
ran against**.

This slice adds deterministic capture of reference identity:
- build name (assembly) and annotation/GTF version,
- `FileHash` checksums of the reference (FASTA) and known-sites files,
- surfaced in provenance (the bundle / run record) and the `contig methods` output,

built **test-first** per the repo's standing discipline.

## Scope (this slice only)

- **Capture-and-reproduce only.** Hash + record reference/known-sites identity into
  the bundle; it appears in provenance and reproduces on re-run.
- The pre-flight contig-naming / assembly-signature **mismatch detector** is the
  deliberate *next* slice and is where the real feasibility risk lives — do NOT
  pull it into this one.

## Known caveats to settle in the dig

- **iGenomes-key case:** when `genome` is an iGenomes key, the FASTA may be a remote
  asset not present locally. Record the key + resolved identity rather than hashing
  a missing local file. A run must NOT fail because a remote reference can't be
  hashed → degrade gracefully (record the key, mark the checksum unavailable).
- **Where capture happens:** confirm whether reference inputs are known at finalize
  (where other provenance/checksums are captured) and whether known-sites paths are
  available from the resolved params. Mirror the existing checksum/provenance path.
- **Annotation/GTF version:** how reliably can a version be derived (from the GTF
  filename, an iGenomes manifest, or left null)? Don't fabricate a version.

## Provenance / why this is next (from contig-next ranking)

- Cleanest **unblocked, testable** slice on the board: deterministic, reuses the
  existing `FileHash` / provenance plumbing (`src/contig/models.py:18`), no new
  compute path, no metric-source blocker.
- Deepens **reproduce**, a core moat requirement (CLAUDE.md): pins the *data* the
  run executed against, not just tools/params.
- **Dependency-first:** unblocks the C5 pre-flight mismatch check AND the C2
  reference/build-mismatch repair (`missing_reference` is already a `FailureClass`,
  `src/contig/models.py:185`).
- Source: `docs/technical/CAPABILITY_ROADMAP.md` C5 (~lines 224-249) — "a run
  succeeds against the wrong genome" silent-failure class.

## Open questions for the interview

- Exact shape of the captured identity: new fields on `RunRecord` vs. a nested
  `ReferenceIdentity` model? (build, annotation_version, fasta checksum, gtf
  checksum, known_sites[] checksums, igenomes_key).
- Known-sites: are their paths available to the engine today (resolved params), or
  is that out of scope until a later slice?
- Annotation/GTF version source — derive vs. leave null when unknown.
- Surface footprint: provenance panel + `contig methods` only, or also the HTML
  report / dashboard provenance card this slice?
- Reproduce semantics: does re-run re-capture identity, and do we assert the
  captured checksums are stable across the re-run?

## Guardrails (CLAUDE.md)

- **Layer 2 only** (verify/reproduce); no Layer-1 workflow authoring.
- **No raw-read egress** — only hashes/metadata leave the machine; runs on the
  user's compute.
- **No correctness over-claiming** — capture/record only this slice; no mismatch
  *verdict* yet.
- **Test-first.**
