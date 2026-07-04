# Card: feat / somatic-vaf-plausibility

- **Type:** feat
- **Slug:** somatic-vaf-plausibility
- **Owner:** aliz
- **Branch:** feat/somatic-vaf-plausibility/aliz
- **Source:** inline brief (no GitHub issue). Handed off from `contig-next` on 2026-07-04.

## Brief

Add a **C3-style biological-plausibility verdict for the somatic (tumor–normal)
assay** shipped in v0.13.0, whose verification is currently **structural-only**.

C4 (somatic variant calling) shipped its first slice today (v0.13.0): intake →
plan → run → verify wired through the engine on `nf-core/sarek` somatic mode. But
the CHANGELOG is explicit that the somatic verdict is "honestly structural-only"
because there is "no somatic rule pack or plausibility yet." Per
`USE_CASE_UNIVERSE.md`, "a passthrough that issues no verdict is not a Contig
assay" — so somatic is currently the weakest-verified assay on the engine, and a
biological-plausibility verdict is what turns it into a real Layer-2 win.

## What to build

Mirror the shipped **germline** C3 slice (`verification/variant_metrics.py`, the
Ti/Tv + het/hom slice from v0.3.0):

- Compute a **VAF-distribution sanity check** (and, if it falls out cheaply, a
  somatic-variant-count band) from the run's **somatic VCF** into a new
  `SOMATIC_PLAUSIBILITY_PACK`.
- Wire it into `_discover_qc`, **gated to `assay == "somatic_variant_calling"`**.
- **WARN-capped** (corroboration, never a cancer diagnosis).
- Emit **UNVERIFIED — never a false pass** — when the VAF field is absent.

## Known caveats (flag / resolve in the dig)

1. **Uncalibrated bands.** The plausibility bands are best-effort engineering
   defaults (WARN-capped only, like every C3 slice so far). FAIL severity is
   deferred until calibrated on real data.
2. **Field parsing differs across callers.** VAF/AF lives in different FORMAT
   fields for **Mutect2** (`AF`) vs **Strelka2** (no direct `AF`; derived from
   tier counts). The dig must decide **which caller's VCF** it computes over and
   degrade to UNVERIFIED cleanly when the field is absent — never a fabricated VAF.
3. **No live somatic run yet.** A real Mutect2 somatic run still needs deferred
   PON / germline-resource wiring, so — exactly as germline Ti/Tv did — this ships
   and is tested against **synthetic VCF fixtures** (no real nf-core/sarek run in
   CI). The compute runs whenever a VCF exists and degrades to UNVERIFIED otherwise.

## Guardrails (CLAUDE.md)

- Layer-2 only: we consume nf-core/sarek somatic; we do **not** author the pipeline
  from English (no Layer 1).
- No raw-read egress; runs on the user's compute (deterministic, synthetic fixtures).
- No clinical over-claiming: a somatic verdict is "ran correctly and reproducibly,"
  research-use, never a cancer diagnosis (`USE_CASE_UNIVERSE.md` bright line).
- Test-first, every capability lands with its failing test written first.

## Grounding citations

- `CHANGELOG.md:9-50` — v0.13.0 somatic slice; verification is structural-only.
- `docs/technical/CAPABILITY_ROADMAP.md:265-309` — C4; VAF/PON plausibility +
  Strelka2-vs-Mutect2 concordance hook deferred to follow-on slices.
- `docs/technical/USE_CASE_UNIVERSE.md:73-74, 127-138` — somatic verify menu; the
  depth-first / "must issue a verdict" discipline.
- `CHANGELOG.md:340-356` — germline C3 slice (v0.3.0) to mirror.
