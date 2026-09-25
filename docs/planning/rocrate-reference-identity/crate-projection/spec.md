# Spec: `crate-projection` (the only aspect of `rocrate-reference-identity`)

## Problem slice and user outcome

`to_rocrate` (`src/contig/provenance.py:23`) projects a `RunRecord` into RO-Crate JSON-LD but
ignores `reference_identity` and `annotation_identity`, and its 1.1 context leaves `sha256`
unmapped. After this aspect, an exported crate names the reference, the known sites and the
annotation tool the run used, and its checksums resolve to IRIs.

## In scope

PRD M1–M7 and S1–S2, all in `src/contig/provenance.py`, with tests in
`tests/test_provenance.py`. Docs: CHANGELOG `[Unreleased]`, and the C5 row in
`CAPABILITY_ROADMAP.md` / `FEATURES.md`.

## Out of scope

Everything listed under "Out of Scope" in the PRD. No change to `models.py`, `cli.py`, the
dashboard, signing or the bundle.

## Acceptance criteria (testable)

1. **Context:** `crate["@context"] == ["https://w3id.org/ro/crate/1.1/context", {"sha256":
   "http://schema.org/sha256", "localPath": "https://w3id.org/ro/terms#localPath"}]` for
   every record.
2. **Graph unmoved:** for a record with `reference_identity=None` and
   `annotation_identity=[]`, `crate["@graph"]` equals a snapshot of today's graph built in the
   test from the same record. The root has no `mentions` key.
3. **iGenomes:**
   - `#reference` carries `identifier` → `#reference-genome-key`, which is a `PropertyValue`
     with `propertyID` EDAM `data_2340` and `value` equal to the key.
   - There are no `#reference-fasta` or `#reference-gtf` nodes.
   - No node carries `sha256`, `localPath` or `version` for the reference.
4. **Explicit, both hashes:**
   - `#reference-fasta` and `#reference-gtf` are `File`s, each with `localPath` equal to the
     recorded path, the right EDAM `encodingFormat`, and `sha256` equal to the recorded value.
   - Both are listed in `#reference`'s `hasPart`.
5. **Explicit, a missing hash:** a None `gtf_sha256` produces a GTF node with **no `sha256`
   key**. A None `gtf` produces no GTF node at all.
6. **`annotation_version`:**
   - null → no `version` key on any reference node.
   - A constructed non-null value → `version` appears on `#reference-gtf` only.
7. **Harmonized:**
   - `harmonized=True, direction="add_chr"` → the GTF `description` names the harmonized
     copy, and `#reference-harmonization` has `value` equal to `"add_chr"` and is referenced
     from `#reference`'s `additionalProperty`.
   - direction None → no `value` key.
   - `harmonized=False` → neither node nor key exists.
8. **Known sites:**
   - Explicit source → a `localPath` holding the verbatim path (a relative path stays
     relative).
   - iGenomes s3 path → `contentUrl` and no `localPath`.
   - A path containing `{` → no `contentUrl` and no `localPath`, and a `description`
     containing the verbatim pattern.
   - A duplicate role → the second one gets id suffix `-1`.
   - A null path → only `alternateName` and `encodingFormat` are set.
   - All known-site nodes are listed in `hasPart`.
9. **Annotation:**
   - Two entries → `#annotation-0` and `#annotation-1` `SoftwareApplication`s, both in the
     root `mentions` in order.
   - A None `version` or `db_version` → the matching key is absent.
   - `description` reads "cache/build X".
   - `raw_header` never appears.
   - A record with annotations but no reference → `mentions` contains only the annotations.
10. **Order and determinism:**
    - The `@id` sequence of the graph matches the PRD M6 order.
    - Two calls on the same record are equal.
    - `json.dumps(crate, indent=2)` is identical across two calls.
11. **No null leaks:** no node anywhere in the crate has a value of `None` (a recursive walk).
12. **CLI smoke:** the existing `tests/test_cli.py` export tests pass unchanged.
13. **Manual validator gate (S2):** recorded in this directory before merge.

## Dependencies and sequencing

None outside this module. Suggested TDD order: context (1–2) → iGenomes (3) → explicit and
hashes (4–6) → harmonized (7) → known sites (8) → annotation (9) → order and no-null sweep
(10–11) → docs → validator gate.

## Risks specific to this aspect

- **Separate test fixture factories.** `tests/test_provenance.py` builds its own `RunRecord`s.
  Add a local factory that sets `reference_identity`/`annotation_identity`, rather than
  widening shared fixtures that other suites use.
- **The validator gate can fail.** If an external validator rejects the list context or
  `localPath`, that is a real finding. Record it, and decide at the gate whether to adjust,
  rather than shipping silently.
