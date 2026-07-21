# Phase-2 dig — reproduce-stdout-log-locator (C8 slice 4)

Verified against code at `feat/reproduce-stdout-log-locator/aliz` (branched from `origin/master`,
v0.43.0). Baseline suite: **1829 passed, 1 skipped** (`uv run pytest`).

## What the work is really asking

Add a **third claim-locator addressing mode** to `contig reproduce`: bind a claim's observed value
by **regex capture** over (a) the run's captured combined stdout+stderr, and/or (b) a repo-relative
log/text file. Sibling of the shipped JSON `path` locator (slice 1.5) and TSV/CSV `column/row`
locator (slice 3).

## Affected areas (exact)

`src/contig/verification/reproduce.py` (905 lines) is where ~all the change lands, plus a small
`cli.py` edit and tests. Nothing in `models.py`.

| Site | Lines | What changes |
|---|---|---|
| Module regex constants | 39-44 | a new compiled constant may sit alongside `_MISSING_MODULE_RE` |
| `Locator` (frozen dc) | 142-152 | untouched |
| `TableLocator` (frozen dc) | 155-171 | untouched |
| `Claim.locator` union | 320-335 | widen `Locator \| TableLocator \| None` → `+ PatternLocator` |
| `load_claims` presence probes | 380-386 | add `has_pattern` (+ any siblings) |
| `load_claims` orphan guard | 388-392 | **must be relaxed** — a stdout locator has *no* `from` |
| `load_claims` xor check | 400-404 | becomes a **three-way** mutual exclusion |
| `load_claims` dispatch chain | 406-499 | new `elif has_pattern:` arm building the locator |
| `run_reproduction` setup | 588-591 | possibly a third cache (`_text_cache`) for file-backed mode |
| nested `_observe_located` | 593-640 | untouched (JSON) |
| nested `_observe_table_located` | 642-685 | untouched (table) |
| **new** nested `_observe_pattern_located` | after 685 | sibling observer |
| per-claim dispatch head | 780-785 | add an explicit `elif isinstance(...)` arm |
| `cli.py` containment loop | 805-821 | must skip a `source`-less (stdout) locator |
| `cli.py` reproduce docstring | 753-757 | help note (S2-style) |

## Load-bearing facts found in the code

1. **The input is already there and unused.** The executor seam is
   `Callable[[list[str], Path], tuple[int, str]]` (`reproduce.py:559`). `run_output` is bound at
   `:687`, rebound by the retry at `:721`, and read in exactly two places — `detect_missing_module`
   (`:691`) and `Diagnosis.evidence=[run_output[:500]]` (`:696`). Nothing else consumes it.
2. **Closures make "which run's output" free.** Both observers are **nested functions** inside
   `run_reproduction` (not top-level). Python closures capture the *variable*, not the value, and
   every observer call happens at `:783/:785` — well after the retry rebind at `:721`. So a nested
   pattern observer referencing `run_output` automatically sees the **retried** run's output. No
   restructuring needed; caveat #3 from the card is answered by the code's existing shape. It must
   still be stated in the docstring, since it is the one observable asymmetry vs file locators
   (which are also read after the last run, so both agree).
3. **A failed run never reaches any locator.** `:745-767` short-circuits every claim to
   `unverified` (`"run did not complete (exit N)"`) and returns before the dispatch loop. So a
   stdout locator can only ever read the output of a **successful** run. A real scope limit worth
   naming honestly: this does *not* scrape numbers out of a crashed run.
4. **`.source` is the internal name for the claims-file key `from`** (`from` is a Python keyword).
   Both existing locators declare `source: str` first. The CLI containment loop (`cli.py:811-821`)
   and both engine guards do `(repo_path / loc.source).resolve()` **unconditionally**.
   ⇒ **A stdout locator has no file, so `source` must be optional, and all three call sites must
   short-circuit before the path join.** This is the single most likely place to introduce a crash
   or a containment hole. `cli.py:812` currently reads `if claim.locator is None: continue` — it
   needs `or claim.locator.source is None`.
5. **The dispatch `else` is an unguarded fallback**, not an isinstance test:
   ```python
   if isinstance(claim.locator, TableLocator): ... else: _observe_located(claim.locator)
   ```
   Adding a third type **without** touching `:780-785` would silently route it into the JSON reader
   and raise `AttributeError` on the missing `.path`. Must become explicit.
6. **The observers' contract** is `tuple[float | None, str]` — `(value, "")` on success,
   `(None, reason)` on failure; the reason is passed through *unwrapped* into
   `ClaimResult.message` (`:795`), so each message must be self-describing (all existing ones begin
   `locator ...` and name the source).
7. **The pure-resolver idiom** to mirror: a top-level, never-raising
   `resolve_pointer(data, expr) -> object | None` /
   `resolve_cell(rows, column, row, header) -> tuple[str | None, str]`. A pattern sibling would be
   `resolve_match(text, pattern, ...) -> tuple[str | None, str]` returning the raw captured
   **string**.
8. **The numeric-string rule follows slice 3, not slice 1.5.** A regex capture is a string by
   construction, exactly like a table cell — so it is `float()`-parsed after `.strip()`, then
   finite-guarded. The JSON locator's "a numeric string is strictly UNVERIFIED" rule does **not**
   transfer. (Precedent + rationale: the `_observe_table_located` docstring, `:650-654`.)
9. **Output is never persisted.** `ReproduceRecord` (`models.py:662-678`) has no stdout/log field;
   the only surviving text is `run_output[:500]` in `Diagnosis.evidence`, and only when the
   install/retry branch fired. Making the matched output auditable would be a `models.py` change —
   out of scope unless deliberately chosen.
10. **Ambiguity precedent already exists.** `resolve_cell` returns `f"row {row!r} matched 0 rows"` /
    `matched {n} rows` (`:290-292`) and `column {c!r} is ambiguous: {n} header matches`
    (`:257-259`). The 0-or-many rule for regex matches should reuse that exact wording shape.
11. **Doc surfaces for a shipped slice** (from `git show --stat` on the slice-3 commits): only
    `CHANGELOG.md`, `docs/technical/CAPABILITY_ROADMAP.md` (C8), and `docs/planning/**`. Slice 3
    touched **no** README/FEATURES/USAGE — the reproduce surface is documented in the CLI docstring
    (`cli.py:745-757`).

## Ambiguities / open questions for the interview

- **Q1 — How is "the run's output" addressed vs a log file?** Options: `from` absent ⇒ stdout
  (implicit), or an explicit `"stream": "stdout"` / `"from": "-"` sentinel. Affects the
  `load_claims` orphan guard (fact #4) and readability.
- **Q2 — Which capture is the value?** Group 1 by default when the pattern has groups, whole match
  otherwise? Or require an explicit `group` (int or name)? Named groups (`(?P<v>…)`) are a
  self-documenting third option.
- **Q3 — Multiple matches.** Strict 0-or-many ⇒ UNVERIFIED (the shipped precedent, fact #10), or
  an `occurrence: first|last` selector? Progress logs legitimately print the same line many times,
  so strictness may reject common real cases — but a selector is a guess-shaped foot-gun.
- **Q4 — Regex safety framing.** A user-supplied pattern is a ReDoS surface, but `--run` already
  executes an **arbitrary command** from the same trust domain (`cli.py:716`), so a regex is
  strictly *less* dangerous than what the same invocation already authorizes. Proposal:
  compile-validate in `load_claims` (bad pattern ⇒ `ClaimsError`, pre-run, nothing written) + cap
  the matched text length; do **not** attempt a regex timeout (impossible stdlib-only).
- **Q5 — Multiline/flags.** Are `re.MULTILINE`/`re.IGNORECASE` exposed as claim fields, or is the
  pattern trusted to carry inline flags (`(?im)`)? Inline flags need no schema surface at all.

## Guardrail check (`CLAUDE.md`)

Layer 2 only (a resolver over verify output; never NL→workflow, never a conclusions verdict) ✅ ·
Moat = verification/reproducibility infra + corpus ✅ · Stdlib-only holds (`re` already imported)
✅ · No raw-data egress (a file-backed pattern reuses the containment guard; the stdout variant
reads only in-memory output Contig itself produced) ✅ · Test-first ✅.

## Contradictions with the card brief

None material. One correction: the card's caveat #3 ("under `--allow-install` the bound output must
be the RETRIED run's") is **already satisfied by the closure shape** (fact #2) rather than needing
new work — it becomes a test + a docstring sentence, not a mechanism.
