# self-heal-reference-mismatch (C2 reference/build-mismatch repair)

- **Type:** feat
- **Id/slug:** self-heal-reference-mismatch
- **Owner:** aliz
- **Branch:** feat/self-heal-reference-mismatch/aliz
- **Source:** inline brief (no GitHub issue; handed off from `contig-next`)
- **Capability:** C2 (self-heal breadth) — the reference/build-mismatch *repair* that
  the v0.7.0 contig-naming *detector* (C5 slice 2) and v0.6.0 reference-identity
  *capture* (C5 slice 1) were groundwork for.

## Brief (from the contig-next handoff)

Build the **C2 reference/build-mismatch repair** — the self-heal that the shipped
v0.7.0 contig-naming *detector* and v0.6.0 reference-identity *capture* were
groundwork for.

Today a disjoint-contig-naming mismatch (`chr1` in the FASTA vs `1` in the GTF) is
only *refused* at the pre-flight gate (`_dispatch_run`); this slice turns that
refusal into an autonomous recovery by **harmonizing seqnames** when the mismatch is
an unambiguous `chr`-prefix asymmetry, recording the harmonization in provenance,
then proceeding — and seeding a new `reference_mismatch` golden corpus case.

Critical scope guard: harmonization is the *only* honest repair for a naming
mismatch; a genuine wrong-assembly mismatch has no safe repair and must keep refusing
(never fabricate or guess a genome), and the sample-data-vs-reference
assembly-signature path stays deferred because the finished bundle carries no aligned
BAM.

Test-first against the detector's existing synthetic FASTA/GTF fixtures — no real
nf-core run in CI.

## Caveat to dig on FIRST (the key design risk)

The repair must be **honest and conservative**. Two questions drive the design:

1. **What is a *safe* harmonization?** Only an unambiguous `chr`-prefix asymmetry
   (one side has `chr1, chr2, …`, the other `1, 2, …`) where adding/stripping the
   `chr` prefix makes the two contig-name sets *match*. If after a candidate
   harmonization the sets still do not match (a genuine different-assembly mismatch),
   there is NO safe repair — keep refusing. Never fabricate or download a genome.

2. **Which side do we rewrite, and where does the rewritten file go?** Rewriting the
   GTF seqnames vs the FASTA headers; writing the harmonized copy to a worktree/run
   scratch path (never mutating the user's original reference in place); recording the
   harmonization in the launch manifest + provenance so `rerun`/`resume` reproduce the
   harmonized intent faithfully.

## Pre-dig facts (to confirm in Phase 2)

- The v0.7.0 detector lives in a `reference_check` module and gates at the single
  launch chokepoint `_dispatch_run`, with an `--allow-reference-mismatch` escape hatch
  recorded in the launch manifest (CHANGELOG.md:51-75). The repair plugs in HERE, not
  on a runtime-failure path.
- `missing_reference` is already a `FailureClass` (CAPABILITY_ROADMAP.md:258). Confirm
  whether `reference_mismatch` should be a new `FailureClass` or reuse an existing one,
  and that v0.7.0 did NOT seed a corpus class for it (CHANGELOG.md:74-75).
- The detector already distinguishes the disjoint-but-`chr`-asymmetric case (it names
  "the `chr`-prefix asymmetry" in its message) — that is the signal the repair keys on.

## Why this was picked (contig-next ranking)

- Both prerequisites shipped **specifically to enable it**: reference-identity capture
  (v0.6.0) and the pre-flight contig-naming detector (v0.7.0). Named as the next slice
  across three planning files (`reference-mismatch-detector/prd.md:136`,
  `self-heal-dict-index/prd.md:169`, `_card/understanding.md:84`; CHANGELOG.md:74-75).
- Converts a *detected* notorious silent-failure class into an *autonomously
  recovered* one — recover more failures without a human; raises the Phase-1
  unattended-completion metric. Seeds a new `reference_mismatch` corpus class
  (moat #2 compounding).
- Unblocked, unlike STAR/BWA directory indexes (shape-blocked), peak-RSS (refactor
  blocker), and assembly-signature/concordance auto-discovery (no aligned BAM in the
  bundle) — all agent-confirmed blocked.

## Open questions for the interview

- **Repair trigger model:** auto-harmonize-and-proceed by default, or
  propose-and-require-approval (this is a self-heal that mutates reference inputs —
  risk tier)? Interaction with the existing `--allow-reference-mismatch` escape hatch.
- **Safe-harmonization predicate:** exact rule for "unambiguous `chr`-prefix
  asymmetry"; what about `MT`/`chrM`, scaffold/`GL...` contigs, and partial-overlap
  (subset) references the detector already passes?
- **Which file is rewritten** (GTF vs FASTA), the streamed/gzip-transparent rewrite,
  and the scratch output location (never in-place).
- **Provenance/manifest:** how the harmonization is recorded so `rerun`/`resume`
  reproduce it; what `RepairStep`/outcome name (mirror `built_index_and_retried` →
  e.g. `harmonized_reference_and_proceeded`); honest give-up name when no safe
  harmonization exists.
- **Corpus seed:** one `reference-mismatch` case; new `FailureClass` vs reuse.

## Guardrails (CLAUDE.md)

- **Layer 2 only** (self-heal/execution/verification). In scope.
- **No raw-read egress** — harmonization rewrites a local reference annotation on the
  user's compute; nothing leaves the machine.
- **No correctness over-claiming** — harmonize ONLY an unambiguous naming asymmetry;
  a genuine wrong-assembly mismatch keeps refusing honestly. Record the harmonization,
  never claim correctness beyond "names harmonized."
- **Test-first**; synthetic `tmp_path` FASTA/GTF fixtures, no real nf-core run in CI.

## Out of scope (deferred — do not drift)

- **Sample-data-vs-reference assembly-signature** comparison/repair — blocked: raw
  FASTQ / the finished bundle carry no sample-side contig signal
  (`reference-mismatch-detector/prd.md:130-132`).
- Fabricating, guessing, or downloading a "matching" genome for a true wrong-assembly
  mismatch — there is no safe repair; refuse.
- Known-sites/BED-vs-reference consistency; GTF annotation-version resolution.
- STAR/BWA directory indexes; BAM/CRAM `.csi`; stale-index; peak-RSS scaling.
