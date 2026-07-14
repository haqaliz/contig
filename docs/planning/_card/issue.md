# Card: germline-plausibility-fail-severity

- **Type:** feat
- **Id / slug:** germline-plausibility-fail-severity
- **Branch:** feat/germline-plausibility-fail-severity/aliz
- **Owner:** aliz
- **Source:** inline brief (from `contig-next` handoff — no GitHub issue)

## Brief

Give the germline biological-plausibility axis its first FAIL gate, Ti/Tv-first, by
adding conservative `fail_below`/`fail_above` bands to the germline checks in
`src/contig/verification/rule_pack.py` (`ts_tv`, then `het_hom`, and a gross ceiling on
`variant_count`) — the checks already compute; only the bands/severity change.

Use **gross-implausibility-only** bands sourced from published literature (e.g. Ti/Tv
`fail_below ~1.2`, `fail_above ~3.6` so a legitimate WES run at ~3.3 stays PASS/WARN
while a noise call set at ~0.5 FAILs), keeping the existing tight WARN band intact —
this is a "the call set is broken" claim on the same honesty tier as
`mean_coverage fail_below 10`, never a clinical/biological claim.

**Caveat to resolve in the dig:** this reverses the stated "germline plausibility never
FAILs / never changes the exit code" contract, so confirm that's intended and update the
tests and CHANGELOG/roadmap language that assert WARN-only; keep it test-first (fixtures
at, just-inside, and grossly-outside each band).

Leave the somatic/RNA-seq/annotation plausibility packs WARN-only for now — germline
Ti/Tv is the depth-first first slice.

## Why (moat framing, from contig-next)

- The biological-plausibility axis is entirely WARN-only today; C1/C3/C4/C7 each ship
  plausibility/concordance checks WARN-capped with "FAIL severity deferred until
  calibrated" (`docs/technical/CAPABILITY_ROADMAP.md:387,427,449,526`). Code confirms:
  `ts_tv`, `het_hom`, `variant_count` carry no `fail_*` (`rule_pack.py:49-86`).
- A plausibility check that can only WARN can never fail a run whose biology is broken
  but which ran fine — exactly the silent-failure class the axis exists to catch. Giving
  it teeth is CLAUDE.md #2: "make every verdict harder to fool."
- Precedent already set: the did-it-run packs (`mean_coverage fail_below:10`,
  methylseq/ampliseq/mag, scrnaseq capture) already FAIL on gross failure as honest
  engineering defaults (`rule_pack.py:80-264`). The germline pack's own comment already
  names a defensible gross band — "values far outside [1.5, 3.0] flag a likely run
  problem" (`rule_pack.py:44-48`).

## Guardrails (CLAUDE.md)

- Layer 2 only (run/verify/reproduce). This is verification depth — on-thesis.
- No clinical/diagnostic claim: FAIL bands are "the call set is broken" engineering
  tripwires, not biological/pathogenicity claims. Research-use only.
- No proprietary data: bands come from published literature (public knowledge).
- Test-first (repo standing discipline).
