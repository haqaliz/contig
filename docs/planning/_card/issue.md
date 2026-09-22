# feat table-locator-predicates — multi-key / predicate row match for the table locator

## Brief

Widen the TSV/CSV table locator's row addressing from single key-column equality
to multi-key / predicate rows: accept `"row": {colA: x, colB: y}` as a
first-class match (currently refused at `load_claims`), plus plain
numeric/equality predicates where the contract allows, resolving exactly-one row
else UNVERIFIED, with the freshness guard, never-raises, and
UNVERIFIED-never-DIVERGED contracts intact. Caveat: preserve the shipped
matcher's strict exactly-one site rule and the M10 semantic filter's scope —
locator inference stays single-key, and a multi-key predicate that binds 0 or >1
rows degrades to UNVERIFIED, never an arbitrary pick. Strict TDD on real fixture
tables, stdlib only, no new deps, no real repo/network in CI.

## Source

Selected by `contig-next` re-pick (2026-09-22) after the bwa-mem2 pick was
abandoned at the review gate (blocker: no live trigger, recorded in the
abandoned worktree's `docs/planning/_card/understanding.md`). Grounded in
`docs/planning/reproduce-tsv-csv-locator/prd.md:172,254` (single key-column
equality only; multi-key/predicate rows, column ranges, regex out of scope),
`spec.md:26`, `docs/technical/CAPABILITY_ROADMAP.md:1874`. No GitHub issue
exists for this work.