# Issue Card: self-heal CRAM↔BAM conversion

## Brief (inline, from the contig-next recommendation)

Build the C2 CRAM↔BAM conversion slice: a run supplied with the wrong alignment format
(CRAM where a tool needs BAM, or vice versa) is detected, converted via the shipped
scratch/redirect seam (bgzip-reference precedent: `<run_id>/healed_reference/`, in-memory
`params` redirect, bounded to one conversion per run), and retried with honest
`format_convert_failed`-style give-ups — never a false pass. New `FailureClass` + one
golden corpus case + one heal-guard scenario, detector guard held at 100%,
`--update-baseline` refreeze.

Caveats to resolve in the dig:

- This is push, not demand-pull — organic frequency is unmeasured.
- Confirm a reachable live trigger inside a Contig-launched pipeline (sarek's CRAM input
  path is the prime candidate); if none exists, ship detector-only like the bwa-mem2 slice
  (v0.11.0).
- Decide the direction scope first (CRAM→BAM is the common case).
- Keep it stdlib/subprocess-only, and test-first with injected executors — no real
  nf-core in CI.

Sources in the roadmap:

- `docs/technical/CAPABILITY_ROADMAP.md` (C2, bgzip-reference slice): "**Deferred:**
  CRAM↔BAM conversion (the other half of this class)."
- The bgzip-reference slice's detector/scratch/redirect pattern:
  `_recompress_reference`, `_gzip_kind` classifier, `reference_not_bgzf` `FailureClass`
  (`models.py`), `healed_reference/` scratch.
- The bwa-mem2 slice (v0.11.0) as the detector-only precedent if no live trigger exists.
- The `heal-guard` scenario pattern (catalog-coverage slice: `covered_classes` 11 → 15;
  `fasta_artifact` fixture directive precedent).

## Decision record

- Feature slug: `self-heal-cram-bam-conversion` (docs/planning/self-heal-cram-bam-conversion/)
- Branch: `feat/self-heal-cram-bam-conversion/aliz`
- Owner: aliz
- Worktree: `.claude/worktrees/feat-self-heal-cram-bam-conversion`
