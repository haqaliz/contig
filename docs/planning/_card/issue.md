# Card: annotation-m5-surface (feat)

Type: feat · Slug: annotation-m5-surface · Owner: aliz · Branch: `feat/annotation-m5-surface/aliz`

No GitHub issue (tracker has no filed issue) — source is the inline brief below,
produced by the `/contig-next` handoff (2026-07-10) that selected this feature.

- Initiative PRD: `docs/planning/variant-annotation-assay/prd.md`
- Capability: C7 (research-use variant annotation & prioritization), milestone **M5** —
  the final annotation-assay slice.
- Shipped so far: M1 (germline structural verify + provenance) v0.25.0; M2 (somatic
  gate) + M3 (annotation plausibility, both assays) v0.26.0; **M4 (VEP-vs-SnpEff
  concordance, both assays) v0.27.0 — just shipped** (see `CHANGELOG.md`).

## Brief (from /contig-next handoff)

Ship **C7 M5** scoped to the **two unblocked parts**, explicitly deferring the third
(blocked) part:

1. **"Corroborated by" surface line.** A verdict-card / report line surfacing the M4
   annotation-concordance metrics (`consequence_concordance` and
   `gene_symbol_concordance`) with both annotator names — the human-legible corroboration
   line M4 deferred.
2. **Annotation DB/cache-version provenance.** Extend `AnnotationProvenance` to capture the
   annotation **database / cache version** from the VCF header (VEP `##VEP` header line;
   SnpEff `SnpEffCmd` / `ANN` header) alongside the tool+version M4 already captures.
   Render it in `contig methods`, the HTML provenance panel, and the reproduce bundle.

**Explicitly deferred (do NOT build this slice):**

3. **Fold annotation outcomes into the C6 eval corpus.** Blocked on C6's standing blocker:
   the C1/C3/annotation corroboration signals carry **no ground-truth labels**, so they
   need a labeling design before they can join `eval-guard`/`heal-guard` (deferred across
   v0.17.0 and v0.22.0). Note it as deferred; don't build it.

## Known caveats to resolve in the dig

- **Honest provenance.** When a given VCF header carries no DB/cache version, degrade to
  the existing tool-only provenance — never fabricate a version (mirrors C5's "left null,
  never fabricated" rule). Verify VEP `##VEP` and SnpEff `SnpEffCmd`/`ANN` headers actually
  carry a parseable DB/cache-version token in our synthetic fixtures; if a header lacks it,
  the field stays `None`.
- **Live-cache caveat (carried from M1–M4).** Enabling annotation may still need a
  VEP/SnpEff cache Contig doesn't wire; when annotation didn't run there is no
  concordance metric and no provenance version — the surface line must simply not render
  (or render UNVERIFIED), never a fabricated corroboration.
- **Surface must be kind-driven, not re-computed.** The "corroborated by" line should read
  the already-computed M4 `kind="concordance"` `QCResult`s, not recompute concordance.
- **Reproduce round-trip.** The new provenance field must serialize into the bundle and
  survive rerun/resume, with back-compat for pre-M5 bundles (mirrors M4's list migration).

## Precedent to reuse (shipped contracts)

- M4 concordance: `verification/annotation_concordance.py` (emits the two `kind="concordance"`
  `QCResult`s this slice surfaces).
- Provenance: `AnnotationProvenance` (M4 made `RunRecord.annotation_identity` a list;
  `models.py` ~206-216, ~297) + `bundle.compute_annotation_identity`.
- Report grouping: the existing `kind=="concordance"` display split in `report.py`
  (~101-109) and `contig methods` / HTML provenance panel rendering.

## Guardrail

Research-use verification only. Surface + provenance, never a pathogenicity/clinical
verdict. A verdict means "ran correctly and reproducibly," never "clinically true."
UNVERIFIED is never rendered as PASS. Bright line: `docs/technical/USE_CASE_UNIVERSE.md:33-48`.
