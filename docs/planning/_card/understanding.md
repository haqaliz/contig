# Phase 2 — Understanding: reproduce-tsv-csv-locator (C8 slice 3)

## What the work is really asking

Extend `contig reproduce`'s claim output-locator (slice 1.5, JSON-only) so a claim can
bind its observed number from a **cell in the repo's own tabular output** (`.tsv`/`.csv`).
This is the "named next step" both shipped locator slices deferred
(`CAPABILITY_ROADMAP.md:1093,1122`; `reproduce-output-locator/prd.md:121`). Rationale:
real bioinformatics repos emit their numbers in tables (DESeq2 results, count matrices,
stats tables) far more than in structured JSON — JSON-only is a weak locator for this
domain.

## Affected code (precise seams — from the Phase-2 code map)

All in `src/contig/verification/reproduce.py` + `src/contig/cli.py`; **no `models.py`
change** (a located claim records only the resolved observed number, which is
locator-agnostic).

1. **`Locator` dataclass** (`reproduce.py:139-150`) — the typed carrier `(source, path)`.
   A table locator either extends this or adds a parallel dataclass; `Claim.locator`'s
   type widens (`reproduce.py:165`).
2. **`load_claims` hand-rolled validation** (`reproduce.py:210-222`) — the *one* schema
   spot. The new table shape (row/column/etc.) is parsed & validated here; keep it
   repo-agnostic (structural only). Existing rule: `from` and `path` both-or-neither.
3. **`run_reproduction` branch** (`reproduce.py:457-544`) — routes `claim.locator is not
   None` today. Add a sibling reader to `_observe_located` (`:315-362`) that reads the
   table via stdlib `csv` and returns `(float | None, message)`. The surrounding branch,
   the per-file parse **cache** (`_json_cache`, `:313`/`:327-339`), and the engine
   containment guard (`:321-325`) stay identical in shape.
4. **CLI containment pre-check** (`cli.py:800-816`) — refuses an escaping/absolute
   `from` **before any run** (exit 1, no record), reusing `resolved.relative_to(repo_root)`
   in try/except. If the table locator reuses `Locator.source` for its path, it's already
   covered; a new path-field name would need adding to this loop.

## Inherited honesty contract (non-negotiable — slice 1.5)

- The numeric guard is inline & duplicated (no named helper), pattern:
  `isinstance(x, bool) or not isinstance(x, (int, float))`, then `math.isnan/isinf`.
  A cell is a **string**, so the table branch must `float()`-parse then apply the nan/inf
  reject — a **numeric string is the normal case for a cell**, so "strictly UNVERIFIED on
  numeric string" (the JSON rule) **cannot** transfer verbatim; the table branch's
  contract is "parse the cell as a float; unparseable → UNVERIFIED." This is the one
  contract that legitimately differs from JSON and must be stated explicitly.
- Every unresolved / out-of-range / unparseable address → **UNVERIFIED**, never
  `DIVERGED`, never a false reproduce. bool/non-finite excluded.
- Escaping `from` refused pre-run (CLI) + defensive UNVERIFIED if it reaches the engine.
- Models / verdict / bundle / signing / `--fail-on-diverged` all reused unchanged;
  `claims_sha256` already covers the new locator keys (they're claims-file bytes).

## The design fork to resolve in the interview (Phase 3)

1. **Locator shape / discriminator.** `path` (JSON) vs new `row`+`column` (table) as the
   discriminator, vs an explicit `kind`/`format` field.
2. **Column selection** — header name (str), positional index (int), or both.
3. **Row selection** — key-column match (`{"gene_id": "ENSG…"}`), positional index (int),
   or both. (Key-match is the compelling DESeq2 case.)
4. **Delimiter** — infer from extension (`.tsv`→tab, `.csv`→comma), `csv.Sniffer`, or
   explicit `delimiter`.
5. **Scope extras** — headerless files? **gzip-transparency** (`.tsv.gz`/`.csv.gz`)?
   Slice 1.5 explicitly punted gzip "revisit with TSV" (`reproduce-output-locator/prd.md:134`);
   bioinformatics tables are frequently gzipped, so this is a real question.
6. **Ambiguity handling** — a row-key match that hits 0 rows or >1 rows → UNVERIFIED
   (omit-never-guess), never an arbitrary pick.

## Guardrail check (`CLAUDE.md`)

Layer 2 (a resolver over verify output) ✅ · moat = verification/reproducibility infra +
corpus ✅ · stdlib-only, founder's edge ✅ · no raw-read egress (repo-relative,
escape-guarded) ✅ · test-first ✅. No Layer-1 drift.

## Contradictions / flags

- None between brief and code. The brief's "numeric-string strictly UNVERIFIED" line
  (inherited from JSON) must be **re-scoped** for tables: a cell is a string by nature, so
  the rule becomes "float-parse the cell; unparseable → UNVERIFIED." Flagged above; will
  be explicit in the PRD so it isn't mistaken for the JSON rule.
