# Understanding: rocrate-reference-identity

Dig of 2026-09-25 (three read-only agents: export code, reference capture, RO-Crate vocabulary).

## What the work is really asking

`contig export <run> --rocrate` produces an RO-Crate that says nothing about which reference
genome the run consumed, even though `RunRecord.reference_identity` has recorded it since the
C5 capture slice. Close that gap: project the already-recorded identity into the crate, offline,
from the record alone. This is the deferral named in
`docs/planning/reference-identity-provenance/prd.md:188` and `:203`.

Layer 2 (reproducibility/provenance). No Layer-1 drift.

## Affected code

- `src/contig/provenance.py:18-81`: `to_rocrate(record) -> dict` and `_file_entity`. It is pure
  and does not serialize. Graph order is descriptor, root, pipeline, inputs, outputs. Optional
  root keys (`nextflowVersion`, `contigVersion`) are already added only when truthy, and that
  pattern keeps byte-identity for records without a reference.
- `src/contig/cli.py:2881-2912`: `contig export --rocrate` calls `json.dumps(..., indent=2)`
  with no `sort_keys`, so insertion order is the byte order.
- Consumers: the dashboard only shells out to the CLI and streams the bytes
  (`dashboard/lib/runs.ts:1303`); nothing parses the crate. The crate is **not signed**;
  `signing.py:55` signs the RunRecord, which we only read.
- Tests: `tests/test_provenance.py:42-120` (12 tests, lookup by `@id`, no golden bytes);
  `tests/test_cli.py:4273-4301` (parses and checks `@graph[0]` is the descriptor).

## Data available on the record (`models.py:207-229`, `:356`, `:361`)

- `ReferenceIdentity`:
  - `mode` is `igenomes` or `explicit`.
  - Also carries `genome`, `fasta`, `gtf`, `fasta_sha256`, `gtf_sha256`,
    `annotation_version` (**always null, never populated**), `harmonized`,
    `harmonized_direction` (`add_chr`/`strip_chr`/`alias`) and `known_sites`.
- iGenomes mode: key only, with fasta/gtf/sha256 always None.
- Explicit mode: absolute resolved local paths. sha256 is None when the file is missing or
  unreadable.
- `KnownSiteIdentity`:
  - `role` (`dbsnp`/`known_indels`/`known_snps`), `path`, `sha256`, `source`.
  - Explicit paths are kept **as typed**, so they may be relative.
  - iGenomes paths are `s3://ngi-igenomes/...` with sha256 None, and `known_indels` holds an
    **unexpanded brace glob** `{A,B}.vcf.gz`.
- `annotation_identity: list[AnnotationProvenance]` (tool, version, db_version = "cache/build",
  raw_header). This is the optional fold-in and has the same shape of gap.

## Contradictions and hazards (flagged, not papered over)

1. **Harmonized GTF.** When `harmonized` is true, `gtf`/`gtf_sha256` describe Contig's
   *rewritten* copy under `runs/<id>/harmonized/`, not the user's original annotation
   (`cli.py:802`). A crate that labels it "the reference GTF" without saying so would misstate
   provenance. The crate must name the harmonization.
2. **The `sha256` term is unmapped in the RO-Crate 1.1 context.** The existing input/output
   Files already use it, so JSON-LD expansion silently drops every checksum in today's crates.
   This defect predates the card. Fixing it globally (1.2 context, or an extra term map) changes
   the bytes of **every** crate, which conflicts with the brief's byte-identical constraint.
   This is a decision for the user, not the implementer.
3. **No established "reference genome" type** exists in RO-Crate 1.1–1.3, Workflow Run Crate 0.6
   or Bioschemas. The closest spec text is Process Run Crate's "reference datasets" in a
   `CreateAction.object`. The crate has no CreateAction today, and adding one is a restructure.
   EDAM terms exist and are current: `data_2340` (genome build id), `format_1929` (FASTA),
   `format_2306` (GTF), `format_3016` (VCF).
4. **Local paths are not URIs.** RO-Crate says an absolute-URI `@id` should be downloadable.
   Non-shipped files use `#`-prefixed ids plus `localPath` (a 1.2 term). An s3 path could be a
   `contentUrl`, but the brace glob is not a fetchable URL.
5. **The brace glob.** Emitting `{A,B}.vcf.gz` as if it were one file is dishonest. It needs a
   decision: expand it, or record it verbatim and label it a pattern.

## Honesty contract (carried from C5)

- Never fabricate a checksum. Omit the key when sha256 is None; don't write null.
- Never emit `annotation_version` while it is null.
- Records with `reference_identity is None` (Snakemake, legacy) produce byte-identical crates.
- No `models.py` change and no signed-field change. Stdlib-only, offline.

## Open questions for the PRD interview

- Q1: Leave the context at 1.1, add a term map only when reference entities are present, or fix
  `sha256` for all crates (which breaks byte-identity)?
- Q2: How to attach the entities: a root-level link (`mentions`, or a named property) or a new
  `CreateAction.object` (Workflow Run Crate-shaped, bigger)?
- Q3: Fold in `AnnotationProvenance` now, or leave it for later?
- Q4: For the iGenomes brace glob: expand it, or keep it verbatim and label it a pattern?
