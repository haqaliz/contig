# Validator gate (PRD S2): recorded 2026-09-25

Run by the integrator outside the repo, in a throwaway venv. The validator is **not** a project
dependency.

- **Tool:** `roc-validator` 0.11.4 (crs4 `rocrate-validator`)
- **Command:** `rocrate-validator validate --no-paging --no-auto-profile --profile-identifier
  ro-crate-1.1 --requirement-severity RECOMMENDED --skip-availability-check --output-format json
  <crate-dir>`
- **Fixtures:** three `RunRecord`s built in a script, each exported with `to_rocrate` and written
  as `ro-crate-metadata.json`:
  - `baseline`: no reference, no annotation
  - `igenomes`: GATK.GRCh38 key, an s3 dbSNP, the s3 brace-pattern known_indels, and two
    annotations
  - `explicit`: a hashed FASTA; a harmonized (`add_chr`) GTF with no hash; a relative-path
    dbSNP with a hash; a duplicate dbSNP with a null path
- **Comparison:** the same `baseline` record exported by **master's** `to_rocrate`.

## Result

| Crate | Issues vs its comparison |
|---|---|
| master `baseline` → branch `baseline` | **1 fixed, 0 new.** Fixed: REQUIRED `ro-crate-1.1_2.1`, "JSON-LD key `sha256` ... not present in the @context". The M1 term map resolves it. |
| branch `igenomes` vs branch `baseline` | **0 new** |
| branch `explicit` vs branch `baseline` | **1 new**, RECOMMENDED `ro-crate-1.1_24.1`: a one-item `mentions` array "SHOULD be a single value" |

**No new REQUIRED issue** comes from the list `@context`, `localPath`, or any reference, known-sites
or annotation entity. That answers the PRD's hard question: the validator accepts the term map.

## Findings acted on

- **First run:** every File's `encodingFormat` failed RECOMMENDED `ro-crate-1.1_27.1`. A bare EDAM
  IRI string is neither a MIME type nor a link to a `WebSite` contextual entity. We fixed it in
  `44f9b79`: `encodingFormat` is now `{"@id": <EDAM IRI>}`, with one deduplicated
  `WebSite` entity per format used. This is RO-Crate 1.1's "detailed descriptions of
  encodings" pattern. The re-run shows 0 new issues for these.
- **Kept deliberately:** a one-item `mentions` stays a list (RECOMMENDED 24.1), so consumers
  see a stable shape. The pre-existing `qcResults` carries the same warning on master.

## Pre-existing and out of scope (present on master, unchanged)

These are REQUIRED on master and unchanged by this branch:
- the root has no `license`, `datePublished` or `description`
- `parameters`, `verdict` and `qcResults` are not in the context
- nested non-flattened objects
- input/output Files are not shipped in the crate

They belong to a separate "make the crate RO-Crate-conformant" slice, and are recorded here so
that slice has a baseline.
