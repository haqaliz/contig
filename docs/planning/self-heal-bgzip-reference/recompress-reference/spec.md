# Aspect spec: recompress-reference

Single aspect of the `self-heal-bgzip-reference` feature (see `../prd.md`). It is
the whole slice — one cohesive self-heal path — so there is exactly one aspect.

## Problem slice & user outcome

A Contig-launched nf-core/sarek run whose `--fasta` is a plain-`gzip`'d (non-BGZF)
reference fails at `SAMTOOLS_FAIDX` with `Cannot index files compressed with gzip,
please use bgzip`. Outcome: the engine detects it, decompresses the reference to
plain uncompressed `.fa` in run-scoped scratch, redirects `params["fasta"]`,
retries, and the run completes — unattended.

## In scope

- New `FailureClass` `reference_not_bgzf` + a narrow detector branch (faidx-specific).
- A `propose_patches` branch → `Patch(kind="reference", operation={"recompress_reference": True})`.
- A `_recompress_reference` helper (stdlib-gzip streaming decompress, magic-byte
  discrimination, run-scoped scratch, in-memory `params["fasta"]` redirect,
  one-per-run guard) dispatched from `_apply_patch_and_maybe_build`.
- Detector-corpus golden case + held-out twin.
- Reproduce-safety (launch.json keeps the original fasta; rerun re-derives).
- Injected-executor + real-gzip-fixture tests; no real samtools/nf-core in CI.

## Out of scope

Everything in the PRD's Out of Scope (rnaseq/other assays, CRAM↔BAM, BGZF target,
corrupt-gzip, the `resolve_reference` gtf-coupling quirk).

## Acceptance criteria (testable)

- AC1 — a faidx `Cannot index files compressed with gzip` log classifies as
  `reference_not_bgzf` (not `tool_crash`); golden + holdout corpus cases score correct.
- AC2 — `propose_patches` returns exactly the recompress reference patch; not `safe`.
- AC3 — magic-byte guard: plain-gzip → proceed; valid BGZF → left untouched (give up,
  no redirect); uncompressed / non-gzip → give up; missing `params["fasta"]` → give up.
- AC4 — end-to-end: executor fails attempt 1 with the faidx log, succeeds on retry →
  record succeeds, outcome `recompressed_reference_and_retried`, `params["fasta"]`
  redirected to the scratch `.fa`, exactly one recompress, the re-run happened.
- AC5 — one-recompress-per-run guard: a persisting failure gives up honestly, never loops.
- AC6 — reproduce-safety: after a recompress heal, launch.json / reproduce sidecar
  still carries the ORIGINAL fasta path; `rerun` re-derives the heal from it.
- AC7 — the full suite stays green; eval-detector guard 24/24; eval-guard holdout
  re-baselined deliberately.

## Dependencies / sequencing

Detector+class first (unblocks corpus + repair), then repair patch, then the helper,
then the loop wiring, then reproduce-safety, then breadcrumb/docs. See the plan.

## Aspect-specific risks

PRD R2 (BGZF discrimination — the top correctness risk) and R6 (orphaned sidecars)
land in this aspect. R3 resolved favorably; R5 dissolved by using stdlib streaming.
