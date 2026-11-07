# PRD — Coverage and interpretation-readiness workbench (M2)

Feature slug: `readiness-workbench` · Type: feat · Owner: aliz
Branch: `feat/readiness-workbench/aliz` · Capability: **M2 (readiness workbench)**
Status: drafted 2026-11-07

## Problem Statement

A verified call set can still be unusable for a specific gene. The region may
have zero coverage, the mean depth may be too low to call a het, or the gene may
sit in a homology/pseudogene region where short reads cannot distinguish the
copies (SMN1/SMN2, PMS2/PMS2CL, HBA1/HBA2). Today the user finds this out after
interpreting a variant, or not at all.

M2 adds a **coverage and interpretation-readiness workbench**: per-gene/per-exon
depth metrics, explicit homology/pseudogene caveats, and a deterministic
`ready` / `caution` / `not-interpretable` state with the reason. It is a
data-sufficiency check, not a clinical guarantee and not a CNV caller.

**Who has the problem:** the disease-research ICP with a panel/WES call set who
needs to know which genes are safe to interpret before spending time on them.

**Why now:** the M1 workbench can filter variants but does not say whether the
data beneath a gene supports a call. The depth, target, and homology data are
already available (`DATA_SOURCES.md`).

## Goals & Success Metrics

- **G1 — Per-target metrics.** Mean depth, % ≥20x/50x/100x, covered bases, and
  zero-coverage bases for every target (BED interval or GTF exon).
- **G2 — Deterministic readiness.** `ready` / `caution` / `not-interpretable`
  from documented thresholds and caveats; the reason is always shown.
- **G3 — Caveats are explicit.** A target overlapping a homology/pseudogene
  region is `caution` even when depth is high, with the region named.
- **G4 — Reproducible.** Output records the depth/target/caveat source paths,
  SHA-256, thresholds, Contig version, and a UTC timestamp.
- **Success metric:** a user can go from `samtools depth` + a panel BED to a
  per-target readiness table in one command, and the same inputs produce the
  same states.

## Requirements

### Must-have (v1)

- **Depth input:** a TSV from `samtools depth -a`, columns `chrom pos depth`
  (1-based). Missing positions are treated as zero, never as "unknown".
- **Targets:** a BED3/BED4 (`chrom start end [name]`) or a GTF plus a gene list;
  GTF exons are grouped per gene/transcript/exon and prefer MANE Select when the
  annotation tags it.
- **Metrics:** bases, covered bases, mean depth, % ≥20x, % ≥50x, % ≥100x,
  zero-coverage bases.
- **Caveats:** an optional BED of homology/pseudogene regions. A target that
  overlaps one is `caution` and carries the caveat name/reason. A BED4 or the
  8-column homology BED are both accepted.
- **Readiness:** documented thresholds with CLI overrides:
  - `not-interpretable` when there are no target bases, or the % at the depth
    threshold is below the caution floor;
  - `caution` when a caveat is present, the % at threshold is below the ready
    floor, or the mean depth is below the depth threshold;
  - `ready` otherwise.
- **Output:** TSV by default; `--json` for the table plus provenance; `--out`
  writes to a file.
- **CLI:** `contig readiness ...` with `--help`.
- **Tests:** synthetic depth/BED/GTF fixtures; no BAM/CRAM, no `samtools` in CI.

### Should-have (later slices)

- `--bam`/`--cram` that runs `samtools depth -a -b` behind an injectable seam.
- Sex check / sample-swap caveats (reuse `verification/sex_plausibility.py`).
- MultiQC/coverage-artifact ingestion (no depth TSV needed).
- Liftover for GRCh37 targets.
- Dashboard readiness column/table.
- A "why is this gene not ready?" one-line explanation in the M1 table.

### Nice-to-have / explicit non-goals

- Clinical coverage guarantees or diagnostic-grade claims.
- CNV calling, LOH, or structural-variant interpretation.
- A diagnosis or treatment recommendation.
- A trained model.

## Technical Considerations

- **No new dependencies.** Depth/BED/GTF parsing is stdlib. `samtools` is only a
  future optional external tool.
- **Panel-scale input.** The depth TSV should be restricted to the target BED
  (`samtools depth -a -b panel.bed`). A whole-genome depth file is too large for
  the v1 in-memory table.
- **BED semantics.** BED is 0-based half-open; depth positions are 1-based.
  Convert explicitly: BED `[start, end)` -> positions `start+1 .. end`.
- **Honest gaps.** A missing depth position is zero coverage. A target with no
  bases is `not-interpretable`, not a pass. A caveat is a caution, never a silent
  pass.
- **Attribution.** The readiness state is a data-sufficiency statement, not a
  clinical claim. The CLI prints a research-use notice.

## Risks & Open Questions

- **R1 — threshold arbitrariness.** The defaults (20x, 90% ready, 50% caution)
  are engineering defaults, not calibrated. Mitigation: expose every threshold;
  document them as defaults; revisit with real panel data.
- **R2 — homology list completeness.** The shipped caveat list covers SMN1/SMN2,
  PMS2/PMS2CL, and HBA1/HBA2. It is not exhaustive. Mitigation: accept any
  caveat BED; name the source and version.
- **R3 — depth TSV size.** Whole-genome depth is huge. Mitigation: require the
  target BED and document the `samtools depth -b` invocation.
- **Open:** should readiness gate the M1 filters, or be advisory? (v1: advisory,
  with the state in the table; a gate is a follow-up.)

## Out of Scope

- Clinical diagnosis, ACMG classification, treatment advice.
- CNV/SV calling, sex check (v1), BAM/CRAM ingestion (v1), dashboard (v1).
- Model training.

## Data

- `samtools depth -a -b target.bed sample.bam > depth.tsv`
- A panel BED or GENCODE GTF + gene list.
- `data/homology/homology_caveats_GRCh38.bed` (curated) or any caveat BED.
- Manual check data: `data/nfcore/NA12878_*.cram` + `target_chr20.bed`.

## Acceptance

- `contig readiness --depth depth.tsv --bed panel.bed --homology-bed caveats.bed
  --out readiness.tsv` produces one row per target with the metrics above and a
  state/reason.
- A target with zero coverage is `not-interpretable`.
- A high-depth target overlapping a homology region is `caution` with the caveat
  named.
- A target with ≥90% at 20x, mean ≥20x, and no caveat is `ready`.
- The same inputs produce identical output; the metadata records source
  checksums and thresholds.
