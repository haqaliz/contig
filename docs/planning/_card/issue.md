# Card: annotation-plausibility (feat)

Type: feat · id/slug: `annotation-plausibility` · owner: aliz
Branch: `feat/annotation-plausibility/aliz`
Source: no GitHub issue — inline unit of work handed off by `/contig-next` (2026-07-10).

The initiative PRD already exists in-repo (committed to master), so this card links
to it rather than restating it.

- Initiative PRD: `docs/planning/variant-annotation-assay/prd.md`
- Capability: C7 (research-use variant annotation & prioritization), milestones **M2 + M3**.
- M1 (germline structural verify + provenance) shipped in v0.25.0 (see `CHANGELOG.md`).

## Brief (from /contig-next handoff)

Build C7 M2+M3: extend annotation verification past M1's germline-structural slice.

- **M2 — same verifier, somatic (small assay gate).** Gate M1's
  `verification/annotation_structural.py` structural verifier and the
  `AnnotationProvenance` capture to `somatic_variant_calling` (Mutect2/Strelka2 VCFs).
  New assay gate only — no new verification logic.
- **M3 — annotation plausibility (C3-style, both assays; the meat).** A new
  plausibility pack for both germline `variant_calling` and `somatic_variant_calling`:
  an annotated-fraction band plus a consequence-type-distribution sanity check parsed
  from the VCF's `CSQ` (VEP) / `ANN` (SnpEff) INFO field. WARN-capped; degrades to
  UNVERIFIED (never a false pass) when the annotation field is absent. Mirrors the
  shipped somatic-VAF plausibility slice (`verification/somatic_plausibility.py`,
  v0.14.0).

Research-use only — Contig verifies the annotation ran *plausibly*, never adjudicates
pathogenicity. Test-first with synthetic annotated-VCF fixtures covering **both** VEP
`CSQ` and SnpEff `ANN` field shapes. No real VEP/SnpEff/sarek run in CI.

## Known caveat to resolve in the dig

Carried from the C7 M1 card + `CHANGELOG.md` v0.25.0 live-cache caveat: enabling
`--tools …,vep` makes sarek emit an annotated VCF, but a live run may still require a
`--vep_cache`/`--download_cache` or `--step annotate` that Contig does not yet wire.
Both the M2 structural verifier and the M3 plausibility pack degrade to **UNVERIFIED
(never a false pass)** when annotation didn't run, so the slice is shippable on
synthetic fixtures regardless. The concrete thing to pin in the dig: the exact **`CSQ`
(VEP) vs `ANN` (SnpEff)** INFO field shapes M3 must parse for the consequence-type
distribution — they differ in delimiter and field order, and the fixtures must cover
both.
