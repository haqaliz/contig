# PRD — stdout/log pattern locator for `contig reproduce` (C8 slice 4)

**Slug:** `reproduce-stdout-log-locator`
**Branch:** `feat/reproduce-stdout-log-locator/aliz`
**Capability:** C8 (`docs/technical/CAPABILITY_ROADMAP.md` §C8) — the "stdout/log scraping" deferral
named in the slice-3 **Deferred** list and in the CHANGELOG slice-3 entry ("No stdout/log
scraping, no notebook (`.ipynb`) numeric extraction").
**Parent PRDs:** slice 1 `reproduce-published-work/prd.md` · slice 1.5
`reproduce-output-locator/prd.md` · slice 2 `reproduce-env-resurrection/prd.md` · slice 3
`reproduce-tsv-csv-locator/prd.md`.
**Status:** Interview complete (4 shaping decisions locked via AskUserQuestion). Pending
prd-generator critique + review-gate approval.

---

## Problem Statement

`contig reproduce` can bind a claim's observed value from a flat `results.json` (slice 1), a
**JSON** locator (slice 1.5), or a **TSV/CSV cell** (slice 3). All three require the repo to write
its numbers into a **structured file**. A large share of published analysis scripts do not: they
`print()` the headline number, or append it to a `.log`, and write no JSON and no table at all.
Against those repos every claim degrades to `UNVERIFIED` today — honest, but a dead end.

The engine already *has* the text. The slice-2 executor seam returns `(exit_code, output)`
(`reproduce.py:559`) and `run_output` is bound at `:687` / rebound by the retry at `:721`, but it
is read in only two places: `detect_missing_module` (`:691`) and
`Diagnosis.evidence=[run_output[:500]]` (`:696`). Nothing binds claims from it. This slice makes
that captured output a **third locator addressing mode**: a regex whose capture is the observed
value, over the run's combined stdout+stderr, or over a repo-relative log/text file.

**Evidence it's real:** the C8 reproducibility numbers (~3.2% of 27,271 biomedical notebooks
reproduce; ~4% in Pimentel's 1.4M-notebook study; 21% best agent score on CORE-Bench —
`CAPABILITY_ROADMAP.md` §C8); both the roadmap's C8 deferred list and the slice-3 CHANGELOG entry
name stdout/log scraping explicitly as the next unblocked step; of C8's remaining deferrals it is
the only one with **no** feasibility blocker (figure/plot claims are hard-blocked — no plot-hash,
and adding perceptual hashing would break the stdlib-only dependency contract; paper-parsing needs
its own parser design; remote `<doi|url>` needs network). On-thesis Layer 2 (a resolver over
verify output; never NL→workflow, never a conclusions verdict).

**Honest counter-argument, recorded up front:** a regex over free-text output is the **weakest**
locator we will have shipped. It binds to a formatting accident, not to a data structure — a repo
that changes `print(f"AUC={x}")` to `print(f"AUC: {x}")` breaks the claim. The mitigation is not
cleverness but honesty: a non-matching pattern is `UNVERIFIED` naming the match count, never
`DIVERGED`, so a formatting drift can never be misread as a failed reproduction.

## Goals & Success Metrics

- **G1 — A claim can bind its value from the run's stdout.** A claim carrying `pattern` (and no
  `from`) binds its observed number from the run's captured combined output and classifies with
  the existing verdict. *Measured:* an engine + CLI test where the scripted executor emits
  `AUC = 0.91` on stdout and writes **no** results file yields
  `REPRODUCED`/`WITHIN-TOLERANCE`/`DIVERGED` per claim.
- **G2 — A claim can bind its value from a repo-relative log file.** The same `pattern` with
  `from: "logs/train.log"` reads that file. *Measured:* engine + CLI tests over an on-disk fixture
  log in `tmp_path`.
- **G3 — Ambiguity is never guessed.** A pattern matching **0 or >1** times is `UNVERIFIED` with
  the count named in the message — never an arbitrary first-match pick. *Measured:* dedicated
  0-match and N-match tests assert `unverified` **and** the count in the message.
- **G4 — No false reproduce, ever.** Every unresolved / unparseable / non-finite / oversized /
  containment-refused address is `UNVERIFIED`, never `DIVERGED`. *Measured:* one test per failure
  mode.
- **G5 — A malformed pattern is refused pre-run.** An uncompilable regex is a `ClaimsError` at
  load time: exit non-zero, **nothing written** — no run, no record, no bundle. *Measured:* a
  `load_claims` rejection test + a CLI test asserting no `reproduce_record.json` exists.
- **G6 — Stdlib-only, no new dependency, no `models.py` change.** `re` is already imported
  (`reproduce.py:15-37`); runtime deps stay `pydantic`/`typer`/`cryptography`. *Measured:* no
  dependency added; `models.py` untouched (the slice-3 precedent).
- **G7 — Containment and back-compat hold.** An escaping/absolute `from` on a pattern claim is
  refused before any run; a `from`-less pattern claim never touches the filesystem. JSON-locator,
  table-locator, and flat claims behave byte-identically. *Measured:* CLI + engine containment
  tests; the existing suites stay green. Baseline **1829 passed, 1 skipped**.

## User Personas & Scenarios

- **A, lone computational biologist:** clones a published repo whose `analysis.py` ends with
  `print(f"Final AUC: {auc:.3f}")` and writes nothing else. Writes a claims file with
  `{"pattern": "Final AUC: ([0-9.]+)"}` and gets a per-claim verdict without editing the repo.
- **C, core facility:** batch-checks many labs' scripts. Most are "print the number" scripts; this
  is the locator that makes them checkable at all, feeding the same signed-bundle contract as a
  first-party run.

## Requirements

### Must-have (this slice)

- **M1 — Pattern locator schema (extends `load_claims`, `reproduce.py:338-510`).**
  A claim may carry `pattern` (string). Addressing (locked in the interview):
  - **`pattern` WITHOUT `from` ⇒ the run's captured combined stdout+stderr.**
  - **`pattern` WITH `from` ⇒ that repo-relative text file.**
  Validation (structural, repo-agnostic; every violation raises `ClaimsError` → exit non-zero,
  nothing written):
  - Three-way mutual exclusion: a claim with `from` must carry **exactly one** of `path` (JSON),
    `column`+`row` (table), or `pattern`. Any two together → error. (Extends the existing xor at
    `:400-404`.)
  - `pattern` must be a non-empty string; **it must compile** (`re.compile`) — `re.error` →
    `ClaimsError` naming the claim and the regex error. This is the pre-run gate of G5.
  - The existing orphan guard (`:388-392`, "a locator field without `from` is an error") **must be
    relaxed for `pattern` only** — a `from`-less `pattern` is the stdout mode and is legal. A
    `path`/`column`/`row`/`header`/`delimiter` without `from` stays an error, unchanged.
  - **Flags:** no `flags` key. Inline flags (`(?i)`, `(?m)`, `(?s)`) are the supported mechanism —
    Python compiles them from the pattern string, so this needs zero schema surface. Documented,
    not silently implied.
- **M2 — Typed carrier.** Add `PatternLocator(source: str | None, pattern: str)` alongside
  `Locator` and `TableLocator`; widen `Claim.locator` to
  `Locator | TableLocator | PatternLocator | None`. **`source` is `str | None`** — `None` means
  the run's output. The name `source` is kept deliberately so the *file* case reuses every
  existing `.source` code path.
- **M3 — Capture selection (locked).** If the compiled pattern has capturing groups, **group 1**
  is the observed value; if it has none, the **whole match** is. No `group` key this slice.
  Documented in the CLI docstring so it is not a surprise.
- **M4 — Match resolution (new pure resolver, sibling of `resolve_pointer`/`resolve_cell`).**
  A new top-level, **never-raising** `resolve_match(text, pattern) -> tuple[str | None, str]`:
  - Finds **all** non-overlapping matches (`re.finditer`).
  - **0 matches → `(None, "pattern … matched 0 times")`; >1 matches → `(None, "pattern … matched
    N times")`** — the shipped `resolve_cell` wording shape (`:290-292`). Never an arbitrary pick.
  - Exactly 1 match → returns the raw captured **string** (group 1 or whole match per M3).
  - **A capture group that did not participate in the match** (e.g. `AUC=(?:(old)|([\d.]+))`
    against `"AUC=0.9"`, or `(?:x)?(y)?z` against `"z"` — `match.group(1)` is `None`) →
    `(None, "pattern … capture group did not participate in the match")` ⇒ UNVERIFIED. This is the
    one input shape that could otherwise **crash** the resolver — `float(None)` raises
    `TypeError` — so it breaches the never-raises contract if unhandled. Requires its own test.
    *(Corrected during Phase 2: the originally-drafted example `(old)?|AUC=([\d.]+)` does **not**
    reach this branch — `(old)?` matches the empty string at several positions, so `finditer`
    returns 3 matches and the input degrades through the **ambiguity** branch instead. Both
    behaviours are now pinned by tests.)*
  - Compiles defensively inside a `try/except re.error` so it holds the never-raises contract even
    if called directly with an uncompilable pattern (belt-and-braces; `load_claims` already gates).
- **M5 — Observation (new nested `_observe_pattern_located`, sibling of `_observe_table_located`).**
  - **stdout mode (`source is None`):** the text is `run_output` from the enclosing scope. Because
    the observers are closures and every call happens at `:783/:785` — *after* the retry rebind at
    `:721` — this is automatically the **retried** run's output under `--allow-install`. No
    mechanism needed; assert it with a test and state it in the docstring.
  - **file mode (`source` set):** repeat the verbatim containment guard
    (`(repo_path / loc.source).resolve()` → `relative_to(repo_root)` → `ValueError` ⇒
    `"locator 'from' … escapes the repo"`, file never read), then read the file as utf-8. A
    missing / directory / non-UTF-8 / unreadable file → `UNVERIFIED`, never raises. Cache the text
    per resolved path (`_text_cache`), mirroring `_json_cache`/`_table_cache`.
  - The captured string is `.strip()`ed and `float()`-parsed; a non-parsing or non-finite value →
    `UNVERIFIED`. **A numeric string is the normal, valid case here** — the slice-3 rule, not the
    slice-1.5 strict-UNVERIFIED JSON rule (a regex capture is a string by construction).
  - The observed float feeds the **unchanged** `classify`.
- **M6 — Bounded matching (a ReDoS input bound — *not* a memory guard).** Matching runs against at
  most `_MAX_MATCH_BYTES` (**8 MiB**) of text. Text longer than the cap → `UNVERIFIED` naming the
  size and the cap — **not** a silent truncated search, which could report "0 matches" for a
  pattern that does match later in the text. In **file** mode the size is checked via `stat()`
  **before** reading, so an oversized file is never read into memory: there the cap is a genuine
  read bound.
  **Honest framing of the stdout case:** `default_command_executor` (`runner.py:616-619`) already
  uses `subprocess.PIPE` with **no cap**, so the entire run output is fully buffered in memory
  before this slice ever sees it. An enormous stdout is therefore a **pre-existing upstream**
  memory problem that this slice neither creates nor solves; the cap there bounds only how much
  text a regex is run over. Stated explicitly so the limit is not later removed as "pointless".
  **Trust domain:** a pattern is user-authored input from the same source as `--run`, which
  already executes an **arbitrary command** (`cli.py:716`) — a regex is strictly less dangerous
  than what the same invocation already authorizes. We therefore compile-validate pre-run and
  bound the input size; we do **not** attempt a regex execution timeout (not achievable
  stdlib-only, single-threaded).
- **M7 — Dispatch must become explicit (`reproduce.py:780-785`).** The current head is
  `if isinstance(claim.locator, TableLocator): … else: _observe_located(…)` — an **unguarded
  fallback**. Adding a third type without changing it would route a `PatternLocator` into the JSON
  reader and raise `AttributeError` on the missing `.path`. It becomes an explicit
  `elif isinstance(claim.locator, PatternLocator):` chain.
- **M8 — CLI containment loop must skip the stdout mode (`cli.py:810-821`).** It currently does
  `if claim.locator is None: continue` then `(repo_path / claim.locator.source).resolve()`
  unconditionally — a `source=None` locator would raise `TypeError` there. It must become
  `if claim.locator is None or claim.locator.source is None: continue`. A **file**-mode pattern
  claim keeps the existing pre-run refusal unchanged.
- **M9 — Verdict / model / bundle reuse unchanged.** `classify`, `reduce_reproduction`,
  `ClaimResult`, `ReproduceRecord`, `write_reproduce_bundle`, signing, `render_reproduction`,
  `--fail-on-diverged` all reused as-is. **No `models.py` change** (slice-3 precedent).
  `claims_sha256` already covers the new key (it hashes the claims-file bytes).

### Should-have

- **S1 — Message quality.** A pattern-locator `UNVERIFIED` names *why*:
  `pattern 'AUC = ([0-9.]+)' matched 0 times in the run output`,
  `… matched 4 times in 'logs/train.log'`,
  `locator file 'logs/train.log' is missing or unreadable`,
  `captured 'NA' is not a finite number`,
  `run output is 12.4 MB, over the 8 MiB match limit`.
- **S2 — CLI docstring note.** Extend the existing locator sentence (`cli.py:753-757`) with the
  pattern form, the group-1-else-whole-match rule, the strict 0-or-many rule, and an example.

### Nice-to-have (explicitly later slices, NOT this one)

- An `occurrence: first|last` selector, or a `group` index/name override.
- A `flags` array (inline flags cover it).
- Notebook (`.ipynb`) numeric extraction; multi-key/predicate table rows; column ranges.
- Paper-parsing to auto-extract claims + locators; figure/plot & table-image claims (hard-blocked:
  no plot-hash, stdlib-only).
- Remote `<doi|url>`; a dashboard card; the C6 eval fold-in.
- Persisting the matched output on the record for audit (would require a `models.py` change).

## Technical Considerations

- **Localized change, mirroring slices 1.5 and 3.** New: a `PatternLocator` dataclass + a
  `load_claims` pattern branch + a pure `resolve_match` + a nested `_observe_pattern_located` + a
  `_text_cache` + an explicit isinstance dispatch + two small `cli.py` edits (containment guard,
  docstring). Everything downstream of "observed value" is untouched.
- **Stdlib-only.** `re` is already imported at `reproduce.py:15-37`; `_MISSING_MODULE_RE` /
  `_SAFE_PACKAGE_TOKEN_RE` (`:43-44`) are the precedent for module-level compiled constants.
- **The failed-run limit is real and must be documented.** `reproduce.py:745-767` short-circuits
  every claim to `unverified` **before** the dispatch loop when the exit code is non-zero. So a
  stdout locator reads the output of **successful runs only**; it cannot scrape numbers out of a
  crashed run. This is consistent with every other locator (a failed run's files aren't read
  either) but is worth stating so it isn't reported as a bug.
- **Reproducibility/verification impact:** widens *what* the signed verdict can be computed over
  (repos that only print their numbers) **without** weakening the honesty contract —
  UNVERIFIED-on-any-doubt is load-bearing and preserved; ambiguity is surfaced with a count, never
  guessed.
- **Determinism/CI:** no real repo, no network, no pip. Scripted executor returning canned
  `(exit_code, output)` tuples + on-disk fixture log files in `tmp_path`, mirroring
  `tests/test_reproduce_env_resurrection.py::_ScriptedExecutor` and the slice-3 fixtures.

## Data Model / Artifact Contracts

**Claims file (input), extended — a claim is now one of five shapes:**
```json
[
  {"id": "auc", "value": 0.91, "tolerance": 0.02,
   "pattern": "Final AUC: ([0-9.]+)"},

  {"id": "n_reads", "value": 1200000,
   "from": "logs/align.log",
   "pattern": "(?i)^total reads:\\s+([0-9]+)$"},

  {"id": "brca1_lfc", "value": -2.31,
   "from": "results/deseq2.tsv",
   "row": {"gene_id": "ENSG00000012048"}, "column": "log2FoldChange"},

  {"id": "model_auc", "value": 0.91, "from": "out/summary.json", "path": "$.model.auc"},

  {"id": "mean_cov", "value": 30.4}
]
```
1. **Pattern (stdout):** `pattern`, no `from`. **NEW.**
2. **Pattern (file):** `from` + `pattern`. **NEW.**
3. **Table:** `from` + `column` + `row` (slice 3). 4. **JSON:** `from` + `path` (slice 1.5).
5. **Flat:** neither — id lookup in `--results` (slice 1).

- **`pattern`:** a Python regex. Group 1 if it has groups, else the whole match. Inline flags
  supported. Must compile at load time.
- **`ClaimResult` / `ReproduceRecord`:** **unchanged**. A pattern claim populates
  `observed`/`delta`/`status`/`message` through the same fields.

## Risks & Open Questions

- **R1 — Formatting-brittleness is inherent, not fixable.** A regex binds to output formatting. The
  honest mitigation is the verdict contract (never `DIVERGED` on a non-match) plus documentation,
  not a smarter matcher. Recorded so it is not mistaken for an implementation defect.
- **R2 — Strictness vs. epoch logs.** A script printing its metric every epoch produces N matches
  and is `UNVERIFIED` until the user anchors the pattern (`(?m)^Final AUC: …$`). This was the
  locked decision (never guess); the escape hatch (`occurrence`) is deliberately deferred. Expect
  this to be the most common real-world friction — and the strongest evidence for or against
  adding `occurrence` in a later slice.
- **R3 — The 8 MiB cap could reject a legitimate large log.** Refusing (rather than truncating) is
  the honest choice — a truncated search could report a false "0 matches". A later slice could add
  a tail-window address. Open question: is 8 MiB the right number? (Chosen as comfortably above
  any realistic stdout capture, below a memory concern.)
- **R4 — ReDoS is bounded, not eliminated.** No stdlib-only regex timeout exists. Mitigations:
  compile-validate pre-run, cap the input at 8 MiB, and the trust-domain argument (`--run` already
  runs arbitrary commands). A pathological pattern from an untrusted claims file could still spin
  CPU. Stated, not hidden.
- **R5 — `source: str | None` is a new shape for the three `.source` call sites.** The CLI loop
  (`cli.py:814`) and both engine guards join `repo_path / loc.source` unconditionally; a `None`
  raises `TypeError`. M8 + M5 fix them, but this is the likeliest place to leave a crash or a
  containment hole — explicit tests required for both.
- **R6 — The unguarded dispatch `else` (M7)** would silently misroute the new type. Explicit test:
  a pattern claim must never hit the JSON reader.
- **R7 — "Located but still UNVERIFIED" stays common.** Numbers in notebooks, plots, or prose
  aren't reached by this slice. Honest framing: the win is "reads repos that print their numbers,"
  not "reads any repo."

## Out of Scope (explicit)

- `occurrence`/`group`/`flags` keys; multiple captures per claim; regex over binary files.
- Notebook (`.ipynb`), prose, figures/plots/table-images (hard-blocked: no plot-hash; stdlib-only).
- Scraping a **failed** run's output (the engine short-circuits before locators by design).
- Persisting run output on the record; any new dependency; any `models.py`/bundle/signing change.
- Paper-parsing, remote fetch, dashboard card, C6 eval fold-in — all other slices.
- Any judgement on the paper's conclusions. Computation-vs-numbers only.

## Post-merge validation — a **counted** experiment (not a CI test)

Per the slice-1/1.5/3 greenlight discipline, but sharpened: every prior slice's success metric
measured "a test exists", not "more repos became checkable". This one carries a number.

After merge, sample **5 real cloned public repos** whose scripts print their headline numbers.
For each, hand-write a claims file using a stdout pattern and record the outcome in one of three
buckets:

| Bucket | Meaning |
|---|---|
| **Resolved** | exactly 1 match; a real per-claim verdict |
| **Multi-match wall** | ≥2 matches ⇒ UNVERIFIED (the R2 friction) |
| **No match / other** | 0 matches, formatting mismatch, or a non-parsing capture |

**This count is the go/no-go for `occurrence`.** Pre-committed threshold: if the multi-match wall
is hit by **≥3 of 5** repos, strictness is wrong in practice and `occurrence: first|last` earns an
immediate follow-on slice; at ≤1 of 5 the strict rule stands as designed. (Deciding the threshold
now, while it is cheap, is the point — `occurrence` is roughly a 20-line addition to these same
code paths, and folding it in later means a second pass over `load_claims` validation, the
resolver, and the docs.)

The three bucket counts are also exactly the publicly-sourced eval-data C8 exists to generate.
Manual, offline-optional, not gated in CI.

## Guardrail check (`CLAUDE.md`)

Layer 2 only (a resolver over verify output; never NL→workflow, never a conclusions verdict) ✅ ·
Moat = verification/reproducibility infra + corpus ✅ · Gets better as base models improve
(claim/pattern extraction is a later slice) ✅ · Founder's edge / stdlib-only ✅ · No raw-data
egress (file mode reuses the containment guard; stdout mode reads only in-memory output Contig
itself produced) ✅ · Test-first ✅.
