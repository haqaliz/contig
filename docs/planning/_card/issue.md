# Card: feat / somatic-variant-calling

- **Type:** feat
- **Slug:** somatic-variant-calling
- **Owner:** aliz
- **Branch:** feat/somatic-variant-calling/aliz
- **Source:** inline brief (no GitHub issue). Handed off from `contig-next` on 2026-07-03.

## Brief

Add **somatic (tumor–normal) variant calling** as a new assay via nf-core/sarek's
somatic mode, through the `ADD_AN_ASSAY` path — the next capability (**C4**) on
`docs/technical/CAPABILITY_ROADMAP.md` and the biggest unblocked lever, reusing the
shipped C1 (concordance) / C2 (self-heal) / C3 (plausibility) machinery on new terrain
to compound the failure-and-verification corpus (moat #2).

It is a natural extension of the **shipped germline assay** (GATK best-practices via
nf-core/sarek), so much of the verification plumbing is reused rather than rebuilt.

## Scope discipline — tight first slice

C4 is genuinely large. The first slice is scoped tightly:

- Registry entry for the somatic goal.
- Planner match for the somatic (tumor–normal) goal.
- Tumor/normal **sample-sheet shape** + pre-flight validation (the paired
  tumor/normal structure sarek somatic requires).
- **Structural output manifest** for the somatic outputs (present / non-empty /
  indexed / gzip-intact), wired into `run_qc` like the other assays.

All **test-first** with synthetic fixtures — no real nf-core run in CI.

## Deferred to follow-on slices (do NOT build in slice 1)

- VAF-distribution plausibility (biological-plausibility check, C3-style).
- Panel-of-normals filtering-present check.
- Second-somatic-caller **concordance hook** (C1-style).
- Seed corpus cases for somatic-specific failure modes (beyond what structural QC needs).

This mirrors how germline / RNA-seq were built up over v0.2.0 → v0.6.0: the assay
lands structurally first, then plausibility, then concordance, in separate releases.

## Caveats to confirm in the dig (from the contig-next handoff)

1. **Roadmap-push, not partner-pull.** No named design partner requested somatic;
   C4 is pre-designated by the roadmap. The discipline (`USE_CASE_UNIVERSE.md`
   "demand-pull, not our guess") prefers a partner ask. Sanity-check the pick against
   deepening a shipped assay before committing.
2. **C4 is large.** Hold the line on the tight first slice above; resist pulling
   plausibility/concordance into slice 1.

## Guardrails (CLAUDE.md)

- Layer-2 only: we consume nf-core/sarek somatic; we do **not** author the pipeline
  from English (no Layer 1).
- No raw-read egress; runs on the user's compute.
- No clinical over-claiming: a somatic verdict is "ran correctly and reproducibly,"
  research-use, never a cancer diagnosis (`USE_CASE_UNIVERSE.md` bright line).
- Test-first, every capability lands with its failing test written first.
