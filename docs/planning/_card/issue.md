# Unit of Work -- runtime-reference-mismatch-detector

> Inline brief (source: contig-next handoff, 2026-08-24). No GitHub issue exists for
> this slug; the branch `feat/runtime-reference-mismatch-detector/aliz` and the PR
> carry the id.

## Brief

Seed the runtime half of the reference-integrity family, which every shipped
harmonization slice explicitly left open ("no new `reference_mismatch`
`FailureClass` or detector-corpus case" -- provenance-only capture was the
deliberate choice then; the C2 deferral list still names "a runtime
`reference_mismatch` detector-corpus case"). Ship a new `FailureClass` literal
plus a narrow AND-guarded detector branch on the hard-fail log signatures of a
wrong reference (aligner fatal errors on reads whose contigs are absent from the
reference), one golden corpus case plus an independently authored holdout twin,
and a heal-guard give-up scenario, syncing the dashboard `FAILURE_CLASSES`
taxonomy; refreeze baselines via `--update-baseline` as deliberate acts.

Caveat to honor: the needle is reasoned-not-observed (no real mismatched-reference
run in CI) and must not double-classify the `qc_anomaly` verdict-trigger family,
which already surfaces wrong-reference runs that complete with a QC FAIL; the
assembly-signature pre-flight form stays blocked and is out of scope. Test-first,
stdlib-only, no real nf-core run in CI.

## Cited context (docs/technical/CAPABILITY_ROADMAP.md)

- C2 deferred-to-later list: "…the wider failure catalog -- the assembly-signature
  form of reference/build mismatch (no sample-side contig signal in raw FASTQ or
  finished bundle)… a runtime `reference_mismatch` detector-corpus case… and pin
  conflict."
- chr-prefix GTF harmonization slice: "Provenance-only eval capture, matching
  v0.9.0 -- no new `reference_mismatch` `FailureClass` or detector-corpus case."
- per-contig alias slice: same provenance-only choice; the runtime half was the
  "moat-vs-architecture question" resolved toward provenance capture then
  (docs/planning/self-heal-reference-mismatch/understanding.md, update note).
- C5: "Kills the wrong-genome silent-failure class; deepens reproduce."
- `qc_anomaly` verdict-trigger slice (shipped, Unreleased): a run that completes
  green and whose QC reduces to FAIL is diagnosed `qc_anomaly` -- the family this
  slice must not double-classify.