# PRD — Annotation verification: somatic gate + plausibility (C7 M2 + M3)

- **Capability:** C7 (research-use variant annotation & prioritization).
- **Milestones:** M2 (somatic gate + enablement) + M3 (annotation plausibility, both assays).
- **Initiative PRD (parent):** `docs/planning/variant-annotation-assay/prd.md`.
- **Predecessor:** C7 M1 (germline structural verify + `AnnotationProvenance`) shipped v0.25.0.
- **Branch:** `feat/annotation-plausibility/aliz`. **Owner:** aliz.
- **Dig:** `docs/planning/annotation-plausibility/understanding.md`.

## Problem Statement

Contig's M1 slice proves an annotation step *ran structurally* (a `CSQ`/`ANN` field is
present, and what fraction of records carry it) for the **germline** assay only, and
issues a methods-line provenance for the annotation tool + version. Two gaps remain in
the shipped annotation verdict:

1. **Somatic runs get no annotation verdict at all.** The M1 structural verifier and the
   `AnnotationProvenance` capture are gated to `assay == "variant_calling"`
   (`runner.py:144-153`); a somatic (tumor–normal) run's annotated VCF is never checked.
   Worse, the somatic assay's registry entry does not even enable annotation
   (`default_params={"tools":"strelka,mutect2"}`, no `vep`), so there is nothing to verify.
2. **The verdict says nothing about whether the annotation is biologically plausible.**
   M1 confirms the field is *present*, not that the result *looks like a real annotation
   run*. An annotation that resolved ~100% of variants to `intergenic` (a wrong-reference
   or wrong-cache smell) passes M1's structural check but is implausible.

Both gaps are Layer-2 verification work: they make the verdict *harder to fool* and add a
new assay×axis to the failure/verification corpus (moat #2), while consuming VEP/SnpEff
as-is. Neither touches Layer-1 workflow authoring, needs proprietary data, or crosses the
clinical bright line.

**Who has the problem:** the C7 ICP — a researcher running germline or somatic variant
calling with functional annotation who needs to trust the annotation *executed correctly
and reproducibly*, without Contig ever adjudicating pathogenicity.

## Goals & Success Metrics

- **G1 — Somatic annotation is verified (M2).** A somatic run that produced an annotated
  VCF yields `annotation_present` / `annotation_complete` structural checks and an
  `AnnotationProvenance` methods line, identical in contract to germline M1.
- **G2 — Somatic annotation is producible (M2).** The somatic registry entry enables
  sarek's annotation (`vep`) so an annotated somatic VCF can actually be emitted, mirroring
  M1's germline enablement — not left dead-on-arrival.
- **G3 — The verdict gains a biological-plausibility axis for annotation (M3), both
  assays.** Two WARN-capped `kind="metric"` checks fire for germline and somatic:
  `annotation_real_fraction` and `annotation_consequence_distribution`.
- **G4 — Never a false pass.** Every uncomputable/absent path is UNVERIFIED, never PASS;
  no check can reach FAIL (WARN-capped).

**Measured by** (test-first, deterministic, no real VEP/SnpEff/sarek in CI):

- Synthetic annotated-VCF fixtures covering **both** VEP `CSQ` and SnpEff `ANN` shapes.
- An in-band annotation → PASS/WARN with the metric reported; an implausible one (e.g.
  ~100% intergenic) → WARN with the named reason; an un-annotated / field-absent VCF →
  UNVERIFIED with `value=None`, `kind="metric"`.
- `_discover_qc` integration cases driving **both** `variant_calling` and
  `somatic_variant_calling`.
- Full `uv run pytest` green; `contig eval-guard` / `heal-guard` unaffected (no detector or
  `FailureClass` change).

## User Personas & Scenarios

- **Computational biologist, somatic panel.** Runs a tumor–normal sarek job with VEP
  annotation. Contig now reports the annotation ran and looks plausible (or flags it), and
  the methods paragraph attributes the annotation to VEP + its version — research output,
  never a clinical call.
- **Wet-lab scientist, germline.** Already gets M1 structural checks; now also gets a
  plausibility signal that catches a grossly-wrong annotation (all-intergenic) that
  structural coverage alone would pass.

## Requirements

### Must-have

- **R1 (M2) — Enable somatic annotation.** Add `vep` to the `somatic_variant_calling`
  registry `default_params` tools string (→ `strelka,mutect2,vep`), injected
  non-destructively (a user's own `--tools` wins), re-applied on rerun/resume — exactly as
  M1 did for germline. *Decision: "Enable + gate (mirror M1)."*
- **R2 (M2) — Gate the M1 structural verifier to somatic.** Widen the annotation gate in
  `_discover_qc` (`runner.py:144-153`) to `assay in ("variant_calling",
  "somatic_variant_calling")`. Reuse the M1 logic verbatim — locate the first VCF whose
  header declares `CSQ`/`ANN` and evaluate `evaluate_annotation_structural`. No new
  verification code.
- **R3 (M2) — Gate provenance capture to both variant assays.** The `AnnotationProvenance`
  capture at `_finalize` (`self_heal.py:1266`) currently fires unconditionally; scope it to
  `assay in ("variant_calling", "somatic_variant_calling")` so it does not attach a
  spurious annotation clause to an unrelated assay whose output happens to carry a `CSQ`
  token. (Behavior for the two variant assays is unchanged; this only tightens other
  assays.)
- **R4 (M3) — `annotation_real_fraction` check (both assays).** Fraction of variants
  carrying a **non-empty, real** consequence term (i.e. excluding empty terms and
  variants whose only consequence is `intergenic_variant`). WARN below an uncalibrated
  band; distinct from M1's `annotation_complete` (which measures field *presence*).
  *Decision: "Real-consequence fraction."*
- **R5 (M3) — `annotation_consequence_distribution` check (both assays).** WARN when the
  **intergenic fraction exceeds an uncalibrated ceiling** (the PRD's "~100%-intergenic"
  smell). Each variant is collapsed to its **single most-severe consequence** (a small
  fixed SO-severity ordering) before tallying, so a multi-transcript VEP record counts
  once. *Decision: "Intergenic ceiling, most-severe."*
- **R6 — CSQ/ANN parser.** A local subfield parser (per the codebase's no-shared-VCF-lib
  convention) that reuses `annotation_structural`'s `_open_text` / `_declared_key` /
  `_record_has_key`. **VEP `CSQ`:** resolve the consequence subfield index from the
  `Format:` string in the `##INFO=<ID=CSQ,...Format: ...>` header; split entries on `,`
  (per transcript/allele) and consequences on `&`. **SnpEff `ANN`:** consequence is the
  fixed `Annotation` subfield (index 1). Aggregation policy: **most-severe consequence per
  variant** for both R4 and R5.
- **R7 — WARN-capped, UNVERIFIED-when-absent, no FAIL.** Follow the shipped plausibility
  wrapper idiom exactly (`somatic_plausibility.py:224-281`): compute `by_metric`, filter to
  `computable`, run shared `evaluate(...)`, then an explicit loop emits
  `QCResult(status="unverified", value=None, kind="metric")` for every uncomputable metric.
  The `ANNOTATION_PLAUSIBILITY_PACK` lives in `rule_pack.py`, is WARN-capped (no `fail_*`),
  and is **not** registered in `_RULE_PACKS` (imported directly, like the other plausibility
  packs).
- **R8 — Research-use only.** The distribution check is a statistical sanity signal, never
  a per-variant biological or clinical judgement. No pathogenicity claim anywhere.

### Should-have

- **R9 — M3 both assays in one slice.** Ship germline + somatic plausibility together (M2's
  somatic gate lands just before, so both-at-once is consistent). *Decision confirmed.*
- **R10 — Somatic VCF selection reuse.** Reuse the M1 "first VCF whose header declares
  CSQ/ANN wins" approach for the somatic gate; if the somatic annotated VCF is emitted per
  caller, prefer the Mutect2 path component when disambiguation is needed, consistent with
  the existing somatic-plausibility selection (`runner.py:169-176`).

### Nice-to-have (explicitly deferred)

- FAIL severity on any annotation band (until real-data calibration).
- Consequence-severity taxonomy beyond the minimal ordering needed for "most-severe."

## Technical Considerations

- **Integration point:** `_discover_qc` in `src/contig/runner.py:106-226` — the single
  assay-gated verdict-discovery seam. M2 widens the existing annotation block; M3 adds a new
  plausibility block gated to `assay in ("variant_calling","somatic_variant_calling")`,
  mirroring the germline/somatic plausibility blocks already there.
- **New module:** `src/contig/verification/annotation_plausibility.py` (evaluator +
  metrics), plus `ANNOTATION_PLAUSIBILITY_PACK` in `rule_pack.py`.
- **Reuse, don't reinvent:** `annotation_structural._open_text/_declared_key/_record_has_key`;
  the shared `evaluate()` band machinery (`rule_pack.py:330-349`); the somatic-plausibility
  wrapper shape.
- **Reproducibility:** R1's `default_params` change is captured in the launch manifest and
  re-applied by rerun/resume (same path M1 exercised) — no new reproduce surface.
- **Verification contract:** additive to the verdict only. No new `FailureClass`, detector,
  model, or persisted-record schema change; no exit-code change (WARN-capped). `eval-guard`
  and `heal-guard` baselines are untouched.
- **No raw-read egress:** parsers read VCFs on the user's compute; nothing leaves the box.
- **Live-cache caveat (carried from M1):** enabling `vep` makes sarek emit an annotated VCF,
  but a live run may still need `--vep_cache`/`--download_cache` or `--step annotate` that
  Contig does not yet wire. Both verifiers degrade to honest UNVERIFIED when annotation
  didn't run, so the slice is shippable on synthetic fixtures; a live-wiring follow-on is
  out of scope here but the caveat is recorded, not silently assumed away.

## Data Model

- **No new persisted model.** `AnnotationProvenance` (`models.py:206-216`) is reused as-is;
  M2 only changes *when* it is captured (gate to the two variant assays).
- New in-memory: an `AnnotationPlausibilityMetrics`-style dataclass local to the new module
  (real-consequence fraction, intergenic fraction) — not serialized.

## Risks & Open Questions

- **R-risk-1 — Uncalibrated bands.** All M3 band edges are engineering defaults on synthetic
  data. Mitigation: WARN-capped + UNVERIFIED-when-absent absorb a wrong band; FAIL is
  deferred until real-data calibration (R3 of the parent PRD).
- **R-risk-2 — CSQ Format variance.** Real VEP `Format:` strings vary by run config; if the
  `Consequence` field can't be located, the metric must degrade to UNVERIFIED, never guess.
  Mitigation: parser returns `None` on an unresolvable index → wrapper emits UNVERIFIED.
- **R-risk-3 — SO-severity ordering scope creep.** "Most-severe" needs an ordering, but a
  full SO term hierarchy is out of scope. Mitigation: ship a **minimal fixed ordering**
  sufficient to rank the common terms (e.g. intergenic/intron/synonymous < missense <
  stop/frameshift), with unknown terms treated as a low-severity default; documented as
  uncalibrated. Open question for the plan: the exact minimal term list.
- **R-risk-4 — Somatic annotated-VCF location.** If sarek writes the annotated somatic VCF
  somewhere the M1 "first CSQ/ANN VCF" scan doesn't cover, the gate reports UNVERIFIED.
  Mitigation: `rglob("*.vcf.gz")` already spans the run dir; confirm the somatic annotation
  output path in the plan (tolerated, not a blocker — UNVERIFIED is honest).

## Out of Scope

- **M4** VEP-vs-SnpEff cross-tool annotation concordance (a later milestone). M3 does **no**
  cross-tool comparison.
- **M5** "corroborated by" surface line, DB-version in the reproduce bundle, C6 eval
  fold-in.
- **Research prioritization** (ACMG/PGx/PRS) — this initiative is verify-only.
- **FAIL-severity** annotation bands; real-data band calibration.
- Live sarek `--vep_cache`/`--step annotate` wiring; non-sarek/standalone annotation;
  trained classifier models.
- Any pathogenicity/clinical adjudication — permanently out of scope by the bright line.
