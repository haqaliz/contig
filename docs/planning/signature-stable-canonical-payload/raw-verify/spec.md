# Spec: raw-verify (the only aspect of signature-stable-canonical-payload)

## Problem slice and outcome
`contig verify <run>` must verify a signed run bundle over the stored `run_record.json` bytes,
canonicalized, so old signatures survive model growth and verdict-logic change. Reproduce bundles get
the same raw verification as a library function (no CLI command verifies them today).

## In scope
- Pure raw canonicalizer in `signing.py` (same rule: sort_keys, `(",",":")`, UTF-8, default ensure_ascii).
- A bundle-level helper that reads record file + `signature.json`, verifies raw, cross-checks `signed_sha256`.
- `_signature_status` (`cli.py:2792`) uses it; model path only when no record file exists.
- Flip the "no longer verifies" pins; add the verdict pin; docstring fix; CHANGELOG + roadmap notes.

## Out of scope
`canonical_version`; sidecar or signed-field changes; new CLI commands; dashboard changes; key trust.

## Acceptance criteria
1. Corpus test: for floats (`1e16`, `1e-7`, `0.1+0.2`), non-ASCII, nested optionals, empty lists/dicts,
   `canonical_from_raw(record.model_dump_json(indent=2)) == canonical_record_bytes(record)`.
2. Hand-built old-shape fixtures (record file lacking the newer keys, signed over its own canonical
   bytes) verify for: verdict-logic change, reproduce slice 6 fields, slice 8 field, `patch_applied`,
   `known_sites`.
3. Editing any value in the stored file, including `verdict`, fails verification.
4. Sidecar whose `signed_sha256` disagrees with the raw hash fails with a distinct message even when
   the signature itself verifies.
5. Malformed / non-object record file => mismatch (exit 1), not a crash.
6. Raw mismatch never falls back to the model path; model path only when the record file is absent.
7. Non-finite audit: claims loader rejects non-finite `claimed`; test documents that observed values
   are rejected pre-record, so `Infinity` cannot be signed.
8. `uv run pytest` green; `--json` output keys unchanged on the success and plain-mismatch paths.

## Risks
Byte divergence (R1) covered by criterion 1; fixtures are hand-signed, not observed.
