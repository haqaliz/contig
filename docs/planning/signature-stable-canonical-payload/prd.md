# PRD: signature-stable canonical payload

Status: draft for review. Source: inline brief (`docs/planning/_card/issue.md`) and
`understanding.md`. Roadmap-push, not demand-pull: no design partner asked for it.

## Problem Statement
Contig signs run and reproduce bundles with Ed25519 (opt-in via `CONTIG_SIGNING_KEY`). Verification
re-validates the stored JSON into a Pydantic model and re-dumps it (`signing.canonical_record_bytes`,
`signing.py:55-64`; `bundle.py:69-72,122-131`; `cli.py:2792`). So anything that changes the dump of an
unchanged file breaks old signatures: a new model field (defaults to null), or a change to the
`@computed_field` `verdict` logic. Five breaks are disclosed in `CAPABILITY_ROADMAP.md`/`CHANGELOG.md`
(verdict, reproduce slice 6, slice 8, `RepairStep.patch_applied`, `ReferenceIdentity.known_sites`),
none fixed. A signature that dies on upgrade undermines the "auditable, reproducible" promise.

## Goals & Success Metrics
- G1: a bundle signed by any prior contig version verifies after upgrade. Metric: hand-built
  old-shape fixtures for each of the five breaks verify (the existing "no longer verifies" pins flip).
- G2: future model-field additions and verdict-logic changes never invalidate a signature. Metric:
  a test adds an unknown field to the stored JSON path's model and verification is unaffected.
- G3: tampering is still detected. Metric: editing any byte-level value in the stored file (including
  `verdict`) fails verification.
- G4: zero false mismatches on existing bundles. Metric: for a corpus of records,
  `canonical(raw stored JSON)` equals legacy `canonical_record_bytes(model)`.

## Personas & Scenarios
Lone computational biologist or core facility that signs bundles for a Methods section or audit,
then upgrades contig months later and re-runs `contig verify <run>`; today it exits 1 "record was
modified" though nothing was modified.

## Requirements
Must:
- M1: `contig verify` verifies run bundles over the stored raw JSON of `run_record.json`: parse to a dict, canonicalize with the existing rule (sort_keys, compact separators,
  UTF-8), verify. No model re-validation or re-dump on the verify path. Reproduce bundles are never verified by any
  command today (`_signature_status` has one caller, `cli.py:2244`, taking a `RunRecord`); they get
  the raw verify as a library function plus a test only, no new CLI surface.
- M2: no `canonical_version` and no signed-field change; sidecar format unchanged (so no sixth break).
- M3: keep model-based `verify_signature(record, ...)` for callers without a file. Ordering: raw
  first; the model path runs ONLY when no record file exists, and is never a retry after a raw
  mismatch (that would let a tampered file pass whenever the model happened to match).
- M4: cross-check the sidecar's `signed_sha256` against the raw canonical hash; a disagreement is a
  distinct, clearly worded mismatch.
- M5: flip the five "no longer verifies" pins to "still verifies"; add a pin for the verdict case.
- M6: fix the stale `signing.py:58` docstring; document the contract and the semantic change in
  CHANGELOG and `CAPABILITY_ROADMAP.md`.
Should:
- S1: a malformed or non-object record file reports a mismatch (exit 1), never a crash.
Nice: none.

## Technical Considerations
- Semantic change (accepted): the stored `verdict` string is part of what is signed and is no longer
  recomputed at verify time. Verify now means "the file is exactly what was signed".
- Byte-identity is the central risk. `model_dump_json` (file) vs `model_dump(mode="json")`+`json.dumps`
  (legacy) can differ for non-finite floats (JSON emits null; legacy would emit `Infinity`) and
  possibly float formatting; the equality corpus must cover floats, non-ASCII, nested optionals,
  empty lists, and non-finite values. Where legacy bytes were never producible (non-finite), define behavior.
- Dashboard shells out to `contig verify --json` and re-implements nothing; no dashboard change.
- No `models.py`, dependency, or verdict/exit-code semantics change beyond the above. Layer 2.

## Risks & Open Questions
- R1: byte divergence on edge values (above) causing false mismatches. Mitigation: G4 corpus test.
- R2: a record file edited by hand then re-signed elsewhere is out of scope.
- R3: reasoned, not observed: no real long-lived signed bundles exist in CI; fixtures are hand-signed.
- Q1 (resolved): no command verifies reproduce bundles; see M1.
- Q2 (resolved, option 1, decided by the human): non-finite floats. Floats and non-ASCII are byte-identical between file JSON and legacy path, but `inf` is `null` in the file vs `Infinity` in legacy bytes. Decision: sign the stored text, so a non-finite claim is signed as null; the loader (`load_claims`) is not changed.
- Q3 (resolved): no user-facing surface relied on the recomputed-verdict signal; stated here.

## Out of Scope
`canonical_version`; signature-contract redesign; trust/identity of the public key (it is read from
the sidecar, so verify proves integrity, not signer identity); dashboard verification of reproduce
bundles (PRD N1 defers it); re-signing tooling; signing new fields.

## Outcome
Shipped as `signature-stable-canonical-payload` (Unreleased). Verification runs over the stored record file text; all five disclosed breaks no longer invalidate earlier signatures; the stored `verdict` is signed as written and not recomputed. Finite records sign byte-identically to before. Limits as stated: fixtures are hand-signed, reproduce bundles are still not verified by any CLI command, and an old-path bundle with a non-finite claim cannot be verified raw (believed unreachable, untested). See CHANGELOG [Unreleased].
