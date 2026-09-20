# Spec — aspect `candidate-sweep`

Parent PRD: [`../prd.md`](../prd.md). Aspect 1 of 3. Feeds aspect 2 (`match-and-propose`).

---

## Problem slice

Before anything can be matched, we need to know **what numbers exist in a repo and exactly
where they live** — expressed as coordinates the *shipped* resolvers can re-resolve. This
aspect is the pure, never-raises sweep: walk a repo, enumerate every numeric value in every
candidate artifact, and emit a coordinate for each. **No matching. No claims. No CLI.**

User outcome: none directly — this is the substrate. Its value is that aspect 2 can be a pure
function over its output, and the evidence gate can be run without a CLI.

## In scope

- **R1 — Safe walk.** `iter_artifacts(repo)` yields candidate artifact paths.
  `os.walk(followlinks=False)`, prune any directory component named `.git` at any depth, skip
  symlinked files and directories. Mirrors `compute_tree_sha256`'s published discipline.
- **R2 — Extension filter.** `.json`, `.tsv`, `.csv`, `.tsv.gz`, `.csv.gz` only. Deterministic
  ordering (sorted by POSIX-relative path) so a sweep is reproducible.
- **R3 — Size bound.** An artifact larger than `_MAX_MATCH_BYTES` (8 MiB, `reproduce.py:52`)
  is an honest skip naming the size, never a truncated read.
- **R4 — JSON enumeration.** For each `.json`, yield one candidate per **numeric leaf**, with
  a `path` expression that `resolve_pointer` (`reproduce.py:129`) re-resolves to that value.
- **R5 — Table enumeration.** For each `.tsv`/`.csv`(`.gz`), yield one candidate per **numeric
  cell**, with `column`/`row`/`header` that `resolve_cell` (`reproduce.py:263`) re-resolves.
- **R6 — Honest skips.** Every unreadable / malformed / oversized / unparseable artifact
  produces a `SweepSkip(source, reason)`. Never raises, never aborts the sweep.
- **R7 — Reuse, never reimplement.** Table reading goes through `reproduce._read_table`;
  path resolution is validated against the unchanged `resolve_pointer` / `resolve_cell`.

## Out of scope (aspect 2 or later)

- Matching a candidate to a claim value; rounding; the `÷100` scale attempt; the exactly-one
  rule; low-information refusal (PRD M9). **All of that is aspect 2.**
- Locator *construction* (building `Locator`/`TableLocator` objects) and `load_claims`
  round-tripping — aspect 2 and 3.
- The CLI, the sidecar, `--force`/`--dry-run` — aspect 3.
- `pattern`/notebook artifacts (`.ipynb`, `.log`, `.txt`) — deferred at PRD level.

## Key design decisions

**D1 — JSON path expressions must be expressible in `_parse_path`'s grammar**
(`reproduce.py:78`): one optional leading `$`, one optional leading `.`, bare key in first
position, `[n]` inner text must pass `.isdecimal()`. A dict key containing `.` or `[` **cannot
be expressed** and is skipped with a reason — never emitted as a path that would silently
resolve elsewhere. This is a real, disclosed coverage hole, not an oversight.

**D2 — Header detection is deterministic and conservative.** A table's first row is treated as
a header **iff no cell in it parses as a float**. Otherwise headerless (`header=False`, integer
column indices). Rationale: real bioinformatics outputs (DESeq2, count matrices, feature
tables) carry text headers, and a numeric first cell almost always means data. This is an
**uncalibrated engineering default** and is named as such. Note the asymmetry it creates:
`header=True` yields a **column name**, `header=False` yields an **integer index**, and in
header mode `row` indexes **data rows only** (`rows[1:]`, `reproduce.py:263`).

**D3 — Delimiter is left implicit.** `load_claims` infers it from the extension and only
requires an explicit `delimiter` for an unrecognized one (`reproduce.py:778`). We emit only
recognized extensions, so we never set `delimiter` — which also keeps us clear of the
"`delimiter` alone counts as a table field" trap (`reproduce.py:703`).

**D4 — `bool` is not a number.** JSON `true`/`false` are `bool`, which is an `int` in Python.
Mirror the repo-wide idiom (`isinstance(x, int) and not isinstance(x, bool)`) and never emit a
bool as a numeric candidate. Non-finite floats (`nan`/`inf`) are likewise never candidates.

**D5 — Numeric strings in tables are candidates; numeric strings in JSON are not.** This
mirrors the shipped asymmetry exactly: a table cell is always a string and parsing it is the
caller's job (slice 3's rule), whereas a JSON numeric *string* is strictly UNVERIFIED at
reproduce time (slice 1.5's rule). Emitting a JSON string candidate would propose a locator
that can never verify.

## Acceptance criteria (testable)

- **A1** `iter_artifacts` skips `.git` at any depth, skips symlinked files and dirs, and
  returns paths sorted by POSIX relative path.
- **A2** An 8 MiB+ artifact yields a `SweepSkip` naming the size and **no** candidates.
- **A3** For every JSON candidate, `resolve_pointer(json.loads(text), cand.path)` returns a
  value equal to `cand.value`. **Round-trip pin — the test that proves reuse.**
- **A4** For every table candidate, `resolve_cell(rows, cand.column, cand.row, cand.header)`
  returns a string that floats to `cand.value`. **Round-trip pin.**
- **A5** Nested dicts, lists, and lists-of-dicts all enumerate; `[n]` indices resolve.
- **A6** A dict key containing `.` or `[` is skipped with a reason, not emitted.
- **A7** `true`/`false`/`null`/`nan`/`inf` are never candidates; a JSON numeric *string* is
  never a candidate; a numeric table cell as a string **is** one.
- **A8** A header-ful table yields string column names and data-row-relative row indices; a
  headerless table yields integer column indices.
- **A9** Malformed JSON, a ragged CSV, a corrupt `.gz`, and an unreadable file each yield a
  `SweepSkip` and never raise.
- **A10** Never-raises is asserted against wild inputs (the `test_claim_extraction.py:187`
  discipline).
- **A11** The full suite stays green; no shipped file is modified in this aspect.

## Dependencies & sequencing

- Depends on nothing unshipped. Reads `reproduce._read_table`, `resolve_pointer`,
  `resolve_cell` — all shipped and unchanged.
- **Blocks** aspect 2 (`match-and-propose`), which is a pure function over `Candidate`.
- Aspect 2 then feeds the **⛔ evidence gate** in the PRD; aspect 3 is gated on it.

## Risks specific to this aspect

- **Candidate explosion.** A large count matrix is *n×m* candidates. Aspect 2's matcher must
  not be O(candidates × claims) in a pathological way, and memory could matter. Mitigation:
  yield lazily (a generator), let aspect 2 index by value.
- **D2 header misdetection** silently shifts every row index for that file by one. A1/A8 pin
  the rule; the real-repo gate is where a wrong guess would surface.
- **Float equality in round-trip pins** (A3/A4) — compare exactly for values that survive a
  JSON round-trip, and use the parsed float rather than the printed token.
