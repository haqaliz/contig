# Card: feat/contig-alias-harmonization

- **Type:** feat
- **Id/slug:** contig-alias-harmonization
- **Owner:** aliz
- **Branch:** feat/contig-alias-harmonization/aliz
- **Source:** inline brief (no GitHub issue — slug-based unit of work, handed off from `contig-next`)

## Brief

Extend the shipped reference-mismatch self-heal (`src/contig/reference_harmonize.py`,
`plan_harmonization` / `harmonize_gtf`) from pure `chr`-prefix harmonization to
**per-contig alias harmonization**, so a UCSC-FASTA + Ensembl-GTF mismatch
(canonically `chrM`↔`MT`, plus the wider UCSC↔Ensembl/GenBank naming family) is
auto-harmonized at pre-flight into a run-scoped scratch GTF and the run proceeds,
instead of being silently mis-harmonized or refused.

This is capability **C2** (self-heal breadth), an explicitly-deferred follow-on of
**v0.9.0** (the chr-prefix GTF harmonizer).

## Grounding (files, not memory)

- **Deferral is real and named:** CHANGELOG.md v0.9.0 — "**Deferred:** … per-contig
  name mapping for ambiguous cases (e.g., `chrM`↔`MT`)". Also the C2 deferred list in
  `docs/technical/CAPABILITY_ROADMAP.md` (per-contig name mapping `chrM`↔`MT`).
- **Seam exists:** `src/contig/reference_harmonize.py` holds `plan_harmonization` and
  `harmonize_gtf`; detection lives in the v0.7.0 `reference_check` path; the launch
  chokepoint is `_dispatch_run`.
- **Edge cases already flagged:** `docs/planning/self-heal-reference-mismatch/understanding.md`
  names `MT`/`chrM`, scaffold `GL…`/`KI…` contigs, and subset/partial-overlap references
  as the open predicate edge cases.
- **Moat fit:** CAPABILITY_ROADMAP frames C2 self-heal breadth as "the most directly
  'gets better with better models' surface and the richest corpus fuel"; unattended-
  completion is the Phase-1 headline metric (`docs/ROADMAP.md`).

## Known caveat (from the handoff)

The current `plan_harmonization` only accepts a **uniform** chr-add/chr-strip and
requires the post-transform contig sets to intersect. `chrM`↔`MT` is **not** a uniform
prefix transform, so the design must add an **alias table** (chrM↔MT, and the
UCSC↔Ensembl/GenBank family) layered on top of the prefix rule — while preserving the
v0.9.0 safety property: a genuine wrong-assembly (still disjoint after aliasing) must
still be **refused**, never fabricated.

**The real target / trickiest test:** the residual case where prefix-harmonization
already makes the autosomes intersect (so the run proceeds today) but `chrM`/`MT`
stays silently mismatched.

## Definition of done (from the brief)

- Build **test-first** with synthetic FASTA/GTF fixtures (no real nf-core run).
- Record the decision in the launch manifest + `ReferenceIdentity` and a WARN
  `reference_harmonized` breadcrumb, exactly as the prefix slice does.
- Seed a golden corpus case.
- Preserve the refuse-on-genuine-wrong-assembly invariant.

## Strategic guardrail check

Stays in **Layer 2** (run/self-heal/verify/reproduce). No Layer-1 workflow authoring,
no wet-lab/clinical credentials, no raw-read egress (operates on reference contig
names on the user's compute). ✅
