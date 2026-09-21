# Unit of work: reproduce-locator-matcher (C8 locator inference, aspect 2)

Branch: `feat/reproduce-locator-matcher/aliz`. Source: contig-next handoff brief
(confirmed by user, 2026-09-21). No GitHub issue exists for this work.

## Brief

Build C8 locator-inference aspect 2 (match-and-propose) per
`docs/planning/reproduce-locator-inference/prd.md`: a pure stdlib matcher that
consumes the shipped `sweep_repo` candidate enumeration and the `extract-claims`
draft, applying rounding-aware equality at the claim's printed precision, the
dual-scale `v`/`v/100` attempt with sidecar disclosure, the strict exactly-one
rule (0 or >1 → emit nothing, count named), complete-or-nothing table locators,
and the M9 low-information-value refusal — with G1 (exactly 0 wrong locators on
the fixture corpus) as the hard gate and a round-trip through the unchanged
`load_claims`. No CLI, no `models.py` change, no verdict/bundle/signature change;
`pattern`/notebook inference stays out (synthesized-regex blocker).

Caveat to respect: R6 stale-coordinate/fresh-path mismatch is
accepted-and-disclosed, not solved — record it in the sidecar wording and in the
evidence-gate plan; after the matcher, the PRD's evidence gate (one real
published repo, count binds/ambiguities/refusals) must be run and recorded before
any CLI aspect is started.

## Source references

- PRD: `docs/planning/reproduce-locator-inference/prd.md` (aspect decomposition at
  lines 274-293; aspect 2 = `match-and-propose`, no I/O, evidence gate after it)
- Shipped substrate: `CHANGELOG.md` [Unreleased] candidate-sweep entry;
  `src/contig/verification/locator_inference.py`
- Capability home: `docs/technical/CAPABILITY_ROADMAP.md` C8