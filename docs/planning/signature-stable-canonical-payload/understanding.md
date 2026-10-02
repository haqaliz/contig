# Understanding: signature-stable canonical payload

## What is really being asked
Signed bundles must keep verifying after contig adds a model field or changes verdict logic, and
tampering must still be detected. Today they do not (five disclosed breaks, see below).

## Root cause (verified in code)
- Sign: `bundle._maybe_write_signature` -> `signing.sign_record(record)` over
  `canonical_record_bytes(record)` = `json.dumps(record.model_dump(mode="json"), sort_keys=True,
  separators=(",",":"))` (`signing.py:55-64`). Includes the `@computed_field` `verdict`
  (`models.py:399-401`).
- Verify: `cli._signature_status` (`cli.py:2792`) loads the bundle through
  `Model.model_validate_json` (`bundle.py:69-72`, `122-131`), then `verify_signature` RE-DUMPS the
  re-validated model. The stored JSON text is on disk but never used. So any field added to the
  model after signing (defaulting to null) changes the recomputed bytes, and a recomputed
  `verdict` changes them whenever rule-pack logic moves.

## Direction (needs PRD confirmation)
Verify over the stored raw JSON: parse `run_record.json` / `reproduce_record.json` to a dict and
canonicalize that dict with the same sort/compact/UTF-8 rule. Why this is likely byte-identical
to every existing signature: the file is `model_dump_json` of the same model that was signed, and
parse-then-`json.dumps` round-trips the same values (floats via repr). Consequences:
- Old bundles verify with no version marker, because their stored JSON is old-shape.
- Future field additions and verdict-logic changes cannot break anything: no recompute.
- Tampering still fails: any edit to the file (including the stored `verdict`) changes the bytes.
- No `canonical_version` is needed for existing bundles. The sidecar could still carry one as a
  forward marker; no signed-field change, so no sixth break.
Must be proven, not assumed: hand-built old-shape fixtures, and a float/unicode/None round-trip
equality test of raw-canonicalization vs the legacy model path.

## Affected areas
- `src/contig/signing.py` (new raw-bytes canonicalizer + raw verify; stale docstring at :58).
- `src/contig/cli.py:2792-2810` (`_signature_status`: pass raw file content).
- `src/contig/bundle.py` (expose raw record text/dict for a run and a reproduce bundle).
- Dashboard: no canonicalization in TS; it shells out to `contig verify --json`
  (`output-integrity-card.tsx`, `runs.ts:1100`). No change expected.
- Tests that pin breaks: `test_signing.py:167,345` (+ still-verifies twins), `test_reproduce_bundle.py:348`,
  `test_reproduce_checkout_hash.py:367`. These flip to "still verifies".

## Contradictions / corrections to the brief
- Five disclosed breaks, not four: also `ReferenceIdentity.known_sites` (v0.60.0, `test_signing.py:345`).
- The verdict break has no pinning test today (only prose).
- `signed_sha256` in the sidecar is written but never checked.
- `signing.py:58` docstring says `model_dump_json`; code uses `model_dump` + `json.dumps`.
- The brief's "add a canonical_version with a legacy path" is probably unnecessary; see Direction.

## Open questions for the interview
1. Keep the model-based `verify_signature(record, ...)` API (used by tests, sign round-trip) or
   replace it? Proposal: keep `sign_record`; add `verify_signature_bytes`/raw path; CLI uses raw.
2. If the stored file was re-saved by a newer contig (does any command rewrite
   `run_record.json` after signing?) the signature would fail for a legit reason; check and decide.
3. Check `signed_sha256` too (cheap integrity cross-check) or leave out of scope?
4. Behavior when no raw file exists (record passed in memory only): fall back to the model path.

## Guardrails
Layer 2 (reproducibility). No new dependency. No `models.py` change. Not Layer 1.
