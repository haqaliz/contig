# Card: rnaseq-concordance-autorun (feat)

Type: feat · id/slug: `rnaseq-concordance-autorun` · owner: aliz
Branch: `feat/rnaseq-concordance-autorun/aliz`
Source: no GitHub issue — inline brief from `/contig-next` handoff (2026-07-08), after the
`self-heal-corrupt-star-index` pick was found blocked in the Phase 2 dig and the user chose
this alternate.
Capability: **C1 (cross-tool concordance verification), RNA-seq slice — the turnkey autorun
follow-on.**

## Brief

Make RNA-seq cross-tool concordance **turnkey**: add a `contig verify <run>
--concordance-counts-auto …` path that runs a **second, independent quantifier** on the
run's own inputs — behind an **injectable seam** — to produce a second gene-count matrix,
then feeds it into the **already-shipped** `verification/count_concordance.py` machinery
(v0.12.0). This is the exact follow-on the docs name: it mirrors how the germline autorun
`--concordance-auto` (v0.4.0) followed the user-supplied germline `--concordance-vcf`
(v0.2.0) one release later — here it follows the user-supplied RNA-seq `--concordance-counts`
(v0.12.0).

### Contract (mirror germline `--concordance-auto` exactly)
- Second quantifier lives behind an **injectable seam**, so it is **never executed in CI**;
  a missing binary, missing input, or quantifier failure prints a **clear skip note**,
  **never a false pass**, and **never changes the verify exit code**.
- Corroboration only: **at most WARN**, structurally incapable of promoting UNVERIFIED→PASS.
- **Mutually exclusive** with `--concordance-counts` (user-supplied matrix) and with the
  germline `--concordance-vcf` / `--concordance-auto` flags.
- Reuses the existing Spearman / fraction-agreeing / gene-overlap checks and the
  UNVERIFIED-below-10-shared-genes guarantee — no new metric math.
- RNA-seq (`rnaseq`) assay only.

## Open questions for the Phase 2 dig (answer from code, not memory)

1. **Germline autorun shape** — read the v0.4.0 `--concordance-auto` implementation end to
   end: the injectable second-caller seam signature, CLI wiring, skip-note behavior,
   mutual-exclusion enforcement, and its tests. This is the template to copy.
2. **What second quantifier + what inputs?** Germline autorun took `--bam <bam> --ref <ref>`
   and ran bcftools. RNA-seq quantification needs **reads (FASTQ) + a transcriptome/index**.
   Determine what inputs are available at `verify` time (the run record / sample sheet /
   params), what a realistic second quantifier is (e.g. Salmon vs the primary, or kallisto),
   and therefore the seam's input signature. This is the main design decision.
3. **Primary matrix locator** — reuse v0.12.0's `*salmon.merged.gene_counts*` glob; confirm
   the path and how the primary matrix is found so the autorun corroborates against it.
4. **Mutual exclusion / flag surface** — where the existing `--concordance-counts` /
   `--concordance-vcf` / `--concordance-auto` flags are validated for exclusivity, so the
   new flag joins that guard.

## Why this pick (moat framing, from contig-next ranking)

- Deepens **moat #1**, the novel cross-tool verdict axis: "no incumbent issues a
  correctness verdict, let alone a cross-tool one" (`CAPABILITY_ROADMAP.md` C1).
- **Turnkey follow-on of a shipped manual feature** — an explicitly-blessed high-leverage
  candidate class (contig-next rule 6); precedented exactly by germline v0.4.0.
- **Unblocked, low feasibility risk**: the seam pattern is proven, the concordance math
  already ships, and the second tool is never run in CI (injected seam) — so no fabrication
  or CI-dependency risk.

## Honest caveats (carry into the PRD)

- Concordance is **WARN-only corroboration** and never changes the exit code — this makes
  a manual feature turnkey; it does not add a new verdict lever. Bounded marginal value,
  same as germline v0.4.0 (which shipped anyway).
- Like germline autorun, this proves the **wiring**, not a real second-tool run (the seam is
  injected in tests; the real quantifier is never executed in CI).
- **No corpus fuel**: concordance is not a `FailureClass`, so unlike a C2 self-heal slice
  this adds no golden detector-corpus case (moat #2). Deepens moat #1 only.

## Non-goals (this slice)

- Single-cell concordance; a dashboard "corroborated by" line; FAIL severity / band
  calibration on real data (all deferred per `CAPABILITY_ROADMAP.md` C1).
- Any Layer-1 (NL → workflow) surface.
