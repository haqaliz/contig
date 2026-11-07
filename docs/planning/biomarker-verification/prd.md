# PRD — Oncology biomarker verification (M7)

Feature slug: `biomarker-verification` · Type: feat · Owner: aliz
Branch: `feat/biomarker-verification/aliz` · Capability: **M7 (biomarker verification)**
Status: drafted 2026-11-07

## Problem Statement

A somatic pipeline can report TMB, MSI, LOH, and CNV, but a number is not a
verification. The user needs to know whether the reported biomarker is
reproducible from the call set and callable territory, and whether an
independent check supports it.

M7 adds a **research-use biomarker verification** surface. The v1 slice verifies
**TMB** from a somatic VCF plus a callable-region BED, and records MSI/LOH/CNV
as **not verified** until an independent caller/truth set is wired. It never
emits a treatment recommendation.

**Who has the problem:** the cancer-research ICP with a somatic call set who
needs a defensible biomarker summary before review.

**Why now:** the SEQC2 high-confidence somatic truth set and callable BED are
already downloaded; TMB is computable without a new dependency.

## Goals & Success Metrics

- **G1 — TMB computed from first principles.** Count PASS variants inside the
  callable BED, divide by callable Mb, and record the definition.
- **G2 — Reported-vs-computed check.** If a reported TMB is supplied, compare it
  within a documented relative tolerance and label match/divergent.
- **G3 — Honest gaps.** MSI, LOH, and CNV are recorded as `not_verified` in v1,
  with the reason; never a false pass.
- **G4 — Reproducible output.** TSV/JSON with source hashes, definition,
  thresholds, Contig version, and timestamp.
- **G5 — No treatment advice.** No NCCN, drug, or clinical recommendation.

## Requirements

### Must-have (v1)

- `contig biomarkers --vcf somatic.vcf --callable-bed regions.bed
  [--reported-tmb FLOAT] [--tmb-tolerance 0.20] [--reported-msi TEXT]
  [--reported-loh TEXT] [--reported-cnv TEXT] [--coding-only] [--out] [--json]`
- TMB: PASS variants inside the callable BED / callable Mb. `--coding-only`
  counts only variants with a coding consequence and reports the unannotated
  count.
- TMB status: `computed` when no reported value, `match`/`divergent` when one is
  supplied; `unverified` when the reported value is invalid.
- MSI/LOH/CNV: `not_verified` in v1, with the reason and any reported value.
- TSV/JSON with source SHA-256 and metadata.
- Tests: synthetic somatic VCF/BED; no network.

### Should-have (later slices)

- An independent MSI caller (MSIsensor/MSIpro) and a reference MSI-H/MSS sample.
- LOH/CNV from FACETS/CNVkit segments with a truth set.
- Cross-tool TMB concordance.
- A dashboard biomarker card.
- Calibrated bands per assay/purity.

### Nice-to-have / explicit non-goals

- NCCN/drug/treatment recommendations.
- Clinical tumor-board reporting.
- A trained response model.
- Claiming MSI/LOH/CNV verification before an independent check exists.

## Technical Considerations

- **No new dependencies.** Reuse M1 VCF/annotation parsing; BED interval checks
  are stdlib `bisect`.
- **TMB definition is explicit.** Default is all PASS variants in the callable
  BED; `--coding-only` uses the VEP/SnpEff consequence. The output always names
  the definition; it never silently switches.
- **Callable territory matters.** The BED is required; without it TMB is not
  computed.
- **Honest statuses.** A computed TMB is not a clinical threshold; MSI/LOH/CNV
  are not verified in v1.
- **Attribution.** No NCCN/OncoKB content; no drug recommendations.

## Risks & Open Questions

- **R1 — TMB definition drift.** Mitigation: record the definition and filters;
  require the callable BED.
- **R2 — No MSI/LOH/CNV truth set yet.** Mitigation: explicit `not_verified`,
  never a pass.
- **R3 — TMB tolerance uncalibrated.** Mitigation: default 20% relative, exposed
  as a flag; label match/divergent as a research comparison.
- **Open:** which MSI caller and reference sample to adopt first? (v1: defer.)

## Out of Scope

- Drug/treatment recommendations, clinical reporting.
- MSI/LOH/CNV verification, cross-tool TMB, dashboard (v1).
- Model training.

## Acceptance

- A synthetic VCF + 1 Mb callable BED with 5 PASS variants reports TMB 5.0
  mut/Mb.
- A reported TMB within tolerance is `match`; outside is `divergent`.
- `--coding-only` excludes unannotated variants and reports the count.
- MSI/LOH/CNV entries are `not_verified` with the reason.
- No output contains a drug or treatment recommendation.
