# PRD: `rocrate-reference-identity`: say which reference a run used, in the RO-Crate

- **Slug:** `rocrate-reference-identity`
- **Branch:** `feat/rocrate-reference-identity/aliz`
- **Capability:** C5 (reference and input-data integrity), the RO-Crate follow-on deferred at
  `docs/planning/reference-identity-provenance/prd.md:188,203`. It also closes the parallel C7
  gap for annotation provenance.
- **Source:** inline brief (`docs/planning/_card/issue.md`); dig in
  `docs/planning/_card/understanding.md`. Decisions were taken in an interactive interview on
  2026-09-25.
- **Honest scope:** this is roadmap-pull, not demand-pull. No design partner asked for it, and
  nothing parses the crate today.

---

## Problem Statement

`contig export <run> --rocrate` is Contig's portable provenance artifact. It is what a run hands
to someone outside Contig. Today it **cannot say which reference genome the run consumed**,
although the record has held that since the C5 capture slice (`RunRecord.reference_identity`,
`models.py:356`). The same applies to the variant-annotation tool, version and cache
(`annotation_identity`, `models.py:361`). The crate therefore answers "which pipeline, which
containers, which inputs" but not "against which genome": the first question someone
reproducing the run asks, and the one behind a notorious silent-failure class (a run that
"succeeds" against the wrong build).

The dig found a second, pre-existing defect. The crate declares the RO-Crate **1.1** context,
which **does not define `sha256`**. Every checksum on every input and output `File` the crate
has ever carried is therefore dropped by any JSON-LD processor that expands it; it survives only
to a reader that treats the file as plain JSON. Adding reference checksums on top of that would
repeat the bug.

## Goals & Success Metrics

1. **Reference identity is in the crate.** A record with `reference_identity` produces
   contextual entities for the reference, its FASTA and GTF, and each known-sites resource. The
   entities carry exactly the values on the record: no more, no fewer, and none fabricated.
2. **Checksums survive JSON-LD expansion.** For every crate, `sha256` (and the new `localPath`)
   resolve to IRIs. This is verifiable by inspecting the context map; no JSON-LD library is
   needed in CI.
3. **The existing graph is unmoved.** For a record with no reference and no annotation identity,
   the `@graph` is equal to today's output (dict equality). Only `@context` changes.
4. **Honesty contract holds.** A None checksum gives no `sha256` key. `annotation_version` is
   never emitted while it is null. A harmonized GTF is labelled as Contig's rewritten copy. A
   brace-pattern path is labelled a pattern.

These are measured by the test suite; there is no runtime metric.

## User Personas & Scenarios

- **Lone computational biologist** sharing a run with a collaborator or a methods reviewer: the
  crate now answers "GRCh38 via iGenomes" or "this FASTA, sha256 …" without access to Contig.
- **Core facility** archiving runs in an RO-Crate-aware repository (WorkflowHub, Zenodo): the
  checksums and reference now survive the repository's JSON-LD processing.

## Requirements

### Must-have

**M1: Context term map, for all crates.** `@context` becomes a list: the existing 1.1 URL
followed by a map object:
`{"sha256": "http://schema.org/sha256", "localPath": "https://w3id.org/ro/terms#localPath"}`.
These are the exact IRIs the RO-Crate 1.2 context uses, verified 2026-09-25. The same
context is used for every crate, whether or not a reference is present, so it is deterministic.

**M2: Reference entities, linked by `mentions`.** When `record.reference_identity` is not None:
- The root Dataset gains `"mentions": [{"@id": "#reference"}, ...]`, added after
  `contigVersion`. The key is absent when there is nothing to mention.
- `#reference` has `@type` `Dataset`, a `name` in the `contig methods` wording, and `hasPart`
  listing the file entities below that exist.
  - **iGenomes mode:** `identifier` points to `#reference-genome-key`, a `PropertyValue` with
    `propertyID` `http://edamontology.org/data_2340` (Genome build identifier), `name` `genome`
    and `value` set to the key. `name` is "iGenomes {key} reference (downloaded by the
    pipeline)". There are no FASTA or GTF entities, because the record has none.
  - **Explicit mode:** `#reference-fasta` and `#reference-gtf` are `File`s, each emitted only
    when its path is non-null. Each has:
    - `name` set to the basename
    - `localPath` set to the recorded path
    - `encodingFormat`, EDAM `format_1929` (FASTA) or `format_2306` (GTF)
    - `sha256` **only when non-null**
- File ids are `#`-prefixed, because the files are not shipped in the crate and a local path
  is not a downloadable URI (RO-Crate 1.2, data entities).

**M3: Harmonization.**
- When `harmonized` is true, `#reference-gtf` gains a `description` stating it is
  Contig's contig-name-harmonized copy of the user's annotation, not the original. `#reference`
  gains `additionalProperty` pointing to `#reference-harmonization`, a `PropertyValue` with
  `name` `contig_harmonization` and `value` set to the direction (`add_chr`/`strip_chr`/
  `alias`).
- If `harmonized_direction` is None, `value` is omitted rather than invented.
- The source is `ReferenceIdentity.harmonized` / `.harmonized_direction` only. The duplicate
  `RunRecord.harmonized_reference_direction` (`models.py:362`) is not read, so the crate has
  one source of truth.
- When `harmonized` is false, none of this appears.

**M4: Known sites.**
- Each `KnownSiteIdentity` becomes a `File` with id `#known-sites-{role}` (with suffix
  `-{n}` from the second occurrence of a role on, in record order). It is listed in
  `#reference`'s `hasPart` and has:
  - `alternateName` set to the role
  - `name` set to the basename of the path
  - `encodingFormat` EDAM `format_3016` (VCF)
  - `sha256` only when non-null
- Where the path goes:
  - **Explicit source:** the path goes in `localPath` **verbatim**, even if relative, because
    the record keeps it as typed and we never resolve it after the fact.
  - **iGenomes source:** the path goes in `contentUrl`, because it is where the pipeline
    fetches from.
  - **A path containing a brace pattern (`{`):** no `contentUrl`, no `localPath`. Instead,
    `description` records the pattern verbatim and states it expands to more than one file and
    is not itself one downloadable file.
- A known-site with a null path emits `alternateName` and `encodingFormat` only.

**M5: Annotation provenance.** Each entry of `record.annotation_identity` becomes a
`SoftwareApplication` with id `#annotation-{n}` (0-based, in record order), mentioned from the
root. It has:
- `name` set to the tool
- `version` only when non-null
- `description` "cache/build {db_version}" only when `db_version` is non-null, using the
  `contig methods` wording, never "database version"

`raw_header` is **not** emitted, because it is bulky and already on the record.

**M6: Graph order and determinism.**
- The graph order is descriptor, root, pipeline, inputs, outputs, then `#reference`, then
  `#reference-genome-key` / `#reference-fasta` / `#reference-gtf` /
  `#reference-harmonization` in that order, then the known sites in record order, then the
  annotations in record order.
- Two calls on the same record give equal output.
- Nothing is fetched, hashed or resolved; the output is a pure projection of the record.

**M7: `annotation_version` stays out while null.** It is always null today. If it is non-null,
it is emitted as `version` on `#reference-gtf` (explicit mode) and nowhere else. That branch is
pinned by a constructed record.

### Should-have

- **S1.** The CHANGELOG entry and the C5 row in `CAPABILITY_ROADMAP.md` / `FEATURES.md` both
  record the vocabulary choice and the context fix. That includes the fact that **every
  exported crate's bytes change** (the `@context` only).

- **S2. A manual validator gate before merge.** Run one exported crate, from a
  fixture record with every branch populated, through an external RO-Crate validator
  (e.g. `rocrate-validator` in a throwaway venv, not a project dependency). Record the result
  in the plan dir. CI can only prove we emit what we designed; the validator is the only check
  that a real consumer accepts it (R1).

### Nice-to-have

- None. Keep it small.

## Technical Considerations

- **The whole change is in `src/contig/provenance.py`** plus tests. There is no change to
  `models.py`, the CLI, the dashboard, signing or the bundle.
  - The crate is not signed (`signing.py:55` signs the record, which we only read).
  - The dashboard streams the CLI's bytes without parsing them (`dashboard/lib/runs.ts:1303`).
- **Byte-identity is relaxed deliberately.** The brief said crates with no reference must be
  byte-identical. The interview chose to fix the `sha256` context defect for all crates
  instead, so the contract becomes **`@graph` equality**. No existing test changes: the one
  context assertion (`tests/test_provenance.py:44`) checks the 1.1 URL is `in
  str(crate["@context"])`, which a list context still satisfies.
- **Effort:** small. One module (about 100 lines) plus about 20 focused tests. One aspect.
- **The vocabulary is ours**, built on spec terms. No standard reference-genome type exists in
  RO-Crate 1.1–1.3, Workflow Run Crate 0.6 or Bioschemas. We use schema.org and RO-Crate terms
  (`mentions`, `hasPart`, `identifier`, `PropertyValue`, `encodingFormat`, `contentUrl`,
  `localPath`) and EDAM IRIs, which were checked current on OLS. The docstring in
  `provenance.py` states this.
- **Stdlib-only and offline.** No JSON-LD library is added, not even in tests. Checking that
  "checksums survive expansion" means asserting the term map, not running an expander.
- **Reproducibility impact:** positive. The crate now pins the data the run ran against. There
  is no verdict or exit-code change.

## Risks & Open Questions

- **R1: Mixing 1.1 and 1.2 terms.** `localPath` is a 1.2 term used under a 1.1 context through
  our own map. That's valid JSON-LD, but an RO-Crate 1.1 validator may warn. Moving to the 1.2
  context was declined for this slice.
- **R2: Relative known-sites paths** are emitted verbatim in `localPath`. They are honest, but
  only meaningful relative to the original launch cwd, which the crate doesn't record.
- **R3: No consumer yet.** Nothing parses the crate, so the value is latent until someone
  imports one into WorkflowHub or Zenodo.
- **R4: Deviation from Workflow Run Crate.** A fully conformant crate would list the references
  in a `CreateAction.object`. `mentions` is a pragmatic stand-in, and restructuring is deferred.

## Out of Scope

- Moving to the RO-Crate 1.2/1.3 context, or restructuring into a Workflow Run Crate
  (`CreateAction`/`FormalParameter`).
- Resolving, expanding or hashing anything at export time, including the iGenomes brace pattern
  and relative paths.
- Emitting `raw_header` from the annotation provenance.
- Any change to `models.py`, the signed record, the CLI surface, or the dashboard.
- Annotation/GTF version resolution. That's still the C5 deferral: there's no reliable source.
