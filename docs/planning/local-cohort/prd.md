# PRD — Local cohort frequency layer (M8 v1)

Feature slug: `local-cohort` · Type: feat · Owner: aliz
Branch: `feat/local-cohort/aliz` · Capability: **M8 (local cohort)**
Status: drafted 2026-11-08

## Problem Statement

A lab runs the same variant workbench across many samples. The useful question
is often "have we seen this variant before, and how often?" But a central
frequency database means sending data off-site, and the federated version needs
consent, legal review, and multiple labs.

M8 v1 is the **local, privacy-preserving half**: index the M1 variant tables
already on this machine, aggregate per-variant and per-gene counts, and query
them locally. No network, no sample identifiers, no data leaves the machine. The
federated layer remains a later, opt-in design.

## Goals & Success Metrics

- **G1 — Local cohort index.** Build a cohort JSON from multiple M1 variants
  JSON files, recording per-variant seen-run counts/frequencies and per-gene
  summaries.
- **G2 — Query.** Query by gene, variant, or minimum run count; output TSV/JSON.
- **G3 — Privacy by construction.** Local-only, no network, no sample IDs; run
  labels can be anonymized.
- **G4 — Provenance.** Source paths/SHA-256, total runs, Contig version,
  timestamp.
- **G5 — Federated is deferred.** No cross-lab sharing, no central service, no
  model training.

## Requirements

### Must-have (v1)

- `contig cohort-build --name NAME --variants a.json,b.json [--anonymize]
  [--out cohort.json]`
- Each input is an M1 `contig variants --json` table. For each variant, record
  `seen_runs`, `frequency`, genes, consequences, and ClinVar significance
  strings. For each gene, record the unique variant count and runs with the gene.
- `contig cohort-query --cohort cohort.json [--gene GENE] [--variant
  CHROM-POS-REF-ALT] [--min-runs N] [--json] [--out PATH]`
- `--anonymize` stores only hashed run labels and omits paths; default stores
  local paths for provenance.
- TSV/JSON with metadata; deterministic output for the same inputs.
- Tests: synthetic M1 JSON fixtures; no network.

### Should-have (later slices)

- Opt-in federated aggregation with k-anonymity/differential privacy.
- A cohort dashboard.
- Per-gene carrier/ClinVar summaries.
- Cohort versioning and deletion/consent records.

### Nice-to-have / explicit non-goals

- A public population database (gnomAD exists).
- Cross-lab sharing without consent/legal review.
- Selling or exposing individual-level data.
- Model training.

## Technical Considerations

- **Local-only.** The command never opens a socket. The cohort file is a local
  JSON artifact.
- **No sample IDs.** M1 tables do not carry sample IDs; the cohort uses file
  labels (or hashes) only.
- **Determinism.** Sort by genomic position and gene name; timestamps live in
  metadata only.
- **Reuse.** M1 JSON is loaded with the existing report input validator; no new
  variant parsing.

## Risks & Open Questions

- **R1 — re-identification via rare variants.** Even local cohort files can be
  sensitive. Mitigation: `--anonymize`, local-only, and a documented warning.
- **R2 — federated scope creep.** Mitigation: v1 is explicitly local; federation
  needs consent/legal design.
- **R3 — input schema drift.** Mitigation: validate `meta` + `variants`; fail
  clearly.
- **Open:** should the cohort store run labels at all? (v1: yes, unless
  `--anonymize`.)

## Out of Scope

- Federated/cross-lab aggregation, central service, consent management.
- Public frequency database, clinical claims.
- Model training.

## Acceptance

- Two/three M1 tables with overlapping variants produce the expected
  `seen_runs` and frequencies.
- Gene and variant queries return the right rows; `--min-runs` filters.
- `--anonymize` omits paths and hashes labels.
- No network call is made.
