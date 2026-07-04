# Card: feat/somatic-concordance

Source: inline brief from the `contig-next` handoff (no GitHub issue; slug-based work).
Type: feat · id/slug: somatic-concordance · owner: aliz · branch: feat/somatic-concordance/aliz

## Brief

Add a C1-style cross-tool concordance axis to the **somatic** verdict, corroborating
the run's Mutect2 VCF against the Strelka2 VCF that the *same* sarek
`--tools strelka,mutect2` run already emitted. Unlike germline concordance there is
**no second caller to run and no user-supplied input** — both call sets are already
first-class outputs of the same run bundle.

Reuse the `evaluate_concordance` primitive and the `kind="concordance"` reporting
path, gated to `assay == "somatic_variant_calling"`, capped at WARN, and `unverified`
(never a false pass) when a VCF is missing or the two share no comparable PASS sites.

### Key caveat to dig on first

Strelka2 somatic SNVs carry **no standard `GT`**, so the shipped germline
`genotype_concordance` metric won't transfer. The honest metric here is
**PASS-site overlap / shared-call fraction** (F1 of one caller's PASS calls against
the other), keyed on `(CHROM,POS,REF,ALT)`. The real work is in the somatic-specific
representation: FILTER/`PASS` conventions per caller, indel normalization, and how
Strelka2 splits SNV vs indel output (`somatic.snvs.vcf.gz` / `somatic.indels.vcf.gz`).

### Guardrails (from CLAUDE.md / CAPABILITY_ROADMAP)

- Corroboration only — at most WARN, never promotes UNVERIFIED to PASS.
- No raw-read egress: operates on VCFs on the user's compute.
- Test-first with synthetic two-caller somatic VCF fixtures; no real nf-core/sarek run in CI.
- Layer 2 only (verify axis), no Layer 1 workflow authoring.
- Research-use only; a somatic verdict is "ran correctly and reproducibly," never a cancer diagnosis.

## Provenance in the docs (where this work is named)

- `CAPABILITY_ROADMAP.md:311` — C4: "A concordance hook (C1) against a second somatic caller."
- `CAPABILITY_ROADMAP.md:288-293` — VAF-plausibility slice defers "the second-somatic-caller concordance hook (C1-style — Strelka2 vs Mutect2)."
- `CHANGELOG.md:44-45` (v0.14.0) — defers "the Strelka2-vs-Mutect2 somatic concordance hook (C1)."
- `CHANGELOG.md:76-80` (v0.13.0) — somatic launches sarek with `--tools strelka,mutect2` (both callers in one run).
- `FEATURES.md:253` — "the Strelka2-vs-Mutect2 concordance hook ... deferred."

## Shipped concordance precedent to mirror

- Germline `--concordance-vcf` (v0.2.0) and `--concordance-auto` (v0.4.0).
- RNA-seq `--concordance-counts` (v0.12.0).
- All via `verification/concordance.py` `evaluate_concordance`, `kind="concordance"`, WARN-capped, `unverified` below a comparability floor.

## Shipped somatic precedent to reuse

- `verification/somatic_plausibility.py` (v0.14.0) — how the somatic Mutect2 VCF is
  located (path component below run dir), how the tumor sample is identified
  (`##tumor_sample=` header), and how `_discover_qc` gates on `assay == "somatic_variant_calling"`.
