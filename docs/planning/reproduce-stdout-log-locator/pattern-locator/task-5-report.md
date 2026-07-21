# Task 5 report — Phase 5: tightening, message audit, refactor check, docs (C8 slice 4)

Date: 2026-07-21 · Feature: `reproduce-stdout-log-locator` (C8 slice 4) · Phase: 5 of 5
(one small behavior change under strict TDD, plus documentation).

## Scope

Four pieces, per the plan's Phase 5 and the "Tightening carried over from Phase 1" bullet:

- **(A)** the Phase-1 tightening — `pattern` + any table field is now a `ClaimsError` (behavior
  change, TDD);
- **(B)** an S1 message-wording audit of every UNVERIFIED message the pattern path can emit;
- **(C)** a REFACTOR check on the triplicated finite-float parse (**decision: do not extract**);
- **(D)** `CHANGELOG.md` + `docs/technical/CAPABILITY_ROADMAP.md` §C8 + this report.

## (A) `pattern` + any table field is rejected — RED first

Before this phase, `{"pattern": "…", "header": false}` and `{"pattern": "…", "delimiter": ";"}`
were **accepted with the table keys silently ignored**: the three-way exclusion in `load_claims`
only covered `path` and `column`/`row`, and the relaxed orphan guard let the `from`-less form
through as well. Silent-ignore contradicts the "never a silent misread" ethos every other locator
holds (the slice-3 `header: false` + `row`-object contradiction is a load-time error, not a
guess), so the **preferred** option in the plan was implemented: reject `pattern` together with
**any** of `column`, `row`, `header`, `delimiter`.

Four failing tests were added first to the slice-4 `load_claims` section of
`tests/test_reproduce.py` (`…rejects_pattern_with_table_only_field_with_from` and
`…_without_from`, each parametrized over `("header", False)` and `("delimiter", ";")`). RED:

```
FAILED tests/test_reproduce.py::test_load_claims_rejects_pattern_with_table_only_field_with_from[header-False]
FAILED tests/test_reproduce.py::test_load_claims_rejects_pattern_with_table_only_field_with_from[delimiter-;]
FAILED tests/test_reproduce.py::test_load_claims_rejects_pattern_with_table_only_field_without_from[header-False]
FAILED tests/test_reproduce.py::test_load_claims_rejects_pattern_with_table_only_field_without_from[delimiter-;]
E       Failed: DID NOT RAISE ClaimsError
```

GREEN was a one-line widening of the pattern branch's guard from `if has_column or has_row:` to
`if has_table_field:` (the probe already computed `has_table_field = has_column or has_row or
has_delimiter or has_header`), with the message extended to say *why*:
`"claim 'x' must set 'column'+'row' or 'pattern', not both (a table field has no meaning for a
pattern locator)"`. The existing `pattern`+`path` and `pattern`+`column`/`row` rejections and the
orphan-guard tests are unchanged and still pass.

## (B) S1 message audit

Every UNVERIFIED message the pattern path can emit was read against PRD S1 and against its
siblings in `_observe_table_located`. The composed messages already name **why** in each case:

| Failure | Message |
|---|---|
| 0 / N matches | `locator pattern in 'logs/train.log' did not resolve: pattern '…' matched 4 times` |
| non-participating group | `… did not resolve: pattern '…' capture group did not participate in the match` |
| missing / dir / non-UTF-8 file | `locator file 'logs/train.log' is missing or unreadable` |
| escaping `from` | `locator 'from' '../secret.log' escapes the repo` |
| unparseable capture | `locator capture 'NA' in the run output is not a finite number` |
| non-finite capture | `locator capture 'inf' in the run output is not finite: inf` |
| oversize (stdout) | `locator pattern in the run output did not resolve: text is N chars, over the 8388608-char match limit` |
| oversize (file) | `locator file 'logs/train.log' is N bytes, over the 8388608-byte match limit` |

Two conclusions:

- The Phase-3 choice of the noun **`capture`** (over the table reader's `cell`) is correct and was
  kept — the shape `locator <noun> {value!r} in {where} …` is identical to the table sibling, and
  `where` is either `repr(source)` or the literal `the run output`, which is what makes the
  stdout mode readable. No churn there.
- **One genuine gap:** both oversize messages ended in `over the 8388608 limit` — a **unit-less**
  bound that does not say what it limits, where S1's example reads `over the 8 MiB match limit`.
  Changed to `over the {_MAX_MATCH_BYTES}-char match limit` (resolver, which counts characters)
  and `over the {_MAX_MATCH_BYTES}-byte match limit` (file mode, which `stat()`s bytes). The
  existing tests assert `str(_MAX_MATCH_BYTES) in reason`, which still holds; no test needed
  updating. Nothing else was reworded.

## (C) REFACTOR check — **decision: do not extract**

The plan asked whether the finite-float parse is now triplicated across `_observe_located`,
`_observe_table_located` and `_observe_pattern_located`. On inspection it is **not**: it is
duplicated **twice**, not three times.

- `_observe_located` (JSON) does **not** do `float(x)` in a `try/except`. It applies the strict
  slice-1.5 rule — an `isinstance(target, (int, float))` check that deliberately rejects a numeric
  *string* — and only then `math.isnan/isinf`. Its parse path is a different rule, not the same
  code; folding it into a shared helper would either change JSON behavior or force the helper to
  carry a mode flag.
- The two that do share the shape (`_observe_table_located`, `_observe_pattern_located`) differ in
  the noun (`cell` vs `capture`), in the `where` term (`loc.source!r` always vs `loc.source!r`
  **or** `"the run output"`), and in the input (`float(cell)` vs `float(captured.strip())`).

A shared helper would therefore have to take the value, a noun, and a where-string, and return a
`(float | None, str)` — replacing ~10 lines at two call sites with a parameterized message
template. That trades two obvious, locally-readable blocks for one indirection whose whole purpose
is to interpolate a noun, and it would make the three observers' deliberately *different* rules
harder to see side by side. **Left as-is, deliberately.** No behavior changed.

## (D) Docs

- `CHANGELOG.md` — a new `### Added` entry under `## [Unreleased]`, in the detailed voice of the
  0.43.0 TSV/CSV entry directly below it: the two addressing modes; group-1-else-whole-match and
  inline flags; strict 0-or-many with the count named; the non-participating-group guard; the
  8 MiB bound with its honest framing (a ReDoS **input** bound, **not** a memory guard —
  `default_command_executor` already buffers all output uncapped through `subprocess.PIPE`, a
  pre-existing upstream issue this slice neither creates nor solves); the retried-run binding under
  `--allow-install` (free via the observer closure, no new mechanism); the numeric-string rule
  following slice 3 rather than slice 1.5; the three-way exclusion including the new table-field
  rejection; containment reuse plus the `source is None` CLI skip; stdlib-only with no `models.py`
  change; and the honest limits (a FAILED run never reaches any locator, so this reads **successful
  runs only**; a regex binds to output formatting, making it the **weakest locator shipped** — a
  non-match is UNVERIFIED, never DIVERGED). The slice-3 entry's "No stdout/log scraping…" line was
  **not** rewritten — history is immutable; the new entry supersedes it.
- `docs/technical/CAPABILITY_ROADMAP.md` §C8 — three edits, exactly as slice 3 did:
  1. the `## C8.` heading line gained `+ stdout/log pattern-locator slice 4 SHIPPED (Unreleased)`;
  2. a new `**Shipped (stdout/log pattern locator — slice 4, Unreleased).**` paragraph after the
     slice-3 one, **and** the removal of `stdout/log scraping` from the slice-3 paragraph's
     `**Deferred:**` list (every other item in that list left intact);
  3. the C8 row of the "Sequencing summary" table — both the status cell (`+ stdout/log
     pattern-locator slice 4 SHIPPED (Unreleased)`) and the `**Shipped:** … **Deferred:** …` cell
     (a new `**+ stdout/log pattern locator (slice 4):**` sentence; `stdout/log scraping` removed
     from the deferred list, `occurrence`/`group` selectors added to it).
  `git grep "stdout/log scraping" -- docs/` (excluding `docs/planning/`) returns **no matches**.
- This report.

## Verify

- Full suite after all four pieces:
  ```
  1895 passed, 1 skipped in 13.41s
  ```
  Phase-4 baseline was 1891 passed, 1 skipped; the +4 are the (A) parametrized rejections. The
  pre-slice baseline was 1829.
- `uv.lock` was dirtied by `uv run` and reverted (`git checkout uv.lock`), per the slice's
  standing note.
- `pyproject.toml` and the package version were not touched (release is a separate step per
  `RELEASING.md`).

## Concerns

None blocking. Two things worth recording:

- **(A) is a real, if narrow, back-compat break.** A claims file that carried a stray `header` or
  `delimiter` alongside a `pattern` previously loaded and now exits non-zero. Since `pattern` ships
  for the first time in this same unreleased slice, no released claims file can contain that shape,
  so the break is unreachable in practice.
- **The 8 MiB cap is asymmetric by nature** (a genuine read bound in file mode, only a match-input
  bound in stdout mode). Both the CHANGELOG and the roadmap now say so explicitly, so the limit is
  not later removed as "pointless" — that framing is the honest half of the guard.
