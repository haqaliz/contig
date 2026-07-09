# PRD — Research-use variant annotation assay (run + verify)

Feature slug: `variant-annotation-assay` · Type: feat · Owner: aliz
Branch: `feat/variant-annotation-assay/aliz` · Capability: **C7 (research-use variant
annotation & prioritization) — NEW**
Status: drafted 2026-07-10 (brainstorming → PRD)

## Problem Statement

Contig runs and verifies variant *calling* (germline `variant_calling` via nf-core/sarek,
somatic `somatic_variant_calling`), but it stops at the raw call set. The question every
disease-research user actually asks next — "what do these variants *mean*?" — is answered by
an **annotation** step (VEP / SnpEff against ClinVar, gnomAD) that Contig does not run or
verify today. A grep of `src/` confirms zero annotation/ClinVar/pathogenicity code exists.

This is the closest capability to "disease work" that stays strictly on the Layer-2 side of
the wedge. Contig **runs the annotation pipeline and proves it executed correctly and
reproducibly**, and **surfaces what the annotation databases reported, attributed to the tool
and its DB version, as research output.** Contig does **not** adjudicate pathogenicity, issue
a clinical verdict, or make a diagnosis — that stays with the researcher and the regulated
lab. This is the bright line drawn in `docs/technical/USE_CASE_UNIVERSE.md` (lines 33–48,
75–78) and mandated by `CLAUDE.md` constraint #4.

**Who has the problem:** the Contig disease-research ICP — a lone computational biologist or a
wet-lab scientist who can't code — who has a verified call set and needs the annotation step
run and *verified as having run correctly*, not just executed and trusted blindly.

**Why now:** founder demand-pull (this initiative was explicitly requested). Annotation reuses
the shipped germline/somatic assays (C4), the reference-identity provenance pattern (C5), and
the three verification axes already proven for other assays (structural like C4, plausibility
like C3, concordance like C1). It is a new assay that compounds the failure/verification
corpus (moat #2) without new machinery.

## Goals & Success Metrics

- **G1 — Run + structurally verify annotation, research-use only.** A Contig-launched
  germline run can enable sarek's annotation step and Contig verifies the annotated VCF
  exists and every input variant carries an annotation record — with an honest UNVERIFIED
  (never PASS, never a clinical claim) when annotation output is absent or malformed.
- **G2 — Attributed, reproducible provenance.** The annotation tool + its cache/DB name and
  version are captured into provenance and rendered in `contig methods` and the HTML panel,
  and reproduce on re-run.
- **G3 — No over-claiming.** Every annotation surface says "what tool X reported at DB
  version Y," attributed; no verdict about biological or clinical significance is ever
  emitted by Contig.
- **Success metric:** M1 (germline structural verify) lands test-first with synthetic
  annotated-VCF fixtures, no real VEP/SnpEff run in CI, and an annotation-coverage metric
  captured into the eval corpus.

## User Personas & Scenarios

- **Rare-disease researcher (germline):** has a verified germline call set, wants ClinVar/
  gnomAD annotations attached and *proof the annotation step ran correctly* for their Methods
  section — not a pathogenicity call.
- **Cancer researcher (somatic, M2):** same, for tumor variants from the somatic assay.

## Requirements

### Must-have (M1 — germline structural verify, slice 1)

- Enable sarek's built-in annotation step on the `variant_calling` assay via
  `PipelineEntry.default_params` / `--tools …,vep` (or snpeff); persist the annotation config
  on the `RunRecord` / `launch.json` so it reproduces.
- A structural verifier (new `verification/annotation_structural.py`, gated to the annotated
  germline assay in `_discover_qc`) that checks: annotated VCF present; every input variant
  carries an annotation record; the annotation INFO field (`CSQ` for VEP / `ANN` for SnpEff)
  is present. Degrades to **UNVERIFIED (never PASS)** when the annotated VCF is absent or
  carries no annotation INFO.
- Provenance capture of the annotation tool + cache/DB name and version, reusing the C5
  `ReferenceIdentity` pattern; rendered in `contig methods` and the HTML provenance panel;
  re-derived on `rerun`/`resume` from the manifest (no scratch path persisted).
- All annotation output surfaced strictly as *"what tool X reported at DB version Y,"*
  attributed; no Contig-authored significance claim anywhere.
- Test-first: synthetic annotated-VCF fixtures (tiny VEP-`CSQ` and SnpEff-`ANN` samples);
  **no real VEP/SnpEff/sarek run in CI**. One seed corpus case for an annotation-missing
  failure.

### Should-have (later milestones, same initiative)

- **M2 — somatic:** gate the M1 structural verifier + provenance to `somatic_variant_calling`
  (Mutect2/Strelka2 VCFs). Reuses M1 logic; new assay gate only.
- **M3 — annotation plausibility (C3-style, both assays):** annotated-fraction band (share of
  variants receiving any consequence) + consequence-type distribution sanity (e.g. refuse a
  ~100%-intergenic distribution). WARN-capped, uncalibrated defaults, UNVERIFIED-when-absent.
- **M4 — annotation concordance (C1-style, both assays):** VEP vs SnpEff on the same VCF —
  per-variant consequence / gene-symbol agreement as corroboration. At most WARN, `unverified`
  below a shared-record threshold. Extends the cross-tool concordance primitive to annotation.
- **M5 — surface + eval fold-in:** "corroborated by" line on the verdict card, DB-version
  provenance in the reproduce bundle, and annotation outcomes folded into the C6 eval corpus.

### Nice-to-have / explicit follow-ons (NOT this initiative)

- Research *prioritization* (ACMG-style criteria surfacing, rare-disease inheritance
  filtering, PGx, PRS) — deliberately deferred; this initiative is verify-only per the
  brainstorming decision.
- FAIL severity on any annotation band until calibrated on real data.
- Non-sarek / standalone annotation pipeline.

## Technical Considerations

- **Reuse over new machinery.** sarek already ships VEP/SnpEff annotation (`--tools`), so M1
  wires a param + a verifier + provenance capture — not a new pipeline. The verifier mirrors
  `verification/somatic_plausibility.py` (assay-gated `_discover_qc` discovery, WARN-capped,
  UNVERIFIED-when-absent). Provenance mirrors `ReferenceIdentity` (C5).
- **Verification axes are the shipped three:** structural (M1/M2), plausibility (M3, C3-style),
  concordance (M4, C1-style). No new verification primitive is invented.
- **No models, no proprietary data.** VEP/SnpEff + ClinVar/gnomAD are consumed as-is; they
  improve on their own and a better base model makes the orchestrator better, never redundant
  (`CLAUDE.md` #2/#3). No training, no HuggingFace, no separate repo.

## Risks & Open Questions

- **R1 — interpretation creep (the main risk).** The temptation is to surface pathogenicity as
  Contig's own judgement. Mitigation: M1 verifies only that annotation *ran correctly*; all
  output is attributed to tool + DB version; no significance verdict is emitted. This is the
  bright line and is non-negotiable.
- **R2 — VEP cache size / availability in CI.** Mitigation: no real VEP run in CI; the
  subprocess path is manual-gate only; CI uses injected synthetic annotated-VCF fixtures.
- **R3 — uncalibrated plausibility bands (M3).** Mitigation: WARN-capped, UNVERIFIED-when-
  absent, FAIL deferred until real-data calibration — consistent with every other C3 slice.
- **Open:** exact VEP-vs-SnpEff default (start with VEP `CSQ`; SnpEff `ANN` supported by the
  same parser shape); which annotation databases to pin first (ClinVar + gnomAD via the sarek
  VEP cache) — resolved in the M1 implementation plan.

## Out of Scope

- Any clinical/diagnostic verdict, pathogenicity adjudication, screening, prognosis, or
  treatment claim (the `USE_CASE_UNIVERSE.md` bright line).
- Research prioritization layer (verify-only this initiative).
- Trained detection/classifier models; HuggingFace publication; a separate repository.
- Non-sarek annotation pipelines; FAIL-severity annotation bands (uncalibrated).
