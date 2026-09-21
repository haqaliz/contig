# Unit of work: reproduce-locator-cli (C8 locator inference, aspect 3 of 3)

Branch: `feat/reproduce-locator-cli/aliz`. Source: inline brief (confirmed by
user, 2026-09-21). No GitHub issue exists for this work.

## Brief

Build C8 locator-inference aspect 3 (cli-command) per
`docs/planning/reproduce-locator-inference/prd.md` (M1, S1-S4) and the amended
spec: a new `contig infer-locators <repo> <claims.json>` command that runs the
shipped matcher (`sweep_repo` + `match_claims` with the M10 `metrics` mapping)
over a local repo and an existing claims draft, writing an updated claims file
(locators added where evidence-gated binds exist) plus a review sidecar, with
the `load_claims` round-trip invariant before any write (ClaimsError → exit
non-zero, nothing written), `--force`/refuse-to-overwrite parity with
`extract-claims`, `--dry-run`, Click-param introspection tests. Metric words
come from the extractor's metric field/sidecar and human review — the CLI
threads them, never invents them. No `models.py`/verdict/bundle/signature
change; stdlib only.

Caveat: the matcher module is unmerged (PR #41); this worktree's base is
`origin/master`, so implementation depends on the PR merging (or rebasing this
branch onto it) — planning docs proceed regardless.

## Source references

- PRD: `docs/planning/reproduce-locator-inference/prd.md` (M1 = the command;
  S1 = `--force` parity; S4 = `--dry-run`; aspect 3 = `cli-command`, gated on
  the evidence gate — passed and recorded)
- Spec amendment (M10 + sidecar): `docs/planning/reproduce-locator-inference/match-and-propose/spec.md`
- Gate records: `docs/planning/reproduce-locator-inference/match-and-propose/evidence-gate-semantic-20260921.md`
  (verdict: "Aspect 3 is unblocked to ship narrowed")
- Matcher module (on PR #41, not yet in this base):
  `src/contig/verification/locator_match.py`