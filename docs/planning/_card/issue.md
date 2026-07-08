# Card: self-heal-bgzip-reference (feat)

Type: feat · id/slug: `self-heal-bgzip-reference` · owner: aliz
Branch: `feat/self-heal-bgzip-reference/aliz`
Source: no GitHub issue — inline brief from `/contig-next` handoff (2026-07-08).
Capability: **C2 (self-heal breadth), input-format-conversion class — first slice.**

## Brief

Add a C2 self-heal slice that recovers a plain-`gzip`-compressed (non-BGZF)
reference FASTA — the `samtools faidx` "not BGZF" failure — by re-compressing it
with `bgzip` into run-scoped scratch, redirecting the retried run at the fixed
copy, and recording the recovery, as the first slice of C2's still-unbuilt
**input-format conversion** class.

Reuse the existing scratch + `params`-redirect + `rerun`/`resume` re-derivation
seam already shipped for STAR-index rebuild (v0.10.0) and GTF harmonization
(v0.9.0). Add a new `FailureClass`, one detector-corpus seed, and an
injected-builder fixture, test-first, no real pipeline run in CI.

## Known caveat (dig this FIRST, before PRD)

Confirm a Contig-launched nf-core run actually hits the non-BGZF failure on the
user-supplied `--fasta` **before** nf-core re-bgzips it in its own prep step.
This is the exact live-trigger question that turned the BWA (v0.10.0) and
bwa-mem2 (v0.11.0) slices detector-only. The bgzip case is more favorable — the
failure is on the *user-supplied* FASTA path, which several tools consume
directly — but if no launched run can produce it, this correctly narrows to a
**detector + corpus seed** slice (still real corpus fuel), not a full
build/redirect. Scope the trigger before committing to the redirect.

## Moat framing (from contig-next ranking)

- C2 is the headline-metric capability: unattended-completion rate
  (ROADMAP Phase 1 gate ≥70%), "the most directly 'gets better with better
  models' surface and the richest corpus fuel"
  (docs/technical/CAPABILITY_ROADMAP.md).
- Input-format conversion (bgzip / CRAM↔BAM) is explicitly named in C2's "What
  we build" (`CAPABILITY_ROADMAP.md:274`) and listed among still-pending items
  (`CAPABILITY_ROADMAP.md:256`) — not blocker-deferred.
- Double moat hit: raises unattended-completion (moat #1) + drops a golden
  corpus case (moat #2).

## Prior-art seams to reuse (verify in Phase 2 dig)

- STAR directory-index rebuild → run-scoped scratch + `params["star_index"]`
  redirect + `rerun`/`resume` re-derivation (v0.10.0).
- GTF harmonization → stream-rewrite into `<run_id>/harmonized/`, original file
  untouched, decision re-derived on rerun (v0.9.0).
- `IndexBuilder` injectable seam + one-build-per-path guard (v0.8.0).
- Detector-corpus seeding pattern (one golden case per new kind).

## Non-goals (this slice)

- CRAM↔BAM conversion (the *other* half of the input-format class — a later
  slice; this slice is bgzip-reference only).
- FAIL-severity / band calibration on real data.
- Any Layer-1 (NL → workflow) surface.
