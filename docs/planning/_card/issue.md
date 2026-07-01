# self-heal-dir-index (C2 self-heal breadth — directory-shaped STAR/BWA index build)

- **Type:** feat
- **Id/slug:** self-heal-dir-index
- **Owner:** aliz
- **Branch:** feat/self-heal-dir-index/aliz
- **Source:** inline brief (no GitHub issue; handed off from `contig-next`)
- **Capability:** C2 (self-heal breadth) — the next missing-index kind on the shipped
  `IndexBuilder` seam, after the single-file family (`.fai/.bai/.tbi/.csi/.dict`).

## Brief (from the contig-next handoff)

Extend the C2 self-heal `IndexBuilder` seam to recover a missing or incomplete
**directory-shaped** index — STAR (via `STAR --runMode genomeGenerate`) and BWA
(via `bwa index`) — the next slice after the single-file index family
(`.fai/.bai/.tbi/.csi/.dict`) shipped through v0.8.0.

The detector must recognize a missing/incomplete STAR/BWA *index directory*
distinctly from the single-file missing-index signatures and from a
wrong-reference masquerade. The build deriver must resolve the FASTA (and GTF,
for STAR) and emit a directory rather than a suffix-stripped file — so the build
table `{ext: (derive_source, build_argv)}` and the build-once-per-path guard need
a directory-shaped analog.

Stay test-first with an injected `IndexBuilder`/executor (no real STAR/BWA/nf-core
run in CI), record `built_index_and_retried` on success and give up honestly
(`index_unresolvable` / `index_build_failed`) — never a false pass — and seed one
golden corpus case per kind.

## ⚠️ Caveat to dig on FIRST (the key feasibility/design risk)

**The prior `_card` (self-heal-reference-mismatch) explicitly listed "STAR/BWA
directory indexes" as `shape-blocked` and "agent-confirmed blocked" (old
issue.md:71/109).** Our pick treats it as *unblocked-but-harder*. **Phase 2 must
resolve this contradiction before any PRD work:**

1. **Is it a real blocker or just unimplemented shape complexity?** "Shape-blocked"
   most plausibly meant: the seam's build table is keyed on a file *extension* and a
   *suffix-strip* deriver that emits a single file — a directory-shaped index has no
   extension and no suffix to strip. That is a generalization task, not a hard
   blocker. Confirm by reading the seam (`runner.py` `IndexBuilder`, the build table,
   the build-once-per-path guard) and the detector's missing-index parser.
2. **Does the failure actually surface recoverably?** nf-core/rnaseq builds the STAR
   index itself when none is given; the recoverable "missing index" case is when a
   user passes `--star_index <path>` (or BWA index prefix) that is absent or
   incomplete. Confirm the real failure signature STAR/BWA emit, and that it is
   distinguishable from the single-file signatures and from a wrong-reference
   masquerade.
3. **Build-target shape.** `STAR --runMode genomeGenerate --genomeDir <dir>
   --genomeFastaFiles <fa> --sjdbGTFfile <gtf>` needs FASTA **plus** GTF and emits a
   *directory*; `bwa index <fa>` emits sidecar files next to the FASTA. These are two
   different shapes — confirm both before committing to one build-table generalization.

If the dig confirms a genuine blocker (not just shape complexity), STOP and
re-recommend via `contig-next` rather than forcing the slice.

## Pre-dig facts (confirm in Phase 2)

- The single-file index family is shipped through v0.8.0: `.fai` (`samtools faidx`),
  `.bai` (`samtools index`), `.tbi` (`tabix -p vcf`), `.csi` (`bcftools index`),
  `.dict` (`samtools dict`, companion-FASTA deriver) — `CHANGELOG.md:46-78`,
  `CAPABILITY_ROADMAP.md:98-119`.
- The build table was generalized to `{ext: (derive_source, build_argv)}` for `.dict`
  (the first non-suffix-strip deriver) — `CHANGELOG.md:52-61`. Directory-shaped is the
  next generalization on the same table.
- Outcomes: `built_index_and_retried` on success; `index_unresolvable` /
  `index_build_failed` on honest give-up; build-once-per-path guard bounds the loop
  (`CHANGELOG.md:62-78`).
- Named as still-missing on "the same seam": `CAPABILITY_ROADMAP.md:138-139`.

## Why this was picked (contig-next ranking)

- Named, unblocked (pending dig) next slice on a shipped seam; single-file family done
  through v0.8.0.
- Highest moat-leverage on both axes: C2 is "the most directly gets-better-with-better-
  models surface and the richest corpus fuel" (`CAPABILITY_ROADMAP.md:143-144`).
  A recovered STAR-index failure raises unattended-completion (Phase 1 gate metric,
  `ROADMAP.md:101,108`) **and** seeds a golden detector-corpus case (moat #2).
- Targets the lead ICP: STAR is the RNA-seq aligner; RNA-seq DE is the chosen wedge
  assay with the largest non-programmer TAM (`ROADMAP.md:49`).

## Open questions for the interview

- **Scope:** STAR + BWA both this slice, or STAR first (highest RNA-seq value) and BWA
  follow-on? (Two different build-target shapes — dir vs sidecars-next-to-FASTA.)
- **Incomplete vs missing:** does the slice handle a *partially built* index directory
  (some files present), or only a fully-absent one? Detection differs.
- **GTF resolution for STAR:** STAR's `genomeGenerate` wants `--sjdbGTFfile`; how is the
  GTF resolved at repair time (the chr-prefix harmonization in v0.9.0 already touches
  GTF resolution — reuse that path?).
- **Build-once-per-path guard** for a directory target (the guard is keyed on a path
  today — confirm it keys cleanly on a directory).
- **Corpus seed:** one golden case per kind (STAR, BWA); reuse the existing
  missing-index `FailureClass` (the detector already classifies missing-index) or a
  new one?

## Guardrails (CLAUDE.md)

- **Layer 2 only** (self-heal/execution). In scope.
- **No raw-read egress** — the index is built from a local FASTA/GTF on the user's
  compute; nothing leaves the machine.
- **No correctness over-claiming** — build only when the source FASTA (and GTF) is
  resolvable; give up honestly otherwise. Never a false pass.
- **Test-first**; injected `IndexBuilder`/executor fixtures, no real
  STAR/BWA/nf-core run in CI.

## Out of scope (deferred — do not drift)

- BAM/CRAM form of `.csi`; stale-index detection (could be a follow-on, not this slice).
- Peak-RSS-informed resource scaling (separate C2 slice, refactor-blocked).
- Assembly-signature reference mismatch (blocked: no sample-side contig signal).
- Building Layer 1 (NL → workflow) — not the product.
