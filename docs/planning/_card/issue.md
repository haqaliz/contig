# Brief — verify-time concordance capture

Source: `contig-next` handoff prompt (feat `verify-time-concordance-capture`), run on
master at v0.54.0. No GitHub issue exists for this work (verified 2026-08-18: `gh issue
list` shows no matching item); the brief below is the task source.

## Brief

Ship the last C6 R4a capture gap: germline (`--concordance-vcf`/`-auto`) and
RNA-seq/single-cell (`--concordance-counts`/`-sc-counts`[-`-auto`]) concordance checks
computed at `contig verify` time are the only run-dir-derived verification families not
captured into the eval corpus (CHANGELOG v0.53.0, CAPABILITY_ROADMAP.md C6). Add a
verify-time capture channel — append a pending VerificationCase (pre-band value,
n_shared, status) to a sidecar on `contig verify`, promote via a
`verify-case-promote`-style path with expected status and a mutation-control pin —
without touching the signed record. Mirror the shipped `eval-concordance-capture`
pattern and its round-trip/per-kind pins; guards must not move. Caveat: push, not
demand-pull; the capture hook at verify time is net-new, and the channel must not break
the signed payload.

## Open questions (from the handoff, to resolve in the dig/interview)

- Capture point: the exact hook in the `contig verify` path where concordance results
  exist (and whether the pending-verify-corpus sidecar precedent at `self_heal.py`
  is reusable or a verify-time sidecar is net-new).
- Channel shape: same `pending_verify_corpus.jsonl` + `verify-case-promote` machinery,
  or a sibling sidecar? The handoff says "a verify-time capture channel that does not
  break the signed payload" — the run record must not gain fields that invalidate
  existing Ed25519 signatures.
- Scoring: the verify-corpus scorer must be able to re-derive concordance statuses from
  stored pre-band signals (`value`, `n_shared`) under current thresholds, with a
  mutation-control pin proving a threshold change flips a stored case.
- Guards: `verify-guard` (95.5%), `eval-guard` (92.9%), `heal-guard` (100%),
  `reproduce-guard` (13/14) must not move.

## Non-goals (guardrails from CLAUDE.md / the C6 record)

- No Layer-1 workflow authoring.
- No change to concordance's verdict semantics: at most WARN, never changes the verify
  exit code, `unverified` below 10 shared genes, six flags mutually exclusive.
- No new runtime dependency (stdlib-only is the standing contract).
- Capture must never alter any QC result or the signed record.
