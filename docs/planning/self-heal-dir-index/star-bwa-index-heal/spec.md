# Aspect spec — star-bwa-index-heal

The single aspect of `self-heal-dir-index`: detect, build (into scratch), redirect, and
retry a missing or version-incompatible STAR aligner index (and classic BWA index where a
supported pipeline uses it), on the existing C2 `IndexBuilder` self-heal seam. See the
[PRD](../prd.md) and [understanding](../understanding.md).

This is treated as ONE aspect (not split) because the change is cohesive and sequentially
dependent: detector classifies → parser parses → seam builds into scratch → params
redirect → retry. Parallelism is low (mostly `self_heal.py` + `detect.py` + corpus), so
the plan is sequential TDD phases.

## Problem slice & user outcome

A run handed a stale/missing/old-version STAR index fails hard with no recovery today
(misclassified as `missing_reference` or degraded to `tool_crash`). Outcome: the engine
detects it, rebuilds the index from the run's resolved reference into a run-scoped scratch
dir, redirects the retried run at the scratch index, and continues — pausing once for the
inherited `needs_confirmation` approval. Honest give-up otherwise; never a false pass.

## In scope

- Detector signatures (`detect.py`) for STAR-missing, STAR-version-incompatible,
  BWA-missing → `missing_index` (reuse the class). Narrow enough to not swallow a
  wrong-reference.
- Parser/dispatch generalization (`self_heal.py`) off pure file-extension to a kind
  discriminator; normalize a STAR inner-file token to its parent directory.
- Scratch build + redirect: build into `runs/<id>/healed_index/...`, resolve the source
  FASTA(+GTF) from `params["fasta"]`/`params["gtf"]`, run STAR `genomeGenerate` / `bwa
  index` via the injected `IndexBuilder`, mutate the retried run's index param to the
  scratch path. Never mutate the user's supplied index in place.
- Dir/sidecar non-empty success check; honest `index_unresolvable`/`index_build_failed`.
- Reproduce (`rerun`/`resume` re-derive, no scratch path persisted) + new-reason-retry
  give-up + STAR version recording.
- One golden corpus case per new signature; `eval-detector` stays 100%.

## Out of scope

bwa-mem2 + aligner-mismatch; corrupt/partial STAR signature; auto-heal without approval;
stale-index pre-flight detection; BAM/CRAM `.csi`; peak-RSS scaling; assembly-signature
mismatch. (All per PRD Out of Scope.)

## Acceptance criteria (testable — these are the Phase-6 RED tests)

Mirror the PRD "Acceptance" section: per kind (STAR-missing, STAR-version-incompat,
BWA-missing where live) — (1) `diagnose_failure` classifies as `missing_index`, a
wrong-reference control does not; (2) `self_heal_run` with an injected builder detects →
applies → builds into scratch with expected argv → redirects param → retries with
`built_index_and_retried`; (3) give-up paths (`index_unresolvable` /
`index_build_failed` / redirect-param-unidentifiable) yield a non-passing verdict; (4) a
golden corpus case, `evaluate_detector` == 100%. Plus once: (5) reproduce re-derives;
(6) new-reason retry surfaces honestly; (7) STAR version recorded.

## Dependencies & sequencing

Phase 0 (param-name + BWA-applicability determination) gates the redirect design and BWA's
depth. Detector (Phase 1) and parser (Phase 2) precede the build seam (Phase 3); redirect
(Phase 4) depends on the seam; reproduce/new-reason/version (Phase 5) depend on the full
loop; end-to-end + corpus (Phase 6) closes it.

## Aspect-specific open questions / risks

- **BWA live target (Phase 0):** classic `bwa index` may have no redirectable param in the
  currently-supported assays (rnaseq→STAR; sarek default→bwa-mem2; methyl-seq→bwa-*meth*, a
  different tool). If so, BWA is **detector+corpus-only** this slice (heal deferred), stated
  honestly — not silently dropped.
- **STAR index param name (Phase 0):** confirm nf-core/rnaseq's `--star_index` (or current
  param) is the redirect target; if it can't be set, redirect give-up is
  `index_unresolvable` (R4).
- **OQ1 (S1 sink):** RepairStep.detail vs a provenance field for the STAR version.
