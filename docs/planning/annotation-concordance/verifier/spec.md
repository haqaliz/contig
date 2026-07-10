# Aspect spec: verifier (C7 M4 annotation concordance)

Parent PRD: `docs/planning/annotation-concordance/prd.md`. This is the single aspect for
M4 — the whole milestone is one coherent unit (enable second annotator → verify agreement
→ capture provenance), so it is not further decomposed.

## Problem slice & user outcome

A variant run (germline or somatic) with VEP + SnpEff enabled gains a `kind="concordance"`
annotation axis in the verdict: `consequence_concordance` (WARN-capable) and
`gene_symbol_concordance` (informational). The user sees a corroboration line and both
annotator versions in provenance. Research-use only; never a clinical verdict.

## In-scope requirements (from PRD)

- M-1 enable SnpEff on both variant assays (`default_params.tools`), non-destructive.
- M-2 new `verification/annotation_concordance.py` mirroring the `somatic_concordance.py`
  contract (`kind="concordance"`, site key, `_WARN_BELOW=0.90`, `_MIN_SHARED_VARIANTS=10`,
  never FAIL).
- M-3 two discovery layouts: two separate VEP/SnpEff VCFs (path-component select, join on
  site key) and a single VCF carrying both CSQ+ANN (own dual-key parse, never mutate M3's
  driver); record detected layout.
- M-4 `consequence_concordance` — exact most-severe-SO-term match, WARN < 0.90, UNVERIFIED
  below floor. Reuse M3 primitives.
- M-5 `gene_symbol_concordance` — informational-only (always PASS), fixed minimal
  normalization (case-fold + strip + empty/`.` → unresolvable, no alias table).
- M-6 auto-wire into `_discover_qc`'s `if assay in VARIANT_ASSAYS:` block.
- M-7 provenance pair: `RunRecord.annotation_identity` → list, back-compat validator,
  render both in methods/HTML, reproduce.
- M-8 honest contract: at most WARN, never changes exit code, attributes to tools+versions.

## Out of scope

FAIL severity; M5 verdict-card "corroborated by" line and eval fold-in; SnpEff cache
wiring; non-sarek annotation; prioritization; switching M3 onto a dual-key parser.

## Acceptance criteria (testable)

1. `select_pipeline("variant_calling").default_params["tools"] == "haplotypecaller,vep,snpeff"`
   and somatic `== "strelka,mutect2,vep,snpeff"`; a user `--tools` still wins.
2. Two-file fixture, concordant → `consequence_concordance` PASS, `gene_symbol_concordance`
   PASS; value fractions reported; `kind="concordance"`.
3. Two-file fixture, consequence-divergent → `consequence_concordance` WARN naming both
   tools; verdict at most WARN; `verify` exit unchanged.
4. Symbol-divergent fixture → `gene_symbol_concordance` PASS (informational) with the
   fraction, never WARN.
5. Single-annotator fixture → both metrics UNVERIFIED (value None); below-floor fixture →
   UNVERIFIED. No concordance PASS ever emitted from missing inputs.
6. Single-VCF-both-CSQ+ANN fixture → parsed via M4's own dual-key path; M3 plausibility
   tests still green (no regression).
7. Integration: a synthetic run dir with both assays yields the concordance checks in
   `record.qc_results` via `_discover_qc`.
8. Provenance: both-header fixture → two `AnnotationProvenance` entries in the bundle,
   rendered in `contig methods`; a pre-M4 singular bundle still loads (back-compat test).

## Dependencies & sequencing

Phase 1 (enable) is independent. Phases 2–3 (pure metrics) depend on nothing but fixtures.
Phase 4 (wire) depends on 2–3. Phase 5 (provenance) is independent of 2–4 but shares
fixtures. Phase 6 doc-sync last. See `plan_20260710.md`.

## Open risks (from PRD)

R1 over-claim (mitigated by WARN-cap + loose default), R3 sarek layout unverified in CI
(mitigated by defensive dual-layout + breadcrumb), R4 live-cache (UNVERIFIED when absent),
R5 provenance migration (back-compat validator + test).
