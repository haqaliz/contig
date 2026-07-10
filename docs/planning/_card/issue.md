# Card: annotation-germline-structural-verify (feat)

Type: feat · id/slug: `annotation-germline-structural-verify` · owner: aliz
Branch: `feat/annotation-germline-structural-verify/aliz`
Source: no GitHub issue — inline unit of work handed off by `/contig-next` (2026-07-10).

The initiative PRD and M1 implementation plan already exist in-repo (committed to
master), so this card links to them rather than restating them.

- Initiative PRD: `docs/planning/variant-annotation-assay/prd.md`
- M1 implementation plan (authoritative, task-by-task TDD): `docs/planning/variant-annotation-assay/plan-m1.md`
- Capability: C7 (research-use variant annotation & prioritization), milestone **M1**.

## Brief (from /contig-next handoff)

Build C7 M1: research-use variant annotation, germline structural verify. Enable
nf-core/sarek's built-in annotation step (VEP → `CSQ`) on the germline
`variant_calling` assay, add a `verification/annotation_structural.py` verifier that
proves the annotation *ran correctly* (every variant carries an annotation record),
and capture the annotation tool + DB version into provenance (the C5
`reference_identity` pattern), rendered in `contig methods`.

Research-use only — Contig verifies the annotation EXECUTED, never adjudicates
pathogenicity. WARN-capped; UNVERIFIED (never a false pass) when no annotated VCF is
found. Mirrors the shipped somatic-plausibility slice. No real VEP/sarek in CI
(synthetic VCF fixtures only).

## Known caveat to resolve in the dig (plan Task 4)

The plan defers confirming the exact sarek `--tools` string (`haplotypecaller,vep`)
and whether sarek 3.5.1 actually runs annotation without a `--vep_cache` /
`--snpeff_cache` or `--step annotate`. De-risked but not eliminated: the verifier
degrades to UNVERIFIED when annotation didn't run, so a missing cache surfaces
honestly, not as a green verdict. Since no real VEP/sarek runs in CI, the M1 slice
is shippable even if the live `--tools`/cache wiring needs a follow-on — but resolve
and record the finding rather than silently assuming a cache exists.
