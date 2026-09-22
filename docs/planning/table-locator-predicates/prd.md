# PRD: table-locator-predicates — multi-key row match for the table locator

Slug: `table-locator-predicates` · Aspect: `multi-key-rows` · Source:
`docs/planning/_card/issue.md` (contig-next re-pick) + `_card/understanding.md`
(Phase-2 dig, two code-map agents, graphify-first).

## Problem Statement

Contig reproduces published claims by binding a paper's stated value to a
cell in the repo's own output (TSV/CSV) via a `TableLocator` claim
(`{"from": <file>, "column": <name|int>, "row": <int|{key: val}>}`). The row
object supports **single key-column equality only**: `{"row": {"gene_id":
"ENSG1"}}`. A value that lives at a **2-D intersection** — the normal shape of
DESeq2/edgeR count tables (gene × condition), VCF-like tables (chr × pos),
feature tables (feature × sample) — cannot be addressed: the multi-key row
object is refused at load time (`ClaimsError`, "expected exactly one key",
`src/contig/verification/reproduce.py:748-752`). The author must pre-reshape
the repo's table into a single-key form, or the claim stays UNVERIFIED.

Evidence it is real: the deferral was recorded with no blocker
(`docs/planning/reproduce-tsv-csv-locator/prd.md:172,254`; spec.md:26;
CAPABILITY_ROADMAP.md:1874 — "multi-key/predicate row match, column ranges,
regex"). The locator chain is otherwise complete (sweep → match-and-propose →
`infer-locators` CLI, shipped 2026-09-22); this is its named remaining friction
for table claims.

## Goals & Success Metrics

- A claim with a multi-key row object (`{"colA": x, "colB": y}`) loads, binds
  exactly-one row, and produces a verdict — reproduced/within-tolerance when the
  cell matches the claim value.
- 0 or >1 rows bound by the predicate → UNVERIFIED naming the count — never a
  false pass, never DIVERGED, never an arbitrary pick.
- Back-compat: every shipped single-key claim and the frozen reproduce-guard
  scenario (`table-locator`, `{"gene": "TP53"}`, `within_tolerance`) keep
  working; `reproduce-guard` baseline (16/17) unmoved.
- Success metric: the full suite stays green (3209 passed / 1 skipped today),
  `contig reproduce-guard` passes with the committed baseline, and the flipped
  tests are deliberate, one per enforcement site.

## User Personas & Scenarios

- **Persona D (biotech researcher)** and **A (lone computational biologist)**:
  reproducing a paper whose headline number sits in a two-key table row.
- Scenario: a paper claims "TP53 log2 fold change = 2.3 in treated"; the repo's
  `de.tsv` has columns gene, condition, log2FoldChange. Today the claim cannot
  be written. With this slice:
  `{"from": "de.tsv", "column": "log2FoldChange", "row": {"gene": "TP53",
  "condition": "treated"}, "header": true}` binds the cell and yields a verdict.

## Requirements

### Must-have

1. `load_claims` accepts a row object with **one or more** string keys
   (`len(raw_row) >= 1`); empty object still refused. Widened error message:
   "expected one or more keys" (currently "exactly one key"). Key/value type
   guards unchanged (non-str/empty key, non-str/bool value refused;
   `reproduce.py:754-761`).
2. `resolve_cell` matches a row iff **all** key-value predicates hold on that
   row (AND of exact, `.strip()`ed string equalities — the existing single-key
   compare semantics, `reproduce.py:333-335`, extended per key). Missing
   column, duplicate header name, or header:false + dict row stay unresolved /
   refused exactly as today.
3. 0 or >1 matched rows → `(None, "row {row!r} matched N rows")` —
   UNVERIFIED naming the count; strict exactly-one preserved
   (`reproduce.py:337-340`, `resolve_match` precedent 407-409).
4. Never-raises preserved for all inputs (the wild-input contract,
   `test_reproduce_tsv_locator.py:185`); multi-key moves from *invalid wild
   input* to *valid shape* in that test.
5. Tests: one deliberate flip per enforcement site —
   `test_load_claims_rejects_row_multi_key_object` becomes an accept test;
   new multi-key resolve tests (hit, 0 rows, 2 rows, absent column, duplicate
   header, ragged row); engine-level test through `run_reproduction`
   (multi-key → reproduced; multi-key ambiguous → unverified naming count).

### Should-have

6. Help text for `contig reproduce`'s `--claims` table example
   (`cli.py:1092-1095`) mentions that `row` may carry multiple keys.

### Nice-to-have

7. A second frozen `reproduce_scenarios.jsonl` scenario exercising a multi-key
   row — **only if** it adds family coverage without touching the baseline's
   corpus sha (this would refreeze the baseline deliberately; default: skip).
8. A manual real-repo smoke following the C8 evidence-gate tradition
   (match-and-propose precedent: 6/20 binds on
   `ritvikK05/rnaseq-reanalysis-htt`): one cooperative published repo whose
   output presents the unique-key 2-D shape, one multi-key claim, `contig
   reproduce` run and recorded — honest push-not-demand-pull, skipped if no
   such repo is in hand.

## Targeted table shape (explicit)

This slice targets **unique-key 2-D tables**: DESeq2/edgeR gene×condition
tables, VCF-like chr×pos tables — where the key pair identifies exactly one
row. Tables with repeating keys (feature × sample with duplicated features)
will bind >1 rows and stay UNVERIFIED by the strict exactly-one rule; that is
accepted and recoverable (author reshapes the table), not a defect.

## Technical Considerations

- **Two enforcement sites only**: `load_claims` (load-time `ClaimsError`,
  `reproduce.py:748-752`) and `resolve_cell` (runtime `(None, reason)`,
  `reproduce.py:318-340`). No dispatch change: the isinstance chain
  (`reproduce.py:1344-1355`) and `claim_family` (`reproduce_guard.py:91-92`,
  family stays `"table"`) are shape-agnostic.
- **Freshness guard untouched**: `_require_fresh` runs before parse and before
  the per-run `_table_cache` (`reproduce.py:1011-1019`); a widened row shape
  never weakens it.
- **Inference stays single-key by design**: the sweep emits only int rows
  (`locator_inference.py:90,759,787`); the matcher carries them verbatim
  (`locator_match.py:291-308`); `_locator_for` has no dict-row path. No change
  to the sweep/matcher/CLI; the `load_claims` round-trip gate
  (`cli.py:1884-1904`) continues to validate whatever the CLI writes.
- **Back-compat**: single-key dict rows keep working; the frozen
  `table-locator` scenario (`reproduce_scenarios.jsonl:6`) stays loadable and
  `within_tolerance`; `reproduce_baseline.json` (16/17, table 1/1) unmoved.
- Stack: stdlib only (`csv`, `gzip`); no new dependencies; no network; no real
  repo/tool in CI. Pure local file parsing with `tmp_path` fixtures — the
  established C8 slice discipline.
- Values stay strings; "5" ≠ "5.0" (no numeric coercion — see Out of Scope).

## Risks & Open Questions

- **Ambiguity is the rule, not the edge**: real tables with duplicated keys
  (e.g. multiple rows per gene) will bind >1 rows and degrade to UNVERIFIED —
  honest, recoverable, never a false pass. No fudge tolerance will be added.
- JSON object keys are always `str` after `json.loads`, so the non-string-key
  guard at `reproduce.py:754` remains defensive/dead under JSON input (already
  documented in task-1-report.md:75-81); the empty-key guard is the reachable
  analogue.
- No demand-pull: this is roadmap-pull (recorded deferral), not a design-partner
  ask. Accepting that per the contig-next ranking.

## Out of Scope

- Numeric comparison predicates (>, <), regex row predicates — the separately
  deferred "regex/numeric row predicates" (CAPABILITY_ROADMAP.md:1874,1968);
  they mostly violate the strict exactly-one rule in real tables.
- Column ranges (`column: [a, b]`).
- Numeric-coercion equality ("5" == 5, "1.0" == 1).
- Widening locator **inference** to propose multi-key rows.
- The notebook locator's parallel `{"contains": s}` contract
  (`reproduce.py:218`) — untouched.
- Any change to the freshness guard, `classify`, DIVERGED semantics, or the
  reproduce-guard baseline.

## Data Model / Artifact Contract

`TableLocator.row` type stays `int | dict[str, str]` (`reproduce.py:170-185`);
the invariant moves from "exactly one key" to "one or more keys" (enforced at
`load_claims` and re-checked defensively in `resolve_cell`). Claim JSON shape
unchanged: `"row": {"colA": x, "colB": y}`.

## Non-Functional Requirements

- Suite green at every commit (`uv run pytest`); `reproduce-guard` (CI
  `.github/workflows/ci.yml:35`) passes with the committed baseline.
- No signature change to `RunRecord`/`ReproduceRecord`; no bundle-format change;
  signed bundles unaffected.
- Performance: multi-key adds per-row key comparisons only within the already
  parsed, cached table (`_table_cache`, parse-once pinned).

## Aspect Decomposition

Single aspect: `multi-key-rows` — the whole slice is the two enforcement sites
plus their tests. `spec.md` in `docs/planning/table-locator-predicates/multi-key-rows/`.