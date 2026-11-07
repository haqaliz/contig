# PRD — Family/trio analysis (M6)

Feature slug: `family-trio` · Type: feat · Owner: aliz
Branch: `feat/family-trio/aliz` · Capability: **M6 (family analysis)**
Status: drafted 2026-11-07

## Problem Statement

A trio or family VCF contains the inheritance evidence a researcher needs — but
only if someone computes it. Contig can call variants and filter them, but it
does not say which variants are inherited from which parent, which are de novo
candidates, or whether the family genotypes are Mendelian-consistent.

M6 adds a **research-use family analysis**: read a multi-sample VCF plus a PED,
compute per-variant inheritance and Mendelian consistency, list de novo
candidates, and report simple pairwise sample concordance. No clinical
counselling, no diagnosis, no ACMG classification.

**Who has the problem:** the rare-disease research ICP with a child–parent trio
who needs a defensible inheritance summary before review.

**Why now:** the GIAB trio truth data, HPO, and the deterministic M1/M2 pattern
are already in place; this is the natural next research-use surface.

## Goals & Success Metrics

- **G1 — Inheritance per variant.** For each child, classify the variant as
  paternal, maternal, biparental, de novo candidate, not carried, or
  inconsistent.
- **G2 — Mendelian QC.** Report evaluated sites, inconsistent sites, de novo
  candidates, and a Mendelian error rate (excluding de novo candidates).
- **G3 — Sample concordance.** Report pairwise same-genotype and opposite-
  homozygote rates for the family; flag a possible sample swap when the
  parent–child opposite-homozygote rate exceeds a documented default.
- **G4 — Reproducible output.** TSV/JSON with source hashes, family metadata,
  totals, and Contig version.
- **G5 — Research-use boundary.** No diagnosis, counselling, PGT-M, or clinical
  classification.

## Requirements

### Must-have (v1)

- `contig family --vcf family.vcf --ped family.ped [--out family.tsv] [--json]`
- PED parser: family_id, sample_id, father_id, mother_id, sex, phenotype; one
  family per run; validate that every PED sample exists in the VCF.
- Multi-sample VCF reader: per-sample `GT`, one row per ALT.
- Autosomal inheritance classification and Mendelian consistency; X/Y/MT are
  marked `not_evaluated` in v1 (no sex-aware model yet).
- De novo candidates: child carries ALT, both parents are `0/0`.
- Summary: sites evaluated, inconsistent (excluding de novo), de novo count,
  Mendelian error rate, inheritance counts.
- Pairwise sample concordance: same-genotype fraction, opposite-homozygote rate,
  possible-swap flag (default IBS0 > 0.01 for parent–child).
- TSV/JSON output with source SHA-256 and metadata.
- Tests: synthetic trio VCF/PED; no network.

### Should-have (later slices)

- X-linked/sex-aware Mendelian rules.
- Multiple families/quads per PED.
- Carrier/couple views and recessive-gene panels.
- Sample identity/sex checks from the VCF.
- Readiness caveats per gene (reuse M2).
- A dashboard family view.

### Nice-to-have / explicit non-goals

- Clinical genetic counselling, prenatal diagnosis, PGT-M.
- ACMG classification as Contig's own call.
- De novo validation (Sanger) or phasing.
- Model training.

## Technical Considerations

- **No new dependencies.** Stdlib VCF/PED parsing; reuse the M1 annotation
  helpers and `VariantKey`.
- **Multi-sample VCF.** The input is a single VCF with child/father/mother
  columns; separate per-sample VCFs must be merged first (documented).
- **Mendelian rules.** Autosomal only in v1: every child allele must appear in at
  least one parent. A child ALT with both parents `0/0` is a de novo candidate,
  not a Mendelian error.
- **Thresholds.** The IBS0 swap flag is an engineering default, not calibrated;
  it is reported with the metric, never as a diagnosis.
- **Attribution.** Inheritance is a research calculation from genotypes; it is
  not a clinical interpretation.

## Risks & Open Questions

- **R1 — genotype quality.** A low-quality de novo candidate can be a false
  positive. Mitigation: label it a candidate; no validation claim.
- **R2 — X/Y inheritance.** Sex-aware rules are deferred; mark them
  `not_evaluated` rather than guessing.
- **R3 — sample swap flag.** The IBS0 threshold is uncalibrated. Mitigation:
  report the metric and a "possible" flag; do not assert a swap.
- **Open:** should carrier/couple views be part of v1? (v1: inheritance +
  concordance only.)

## Out of Scope

- Clinical counselling, diagnosis, treatment advice.
- X-linked rules, multiple families, carrier panels, dashboard (v1).
- Model training.

## Acceptance

- A trio VCF + PED produces one row per child/ALT with inheritance, consistency,
  and de novo flags.
- A child ALT with both parents `0/0` is a de novo candidate; a child `1/1` with
  one parent `0/0` is inconsistent.
- The summary reports the Mendelian error rate excluding de novo candidates.
- Pairwise concordance metrics and a possible-swap flag are present.
- Same inputs produce identical rows; metadata records source hashes.
