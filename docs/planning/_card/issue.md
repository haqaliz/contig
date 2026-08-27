# Card: reproduce-doi-pdf-intake

Source: contig-next handoff (2026-08-27). No GitHub issue exists — this is the
inline brief, treated as the task source. Owner: aliz.

## Brief

`contig extract-claims` accepts plain text/markdown only; the standing C8
deferral is PDF parsing, DOI resolution, and paper fetching (extract-claims
PRD R5; CHANGELOG v0.52.0 honest-scope note). Build the intake slice: DOI or
paper-PDF input to extract-claims — DOI→PDF fetch behind an opt-in network
flag in the slice-6 `--allow-fetch` posture (refused-with-message otherwise),
and a PDF→text seam mirroring the Fetcher/Installer injectable-seam pattern
with no new Python dependency, never executed in CI — feeding the shipped
extractor unchanged, with the draft-only `load_claims` round-trip invariant
intact (never emit a draft the reproduce path rejects). Caveat to design
around: two-column scientific PDFs degrade text extraction and the whole
PDF/DOI path is reasoned-not-observed (the standing C8 manual real-repo gate
has not run); the draft-only invariant (wrong claims degrade to UNVERIFIED,
never REPRODUCED) is the safety net. Keep it input-generation only: zero
changes to `run_reproduction`/`classify`/`ClaimResult`/bundle/signing.