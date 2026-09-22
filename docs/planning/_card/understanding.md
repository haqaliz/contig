# Understanding — feat/table-locator-predicates (Phase-2 dig)

Grounded in the fresh graphify graph (2026-09-22) + two read-only code-map
agents on this worktree (HEAD 43d6a56). Every claim carries a file:line.

## What the work is really asking

Widen the TSV/CSV table locator's `row` addressing from **single key-column
equality** (`{"gene_id": "ENSG1"}`) to **multi-key AND-equality**
(`{"gene": "TP53", "condition": "treated"}`) so a value living at a 2-D
intersection (DESeq2-style (gene × condition) tables, VCF-like (chr × pos)
tables) is addressable. Today a multi-key object is **refused at load time**,
and the row-shape contract is enforced at exactly two sites.

## The two enforcement sites (the whole surface to change)

1. **`load_claims`** (`src/contig/verification/reproduce.py:748-752`): `len(raw_row) != 1`
   → `ClaimsError "has an invalid 'row' object (expected exactly one key)"`.
   Sibling guards: non-str/empty key (754-757), non-str/bool value (758-761),
   key-match object + `header:false` refused (743-747). Pinned by
   `tests/test_reproduce.py:477-526` — notably
   `test_load_claims_rejects_row_multi_key_object` (487) **flips deliberately**.
2. **`resolve_cell`** (`reproduce.py:318-340`): defensive exactly-one-key
   re-check + str key/value + exact `.strip()`ed-string equality; 0 or >1
   matches → `(None, "row {row!r} matched N rows")` — never a pick. Pinned at
   `tests/test_reproduce_tsv_locator.py:48-73` and engine-level
   `tests/test_reproduce.py:1849-1886`. Also `test_resolve_cell_never_raises_on_wild_inputs`
   (185-224) currently treats multi-key as a *wild invalid* input — must be
   reworked as a *valid* shape, keeping the never-raises contract.

## What must NOT change (the guard surfaces)

- **Strict exactly-one**: a multi-key predicate binding 0 or >1 rows degrades to
  UNVERIFIED naming the count (`reproduce.py:337-340`; `resolve_match` precedent
  407-409: `"matched N times"`). Never DIVERGED (`classify(None, …)` → unverified,
   `reproduce.py:814-815`).
- **Freshness guard untouched**: `_require_fresh` (890-929) runs before parse and
  before the per-run `_table_cache` (1011-1019); pinned by
  `test_run_reproduction_table_claim_stale_exact_match_is_unverified`
  (test_reproduce.py:1647-1675).
- **Frozen scenario `table-locator`** (`src/contig/data/reproduce_scenarios.jsonl:6`,
  single-key `{"gene": "TP53"}` → `within_tolerance`) must keep resolving;
  baseline `reproduce_baseline.json` = 16/17 with one known miss; `reproduce-guard`
  wired in CI (`.github/workflows/ci.yml:35`); per-family `table: 1/1`. No scenario
  or baseline change expected.
- **Inference stays single-key**: sweep only emits int rows
  (`locator_inference.py:90`, 759, 787); matcher carries them verbatim
  (`locator_match.py:291-308`); `_locator_for` has no dict-row path. No change.
- **CLI unchanged**: every write path validates through the unchanged `load_claims`
  round-trip (`cli.py:1884-1904`); `_claim_with_locator` serializes `row` verbatim
  (1656). Help text example stays single-key (1092-1095) — update optional.
- **Family parity automatic**: `claim_family` is an isinstance chain
  (`reproduce_guard.py:91-92`), multi-key stays `TableLocator` → `"table"`.
- **Notebook locator** (`{"contains": s}`, reproduce.py:218) is a parallel
  single-key contract — out of scope, untouched.

## The one recorded decision to supersede deliberately

`docs/planning/reproduce-tsv-csv-locator/locator/task-5-report.md:25` + `spec.md:26`
+ PRD:172,254 defer "multi-key/predicate rows" with no blocker named — this slice
is that deferral's deliberate supersession, same as the PRD's plan_20260721.md:54
documented the refusal.

## Open questions for the interview

1. **Numeric predicates**: the brief says "plain numeric/equality predicates where
   the contract allows". Proposal: equality-only this slice (values stay str,
   exact stripped compare — "5" ≠ "5.0"); numeric *comparison* predicates
   (>, <, regex) are the separately-deferred "regex/numeric row predicates" item
   and would mostly violate the strict exactly-one rule in real tables. Needs a
   decision: numeric-coercion equality in scope, or out?
2. **Column ranges / regex cell matching** (CAPABILITY_ROADMAP.md:1874,1968):
   named deferrals, out of scope — confirm.
3. Error-message wording on the widened refusal ("expected exactly one key" →
   "expected one or more keys") — cosmetic, but pinned nowhere (no message-match
   in refusal tests), so free to change.

## Guardrail check

Layer 2 (reproduce/verify chain), stdlib only, no new deps, no network/real
repo in CI, UNVERIFIED never a false pass. No Layer-1 drift.