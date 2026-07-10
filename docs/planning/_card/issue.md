# Card: annotation-concordance (feat)

Type: feat · Slug: annotation-concordance · Owner: aliz · Branch: `feat/annotation-concordance/aliz`

No GitHub issue — source is the inline brief below, produced by the `/contig-next`
handoff (2026-07-10) that selected this feature.

The initiative PRD already exists in-repo (committed to master), so this card links
to it rather than restating it.

- Initiative PRD: `docs/planning/variant-annotation-assay/prd.md`
- Capability: C7 (research-use variant annotation & prioritization), milestone **M4**.
- M1 (germline structural verify + provenance) shipped v0.25.0; M2 (somatic gate) +
  M3 (annotation plausibility, both assays) shipped v0.26.0 (see `CHANGELOG.md`).

## Brief (from /contig-next handoff)

Build **C7 M4: VEP-vs-SnpEff annotation concordance** as a C1-style corroboration
axis over the annotated VCF, for both `variant_calling` (germline) and
`somatic_variant_calling`.

Enable SnpEff alongside VEP via `default_params` (`--tools …,vep,snpeff`, injected
non-destructively like M1/M2, re-applied on rerun/resume) so one sarek run emits
both annotation sets, then compute per-variant consequence/gene-symbol agreement —
reusing the shipped `annotation_plausibility.py` CSQ/ANN most-severe-consequence
parser rather than writing a new one.

Hold the standing concordance contract: at most WARN, never FAIL or exit-code
change, and UNVERIFIED (never a false pass) when only one annotator ran, the tools'
vocab can't be reconciled, or shared records fall below threshold. Test-first with
synthetic tiny CSQ/ANN fixtures, no real VEP/SnpEff/sarek run in CI.

## Known caveats to resolve in the dig

- Enabling snpeff means a live run may need a SnpEff cache Contig doesn't yet wire,
  so an absent second annotation must surface as UNVERIFIED (never a false pass) —
  the same live-cache caveat M1–M3 carry for VEP.
- VEP (SO terms) and SnpEff (its own labels) don't use identical consequence vocab,
  so per-variant agreement needs a **conservative** term-equivalence map; the honest
  fallback is UNVERIFIED below a shared-record threshold rather than a guessed match.
- **Key open design question for the dig:** VEP CSQ and SnpEff ANN are two *separate*
  INFO fields that can coexist in one VCF, but they key/annotate variants differently
  (transcript sets, symbol sources). Need to decide the join key
  (CHROM/POS/REF/ALT) and the per-variant reduction (both parsers already collapse to
  a single most-severe consequence) before planning.

## Concordance primitive precedent (reuse the shipped contract)

- C1 germline `--concordance-vcf` (`verification/concordance.py`).
- RNA-seq `--concordance-counts` (`verification/count_concordance.py`): Spearman,
  fraction-agreeing, informational overlap.
- Somatic auto `somatic_site_overlap` (`verification/somatic_concordance.py`):
  Jaccard of Mutect2 vs Strelka2 PASS sites, no user input, auto-wired in
  `_discover_qc`. This is the closest precedent — two tools from ONE run, auto in
  the verdict.

## Guardrail

Research-use verification only. Concordance is corroboration, never a
pathogenicity/clinical verdict. UNVERIFIED is never rendered as PASS.
