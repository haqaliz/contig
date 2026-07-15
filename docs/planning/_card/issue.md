# Card: sibling-plausibility-fail-severity

- **Type:** feat
- **Id / slug:** sibling-plausibility-fail-severity
- **Branch:** feat/sibling-plausibility-fail-severity/aliz
- **Owner:** aliz
- **Source:** inline brief (from `contig-next` handoff — no GitHub issue; id is a slug)

## Brief

Extend gross-implausibility FAIL severity from the germline `VARIANT_RULE_PACK` to the
sibling biological-plausibility packs (`SOMATIC_PLAUSIBILITY_PACK`,
`RNASEQ_PLAUSIBILITY_PACK`, and consider `RNASEQ_COMPOSITION_PACK`) in
`src/contig/verification/rule_pack.py`, following the v0.35.0 germline precedent: WES-safe
gross-implausibility engineering tripwires, not calibrated clinical bands.

This matters now because v0.36.0 shipped `--fail-on-verdict`, so a FAIL verdict finally
exits non-zero — but germline is the only assay whose *biology* can trip it, meaning a
somatic or RNA-seq run wired into CI goes green on broken science.

**Critical caveat to resolve in the dig before writing bands:** unlike germline Ti/Tv
(universal floor ~0.5 = random calls), somatic `median_vaf` and RNA-seq `duplication_rate`
have legitimate tails — a low-purity tumor really does have low VAF, a deep RNA-seq library
really is highly duplicated. Do NOT invent a FAIL band for a metric without a universal
gross floor. The honest outcome may be narrow: ship the empty-call-set floor
(`somatic_variant_count fail_below: 1`, mirroring the shipped germline `variant_count`
floor) plus any equally universal sibling, and document why the rest stay WARN-only.

Test-first per repo discipline; verdict-reduction fixtures only, no real nf-core run in CI.

## Grounding (the named-deferral trail)

- `CHANGELOG.md` (v0.36.0) — shipped the opt-in `--fail-on-verdict` flag: a FAIL verdict
  exits `1`; WARN/UNVERIFIED/PASS stay `0`. This is what makes the sibling gap bite.
- `docs/planning/germline-plausibility-fail-severity/prd.md:120-121` — the explicit deferral
  this work closes: *"FAIL severity for the somatic, RNA-seq, RNA-seq-composition, and
  annotation plausibility packs — they stay WARN-only."*
- `docs/technical/CAPABILITY_ROADMAP.md:458-480` — the v0.35.0 germline slice established the
  honesty tier this one inherits: *"WES-safe gross-implausibility engineering tripwires …
  not a clinical or biological claim"*, i.e. the precedent that unblocks this **without**
  real-cohort calibration.
- `docs/planning/germline-plausibility-fail-severity/prd.md:129-131` — names the chokepoint:
  `verification/rule_pack.py` (the rule dicts). The scorer (`_status_for`), evaluator,
  verdict reducer (`overall_verdict`), report, provenance, and dashboard consume it
  unchanged — so germline was a pure data edit. Confirm the siblings ride the same path.

## Why (moat framing, from contig-next)

- CLAUDE.md #2: "make every verdict harder to fool." v0.36.0 gave the verdict teeth, but
  only germline biology can trip the gate — six of seven wired assays can't FAIL on science.
- Deepens the C3 verification axis across three assays at the shipped chokepoint, with no
  new module, model, `FailureClass`, or dashboard card.
- Depth-first on an already-shipped capability's named follow-on, not a new surface.

## Open questions for the dig / interview

1. Which sibling metrics have a **universal** gross floor (defensible with no calibration),
   and which must honestly stay WARN-only? (The pick's success case may be narrow.)
2. Is `somatic_variant_count fail_below: 1` the direct mirror of the shipped germline
   `variant_count fail_below: 1` empty-call-set floor?
3. Does `RNASEQ_COMPOSITION_PACK` (exonic/intronic/unassigned) belong in this slice or a
   follow-on? Same for the C7 annotation plausibility pack.
4. Do the sibling packs actually ride the same `_status_for` scorer + `overall_verdict`
   reducer as germline — i.e. is this really a pure data edit?
5. Do any sibling packs already carry `fail_*` bands (the "did-it-run" packs — methylseq,
   ampliseq, mag, scrnaseq — reportedly do)? Scope must not disturb those.
6. Does an UNVERIFIED/absent metric stay UNVERIFIED (never converted to FAIL)?

## Acceptance (test-first)

- A grossly-implausible sibling fixture (e.g. an empty somatic call set) drives
  `record.verdict` → **FAIL**, naming the biological reason.
- A legitimate sibling run (low-purity tumor VAF, deeply-duplicated RNA-seq library) stays
  PASS/WARN — **no false FAIL**.
- An absent/uncomputable metric stays **UNVERIFIED**, never FAIL, never PASS.
- Metrics without a universal gross floor keep their current WARN-only behavior, unchanged.

## Guardrails (CLAUDE.md)

- Layer 2 only (verify axis) — no Layer-1 workflow authoring. Satisfied by construction.
- No over-claiming: bands are engineering tripwires, never a clinical or biological claim.
- UNVERIFIED is never rendered as PASS, and must never be converted into FAIL.
- No new dependency; no raw-read egress.
- Test-first (RED → GREEN); no real nf-core/sarek run in CI.
