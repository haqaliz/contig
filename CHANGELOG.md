# Changelog

All notable changes to Contig are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims for
[semantic versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

### Added

- **`contig reproduce` gains a stdout/log regex locator — the C8 slice 4 named as the next
  unblocked step by the slice-3 entry directly below ("No stdout/log scraping…").** Slices 1.5
  (v0.41.0) and 3 (v0.43.0) both required the repo to write its numbers into a **structured
  file** — JSON or a TSV/CSV table. A large share of published analysis scripts do not: they
  `print()` the headline number, or append it to a `.log`, and write no JSON and no table at
  all. Against those repos every claim degraded to `UNVERIFIED` — honest, but a dead end. A
  claim may now carry `{"pattern": <Python regex>}`, optionally with `{"from": <repo-relative
  text/log file>}`, and `contig reproduce` binds the observed value straight out of free text.
  - **Two addressing modes.** `pattern` **without** `from` matches against the run's own
    captured combined **stdout+stderr** — the text the engine already holds, which until now was
    read only by `detect_missing_module` and the diagnosis evidence. `pattern` **with** `from`
    matches against that repo-relative text/log file. `PatternLocator(source: str | None,
    pattern: str)` carries both; `source is None` **is** the stdout mode, and the field is named
    `source` deliberately so the file case reuses every existing `.source` code path.
  - **A new pure, stdlib resolver** (`verification/reproduce.py::resolve_match`, sibling of
    `resolve_pointer`/`resolve_cell`): finds **all** non-overlapping matches with `re.finditer`,
    returns the raw captured **string**, and **never raises** — an oversized text, an
    uncompilable pattern, an ambiguous match count, or a non-participating capture group all
    return `(None, reason)`.
  - **Capture selection: group 1 if the pattern has capturing groups, else the whole match.**
    A named group `(?P<v>…)` is group 1 too. There is no `group`, `occurrence`, or `flags` key
    this slice — **inline flags** (`(?i)`, `(?m)`, `(?s)`) are the supported and documented
    mechanism, since Python compiles them straight from the pattern string and they need zero
    schema surface.
  - **Ambiguity is never guessed.** A pattern matching **0 or more than 1** times is
    `UNVERIFIED` with the **count named in the message** — never an arbitrary first-match pick.
    A script that prints its metric every epoch is therefore unverified until the user anchors
    the pattern (`(?m)^Final AUC: …$`); that is the deliberate strict rule, not a gap.
  - **The non-participating-group guard.** A group 1 that did not participate in the match
    (`(?:x)?(y)?z` against `"z"`) yields `None` from `match.group(1)` — the one input shape that
    would otherwise crash the caller on `float(None)` with a `TypeError`. It degrades to
    `UNVERIFIED` with its own message and its own test.
  - **A bounded 8 MiB match input (`_MAX_MATCH_BYTES`) — honestly framed as a ReDoS input
    bound, NOT a memory guard.** Text over the cap is `UNVERIFIED` naming the size and the cap,
    **never a silently truncated search** (which could report "0 matches" for a pattern that
    does match past the cut). In **file** mode the size is checked via `stat()` **before** any
    read, so an oversized log is never pulled into memory — there the cap is a genuine read
    bound. In **stdout** mode it is not: `runner.default_command_executor` already buffers the
    entire run output through `subprocess.PIPE` with **no cap**, so an enormous stdout is a
    **pre-existing upstream** memory issue this slice neither creates nor solves; the cap there
    bounds only how much text a regex is run over. Recorded explicitly so the limit is not later
    removed as "pointless". No regex execution timeout is attempted — not achievable
    stdlib-only, single-threaded — and a pattern comes from the same claims file as `--run`,
    which already executes an arbitrary command.
  - **`load_claims` validates the pattern shape structurally, pre-run.** `pattern` must be a
    non-empty string and **must compile** — an `re.error` is a `ClaimsError` naming the claim
    and the regex error, so a malformed regex exits non-zero with **nothing written**: no run,
    no record, no bundle. The existing xor became a **three-way mutual exclusion**: a claim sets
    exactly one of `path` (JSON), `column`+`row` (table), or `pattern`. `pattern` together with
    **any** table field (`column`, `row`, `header`, `delimiter`) is rejected — a table key has
    no meaning for a regex locator, and accepting it would be a silent misread of the claim's
    intent. `pattern` is the **first** locator that is legal **without** `from`, so the orphan
    guard was relaxed for `pattern` only: a `path`/`column`/`row`/`header`/`delimiter` without
    `from` stays a `ClaimsError`, unchanged.
  - **`run_reproduction`'s dispatch head became an explicit `isinstance` chain.** It was
    `if TableLocator: … else: _observe_located(…)` — an unguarded fallback that would have
    routed a `PatternLocator` into the JSON reader and raised `AttributeError` on the missing
    `.path`. A new `_observe_pattern_located` (sibling of `_observe_table_located`) reuses the
    same containment guard and a per-run read cache (`_text_cache`, keyed by resolved path — a
    log `from` is read **at most once per run** even across several pattern claims on it).
  - **The retried run's output is bound for free.** The observers are closures over
    `run_output` and are only ever called *after* the `--allow-install` retry rebinds it, so a
    stdout claim automatically observes the **retried** run's output, never the failed first
    run's. No new mechanism — asserted by a scripted-executor test and stated in the docstring.
  - **A numeric-string capture is the normal, valid case** — the slice-3 table rule, deliberately
    unlike the slice-1.5 strict-UNVERIFIED JSON rule, because a regex capture is a string by
    construction. The capture is `.strip()`ed and `float()`-parsed; a non-parsing (`"NA"`) or
    non-finite (`inf`/`nan`) capture is `UNVERIFIED`, never coerced, never guessed. The finite
    float feeds the **unchanged** `classify`.
  - **Safety and reuse, unchanged.** A **file**-mode pattern claim's `from` flows through the
    same CLI pre-run containment refusal and the same engine `resolved.relative_to(repo_root)`
    defense-in-depth guard the JSON and table locators already use; an escaping/absolute `from`
    is refused **before any run**, and one reaching the engine directly degrades to `UNVERIFIED`
    with the file **never read**. The one new line the CLI needed is the **stdout-mode skip**
    (`if claim.locator is None or claim.locator.source is None: continue`) — without it the
    containment loop would have raised `TypeError` joining a `None` source. A `from`-less
    pattern claim touches the filesystem **not at all**. `classify`, `ClaimResult`,
    `ReproduceRecord`, bundle writing, signing, `render_reproduction` and `--fail-on-diverged`
    are all reused as-is — **no `models.py` change**; `claims_sha256` already covers the new
    `pattern` key since it hashes the claims-file bytes. Stdlib-only (`re`, already imported) —
    no new dependency.
  - **Honest scope / limits (recorded, not glossed).** A regex binds to **output formatting**,
    not to a data structure — a repo changing `print(f"AUC={x}")` to `print(f"AUC: {x}")` breaks
    the claim — so this is the **weakest locator shipped**. The mitigation is not cleverness but
    the verdict contract: a non-match is `UNVERIFIED` naming the count, **never `DIVERGED`**, so
    a formatting drift can never be misread as a failed reproduction. The engine also
    short-circuits every claim to `UNVERIFIED` on a non-zero exit *before* any locator runs, so
    a stdout pattern reads **successful runs only** — it cannot scrape numbers out of a crashed
    run (consistent with every other locator, whose files aren't read either, but worth stating
    so it isn't reported as a bug). Deferred: an `occurrence: first|last` selector and a `group`
    override (gated on a counted post-merge experiment over 5 real repos), a `flags` array
    (inline flags cover it), notebook (`.ipynb`) numeric extraction, regex over binary files,
    persisting the matched output on the record (would need a `models.py` change), paper-parsing,
    remote `<doi|url>`, a dashboard card, the C6 eval fold-in. Figure/plot and table-image claims
    remain **hard-blocked** (no plot-hash exists; perceptual image hashing would break the
    stdlib-only dependency contract). Test-first (schema → pure resolver → engine dispatch → CLI
    containment/e2e), deterministic, **no real repo, network, or pip in CI** — scripted executors
    returning canned `(exit_code, output)` tuples plus on-disk fixture logs in `tmp_path`.

## [0.43.0] - 2026-07-21

### Added

- **`contig reproduce` gains a TSV/CSV table cell locator — the C8 slice 3 named as "the next
  step" by both prior locator slices.** Slice 1.5 (v0.41.0) could only bind a claim's observed
  value from a repo's **structured JSON** output; but in bioinformatics the numbers a paper
  reports overwhelmingly live in **tabular** output — DESeq2 results tables, count matrices,
  feature/stat tables — as `.tsv`/`.csv` (often gzipped). Against those repos every claim
  degraded to `UNVERIFIED`. A claim's locator may now also carry `{"from": <repo-relative
  .tsv/.csv[.gz] file>, "column": <name|int>, "row": <int|{key:val}>, "header"?: bool,
  "delimiter"?: str}` — naming a cell the same way the JSON locator names a `path` — so
  `contig reproduce` reads numbers straight out of real, unmodified tabular output.
  - **Two addressing modes.** Named: a header column name + a `{key: value}` row match
    (`row: {"gene_id": "ENSG…"}`, `column: "log2FoldChange"`). Positional: an integer column
    index + integer row index with `header: false`. Indices are 0-based, matching the JSON
    locator's `[n]` list indices.
  - **A new pure, stdlib table reader** (`verification/reproduce.py::_read_table` +
    `resolve_cell`, siblings of the JSON walker): `_read_table` reads `.tsv`/`.csv` via
    `csv.reader` and is gzip-transparent (`.tsv.gz`/`.csv.gz` via stdlib `gzip`, text mode,
    utf-8); `resolve_cell` resolves column-then-row against parsed rows and is index-safe on any
    shape — ragged rows, empty files, header-only tables, directory paths, non-UTF-8 files — and
    **never raises**. `_resolve_delimiter` infers `\t` for `.tsv`/`.tab` and `,` for `.csv`
    (stripping one trailing `.gz` first); an explicit `delimiter` always overrides the extension.
  - **`load_claims` validates the table shape structurally, pre-run.** `from` must carry
    exactly one of `{path}` (JSON) or `{column, row}` (table) — mixing them, or a table field
    without `from`, is a `ClaimsError` (exit non-zero, nothing written). `column` must be a
    non-empty string or non-negative int; `row` a non-negative int or a single-key
    `{str: str}` object; `delimiter` a single character; `header` a bool. A `row`-object or a
    string `column` **requires** `header: true` (a header names the key column) — the
    combination with `header: false` is rejected at load, not silently misread. An
    unrecognized extension (`.txt`) with no explicit `delimiter` is also a load-time
    `ClaimsError`, never a silent wrong-delimiter parse.
  - **`run_reproduction` dispatches on the locator's type** (`isinstance(claim.locator,
    TableLocator)`) to a new `_observe_table_located`, a sibling of the JSON `_observe_located`
    reusing the exact same containment guard, per-run parse cache (`_table_cache`, keyed by
    resolved path — a table `from` is parsed **at most once per run** even when several claims
    address different cells of it), and UNVERIFIED plumbing. The resolved cell string is
    `float()`-parsed after `.strip()`; the finite float feeds the **unchanged** `classify` →
    `REPRODUCED`/`WITHIN-TOLERANCE`/`DIVERGED`.
  - **The deliberate divergence from the JSON rule: a numeric-string cell is the normal, valid
    case.** Every table cell is a string by construction, so `"30.4"` classifies as the observed
    value here — unlike the JSON locator, where a numeric string is strictly `UNVERIFIED`. A
    cell that doesn't `float()`-parse (empty, `"NA"`, `"1,024"`, `"1.5%"`) or parses to a
    non-finite value (`nan`/`inf`) is `UNVERIFIED`, never coerced, never guessed.
  - **No false reproduce, ever.** Every unresolved/ambiguous address is `UNVERIFIED`, never
    `DIVERGED`: a missing/dir/non-UTF-8/unparseable `from`; an absent or duplicate header
    column name; a column/row index out of range; a ragged row shorter than the addressed
    column; a `row`-key match with **0 or more than 1** hits (0-or-many-matches is treated as
    ambiguous, never an arbitrary pick — the count is named in the message). Key-column compare
    is exact on the `.strip()`ed cell string.
  - **Safety and reuse, unchanged.** A table claim's `from` flows through the same `.source`
    field the CLI containment loop and the engine's defense-in-depth guard already check
    (`cli.py`'s pre-run escape/absolute-path rejection, and the engine's own
    `resolved.relative_to(repo_root)` guard) — no new code was needed there; an escaping/
    absolute `from` is refused **before any run**, and a path that reaches the engine directly
    degrades to `UNVERIFIED` with the file **never read**. `classify`, `ClaimResult`,
    `ReproduceRecord`, bundle writing, signing, `--fail-on-diverged` are all reused as-is — **no
    `models.py` change**; `claims_sha256` already covers the new claim fields since they're part
    of the claims-file bytes. Stdlib-only (`csv` + `gzip`, both already stdlib) — no new
    dependency.
  - **Honest scope / limits (recorded, not glossed).** Single key-column equality only this
    slice — no multi-key/predicate row match, no column ranges, no regex. No stdout/log
    scraping, no notebook (`.ipynb`) numeric extraction. Figure/plot and table-image claims
    remain hard-blocked (no plot-hash exists; adding perceptual-image-hashing would break the
    stdlib-only dependency contract). No paper-parsing, no remote `<doi|url>`, no dashboard
    card, no C6 eval fold-in — all deferred to later slices. Test-first (pure reader → engine
    dispatch → CLI containment/e2e), deterministic, **no real repo or network in CI** — tests use
    on-disk fixture `.tsv`/`.csv`/`.tsv.gz` tables written to `tmp_path`, mirroring the JSON
    locator's test discipline.

## [0.42.0] - 2026-07-19

### Added

- **`contig reproduce` gains opt-in environment resurrection — the C8 slice 2 that lets it reproduce
  repos that don't run yet.** Slices 1 (v0.40.0) and 1.5 (v0.41.0) could only issue a verdict on a
  repo whose script already ran; an uncooperative repo that exits non-zero on a missing Python
  dependency just degraded every claim to `UNVERIFIED`. `ModuleNotFoundError` / `ImportError` +
  dependency installs are the dominant reproduction-failure class (~76%), and the roadmap named
  environment resurrection the "load-bearing" piece of C8. It now ships as a bounded, opt-in
  self-heal that reuses the C2 machinery.
  - **New `--allow-install` flag on `contig reproduce` (off by default).** When set, a first run that
    exits non-zero with a `No module named 'X'` message triggers **detect → install → retry once**:
    a new pure `verification/reproduce.py::detect_missing_module` extracts the missing top-level
    package (case-insensitive, `sklearn.utils` → `sklearn`, charset-validated `^[A-Za-z0-9._-]+$`);
    a new injected installer seam (`runner.Installer` + `runner.default_installer` +
    `_pip_install_argv`, mirroring the `IndexBuilder` seam) runs a **fixed** argv
    `[sys.executable, "-m", "pip", "install", <module>]` (no shell, no interpolation); the run is
    retried exactly once and the claims re-classify against the retried run's fresh output. **Off by
    default the behavior is byte-identical to before** — the flag gates all network + environment
    mutation, and its help text says so.
  - **Honest on every unresolved path.** Flag off, no module detected, install fails, or the retry
    still fails → all claims `UNVERIFIED`, **never a false reproduce**. Bounded to exactly one
    install + one retry (provable termination — even a *second* missing module on the retried output
    is not chased). Import-name ≠ package-name mismatches (`cv2` → `opencv-python`) simply fail the
    install and degrade to `UNVERIFIED` (a curated alias map is a deferred follow-on).
  - **The resurrection is recorded and reproducible.** `ReproduceRecord` gains an additive
    `repair_history: list[RepairStep]` (default `[]`, so pre-slice-2 bundles load unchanged); a
    successful or attempted heal appends one `RepairStep` (`Diagnosis(failure_class="missing_dependency")`
    — a new literal kept **reproduce-local**, deliberately *not* wired into the shared
    `diagnose_failure` detector so the C6 eval-guard held-out baseline is unaffected — plus
    `Patch(kind="env", operation={"install": <module>})`), surfaced as a one-line `env-repair` note
    in `contig show`/the rendered report and round-tripped through the signed bundle. The record's
    `exit_code` reflects the final (retried) run.
  - **To surface the error text, the reproduce command-executor seam widened from `int` to
    `(exit_code, combined_output)`** (`runner.default_command_executor` now captures combined
    stdout+stderr); the Nextflow `Executor`/`IndexBuilder` seams are untouched. No new runtime
    dependency (the installer is an injected seam); research-use, computation-vs-numbers only, no
    raw-read egress; test-first with a scripted executor + scripted installer — **no real repo,
    network, or pip in CI**. **Deferred:** import→package alias map, iterative multi-module
    resolution, version pinning from a traced execution, venv isolation, and the TSV/CSV locator
    (the named next step).

## [0.41.0] - 2026-07-18

### Added

- **`contig reproduce` gains a claim-level output-locator — the C8 slice-1.5 that makes reproduce
  read *uncooperative* repos as-is.** The v0.40.0 walking skeleton bound every claim's observed
  value from one flat, Contig-shaped `results.json` (`{claim_id: value}`) the third-party repo had
  to hand-write — so it only reproduced repos you modify (or synthetic fixtures). A claim may now
  carry an **optional locator** `{"from": <repo-relative JSON file>, "path": <expression>}` naming
  where its number already lives in the repo's own structured output — so `contig reproduce` reads
  numbers out of **real, unmodified cloned repos that emit JSON**. This is exactly the piece the
  reproduce PRD's review gate named as what makes the tool "externally credible."
  - **A new pure, stdlib JSON path walker** (`verification/reproduce.py::resolve_pointer`, with
    `_parse_path`): dotted segments + `[n]` list indices, a leading `$.`/`$` tolerated
    (`$.model.auc`, `model.auc`, `samples[0].mean_cov`, `[0].name` for a top-level list). It walks
    nested `dict`/`list` from parsed JSON with strict `isinstance` guards (a key only on a dict, an
    index only on a list; `bool` never treated as an index) and **never raises** — any unresolved
    step (missing key, index out of range, wrong container, malformed expression) returns `None`,
    the repo's omit-never-guess idiom. No JSONPath/regex dependency; the runtime dep set
    (`pydantic`/`typer`/`cryptography`) is unchanged.
  - **Value-binding branches on the locator, verdict core untouched.** In `run_reproduction`, a
    claim **with** a locator is bound from `repo/<from>` at `<path>` (files parsed once and cached
    per run) and classified by the **unchanged** `classify`/`benchmark._relative_delta`; a claim
    **without** one keeps the slice-1 flat-`results` id lookup byte-for-byte. A claims file may mix
    located and flat claims. `ClaimResult`/`ReproduceRecord`, signing, and the `--fail-on-diverged`
    exit contract are reused as-is (no model change); `claims_sha256` already covers the locators
    since they are part of the claims-file bytes.
  - **Honest degradation preserved end-to-end — every locator failure is `UNVERIFIED`, never a
    false pass, never `DIVERGED`:** a missing `from` file, unparseable/non-UTF-8 JSON, an unresolved
    `path`, or a target that is non-numeric — **including a numeric *string* like `"0.91"`, which is
    strictly UNVERIFIED, not coerced** — bool, or non-finite (`NaN`/`inf`). Each carries a specific
    message. A non-zero script exit still short-circuits every claim to `UNVERIFIED` (unchanged).
  - **Safety: no read outside the repo.** An escaping or absolute `from` is refused at the CLI
    **before any run** (exit non-zero, **no** record written), reusing the same
    `(repo/from).resolve().relative_to(repo.resolve())` containment guard as `--results`; and if such
    a path reaches the engine directly it degrades to `UNVERIFIED` with the outside file **never
    opened** (defense-in-depth, `.resolve()` also defeating symlink escapes). No raw-data egress —
    only hashes + claim diffs leave the box.
  - **Honest scope / limits (recorded, not glossed).** Research-use, computation-vs-numbers only —
    never a judgement on the paper's conclusions. **Structured JSON only** this slice: repos that
    emit numbers only to stdout, CSV/TSV, notebooks, or figures still degrade to `UNVERIFIED` — the
    win is "reads repos that emit structured JSON," not "reads any repo." **Deferred:** a TSV/CSV
    locator (the named next step); environment resurrection (slice 2); paper-parsing; figure/plot &
    table-cell claims (still blocked — no plot-hash exists and adding perceptual-image hashing would
    break the stdlib-only dep contract); remote `<doi|url>`; a dashboard card; the C6 eval fold-in.
    Test-first (walker → `load_claims` → engine binding → CLI guard), deterministic, **no real
    third-party repo or network in CI** (scripted executor + on-disk fixture outputs).

## [0.40.0] - 2026-07-18

### Added

- **`contig reproduce` — the first slice of capability C8 (reproduce & verify *third-party
  published* work).** The shipped run→verify→reproduce engine is turned around to face *other
  people's* analyses: `contig reproduce <repo> --run "<cmd>" --claims <file>` runs a repo's script
  and reports, **per stated numeric claim**, whether the computation regenerates it — ending in a
  signed, re-runnable bundle. This is a **deliberately narrow walking skeleton** (the durable
  surface + verdict contract); the hard environment-resurrection piece is slice 2.
  - **Per-claim verdict, four honest states.** Each claim resolves to `REPRODUCED` /
    `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED` via a new `verification/reproduce.py`
    (`load_claims` / `classify` / `run_reproduction` / `reduce_reproduction`) and two new models
    (`ClaimResult`, `ReproduceRecord`). Classification **reuses** `benchmark._relative_delta`
    (the repo's only real tolerance compare): `|Δ| ≤ 1e-9` → REPRODUCED, else `rel_delta ≤
    tolerance` → WITHIN-TOLERANCE, else → DIVERGED; a DIVERGED/WITHIN-TOLERANCE message names
    observed-vs-stated and the delta. **`UNVERIFIED` is never rendered as reproduced** — a missing
    `results.json` key, a non-numeric or non-finite (`NaN`/`inf`) observed value, or a non-zero
    script exit yields UNVERIFIED, never a false pass.
  - **Value binding.** The repo's script writes a flat `results.json` `{claim_id: value}`; the
    comparator joins each claim on its id. A claim absent from `results.json` is UNVERIFIED; extra
    keys are ignored.
  - **Signed, re-runnable bundle for free.** A `ReproduceRecord` is written to
    `<runs-dir>/<reproduce_id>/reproduce_record.json` and **signed by the existing generic
    `_maybe_write_signature`** (it signs any pydantic record via `model_dump(mode="json")` — no
    fork, no `RunRecord` pollution) when `CONTIG_SIGNING_KEY` is set, alongside a `reproduce.json`
    manifest (repo, command, claims sha256) capturing the invocation. A new
    `runner.default_command_executor(cmd, cwd)` runs the script **in the repo dir** (distinct from
    `default_executor`, whose second arg is a trace-file path run in its parent).
  - **Exit codes.** A completed, well-formed invocation exits `0` regardless of claim outcomes;
    opt-in `--fail-on-diverged` exits non-zero when any claim DIVERGED (default unchanged). A
    malformed claims file (bad JSON, duplicate id, non-positive tolerance, non-numeric value)
    aborts non-zero **before any record is written**.
  - **Honest scope / explicit limits (recorded, not glossed).** Research-use; whether the
    *computation* reproduces the stated *numbers*, **never** a judgement on the paper's
    conclusions; no raw-data egress (only hashes + claim diffs). Slice 1 reproduces
    **cooperative** repos — ones that emit a `results.json` — so an uncooperative repo degrades
    honestly to UNVERIFIED; the claim-level output-locator (read numbers out of a repo as-is) and
    **environment-resurrection** (self-heal `ModuleNotFoundError` → install → retry) are slice
    1.5 / slice 2. **Scalar numeric claims only:** figure/plot and table-cell claims are out of
    scope — see the roadmap correction below. Test-first (models → engine → bundle → CLI);
    deterministic; **no real third-party repo or network in CI** (a scripted executor writes a
    canned `results.json`); `created_at`/`reproduce_id` are passed into the pure core, never
    wall-clock inside it.
  - **Corrected `docs/technical/CAPABILITY_ROADMAP.md` C8**, which promised to reuse "existing
    float-tolerance / **plot-hash** / seed-aware diffing." Verified against the code: the
    float-tolerance compare is real and reused; **plot-hash does not exist anywhere**, and adding
    perceptual-image-hashing would break the deliberate stdlib-only dependency contract
    (`pydantic`/`typer`/`cryptography`); "seed-aware diffing" is not a named mechanism. That is the
    hard technical reason figures are deferred, now recorded so the reason travels with the code.

## [0.39.0] - 2026-07-17

### Changed

- **Informational QC checks are now verdict-neutral: a check that cannot fail no longer
  counts as evidence for a `pass`** (capability C3 follow-on; the item
  `CAPABILITY_ROADMAP.md` had flagged as "the strongest follow-on candidate here"). A new
  additive `QCResult.informational` field (default `False`; old records deserialize
  unchanged, exactly as `QCKind` does) marks a check that asserts nothing, and
  `overall_verdict` now reduces over the **non-informational** results only — a result set
  of only informational and/or `unverified` checks reduces to `unverified`, never `pass`.
  Four checks are marked, spanning the two mechanisms by which a check could only ever
  pass: `duplication_rate` (a band-less rule-pack rule, detected by the absence of all four
  bound keys — *not* by a null expected-range, which a `fail_below`-only rule also has while
  remaining able to FAIL) and the three hardcoded-always-pass checks `gene_symbol_concordance`,
  `x_het_ratio`, and `gene_overlap`. A test enumerates the exact informational set, so a
  fifth such check cannot land silently — the durable form of the roadmap's "decide before a
  second band-less rule lands", which prose had already failed to hold (three had landed).
- **`x_het_ratio` now reports `unverified` when the chrX heterozygosity ratio could not be
  computed** (too few callable X sites), instead of a `pass` for something it never checked.
  Only a real, computed ratio is an informational `pass`. The pre-existing test named
  `test_evaluate_indeterminate_is_unverified_with_none_value` had asserted `pass` against its
  own name; it now asserts what the name always said.

### Fixed

- **The dashboard's verdict card no longer prints "PASS: all N checks passed" for a run the
  engine called `unverified`.** `dashboard/lib/derive.ts`'s `overallQc` was a second,
  divergent copy of the reducer with no `unverified` arm and no informational skip: a run
  whose tasks succeeded but whose QC was entirely `unverified` (or entirely informational)
  showed an "Unverified" badge beside a literal false-pass reason string. `overallQc` now
  mirrors `overall_verdict` exactly (skip informational, then `fail > warn > pass >
  unverified`), and its docstring no longer claims "we never re-derive trust" while
  re-deriving. This was the one live, user-visible defect in this change.

### Honest scope

- **This slice is defensive, not corrective: it changed essentially no run's verdict.**
  Marking the four checks needed **no verdict-test rewrites** (the suite went 1588 → 1601,
  +13 tests; the only existing assertions changed were the two `x_het_ratio` "ratio
  unavailable" cases retargeted from `pass` to `unverified`, disclosed above), because a real
  run almost never rests on informational checks alone — the
  main rule pack, the RNA-seq-only `min_sample_count` cross-sample floor, structural manifest
  checks, or an asserting concordance sibling are present and hold the verdict. The value is
  that the invariant is now **true and guarded**, not that a live false-pass class was closed.
- **The roadmap's own motivating example was wrong, and is corrected here.** A
  `PERCENT_DUPLICATION`-only RNA-seq report does **not** flip to `unverified`: `min_sample_count`
  is an asserting check (it can FAIL below two samples) that rides along on every RNA-seq run
  and floors the verdict at `pass`. The honest headline is "a `pass` is now backed by at least
  one check that could have failed", not "the duplication-only run stops passing". The one
  genuinely reachable flip is a count-concordance run over two matrices sharing zero genes
  (both asserting siblings `unverified`, only the informational `gene_overlap` "passing") when
  no MultiQC or manifest is also present — narrow, but a real false pass removed.
- **Named residue (unchanged, not fixed here):** `min_sample_count` can fail but asserts
  nothing *biological*, so a "asserts something biological" distinction remains a possible
  follow-on; `runner.py`'s `multiqc is not None` gate still makes both RNA-seq plausibility
  checks vanish rather than report `unverified`; `rrna_contamination` remains a guessed slug;
  and the CLI `contig report --explain` (`report.py::explain_verdict`) still renders a
  "Decided by" list of the `unverified` checks for an all-unverified completed run — honest
  (the headline is `UNVERIFIED`, never a false pass) but not harmonized with the dashboard's
  cleaner "no check could corroborate this run" wording, a cosmetic follow-on.

## [0.38.0] - 2026-07-15

### Fixed

- **RNA-seq `duplication_rate` now actually ingests from a real MultiQC report — it never had
  before** (capability C3 follow-on). `RNASEQ_PLAUSIBILITY_PACK` keyed the lowercase
  `percent_duplication`; MultiQC republishes Picard MarkDuplicates' field name verbatim as
  uppercase `PERCENT_DUPLICATION`, and `qc_ingest.py`'s general-stats merge is an exact-key
  match, so the check missed on every real run. A second, independent bug compounded the
  first: the pack banded a declared 0-100 scale, but Picard's own javadoc says the value is a
  raw 0-1 fraction ("the fraction of mapped sequence marked as duplicate," no `x100`
  anywhere) — a 70%-duplicated sample reads `0.707214`. Fixing the key alone would have been
  worse than the bug: an unrescaled fraction against the old `warn_above: 80.0` band would
  have silently PASSed every real report.
  - `duplication_rate` now keys `PERCENT_DUPLICATION` and carries `"unit": "fraction"`, and
    ships **informational-only — no band at all**: the pack's own docstring records that a
    deep/high-input library legitimately exceeds 90% duplication, so any band (WARN or FAIL)
    would flag a legitimate protocol, not a broken run. Declined by design, not pending
    calibration — a band becomes justifiable only with real per-protocol duplication
    distributions, or a library-prep/input-amount signal the pack does not have.
  - A new guard in `rnaseq_plausibility.py` refuses a value present but outside `[0, 1]` as
    `unverified` rather than rescaling it (`0.5` is ambiguous between "50%" and "0.5%"), so a
    wrong key was already safe and a wrong unit now is too — every known way this check can be
    wrong degrades to honest, never a silent lie.
  - `rule_pack.py`'s `_expected_range` previously rendered the literal string `">= None"` for
    a band-less rule; it now returns `None`, which `duplication_rate` is the first rule in the
    repo to exercise.
  - `rrna_contamination` is untouched and remains a guessed `percent_rRNA` slug — researched,
    and there is genuinely no default machine-readable rRNA source in `nf-core/rnaseq`
    (SortMeRNA is off by default; featureCounts biotype QC is GTF-dependent and emits
    per-biotype counts, not a percentage). Recommended follow-on: drop the check or build a
    dedicated parser that degrades to UNVERIFIED.
  - **Honest limit:** the corrected key and unit are read from MultiQC's and Picard's own
    source, not from an observed run — no real `nf-core/rnaseq multiqc_data.json` exists in
    this repo (`demo/sample-run`'s is synthetic, `demo/make_sample_run.py:59,105`). The `[0,1]`
    guard is what makes that acceptable: a wrong key or unit degrades to `unverified`, never a
    false PASS.
  - **Caveat for signing users, same shape as v0.35.0/v0.37.0's:** `verdict` is a
    `@computed_field` serialized into the signed canonical payload, so re-verifying an old
    bundle re-reduces the verdict under the corrected pack. Blast radius here is unusually
    small: this check moves from an `unverified` result to an always-PASS informational one,
    and neither carries severity, so a re-reduced verdict should not flip for any bundle whose
    verdict was already set by another check.
  - Corrected `docs/technical/CAPABILITY_ROADMAP.md`'s C3 record, which had called the pack a
    "silent no-op" (it was dormant but honest — it emitted explicit `unverified` results, unlike
    a true silent no-op) and claimed the same defect class as the single-cell dormant pack
    (true only for `percent_rRNA`; `duplication_rate` needed no dedicated parser, only a key/unit
    fix).

## [0.37.0] - 2026-07-15

### Changed

- **A somatic run with an empty call set now FAILs the verdict — and the remaining
  plausibility FAIL bands are formally *declined by design*, not deferred again** (capability
  C4 follow-on / C3 follow-on). v0.36.0 gave the verdict teeth via `--fail-on-verdict`, but
  germline `variant_calling` was the only assay whose *biological* plausibility could bite: a
  somatic (tumor–normal) run whose Mutect2 step truncated or crashed into a 0-record VCF
  rendered a **WARN** and exited `0` even with the flag set, while the germline equivalent of
  that exact failure already FAILed (`rule_pack.py:84-90`). This slice closes that asymmetry
  with one band, and — the more durable half — records why every other proposed band will not
  be built.
  - **What now FAILs:** `somatic_variant_count` gains `fail_below: 1`. The band's shape and
    rationale mirror the shipped germline `variant_count` floor exactly, but the counted
    population differs: `somatic_variant_count` counts biallelic records only (a
    multiallelic record — a comma in ALT — is skipped before the counter increments),
    whereas germline `variant_count` counts distinct sites including multiallelic ones. So
    the floor fires when no biallelic records were called — almost always an empty or
    truncated call set, though a VCF whose calls are all multiallelic would also read `0`
    and FAIL. Either way it now drives `record.verdict` → FAIL wherever the verdict is
    surfaced. The count is always an `int` (initialized to `0` and incremented *before* the
    tumor-column guard), so a real `0` rides the band into the floor rather than routing to
    UNVERIFIED — a zero count is never mistaken for "nothing to check."
  - **The escalation is the narrowest possible.** `warn_below: 10` is **unchanged**, so 1–9
    records still WARN exactly as before; only the exactly-zero case moves. There is
    deliberately **no `fail_above`** — mirroring germline's decision, the `warn_above: 100000`
    ceiling stays a **soft, uncalibrated "absurd-count" tripwire, never a validated ceiling**,
    because a hypermutator (MSI-high, POLE-mutant) or a WGS tumor legitimately exceeds it.
  - **Pure data change.** One key on one rule dict. The scorer (`_status_for`), evaluator
    (`evaluate_somatic_plausibility`), verdict reducer (`overall_verdict`), report,
    `contig show --explain`, provenance, and dashboard consume it unchanged. No new model
    field, `FailureClass`, corpus case, or dashboard card; no CLI or default exit-code change.
  - **Declined by design — not deferred, not pending calibration.** The "FAIL severity
    deferred until the bands are calibrated on real data" line has now been re-deferred across
    five slices (germline v0.3.0, RNA-seq v0.6.0, somatic-VAF, RNA-seq composition, and
    variant-count). It is retired here: an investigation found these bands are not waiting on
    data, they are **structurally impossible to do honestly**, and no amount of calibration
    changes that. The reasons are recorded in the pack comments and
    `docs/technical/CAPABILITY_ROADMAP.md` so they travel with the code:
    - **Somatic VAF (`median_vaf`, `strelka_median_vaf`) stays WARN-capped.** Germline Ti/Tv
      could ship FAIL bands because its expected value is *physically constrained* (~2.0 WGS,
      ~3.0–3.3 WES) with noise at a *distinguishable* ~0.5. A tumor VAF has no such structure:
      its expected value is a function of **purity and clonality, which the engine never
      observes** (no purity estimate, no ploidy, no copy-number, no target type). A low median
      VAF is legitimate science — a low-purity tumor or a subclonal population — so any
      `fail_below` would FAIL a real sample. `strelka_median_vaf` adds a second, independent
      reason: the tier1 ratio is arithmetically bounded to [0,1] given non-negative tier
      counts — which the VCF spec guarantees — since `strelka_vaf.py:95-98,121-124` reject
      `denom <= 0` and the numerator is one of the two summands. So a `fail_above: 1.0` is
      **dead code for every real input**.
    - **`pon_applied` is structurally unbandable.** It is not a numeric metric — a 3-state
      string from a header search, emitted with `value=None`, that never enters `evaluate()`
      at all (it is appended alongside the pack's results, not through it). PON absence is
      also a legitimate configuration that Contig itself does not wire.
    - **RNA-seq (`RNASEQ_PLAUSIBILITY_PACK`, `RNASEQ_COMPOSITION_PACK`) stays WARN-capped**,
      on two independent blockers. *Biology:* every metric has a legitimate protocol occupying
      its extreme — deep/high-input libraries legitimately exceed 90% duplication,
      total-RNA/ribo-depletion legitimately retains rRNA, nuclear/FFPE/3' libraries are
      legitimately intron-dominated, non-model annotation legitimately leaves most tags
      unassigned. "Extreme" and "unusual protocol" are the same number, and the packs see no
      library-prep or annotation-quality signal that separates them. *Engineering:*
      `percent_duplication`/`percent_rRNA` (`rule_pack.py:303,309`, both already commented
      "slug unverified") are **absent from the repo's only real-shaped MultiQC report**
      (`demo/sample-run/results/multiqc/multiqc_data.json` carries only
      `uniquely_mapped_percent`, `percent_assigned`, `total_reads`) — FAIL severity on a
      metric that has never once arrived is severity on dead code. *Also:* the one genuinely
      broken case, `unassigned_fraction == 1.0`, is already caught more honestly by
      `RNASEQ_RULE_PACK`'s `assignment_rate fail_below: 40` on the did-it-run tier, so a
      second FAIL would be redundant rather than new signal.
    - **Not covered by this decision:** the annotation plausibility pack (a separate C7 M-track
      item with its own deferral trail) and the germline sex-check axis (hand-built from scalar
      constants, not a rule pack — unbandable by a data edit) both remain WARN-only.
  - **Caveat for signing users: re-verifying an affected *old* bundle can break its
    signature.** `verdict` is a pydantic `@computed_field` (`models.py:357-369`) and
    `canonical_record_bytes` is `record.model_dump(mode="json")` (`signing.py:63-64`), so the
    verdict is **inside the signed canonical payload** (verified: a WARN record canonicalizes
    to `"verdict":"warn"`). Re-verifying a bundle whose verdict changes under the new band
    recomputes different canonical bytes, and its Ed25519 signature no longer matches. The
    blast radius is **only** bundles whose verdict actually flips — i.e. somatic runs with an
    empty call set, which are broken runs by definition; every other bundle canonicalizes
    identically. This is a pre-existing property of **any** rule-pack edit, inherited unchanged
    from v0.35.0, and is disclosed rather than fixed: excluding `verdict` from the canonical
    payload would be a cross-cutting signature-contract change and its own slice.
  - **Honest scope.** Research-use. The floor is an **engineering tripwire** ("an empty call
    set is a broken run" — the same tier as `mean_coverage fail_below`), **not** a biological
    or clinical claim; this slice actively *refuses* the bands that would have over-claimed.
    A legitimately mutation-free targeted panel **would** FAIL — accepted with eyes open,
    because the engine has no target-type signal, the escalation is the narrowest possible,
    sarek's Mutect2 count is not PASS-filtered (so a genuinely 0-record VCF from a real run is
    a truncation artifact, not a biological result), and `--fail-on-verdict` is opt-in; the
    revisit trigger is the first real-world report of one. The failure is **reasoned, not
    observed**: the somatic assay has never run against real data — **no real nf-core/sarek run
    in CI**, verification rides injected fixtures — so this ships on the germline sibling as its
    existence proof, and its success criteria are test assertions, not field signal. UNVERIFIED
    is untouched and is never converted to FAIL. Test-first (RED→GREEN).
  - **Surfaced, not fixed (recommended next):** `RNASEQ_PLAUSIBILITY_PACK` is a **silent no-op
    on every real rnaseq run** — the same defect class as the single-cell pack fixed in the C3
    ingestion slice — and carries a live unit ambiguity (the pack declares 0–100 while Picard's
    native `PERCENT_DUPLICATION` is a 0–1 fraction and `qc_ingest.py:5-23` does a bare
    `float()` with no normalization). Likely higher user value than any FAIL band.

## [0.36.0] - 2026-07-15

### Added

- **`contig run` and `contig verify` gain an opt-in `--fail-on-verdict` flag that makes a
  verified **FAIL** verdict exit non-zero** — closing the "CLI exit-code wiring" follow-on
  that was deliberately deferred in v0.35.0 (the germline-plausibility-FAIL-severity slice
  noted "the `contig run`/`verify` exit code is unchanged … wiring that is a deliberate,
  separately-scoped, cross-cutting follow-on"). Until now no QC verdict, not even a FAIL,
  moved the exit code: a run that *completed* but whose science was broken (a structural
  FAIL, or a germline gross-implausibility FAIL — noise-level Ti/Tv, grossly-off het/hom,
  empty call set) still returned exit `0`, so any researcher wiring Contig into a shell
  script or CI step got a green result on a FAILed analysis. This gives the verdict teeth
  without changing anyone's defaults:
  - **Opt-in, FAIL-only.** When `--fail-on-verdict` is set and the run's reduced verdict is
    `FAIL`, the command exits `1` after rendering the report. `WARN`, `UNVERIFIED`, and
    `PASS` always exit `0` — `UNVERIFIED` in particular never converts "we couldn't check"
    into "it failed." A one-line reason (`Run <id> verdict is FAIL (--fail-on-verdict).`) is
    echoed to **stderr** on the verdict-driven exit.
  - **Default behavior is byte-identical to before.** Without the flag, exit codes, stdout,
    and `--json` payloads are unchanged; the flag reads the existing `record.verdict` (no
    recomputation, no new model field, no reproduce/signature-contract change).
  - **On `verify`, the flag composes with the existing checks.** A FAIL verdict ORs into the
    output-drift and signature-mismatch exit decision across all four sub-paths (no-checksums
    and has-checksums, text and `--json`) — any one non-zero ⇒ non-zero, including the former
    "nothing to verify" `return 0` path. Concordance still never affects the exit.
  - **Honest scope / deferred.** Only `FAIL` triggers non-zero — no `--fail-on-warn` or
    `--fail-on={fail,warn}` level argument (deferred). The exit code is `1`, reusing the
    crash idiom — no distinct science-FAIL code. No `verdict` key is added to the `verify
    --json` payload (deferred to keep it stable). `rerun`/`resume` inherit the default
    (`False`) and are unaffected, and the dashboard "Run test profile" launch path does not
    expose the flag yet. Test-first (RED→GREEN) for every behavior; **no real nf-core run in
    CI** — the gate is driven by the deterministic verdict reduction over synthetic fixtures.

## [0.35.0] - 2026-07-15

### Changed

- **Germline biological-plausibility checks gain their first FAIL severity — a grossly
  broken germline call set now FAILs the verdict, not just WARNs** (capability C3 follow-on;
  the "FAIL severity deferred" item the germline slices — Ti/Tv + het/hom (v0.3.0),
  variant-count (v0.32.0) — each left open "until calibrated on real data"). The germline
  `VARIANT_RULE_PACK` metrics were WARN-only, so a call set that is essentially noise
  (Ti/Tv ≈ 0.5, the signature of random/garbage calls) or an empty/near-empty call set
  produced only a WARN — easy to overlook, and inconsistent with the *did-it-run* QC packs
  (`mean_coverage fail_below`, methylseq, ampliseq, mag, scrnaseq) that already FAIL on
  gross failure through the exact same scorer. Three metrics now carry gross-implausibility
  FAIL bands:
  - **`ts_tv_ratio`:** `fail_below 1.2` / `fail_above 3.6` (the WARN band `1.8`–`2.4` is
    unchanged). A noise-level Ti/Tv (~0.5) FAILs; a legitimate WGS (~2.0) or WES (~3.0–3.3)
    call set stays PASS/WARN.
  - **`het_hom_ratio`:** `fail_below 1.0` / `fail_above 3.0` (WARN band `1.4`–`2.5`
    unchanged). The FAIL band is deliberately wider than the WARN band — het/hom is more
    population/capture-sensitive than Ti/Tv, so only a grossly-off ratio trips it.
  - **`variant_count`:** `fail_below 1` only — **no `fail_above`**. An essentially-empty
    call set (broken/truncated calling) is now a **FAIL**, not the prior WARN — a strictly
    stronger, correct signal (previously the always-int 0 rode the band as a soft WARN). The
    `warn_above 20_000_000` ceiling stays a soft WARN, so a large joint-called cohort is
    never FAILed for being legitimately large.
  - **Pure data change; the whole verdict path is unchanged.** Only the three
    `VARIANT_RULE_PACK` rule dicts changed — the scorer (`_status_for`), evaluator
    (`evaluate_variant_plausibility`), verdict reducer (`overall_verdict`), report,
    `contig show --explain`, provenance, and dashboard consume it unchanged. A failing
    germline plausibility result now drives `record.verdict` → FAIL wherever the verdict is
    surfaced. An empty germline VCF yields `variant_count` FAIL **and** `ts_tv`/`het_hom`
    UNVERIFIED (the ratios are uncomputable with no variants); FAIL dominates, so the overall
    verdict is FAIL.
  - **Honest framing.** The bands are **WES-safe gross-implausibility engineering
    tripwires** (same honesty tier as `mean_coverage fail_below`, literature-grounded Ti/Tv
    ~2.0 WGS / ~3.0–3.3 WES / noise ~0.5), **not** a clinical or biological/pathogenicity
    claim. **Verdict-only:** the `contig run`/`verify` exit code is unchanged — no QC verdict,
    including pre-existing FAIL packs like `mean_coverage`, moves the exit code today; wiring
    that is a deliberate, separately-scoped, cross-cutting follow-on. **Still WARN-only /
    FAIL deferred:** the somatic, RNA-seq, RNA-seq-composition, and annotation plausibility
    packs, and the germline sex-check axis. Test-first with synthetic inline VCF fixtures —
    **no real nf-core/sarek run in CI**. **Deferred:** CLI exit-code wiring; capture-type-aware
    (WGS/WES/panel) bands; tighter calibration on real cohorts (the WES-safe bands are
    deliberately gross-only); and FAIL severity for the non-germline plausibility packs.

## [0.34.0] - 2026-07-14

### Added

- **Strelka2-native tumor-VAF plausibility — independent cross-caller corroboration of
  somatic VAF** (capability C4 follow-on, closing the "Strelka2-native VAF (tier-count
  derivation — non-Mutect2 VCFs degrade to UNVERIFIED)" item deferred by the v0.14.0
  VAF-plausibility slice). The somatic verdict's biological-plausibility axis previously
  derived tumor VAF from Mutect2's VCF alone; a Strelka2-only or Strelka2-and-Mutect2 run now
  gets a **second, independently-computed** `strelka_median_vaf` metric that fires **alongside**
  the existing Mutect2 `median_vaf` — two callers converging on a similar tumor VAF is stronger
  evidence than one, without either metric depending on the other.
  - **VAF derived from Strelka2's own tier counts, not Mutect2's `AF`/`AD`.** Strelka2 emits no
    `AF`/`AD` FORMAT field; a new `verification/strelka_vaf.py` parses its documented tier1
    ratio directly: for SNVs, `tier1({ALT}U) / (tier1({REF}U) + tier1({ALT}U))` over the
    `AU`/`CU`/`GU`/`TU` FORMAT fields; for indels, `tier1(TIR) / (tier1(TAR) + tier1(TIR))` over
    `TAR`/`TIR`. The tumor sample column is resolved by the **literal column name `TUMOR`** on
    `#CHROM` (Strelka2 emits no `##tumor_sample=` header the way Mutect2 does, so the existing
    header-based resolver doesn't apply here — never a positional guess). A pure, stdlib,
    streaming parser pools tumor VAFs across the **SNV and indel VCFs together** into one median
    (sarek's `*.somatic_snvs*`/`*.somatic_indels*` split), matching how Strelka2 itself is always
    consumed as a pair.
  - **A `strelka_median_vaf` rule riding the existing `SOMATIC_PLAUSIBILITY_PACK`.** WARN-capped
    (`warn_below 0.05`, `warn_above 0.95`, no `fail_*`), deliberately reusing `median_vaf`'s
    uncalibrated band verbatim rather than deriving a new one, and evaluated by its own
    `evaluate_strelka_vaf_plausibility()` over a `by_metric` dict containing only this key — so it
    emits `strelka_median_vaf:<TUMOR>` without ever re-emitting Mutect2's `median_vaf`/
    `somatic_variant_count` rules from the same shared pack. (`evaluate_somatic_plausibility`'s
    None-handling loop now skips any rule it has no metric for, rather than mishandling the new
    shared rule it doesn't track.)
  - **Wired into the somatic `_discover_qc` gate by reusing `select_caller_vcfs`** — the same
    locator the Strelka2-vs-Mutect2 concordance gate already uses, so a "strelka" caller directory
    is resolved once, the same way, everywhere. Three outcomes: a uniquely-resolved Strelka2
    SNV+indel pair → the `strelka_median_vaf` metric; a Strelka2 VCF present but the layout is
    non-unique or mismatched with Mutect2's pair (the same condition `select_caller_vcfs` flags
    for concordance) → one honest UNVERIFIED, never a silent pass; no Strelka2 VCF at all → a
    silent skip (structural QC already owns a genuinely-missing output).
  - **Honest contract, identical to every sibling C3/C4 plausibility slice.** At most WARN, never
    FAIL, never changes the `contig run`/`verify` exit code. UNVERIFIED (never a false pass) when
    no Strelka2 VCF is found, no literal `TUMOR` column is present, or no record yields a
    derivable tier-count ratio; omit-never-guess per record. Verdict-only: no new
    `FailureClass`, model, persisted record, dependency, or reproduce-contract change; no raw-read
    egress (parses VCFs already on the user's compute); research-use corroboration signal, never
    a cancer diagnosis. Test-first with synthetic Strelka2 tier-FORMAT VCF fixtures — **no real
    nf-core/sarek or samtools run in CI**. **Deferred:** FAIL severity and band calibration on
    real tumor–normal cohorts; the cross-column swapped-pair smell test; panel-of-normals /
    germline-resource reference wiring; a dashboard "corroborated by" surface for somatic VAF; and
    QSS/QSI quality-score plausibility.

## [0.33.0] - 2026-07-13

### Added

- **Turnkey single-cell cross-tool count concordance autorun** (`contig verify
  --concordance-sc-counts-auto`) (capability C1, single-cell slice — the autorun follow-on
  to the user-supplied `--concordance-sc-counts` shipped v0.32.0, mirroring how the germline
  autorun `--concordance-auto` (v0.4.0) followed `--concordance-vcf` and the RNA-seq kallisto
  autorun `--concordance-counts-auto` (v0.24.0) followed `--concordance-counts`). Contig now
  produces the **second** single-cell count matrix itself: given `--reads <sample sheet>`, a
  prebuilt STAR genome `--index`, and a barcode `--whitelist`, it runs a second, independent
  single-cell quantifier (**STARsolo**) behind an injectable seam and corroborates the run's
  own `scrnaseq` count matrix against STARsolo's — no user-produced second matrix required.
  This is where the single-cell concordance axis gains turnkey value (the v0.32.0 slice
  acknowledged single-cell users may not have a second matrix on hand). Slices:
  - A new `verification/sc_count_quantifier.py` mirrors the RNA-seq `count_quantifier.py`
    seam: an `ScCountQuantifier` type, a pure `starsolo_command` argv builder (asserted in
    tests, never executed), chemistry presets (`10xv3` default, `10xv2`), a pure
    `readfiles_order` that pins STARsolo's `(cDNA, CB)` `--readFilesIn` order — the reverse of
    the sample sheet's `(fastq_1=CB, fastq_2=cDNA)`, the classic STARsolo footgun — and a
    default `run_starsolo_quantifier` that validates inputs, shells out, locates the Solo
    `matrix.mtx`, and re-raises every failure (missing binary/reads/index/whitelist, nonzero
    exit, missing output) as one named `SecondScQuantifierError`. **STARsolo is never run in
    CI** (the subprocess path is covered only by a manual gate); tests inject a fake
    quantifier. STARsolo emits gene-level counts natively, so — unlike the kallisto seam —
    there is **no transcript→gene collapse step**; the returned `matrix.mtx` feeds the
    **shipped** v0.32.0 `load_sc_matrix` → `evaluate_sc_count_concordance` core unchanged
    (the scientifically load-bearing pseudobulk collapse is already CI-tested from v0.32.0).
  - `verify` CLI wiring, contract-faithful: `--concordance-sc-counts-auto` (with new
    `--whitelist` and `--chemistry` defaulting to `10xv3`; **reuses** `--reads`/`--index`,
    whose help now names both the kallisto-index and STAR-genome-dir uses) is **mutually
    exclusive** with the other five concordance flags. The dispatch resolves the run's own
    primary matrix **first** (assay-gated to `scrnaseq`, `filtered/` over `raw/`) and skips
    without ever spawning STARsolo when it is absent; then validates the three inputs; then
    runs the injected-or-default quantifier in a temp dir. Same honest contract as every
    concordance slice: **at most WARN, never changes the `contig verify` exit code**, and
    `unverified` (never a false pass) below the 10-shared-gene floor. Every unrunnable path —
    a non-`scrnaseq` run, a missing `--reads`/`--index`/`--whitelist`, a quantifier failure,
    or a malformed sample sheet — prints a clear skip note and emits zero checks. The
    corroboration line **names STARsolo** as the second tool (a backward-compatible
    `second_name` on `evaluate_sc_count_concordance`; the v0.32.0 user-supplied path is
    unchanged), rather than an opaque `matrix.mtx vs matrix.mtx`.
  - **Honest scope.** Verify-time flag only — additive to the verdict, no new `FailureClass`,
    model, persisted record, dependency, or exit-code/reproduce-contract change. No raw-read
    egress (STARsolo runs on the user's compute; only gene totals are compared). Research-use
    corroboration, never a clinical claim. Test-first with synthetic MatrixMarket fixtures and
    an injected fake quantifier — **no real STARsolo or nf-core/scrnaseq run in CI**.
    **Deferred:** auto-deriving reads/index/whitelist/chemistry from the run record (Contig
    persists no chemistry/whitelist/aligner today); cell-count and cluster-stability agreement
    (need a downstream clustering step Contig doesn't run); FAIL severity until the bands are
    calibrated on real data (the pseudobulk-washout of benign cross-tool cell-calling
    divergence is an unproven engineering assumption — hence WARN-only); a dashboard
    "corroborated by" surface; and `.h5ad`/AnnData second-matrix parsing.

## [0.32.0] - 2026-07-12

### Added

- **Germline variant-count plausibility — the verdict now catches a grossly-off
  call-set size** (capability C3, biological-plausibility verification; the
  "expected variant-count band" germline slice named at `CAPABILITY_ROADMAP.md`
  C3). A completed germline (`variant_calling`) run whose primary VCF has a
  near-zero count (failed / truncated calling) or an absurd count previously passed
  the verdict silently; the germline plausibility verdict now gains a WARN-capped
  **count-band axis** so the gross failure surfaces to the researcher without ever
  blocking a legitimate run. Details:
  - **`variant_count` on `VariantMetrics`.** Computed as `len(parse_vcf(vcf))` — the
    number of **distinct primary-sample `(CHROM, POS, REF, ALT)` sites** — reusing
    the same `concordance.parse_vcf` reader that already feeds `ts_tv`/`het_hom`, so
    a duplicated site line dedups to one, a multiallelic (comma-ALT) record is a
    single site, and the count is **not** PASS-filtered. It is always an `int` (0 for
    a header-only VCF), so unlike the two ratios it is always computable.
  - **One WARN-only `variant_count` rule in `VARIANT_RULE_PACK`** (`warn_below: 10`,
    `warn_above: 20_000_000`, no `fail_*`), riding the existing germline plausibility
    gate — no `runner`/`_discover_qc` edit. The wide band is an uncalibrated
    engineering default; `warn_above` is a **soft "absurd-count" tripwire, not a
    validated ceiling**, so a very large joint-called cohort tripping it is an honest
    "unusually large, check it" WARN, never a block. Wired into
    `evaluate_variant_plausibility` by adding `"variant_count"` to
    `_PLAUSIBILITY_CHECKS` and `metrics.variant_count` to `by_metric`, so it flows
    through the shared `evaluate()` alongside `ts_tv_ratio:<sample>` /
    `het_hom_ratio:<sample>` as `variant_count:<sample>` with `expected_range`
    `[10, 20000000]`.
  - **Honest contract, identical to every sibling C3 slice.** At most WARN, never
    FAIL, never changes the `contig run`/`verify` exit code. Because the count is
    always an int, a **real 0 rides the band as a WARN and never routes into the
    `ts_tv`/`het_hom` UNVERIFIED branch** — the key guarantee that an empty call set
    is not mistaken for "nothing to check". No VCF at all skips silently (structural
    QC owns a genuinely-missing output). Verdict-only: no new module, `FailureClass`,
    model, provenance/persisted record, dependency, or dashboard card; no exit-code
    change. Local, deterministic, **no raw-read egress** (reads a small VCF already on
    the user's compute). Research-use sanity signal, never a clinical judgement.
    Test-first with synthetic inline VCF fixtures — **no real nf-core/sarek run in
    CI**. **Deferred:** FAIL severity and band calibration on real cohorts,
    capture-aware bands (panel/WES/WGS differ by orders of magnitude), per-sample
    counts for multi-sample VCFs, a dashboard card, and the C6 fold-in.

- **Single-cell RNA-seq cross-tool count concordance** (`contig verify
  --concordance-sc-counts <matrix>`) (capability C1, single-cell slice — the last wired
  assay without a concordance axis; named as deferred in every prior C1 list at
  `CAPABILITY_ROADMAP.md:58,73,117`). A completed `scrnaseq` run's verdict gains a
  cross-tool corroboration axis: the run's own cell×gene count matrix is corroborated
  against a user-supplied **second** single-cell matrix from a different quantifier, so a
  tool-specific quantification error (wrong chemistry, bad barcode whitelist, aligner bias)
  that passes cell-QC and structural checks but skews the counts is caught. This applies the
  shipped C1 concordance primitive — already live for germline, bulk RNA-seq, somatic, and
  annotation — to single-cell for the first time. Slices:
  - **Dict-based concordance seam (pure refactor).** `verification/count_concordance.py`
    grew `stats_from_counts(a, b)` and `results_from_counts(a, b, name_a, name_b)` that
    operate on already-parsed `{gene_id: float}` dicts; the path-based `count_concordance`/
    `concordance_results` became thin wrappers over them. Behavior-preserving — the RNA-seq
    concordance path is byte-identical — so the single-cell path can feed **pseudobulk**
    dicts into the exact same Spearman / fraction-agreeing / shared-gene-floor math.
  - **Stdlib MatrixMarket loader → per-gene pseudobulk.** A new `verification/
    sc_count_concordance.py` with `load_mtx_pseudobulk` reads a `matrix.mtx`(.gz) triplet —
    resolving its sibling `features.tsv`/`barcodes.tsv`(.gz), keying genes by **column 1**
    of features (10x id/name/type; sole token when single-column), inferring the gene axis
    by matching the MatrixMarket dimensions against the feature/barcode counts (an ambiguous
    or mismatched shape → honest error, never an arbitrary transpose) — and **sums each
    gene's counts across all cells** to `{gene_id: pseudobulk_total}`, feeding the reused
    core. It is **pure-stdlib** (no `scipy`/`numpy`/`anndata`/`h5py`; the repo's
    no-new-dependency contract holds). `load_sc_matrix` sniffs by extension: a `.mtx`(.gz)
    path → the triplet loader, anything else → the existing dense-TSV `parse_count_matrix`,
    so the second matrix may be a raw triplet **or** a pre-collapsed pseudobulk gene TSV.
  - **`verify` CLI wiring, contract-faithful.** `--concordance-sc-counts` is mutually
    exclusive with the other four concordance flags; the primary matrix is located by
    `rglob("*matrix.mtx*")` **preferring a `filtered/` over a `raw/` copy**, assay-gated to
    `scrnaseq`. Same honest contract as every concordance slice: **at most WARN, never
    changes the `contig verify` exit code**, and `unverified` (never a false pass) below the
    10-shared-gene floor. Every uncomputable path is explicit — a located-but-unparseable
    matrix (missing sibling, malformed, ambiguous orientation) yields one
    `sc_count_concordance` **UNVERIFIED**; no `matrix.mtx` at all (e.g. an `.h5ad`-only
    simpleaf run) prints an honest skip note and emits nothing; a non-`scrnaseq` run skips.
  - **Honest scope.** Verify-time flag only — additive to the verdict, no new `FailureClass`,
    model, persisted record, dependency, or exit-code/reproduce-contract change. No raw-read
    egress (compares gene totals on the user's compute). Research-use corroboration, never a
    clinical claim. Test-first with synthetic MatrixMarket fixtures — **no real
    nf-core/scrnaseq, STARsolo, or Cell Ranger run in CI**. **Deferred:** `.h5ad`/AnnData
    parsing (would add an `anndata`/`h5py` dependency — an `.h5ad`-only run degrades to an
    honest skip); the second-quantifier **autorun** (`--concordance-sc-counts-auto`, mirroring
    the RNA-seq kallisto autorun — a second single-cell quantifier's barcode/cell-calling has
    no clean CI story, so turnkey value waits on it); cell-count and cluster-stability
    agreement (need a downstream clustering step Contig doesn't run); FAIL severity until the
    bands are calibrated on real data; and a dashboard "corroborated by" surface.

## [0.31.0] - 2026-07-12

### Added

- **RNA-seq read-composition plausibility — the verdict now catches gDNA
  contamination / failed enrichment** (capability C3, biological-plausibility
  verification; the "exonic-mapping fraction" RNA-seq slice named at
  `CAPABILITY_ROADMAP.md` C3 and deferred by the v0.6.0 rnaseq slice). A completed
  RNA-seq run's verdict gains a **read-composition axis** derived from where aligned
  reads fall relative to gene annotation — the classic smell for genomic-DNA
  contamination, failed poly-A / rRNA depletion, or a broken annotation, which passes
  alignment QC today but yields a biologically meaningless expression matrix. Slices:
  - **Dedicated RSeQC-artifact parser (`verification/rnaseq_metrics.py`).** The
    composition fractions are **not** in Contig's MultiQC general-stats ingest (verified
    against a real `multiqc_data.json`), so a new stdlib-only, pure
    `parse_read_distribution` reads RSeQC's own `read_distribution.txt` — the artifact
    `nf-core/rnaseq@3.26.0` writes by default under
    `results/star_salmon/rseqc/read_distribution/` — mirroring the shipped
    scrnaseq/methylseq/ampliseq/mag dedicated-gate pattern. It computes three per-sample
    fractions from the `Tag_count` column: `exonic_fraction` =
    `(CDS_Exons + 5'UTR_Exons + 3'UTR_Exons) / Total Assigned Tags`, `intronic_fraction`
    = `Introns / Total Assigned Tags`, and `unassigned_fraction` =
    `(Total Tags − Total Assigned Tags) / Total Tags`. The two denominators are
    intentional (exonic/intronic are shares *of assigned tags*; unassigned is a share *of
    all tags*), and the nested/overlapping `TSS_up_*`/`TES_down_*` windows are never
    summed (they would double-count). **Omit-never-guess:** any metric whose inputs are
    absent/non-numeric or whose denominator is zero (or would go negative) is omitted from
    the result, never coerced to 0.
  - **A WARN-capped `RNASEQ_COMPOSITION_PACK` + additive `_discover_qc` gate.** Three
    checks (`exonic_fraction` warn-below 0.50, `intronic_fraction` warn-above 0.30,
    `unassigned_fraction` warn-above 0.30) — uncalibrated engineering defaults, kept loose
    so a normal run reads PASS (verified against a real yeast test run: exonic ≈ 0.9998,
    intronic ≈ 0.0002, unassigned ≈ 0.11). The pack is deliberately **not** registered in
    `_RULE_PACKS`. A new locator prefers the published `results/` copy over an intermediate
    `work/` copy (never reading a pre-final write). The gate is **additive** — a separate
    `assay == "rnaseq"` block alongside the existing MultiQC-fed plausibility gate;
    `rnaseq` stays **out** of `_DEDICATED_METRIC_ASSAYS`, so the alignment/dup/rRNA checks
    keep their MultiQC path.
  - **Honest contract, identical to every sibling C3 slice.** At most WARN, never FAIL,
    never changes the `contig run`/`verify` exit code. A located-but-unparseable artifact
    yields one explicit `rnaseq_composition_qc:<sample>` **UNVERIFIED** (never a false
    pass); no artifact at all skips silently (structural QC owns a genuinely-missing
    output; `read_distribution` is not added to the structural manifest). Additive to the
    verdict only: no new `FailureClass`, model, persisted-record, or dependency; no
    exit-code change. Local, deterministic, **no raw-read egress** (parses a small QC text
    file already on the user's compute). Research-use sanity signal, never a clinical
    judgement. Test-first with a committed realistic RSeQC fixture — **no real
    nf-core/rnaseq run in CI**. **Deferred:** gene-body-coverage evenness (needs the
    non-default RSeQC `geneBody_coverage` module), FAIL severity until the bands are
    calibrated on real human RNA-seq, cross-sample composition aggregation, and a dashboard
    card.

## [0.30.0] - 2026-07-11

### Added

- **Germline sex-check plausibility — the verdict now catches sex-chromosome
  discordance** (capability C3, biological-plausibility verification; the
  "sex-check" germline slice named at `CAPABILITY_ROADMAP.md` C3). A germline
  (`variant_calling`) run's own VCF is now checked for karyotypic-sex
  consistency, on a path independent of MultiQC and reusing the same
  `concordance.parse_vcf` reader that already feeds `ts_tv`/`het_hom`. Slices:
  - **Inference core (`verification/sex_plausibility.py`).** Two independent
    signals are derived from one VCF: an **X-heterozygosity ratio** over
    biallelic, non-missing, **non-PAR** X genotypes, and **Y-variant presence**
    over non-PAR Y sites. Pseudoautosomal regions are excluded from the X-het
    denominator using standard GRCh37/GRCh38 PAR coordinates, with the assembly
    detected from the VCF's own `##contig=<ID=…X,length=…>` header (tolerant of
    the multi-attribute `assembly=`/`md5=`/`species=` headers real GATK/sarek
    emits); when the build can't be determined it falls back to **unmasked**
    X-het and says so, never guessing a build. The load-bearing honesty is that
    **Y-absence is uninformative** (a Y-less reference and a female sample are
    indistinguishable from the VCF alone), so Y-presence only ever *corroborates*
    a male call and never forces a discordant one.
  - **A single WARN-capped `sex_plausibility` verdict + informational
    `x_het_ratio`.** X-het is bimodal (near-0 for XY, ~autosomal for XX), so the
    call is derived in code rather than a single threshold band: low X-het → "XY",
    high X-het with no Y → "XX", high X-het **with** Y present (or a mid-band
    ratio) → **"discordant" → WARN** (naming the conflict: possible aneuploidy,
    contamination, or sample swap). Too few X sites, or no X contig, →
    **UNVERIFIED, never a false pass**. At most WARN, never FAIL, and it **never
    changes the `contig run`/`verify` exit code** (exit is decided only by
    pipeline success). Wired into `_discover_qc` gated strictly to
    `variant_calling`, reusing the same located primary VCF as the existing
    germline plausibility checks.
  - **Inferred sex captured into provenance.** A new `SexInference` record is
    attached to the `RunRecord` at finalize (germline-gated, mirroring the C5
    `ReferenceIdentity` pattern — `Optional`, no validator, so pre-slice bundles
    load with `None`), located via the **same** discovery path as the QC verdict
    so the verdict and the provenance can never disagree. Rendered honestly in
    `contig methods` and the HTML provenance panel ("undetermined" for the
    indeterminate case — never a fabricated call — and always labelled a
    research-use inference, never a clinical/karyotype determination), and it
    **round-trips through the reproduce bundle** with pre-slice back-compat.
  - **Research-use only**; thresholds are uncalibrated engineering defaults, kept
    loose and WARN-capped so a normal XX or XY run reads PASS. Test-first (synthetic
    gzipped VCF fixtures, no real nf-core/sarek run in CI). **Deferred:**
    reported-vs-inferred concordance (needs a sample-sheet sex column that does not
    exist today — this slice catches only cross-sex swaps and aneuploidy),
    per-sample sex for multi-sample VCFs (first-sample only, inherited), FAIL
    severity until the bands are calibrated on real data, and a dashboard card.

## [0.29.0] - 2026-07-11

### Added

- **Mag QUAST + CheckM QC ingestion — the dormant shotgun-metagenomics verdict
  now fires** (capability C3, biological-plausibility verification — the `mag`
  slice of `assay-qc-verdict-fires`, fast-follow #3 on the seam the methylseq
  and ampliseq slices established; this closes out the seam). `mag` already
  carried a biological QC pack (`MAG_RULE_PACK`: assembly N50, bin
  completeness, bin contamination), but like methylseq/ampliseq it **silently
  no-oped on every real run**: the exact MultiQC general-stats slug for these
  metrics is unverified, and `nf-core/mag` does not reliably route them there.
  This slice makes the checks **fire** by ingesting QUAST's and CheckM's own
  on-disk stats artifacts:
  - A new `verification/mag_metrics.py` with deterministic, stdlib-only
    parsers: `parse_quast_report` (header-driven `transposed_report.tsv`;
    `n50` from the `N50` column, case-insensitive) and `parse_checkm_summary`
    (header-driven CheckM summary table; `completeness`/`contamination` from
    the `Completeness`/`Contamination` columns, case-insensitive). The
    **entity key is the BIN**, not the sample — matching `MAG_RULE_PACK`'s own
    test fixture and nf-core/mag's per-bin QUAST/CheckM output. Like
    ampliseq's DADA2 artifacts, both files are multi-bin, so both parsers
    return `{bin: {slug: value}}` directly for every bin/assembly row in the
    file. A metric that is absent or non-numeric is omitted everywhere, never
    coerced to 0.
  - A dedicated `_discover_qc` gate (`assay == "mag"`, mirroring the ampliseq
    gate) whose `_locate_mag_qc` rglobs `transposed_report.tsv` and the CheckM
    summary and **merges the two parsers' per-bin dicts by bin id**
    (`setdefault(bin, {}).update(...)`) before evaluating `MAG_RULE_PACK`. A
    located bin yielding zero usable metrics emits one explicit
    `mag_qc:<bin>` **UNVERIFIED** rather than a silent no-op; no artifact at
    all skips silently (structural QC owns a missing required output). A bin
    with only `transposed_report.tsv` (no CheckM summary) evaluates
    `assembly_n50` and is **not** forced into a false whole-bin UNVERIFIED.
  - **Single authoritative source**: `mag` joins `methylseq`/`ampliseq` in
    `_DEDICATED_METRIC_ASSAYS`, so a check can never double-emit if a future
    MultiQC build ever carries a matching slug. `mag` stays registered in
    `_RULE_PACKS`/`rule_pack_for` (unchanged contract) — only metric
    *delivery* moved to the dedicated gate.
  - CheckM only this slice; BUSCO as an alternate completeness source is
    deferred. No band re-calibration (illustrative engineering defaults,
    unchanged); no change to `methylseq`, `ampliseq`, `scrnaseq`, `rnaseq`, or
    the variant paths. Additive to the verdict only: no `FailureClass`,
    model, or persisted-record change; no new dependency. Local,
    deterministic, no raw-read egress. Built test-first with a committed
    realistic QUAST + CheckM fixture set — no real `nf-core/mag` run in CI.

- **Methylseq bisulfite QC ingestion — the dormant methylation verdict now fires**
  (capability C3, biological-plausibility verification — the methylseq slice of
  `assay-qc-verdict-fires`, the same seam as v0.21.0's single-cell fix; `ampliseq`
  and `mag` remain hollow, deferred fast-follows on this seam). The `methylseq` assay
  already carried a biological QC pack (`METHYLSEQ_RULE_PACK`: mapping efficiency,
  duplication rate, bisulfite conversion), but it **silently no-oped on every real
  run**: the pack's metrics are only read from MultiQC general-stats under a slug the
  pack itself flagged "unverified," and `nf-core/methylseq` does not reliably route
  Bismark's per-sample fields there. Because `evaluate()` skips any absent metric,
  the methylation verdict degraded to UNVERIFIED while reading as "wired." This
  slice makes the checks **fire** by ingesting Bismark's own on-disk reports:
  - A new `verification/methylseq_metrics.py` with deterministic, stdlib-only
    parsers: `parse_bismark_alignment_report` (`Mapping efficiency:` from
    `*_PE_report.txt` / `*_SE_report.txt`), `parse_bismark_dedup_report`
    (`... duplicated alignments removed:` from `*.deduplication_report.txt`), and
    `parse_bismark_conversion_report`, which emits `percent_bs_conversion` **only**
    when a recognizable conversion/control-rate line is present — a standard
    splitting report (methylation-context percentages only, no conversion field)
    correctly omits it rather than guessing. A metric that is absent or non-numeric
    is omitted everywhere, never coerced to 0.
  - A dedicated `_discover_qc` gate (`assay == "methylseq"`, mirroring the scrnaseq
    gate) that locates Bismark's alignment/deduplication/splitting reports under the
    run, derives a per-sample id, **merges all report kinds for the same sample**
    into one metric dict (no double-count), and evaluates `METHYLSEQ_RULE_PACK`. A
    located artifact yielding zero usable metrics emits one explicit
    `methylseq_qc:<sample>` **UNVERIFIED** rather than a silent no-op; no artifact at
    all skips silently (structural QC owns a missing required output). A sample with
    only a partial report set (e.g. alignment only, the common single-report case)
    evaluates the checks it can and is **not** forced into a false whole-sample
    UNVERIFIED.
  - **Single authoritative source**: a new `_DEDICATED_METRIC_ASSAYS` set skips the
    generic MultiQC pack path for `methylseq`, so a check can never double-emit if a
    future MultiQC build ever happened to carry a matching slug. `methylseq` stays
    registered in `_RULE_PACKS`/`rule_pack_for` (unchanged contract) — only metric
    *delivery* moved to the dedicated gate.
  - No band re-calibration (illustrative engineering defaults, unchanged); no
    change to `ampliseq`/`mag` (still hollow), `scrnaseq`, `rnaseq`, or the variant
    paths. Additive to the verdict only: no `FailureClass`, model, or persisted-record
    change; no new dependency. Local, deterministic, no raw-read egress (parsers
    read small report text files on the user's compute). Built test-first with a
    committed realistic Bismark report fixture set — no real `nf-core/methylseq` run
    in CI.

- **Ampliseq DADA2 QC ingestion — the dormant amplicon verdict now fires**
  (capability C3, biological-plausibility verification — the `ampliseq` slice of
  `assay-qc-verdict-fires`, fast-follow #2 on the seam the methylseq slice
  established; `mag` remains hollow, deferred). `ampliseq` already carried a
  biological QC pack (`AMPLISEQ_RULE_PACK`: DADA2 read retention, ASV count,
  sample read depth), but like methylseq it **silently no-oped on every real
  run**: the exact MultiQC general-stats slug for these metrics is unverified,
  and `nf-core/ampliseq` does not reliably route them there. This slice makes the
  checks **fire** by ingesting DADA2's own on-disk stats artifacts:
  - A new `verification/ampliseq_metrics.py` with deterministic, stdlib-only
    parsers: `parse_dada2_overall_summary` (header-driven TSV; `input_reads` from
    the `input` column, `percent_retained` = `nonchim / input * 100`, omitted when
    `input` is zero/absent/non-numeric; column names matched case-insensitively
    with common nf-core/ampliseq naming variants tolerated) and `parse_asv_table`
    (rows=ASVs, columns=samples; `asv_count` = number of ASV rows with a non-zero
    count in a sample's column, with `sequence`/id/taxonomy metadata columns
    excluded by name and, as a second guard, by failing to parse as numeric). The
    **structural difference from methylseq's one-file-per-sample Bismark
    reports**: DADA2's artifacts are multi-sample files, so both parsers return
    `{sample: {slug: value}}` directly for every sample in the file. A metric
    that is absent or non-numeric is omitted everywhere, never coerced to 0.
  - A dedicated `_discover_qc` gate (`assay == "ampliseq"`, mirroring the
    methylseq gate) whose `_locate_ampliseq_qc` rglobs `overall_summary.tsv` and
    the ASV table and **merges the two parsers' per-sample dicts by sample key**
    (`setdefault(sample, {}).update(...)`) before evaluating
    `AMPLISEQ_RULE_PACK`. A located sample yielding zero usable metrics emits one
    explicit `ampliseq_qc:<sample>` **UNVERIFIED** rather than a silent no-op; no
    artifact at all skips silently (structural QC owns a missing required
    output). A sample with only `overall_summary.tsv` (no ASV table) evaluates
    read-retention and read-depth and is **not** forced into a false
    whole-sample UNVERIFIED.
  - **Single authoritative source**: `ampliseq` joins `methylseq` in
    `_DEDICATED_METRIC_ASSAYS`, so a check can never double-emit if a future
    MultiQC build ever carries a matching slug. `ampliseq` stays registered in
    `_RULE_PACKS`/`rule_pack_for` (unchanged contract) — only metric *delivery*
    moved to the dedicated gate.
  - No band re-calibration (illustrative engineering defaults, unchanged); no
    change to `mag` (still hollow), `scrnaseq`, `rnaseq`, `methylseq`, or the
    variant paths. Additive to the verdict only: no `FailureClass`, model, or
    persisted-record change; no new dependency. Local, deterministic, no
    raw-read egress. Built test-first with a committed realistic DADA2 stats
    fixture set — no real `nf-core/ampliseq` run in CI.

## [0.28.0] - 2026-07-11

### Added

- **Research-use variant annotation: surface + cache/build provenance** (capability
  C7, M5 — the surfacing and reproduce-provenance follow-on to M4's VEP-vs-SnpEff
  concordance). Two of M5's three sub-parts shipped; the third (C6 eval-corpus
  fold-in) remains **DEFERRED**. Slices:
  - **"Corroborated by" line across all four surfaces.** A new pure helper
    `verification/annotation_surface.py::corroborated_by_line` *reads* M4's already-
    computed `consequence_concordance` and `gene_symbol_concordance` results off the
    record (it never recomputes concordance) and renders a single line, e.g.
    *"Corroborated by VEP and SnpEff: 47/50 consequences agree (0.94); gene symbols
    45/50 (0.90, informational)."* The gene-symbol half is explicitly marked
    **informational** (mirroring M4's always-PASS treatment) and is omitted when
    absent; the whole line is omitted — returns `None` — whenever consequence
    concordance is absent or UNVERIFIED (only one annotator ran, annotation absent,
    too few shared variants), so it never manufactures corroboration that M4 didn't
    establish. The line is surfaced on the **text report**, the **HTML report**,
    `contig methods`, and the **Next.js dashboard** concordance card.
  - **Annotation cache/build provenance, captured and round-tripped.**
    `AnnotationProvenance` gains a `db_version` field, parsed honestly from the VCF
    header: the VEP `cache="…"` token (basename of the cache path, e.g. `110_GRCh38`)
    and the SnpEff genome token (from `##SnpEffCmd`, e.g.
    `GRCh38.105`); absent → `None`, never fabricated. It is labelled **"cache/build"**
    everywhere it renders — *not* "database version" — because it is the annotator's
    cache/build identifier, not a per-database (ClinVar/gnomAD) release. Rendered in
    `contig methods`, the HTML annotation-identity provenance panel, and the dashboard,
    and it **round-trips through the reproduce bundle** (write → load) with pre-M5
    **back-compat**: legacy bundles with no `db_version` key load and default to `None`.
  - **Honest scope.** Surfacing and provenance only — Contig reads and displays M4's
    corroboration signal and the annotator cache/build, and adjudicates nothing new;
    still research-use only, never a pathogenicity/clinical verdict. Test-first with
    synthetic CSQ/ANN and header fixtures; **no real VEP/SnpEff/sarek run in CI**.
    **Deferred (M5's third sub-part):** folding annotation concordance/plausibility
    outcomes into the C6 eval corpus — blocked pending a labeling design for the
    unlabeled annotation signals. With M5's surface + provenance shipped, the C7
    annotation assay's remaining open item is that eval fold-in (and the standing
    research-*prioritization* follow-on, deliberately out of scope).

### Fixed

- **Annotation cache/build header parsing verified against real sarek 3.5.1 output**
  (#13). The M5 SnpEff parser carried an invented `##SnpEffGenomeVersion=` header
  branch that real SnpEff never emits; it is removed. SnpEff writes the genome DB only
  on `##SnpEffCmd` (the first positional token after `SnpEff␣␣`, e.g. `GRCh38.105` for
  sarek 3.5.1's pinned SnpEff 5.1), which the retained branch parses correctly past any
  leading flags; the VEP `cache=` basename parser (`113_GRCh38` for ensembl-vep 113.0)
  was already correct. The provenance fixtures are now realistic sarek-3.5.1 headers
  rather than synthetic placeholders. Verify-only — no behaviour change beyond removing
  dead code; still no real VEP/SnpEff/sarek run in CI.

## [0.27.0] - 2026-07-10

### Added

- **Research-use variant annotation: VEP-vs-SnpEff concordance** (capability C7, M4 —
  the cross-tool corroboration axis for the annotation assay, on both `variant_calling`
  and `somatic_variant_calling`). This applies the C1 concordance primitive to
  annotation: a second independent annotator runs on the same call set and their
  per-variant agreement corroborates that annotation ran sanely. Slices:
  - **Enable SnpEff alongside VEP.** The two variant assays' `default_params.tools`
    widen from `…,vep` to `…,vep,snpeff` (germline `haplotypecaller,vep,snpeff`; somatic
    `strelka,mutect2,vep,snpeff`), injected non-destructively (a user's own `--tools`
    still wins) and re-applied on rerun/resume through the same seam M1/M2 used — so one
    sarek run emits both annotation sets.
  - **Two concordance metrics**, auto-run in the verdict via `_discover_qc` (no CLI flag,
    the somatic-auto path), in a new `verification/annotation_concordance.py`:
    `consequence_concordance` — the fraction of shared variants whose most-severe
    consequence term agrees, **WARN-capped (< 0.90), never FAIL**; and
    `gene_symbol_concordance` — the fraction whose annotated gene symbol agrees,
    **informational-only (always PASS)**, because VEP/SnpEff symbol sources diverge
    enough that a WARN would only train users to ignore the signal. Both reuse the
    shipped M3 CSQ/ANN most-severe-consequence parser rather than forking it (M3's
    single-key driver is untouched — M4 owns its own dual-key parse).
  - **Both VCF layouts.** Discovery keys on header-declared annotation keys (path
    component as tie-break) and handles both a **two-file** layout (separate VEP and
    SnpEff VCFs, joined on `(CHROM,POS,REF,ALT)`) and a **single-VCF-both** layout (one
    VCF carrying both `CSQ` and `ANN`), recording which layout it detected in the
    message.
  - **Provenance pair.** `RunRecord.annotation_identity` becomes a list capturing BOTH
    annotators' tool + version (deduped by tool), rendered in `contig methods` and a new
    HTML provenance panel; a mode="before" validator keeps pre-M4 single-object bundles
    loading and reproducing.
  - **Honest contract throughout:** concordance is at most WARN and never changes the
    `verify` exit code; every uncomputable/absent path — only one annotator ran (e.g. a
    missing SnpEff cache), annotation absent, too few shared/resolvable variants, an
    ambiguous multi-file layout — is **UNVERIFIED, never a false pass**. Research-use
    only: a corroboration signal, never a pathogenicity/clinical verdict. Test-first with
    synthetic CSQ/ANN fixtures; no real VEP/SnpEff/sarek run in CI. Milestone M5 (verdict-
    card "corroborated by" line, DB-cache provenance, eval fold-in) remains pending.

## [0.26.0] - 2026-07-10

### Added

- **Research-use variant annotation: somatic gate + plausibility** (capability C7,
  M2 + M3 — the somatic and biological-plausibility follow-ons to M1's germline
  structural verify). Two slices:
  - **M2 — somatic annotation enablement + gate.** The `somatic_variant_calling`
    registry entry now enables sarek's annotation step too: `default_params`
    widens `tools` from `strelka,mutect2` to `strelka,mutect2,vep`, injected
    non-destructively (a user's own `--tools` wins) and re-applied on
    rerun/resume — the same seam M1 used for germline. The M1 structural
    verifier (`annotation_present`/`annotation_complete`) and the
    `AnnotationProvenance` capture are now gated to a new `VARIANT_ASSAYS`
    constant covering **both** `variant_calling` and `somatic_variant_calling`,
    so a somatic run's annotated VCF is verified identically to germline.
    Provenance capture at `_finalize` is now gated to the two variant assays
    (previously unconditional) — a tightening for every other assay; unchanged
    for both variant assays, and never dropped for a genuine variant run even
    when the assay can't be resolved (falls back to attempting capture).
  - **M3 — annotation plausibility, both assays.** A new
    `verification/annotation_plausibility.py` parses the consequence terms out
    of the VEP `CSQ` or SnpEff `ANN` INFO field (the CSQ subfield index is
    resolved from the header `Format:` string; ANN uses SnpEff's fixed layout;
    multi-transcript comma-separated entries and `&`-joined terms are both
    handled) and computes two metrics over the records that carry the field:
    `real_consequence_fraction` (share whose most-severe consequence is a real,
    non-intergenic term) and `intergenic_fraction`. Each variant collapses to a
    single most-severe consequence via a small fixed severity ordering; an
    unknown non-empty term ranks as real, never as intergenic. A new
    WARN-capped `ANNOTATION_PLAUSIBILITY_PACK` (not registered in
    `_RULE_PACKS`) drives two checks wired into `_discover_qc` for both variant
    assays: `annotation_real_fraction` (WARN below 0.10) and
    `annotation_consequence_distribution` (WARN above 0.95 intergenic — the
    "~100%-intergenic" smell). The annotated VCF is located once and fed to
    both the structural and plausibility verifiers, avoiding a duplicate scan.
  - **Honest contract:** the bands are **uncalibrated engineering defaults**,
    deliberately loose so a legitimate high-intergenic run doesn't cry wolf;
    at most WARN, never FAIL, no exit-code change. Every uncomputable/absent
    path — no annotated VCF, an unresolvable CSQ `Format:`, zero annotated
    records — is UNVERIFIED, never a false pass. Additive to the verdict only:
    no new `FailureClass`, model, or persisted-record change; `eval-guard`/
    `heal-guard` baselines untouched. Research-use only: Contig verifies the
    annotation ran plausibly and never adjudicates pathogenicity — the
    consequence-distribution check is a statistical sanity signal, not a
    per-variant biological or clinical judgement.
  - **Carried live-cache caveat (same as M1):** enabling `vep` makes sarek emit
    an annotated VCF, but a live run may still need a `--vep_cache`/
    `--download_cache` or a `--step annotate` entry point that Contig does not
    yet wire — when annotation didn't run, both verifiers degrade to
    UNVERIFIED honestly. No real VEP/SnpEff/sarek run in CI; synthetic gzipped
    VCF fixtures only. **Deferred:** VEP-vs-SnpEff cross-tool annotation
    concordance (M4), surfacing + C6 eval fold-in (M5), FAIL severity until
    real-data calibration, and research prioritization.

## [0.25.0] - 2026-07-10

### Added

- **Research-use variant annotation, germline structural verify** (capability C7, M1).
  A Contig germline (`variant_calling`) run now enables nf-core/sarek's built-in
  annotation step (VEP → `CSQ`) and verifies it ran: a new
  `verification/annotation_structural.py` reports `annotation_present` and
  `annotation_complete` (WARN-capped, UNVERIFIED when no annotated VCF is found —
  never a false pass), and the annotation tool + version is parsed from the VCF
  header into a new `AnnotationProvenance` record, rendered in `contig methods`.
  Research-use only: Contig verifies the annotation EXECUTED, never adjudicates
  pathogenicity. Enabling `--tools haplotypecaller,vep` makes sarek produce an
  annotated VCF, but a live run's annotation step may still require a VEP/SnpEff
  cache (`--vep_cache`/`--download_cache`) or a `--step annotate` entry point that
  Contig does not yet wire — and when that annotation output is absent the verifier
  degrades to UNVERIFIED (never a false pass), so a missing cache surfaces honestly
  rather than as a silent success. Test-first; no real VEP/sarek run in CI.

## [0.24.0] - 2026-07-10

### Added

- **Turnkey RNA-seq cross-tool concordance autorun** (`contig verify
  --concordance-counts-auto`) (capability C1, RNA-seq slice — the autorun follow-on to the
  user-supplied `--concordance-counts` shipped v0.12.0, mirroring how germline
  `--concordance-auto` (v0.4.0) followed `--concordance-vcf`). Contig now produces the
  second gene-count matrix itself: given `--reads <sample sheet>` and a prebuilt `--index`,
  it runs a second, independent quantifier (**kallisto**) behind an injectable seam and
  corroborates the run's primary Salmon gene matrix against kallisto's — no user-produced
  second matrix required.
  - A new `verification/count_quantifier.py` mirrors the germline `second_caller.py` seam:
    a `CountQuantifier` type, a pure `kallisto_command` argv builder (asserted in tests,
    never executed), and a default `run_kallisto_quantifier` that validates inputs, shells
    out, and re-raises every failure (missing binary, missing/malformed reads, missing
    index, missing `abundance.tsv`, missing transcript→gene map) as one named
    `SecondQuantifierError`. **kallisto is never run in CI** (the subprocess success path is
    covered only by a manual gate); tests inject a fake quantifier.
  - The transcript→gene collapse is a **pure, CI-tested** function (`collapse_to_gene`) that
    sums kallisto's transcript-level `est_counts` to gene level via the `t2g.txt` carried in
    the kallisto index directory — so the one scientifically load-bearing step is verified
    for real even though the tool itself is not. A missing `t2g.txt` is an honest
    `SecondQuantifierError`, never a silently-emitted transcript-level matrix.
  - Same honest contract as every concordance slice: **at most WARN**, **never changes the
    verify exit code**, `unverified` (never a false pass) below 10 shared genes. Every
    unrunnable path — a non-rnaseq run, a missing `--reads`/`--index`, a quantifier failure,
    or a malformed sample sheet — prints a clear skip note and emits zero checks. The four
    concordance flags (`--concordance-vcf`, `--concordance-auto`, `--concordance-counts`,
    `--concordance-counts-auto`) are mutually exclusive.
  - No raw-read egress (the quantifier runs on the user's compute; only gene-count metrics
    are compared); no new dependency; no change to the run record, the reproduce contract,
    or the verdict/exit logic. Built test-first with an injected fake quantifier and real
    stdlib collapse/parse fixtures — no real kallisto or nf-core run in CI. **Deferred:** a
    persisted-sample-sheet fallback for `--reads`; building the index in-seam from a
    `--transcriptome`; single-cell concordance; a dashboard "corroborated by" line; and
    FAIL-severity until the bands are calibrated on real data.

## [0.23.0] - 2026-07-08

### Added

- **Self-heal a plain-`gzip`'d (non-BGZF) reference FASTA** (capability C2, self-heal
  breadth — the **first slice of the input-format-conversion class**). A Contig-launched
  **nf-core/sarek** run (assays `variant_calling` germline and `somatic_variant_calling`)
  fails hard when the user's `--fasta` was compressed with plain `gzip` instead of `bgzip`:
  `samtools faidx` rejects it outright (`[E::fai_build3_core] Cannot index files compressed
  with gzip, please use bgzip`), and previously fell through to the opaque terminal
  `tool_crash`. **rnaseq is deliberately excluded** — nf-core/rnaseq's `PREPARE_GENOME`
  gunzips a `.gz` fasta before faidx ever sees it, so the failure never reaches Contig
  there; sarek 3.5.1 has **no gunzip module** and passes `--fasta` straight to
  `SAMTOOLS_FAIDX`, so it *is* reachable through the real CLI (the forced `--gtf` that
  `resolve_reference` couples to `--fasta` is tolerated by sarek's nf-schema as a warning,
  not a validation failure, since sarek defines no `gtf` param and
  `validationFailUnrecognisedParams` defaults false).
  - A new `_recompress_reference` in `self_heal.py` **stream-decompresses** the reference
    with stdlib `gzip` (no external tool — `shutil.copyfileobj` in 1 MiB chunks, never
    reading the whole file into memory) to a plain **uncompressed `.fa`** in run-scoped
    scratch `<run_id>/healed_reference/<name>`, redirects the in-memory `params["fasta"]`
    to the scratch copy, and retries — the user's original file is never touched or
    rewritten. Reuses the STAR-index scratch/redirect/`built_paths` seam and the
    GTF-harmonization reproduce-safety contract (verified empirically, not assumed: a
    dedicated test injects a temporary leak into `_dispatch_run` to prove the assertion is
    load-bearing, then confirms `launch.json` keeps the original `fasta` on the real code
    path — `rerun`/`resume` read only `launch.json` and re-derive the heal from the
    original path; the scratch path is never persisted, only `run_record.json`'s
    provenance legitimately shows it).
  - A new `_gzip_kind` classifier discriminates `"plain_gzip"` from `"bgzf"` (magic-byte
    check plus a walk of the FEXTRA subfields for the samtools/htslib `BC` tag) from
    `"not_gzip"`, so a **valid BGZF reference is left untouched** — recompressing it would
    be pointless churn on an already-correct file, never a false diagnosis.
  - A new `FailureClass` `reference_not_bgzf`, with a **narrow** detector branch anchored
    on the faidx-specific `cannot index files compressed with gzip` (not the bare "please
    use bgzip" that tabix/bcftools emit for VCFs — a different fix entirely). One golden
    detector-corpus case plus a held-out twin; `eval-guard`'s held-out accuracy moved from
    83.3% (10/12) to **84.6% (11/13)** on the refrozen baseline (`--update-baseline`, a
    deliberate act).
  - A new `repair.py` branch proposes a `kind="reference"` patch
    (`operation={"recompress_reference": True}`) with `risk="needs_confirmation"` —
    mirroring the sibling `build_index` reference patch, not `safe`, so a human can veto a
    reference rewrite; tests drive it with `auto_approve=True`.
  - **Every give-up is honest, never a false pass:** no `params["fasta"]`, a file that
    isn't actually plain-gzip (already-BGZF or genuinely uncompressed/corrupt), or a failed
    decompression all end in a distinct `reference_recompress_unresolvable` /
    `reference_recompress_failed` outcome and an honest FAIL — never masked as a recovery.
    Bounded to **one recompress per run** (`built_paths` guard); a second identical failure
    after a successful recompress gives up rather than looping.
  - **No raw-read egress; research-use only.** Recompression runs entirely on the user's
    compute. Built test-first with an injected executor and tiny real gzip/hand-crafted-BGZF
    fixtures (real stdlib `gzip` runs for real in CI on those fixtures) — **no real
    nf-core/sarek or samtools run in CI.**
  - **Deferred (honestly, out of scope for this slice):** **CRAM↔BAM conversion**, the
    other half of the input-format-conversion class; a **BGZF fix target** (declined in
    favor of plain uncompressed — universal downstream acceptance, mirrors rnaseq's own
    GUNZIP, one step); promoting `recompress_reference` from `needs_confirmation` to a
    `safe` auto-approved patch; a `heal-guard` scenario promoting `reference_not_bgzf` to a
    covered outcome-match class (C6 slice 2); and cleaning up the `resolve_reference`
    `--fasta`/`--gtf` coupling quirk that this slice merely tolerates rather than fixes (a
    separate follow-up).

## [0.22.0] - 2026-07-07

### Added

- **Held-out regression guard for the self-heal loop's outcome-match rate**
  (capability C6, eval flywheel — slice 2). Where `contig eval-guard` (slice 1)
  guards only the detector's classification accuracy on a labeled corpus, this
  slice guards the **whole self-heal loop's outcome-match rate**: did the loop
  both diagnose the right `FailureClass` *and* reach the scenario's declared
  terminal outcome (`patched_and_retried`, `built_index_and_retried`,
  `approved_and_retried`, `gave_up`, `index_unresolvable`,
  `approval_timed_out`)? A new `HealScenario` driver (`src/contig/heal.py`) replays each case
  through the **real** `self_heal_run` detect→diagnose→patch→retry loop — the
  detector and `propose` are never stubbed (PRD R2) — via scripted
  executor/index-builder/poll seams, so this measures the actual loop, not a
  mock of it. A new frozen `src/contig/data/heal_scenarios.jsonl` (7 synthetic
  cases) is scored by a new `contig heal-guard` command, which fails the build
  (`exit 1`, `REGRESSION: ...`) when the current outcome-match rate drops below
  a committed baseline (`src/contig/data/heal_baseline.json`, pinning
  `corpus_sha`, `covered_classes`, and `contig_version`) minus a small float
  tolerance. `--update-baseline` (re)freezes the baseline as a deliberate,
  reviewed act — never an automatic side effect of running the guard. The
  guard also warns loudly (non-failing, stderr) on a scenario-sha mismatch
  (set changed but baseline not refreshed), and nudges
  (`consider --update-baseline`) when the rate improves beyond tolerance. The
  committed baseline is honestly **outcome-match 1.0 (7/7)** over the 5 failure
  classes the frozen set currently covers (`bad_param`, `missing_index`, `oom`,
  `time_limit`, `tool_crash`); a `recovery_rate` (`healed`/total, currently
  4/7) is also reported as an **informational-only sub-metric — never
  guarded**, since some declared outcomes are an honest give-up
  (`gave_up`, `index_unresolvable`, `approval_timed_out`) rather than a
  recovery. **Honest scope:** this number is over **7 SYNTHETIC scenarios**,
  not a field recovery rate; `qc_anomaly`
  and `no_progress` remain structurally unreachable by the detector (as noted
  in slice 1), and the wider failure-class catalog (container, download, disk,
  permission, missing-reference families) has no scenario yet. Folding the
  unlabeled C1 concordance / C3 plausibility corroboration signals into a
  single eval number remains **deferred**, as does a held-out-accuracy trend
  over corpus/loop versions. The guard now runs in CI
  (`.github/workflows/ci.yml`, immediately after `eval-guard`), so a change to
  the self-heal loop, a detector, or a patch that regresses outcome-match on
  the frozen synthetic set fails the build. Local, deterministic, no network.

## [0.21.0] - 2026-07-07

### Added

- **Single-cell (scrnaseq) cell-QC ingestion — the dormant single-cell verdict now
  fires** (capability C3, biological-plausibility verification — single-cell slice). The
  scrnaseq assay already carried a biological QC pack (`SCRNASEQ_RULE_PACK`: recovered
  cells, median genes per cell, fraction reads in cells, and a mitochondrial-fraction
  check), but it **silently no-oped on every real run**: the pack's metrics are only read
  from MultiQC general-stats, and the base `nf-core/scrnaseq@4.1.0` pipeline does not route
  single-cell cell-level QC there (its default `simpleaf`/alevin-fry aligner emits
  AlevinQC/QCatch HTML; the stock MultiQC STAR module does not parse STARsolo's
  `Summary.csv`). Because `evaluate()` skips any absent metric, the single-cell verdict
  degraded to UNVERIFIED while reading as "wired." This slice makes the checks **fire** by
  ingesting the cell-QC the aligner writes to disk:
  - A new `verification/scrnaseq_metrics.py` with deterministic, stdlib-only parsers:
    `parse_starsolo_summary` (STARsolo `Summary.csv`), `parse_cellranger_metrics`
    (Cell Ranger `metrics_summary.csv`, handling comma-thousands and normalizing a
    `"92.3%"` rate to the `0.923` **fraction** the pack band expects), and
    `parse_simpleaf_metrics` at its honest **floor** — the default simpleaf path has no
    confirmed machine-readable cell-QC artifact, so it returns `{}` (→ UNVERIFIED, never a
    false pass; **no HTML scraping**). A metric that is absent or non-numeric is omitted,
    never guessed.
  - A dedicated `_discover_qc` gate (mirroring the germline VCF gate, not the MultiQC path)
    that locates the aligner artifact under the run dir, derives a per-sample id, evaluates
    `SCRNASEQ_RULE_PACK`, and — for a located-but-unparseable file — emits one explicit
    `scrnaseq_cell_qc:<sample>` **UNVERIFIED** rather than a silent no-op. No artifact at
    all skips silently (structural QC owns a missing required output). **Cell Ranger takes
    deterministic precedence over STARsolo** for the same sample (no merge of two aligners'
    numbers). Gated strictly to `assay == "scrnaseq"`; all other assays unchanged.
  - **Kept the FAIL bands** on the three grossly-failed-capture checks (a near-empty
    capture genuinely FAILs), consistent with the sibling did-it-run packs
    (methylseq/ampliseq/mag). **Removed** the dead `pct_reads_mito` check — the base
    pipeline never produces it (needs a downstream scanpy step), so it could never fire;
    mitochondrial-fraction and doublet-rate are deferred until a downstream
    scanpy/scDblFinder step exists. No band re-calibration (illustrative engineering
    defaults, unchanged).
  - Additive to the verdict only: no detector/`FailureClass`, model, or persisted-record
    change; no new dependency. Local, deterministic, no raw-read egress (parsers read small
    summary files on the user's compute). Built test-first with synthetic CSV fixtures — no
    real nf-core/scrnaseq run in CI. **Deferred:** a structured QCatch-JSON recognizer for
    the default simpleaf path (if a real fixture ever confirms one — a clean follow-on, no
    redesign), and mitochondrial-fraction/doublet-rate plausibility.

## [0.20.0] - 2026-07-07

### Added

- **Walltime-informed scaling for the `time_limit` self-heal** (capability C2, self-heal
  breadth — the symmetric walltime follow-on to v0.19.0's peak-RSS OOM memory scaling).
  When a task is killed for exceeding its wall-clock limit, the retry is no longer a blind
  `time × 2` guess: the engine parses the run's **own partial `trace.txt`** at heal-decision
  time and sizes the retry from the **longest observed `realtime`** across the trace rows —
  `target = ceil(max_realtime_sec / 3600 × 1.5)` hours (new pure
  `resource_sizing.realtime_informed_time_h`, mirroring `peak_informed_memory_gb`), threaded
  through a new `apply_patch(observed_target_h=…)` seam while the **72 h ceiling clamp, the
  never-shrink rule, and the `gave_up_at_ceiling` give-up stay exactly as before**.
  - **Honest about a weaker signal than memory — floored at blind, never worse.** Unlike an
    OOM'd task's `peak_rss` (a real high-water mark ≈ the task's demand), a walltime-killed
    task **never finished**, so its `realtime` is only a **lower bound** on the time needed
    and is **hard-censored at ≈ the current limit**. So the observed override is **floored at
    the blind `× 2` bump** (`max(observed, blind)`) — the one intentional asymmetry vs the
    memory branch — which means it **ties blind in the common censored case** and only rises
    in the **tail** (the trace carries a `realtime` above the current limit: a higher-label
    sibling process that also timed out, a mis-classified `time_limit`, or a grace/staging
    overrun). It is thus **never worse than today's behavior**, and a trace-less run, a
    snakemake run, or a dash/0 `realtime` degrades to the unchanged blind `× 2` fallback.
  - **Shipped mostly as a field instrument.** Every walltime heal records the observed
    `realtime`, the applied (post-floor/clamp) walltime, the evidence tier, and whether it
    **beat or tied blind** into `RepairStep.detail` — the instrument that will show, in the
    field, how often a walltime kill even carries a usable signal. **Revisit trigger:** after
    ≥ 20 observed walltime heals, if the tail case fires in < ~20% of them, do **not** invest
    further in walltime sizing (no sibling-rescue tier, no calibration) — redirect C2 effort
    to a new failure class. The decision trigger is a deliverable alongside the code.
  - **Deferred (deliberately):** the **same-process sibling rescue** (borrowing an uncensored
    sibling task's `realtime` when the killed row's own is censored) — unreachable while the
    trace parser sets `process == name` for every row, exactly as for the memory slice's
    deferred sibling rung; and factor/ceiling calibration on real data. Memory-only path
    untouched; Nextflow-only; no verdict / exit-code / `FailureClass` / model / parser
    change. Local, deterministic, no raw-read egress; fully covered by injected
    trace/executor fixtures (no real pipeline run in CI).

## [0.19.0] - 2026-07-06

### Added

- **Peak-RSS-informed memory scaling for the OOM self-heal** (capability C2, self-heal
  breadth — the "peak-RSS-informed scaling" slice deferred by v0.5.0's bounded-ceiling
  work). When a task is OOM-killed (`exit 137`), the retry is no longer a blind
  `memory × 2` guess: the engine now parses the run's **own partial `trace.txt`** at
  heal-decision time and sizes the retry to the failed task's **observed peak resident
  memory** — `target = ceil(peak_rss_mb / 1024 × 1.5)` binary GB — so a task that needs
  ~5× lands in **one** retry instead of climbing 2×→4×→8× and exhausting the bounded
  retry budget or the 128 GB ceiling first. A new pure `resource_sizing.peak_informed_memory_gb`
  computes the target from the trace (joining the `exit==137` task events to their
  `TaskResource` rows; multiple OOM'd tasks size off the **max** peak, since
  `process.resourceLimits` is global), and `apply_patch` gained an `observed_target_gb`
  seam that overrides the multiplier while the **ceiling clamp, the never-shrink rule, and
  the `gave_up_at_ceiling` give-up stay exactly as before**. Every heal records the
  observed peak, the sizing, and the evidence tier into `RepairStep.detail` (surfaced in
  `repair_history` and `repair_progress.jsonl`) — the instrument that will show, in the
  field, how often real OOM'd tasks even carry a usable `peak_rss`.
  - **Honest two-tier ladder (not the three-tier originally speced).** (a) the OOM'd
    task's own observed peak, else (b) **unavailable → today's blind `× 2` fallback runs
    unchanged**, so a signal-killed task whose trace row reports a `-`/0 peak, a
    trace-less run, or a snakemake run never regresses. A `peak_rss` of 0/absent is
    treated as **unknown, never "0 MB."** A sized target below the current request is
    expected (never-shrink holds the current value), so the retry is never *worse* than
    before.
  - **Deferred (deliberately, with a named blocker):** the **same-process sibling rescue**
    (borrowing a surviving shard's peak when the killed row's own peak is a dash) was cut
    rather than shipped dormant — it can never fire while the trace parser sets
    `process == name` for every row, so it first needs a coarse `process` column in the
    parser (which has a `progress.py` blast radius). Also deferred: **walltime** sizing to
    observed `realtime`, and folding the observed peak into the `FailureCase` corpus
    schema (telemetry rides in `RepairStep.detail` for now). Memory-only, Nextflow-only,
    no verdict / exit-code / `FailureClass` change. Local, deterministic, no raw-read
    egress; fully covered by injected trace/executor fixtures (no real pipeline run in CI).

## [0.18.0] - 2026-07-06

### Added

- **Per-contig alias harmonization for reference/build-mismatch repair** (capability
  C2, self-heal breadth — a follow-on of v0.9.0's chr-prefix GTF harmonizer). The
  reference pre-flight harmonizer is widened from pure `chr`-prefix add/strip to a
  **general per-contig rename map** driven by a **lookup against the actual FASTA
  contig set**: a new alias equivalence table treats the mitochondrion `M`↔`MT` as
  universal (a code constant) and consults a small **curated, extensible GRCh38
  scaffold table** (`src/contig/data/contig_aliases.tsv`, sourced from UCSC
  chromAlias) for common unplaced scaffolds; the loader fails loud on malformed or
  duplicate rows. `plan_harmonization` now resolves each GTF contig to whichever
  spelling actually exists in the FASTA (prefix variants ∪ alias group ∩ FASTA), so
  it handles the canonical UCSC-FASTA (`chrM`) + Ensembl-GTF (`MT`) case; the
  **residual case where the autosomes already match but the mito differs**
  (previously silently skipped because harmonization was gated behind the
  disjoint-only detector); pure-alias mismatches; and a hybrid FASTA (`chrMT`) via
  FASTA-lookup. It still **refuses (no harmonization) a genuine wrong-assembly**
  (disjoint after mapping) and now also **refuses a non-injective map** (two GTF
  contigs that would collapse onto one FASTA target) — never a silent contig merge.
  The CLI pre-flight is now driven by the plan itself (rather than the disjoint-only
  detector), with a strengthened overlap-increase post-check; `--allow-reference-
  mismatch` still harmonizes-first; `rerun`/`resume` continue to re-derive the plan
  from the original GTF path stored in the manifest, unchanged. **Honesty:** the
  WARN-level `reference_harmonized` breadcrumb now enumerates any GTF contigs that
  could not be matched to the FASTA and were left as-is, so a partial harmonization
  is visible rather than a relocated silent failure. Provenance-only eval capture —
  no new `reference_mismatch` `FailureClass` or detector-corpus case, matching
  v0.9.0. Local, deterministic, no raw-read egress; fully covered by synthetic
  FASTA/GTF fixtures (no real nf-core run in CI). **Deferred:** exhaustive
  per-assembly scaffold-table completeness (the shipped table is a seed, not
  exhaustive); network fetch of chromAlias; rewriting the FASTA (only the GTF is
  ever rewritten); and the sample-data-vs-reference assembly-signature comparison.

## [0.17.0] - 2026-07-05

### Added

- **Held-out regression guard for the diagnosis detector** (capability C6, eval
  flywheel — slice 1). A new frozen `src/contig/data/detector_corpus_holdout.jsonl`
  (12 newly authored `FailureCase`s, `source="holdout:synthetic"`, disjoint `case_id`s
  from the training corpus) is scored by a new `contig eval-guard` command, which
  reuses the shipped `evaluate_detector`/`get_detector` machinery (no reimplemented
  scoring) and **fails the build** (`exit 1`, `REGRESSION: ...`) when the current
  detector's held-out accuracy drops below a committed baseline
  (`src/contig/data/holdout_baseline.json`, one `EvalSnapshot` pinning `corpus_sha`,
  `detector`, and `contig_version` so a drop is attributable to a detector change vs
  a held-out-set change) minus a small float tolerance. `--update-baseline`
  (re)freezes the baseline as a deliberate, reviewed act — never an automatic side
  effect of running the guard. The guard also warns loudly (non-failing, stderr) on
  a held-out-sha mismatch (set changed but baseline not refreshed) or a
  detector-mismatch (baseline measured with a different detector than the one being
  guarded), and nudges (`consider --update-baseline`) when accuracy improves beyond
  tolerance. The committed baseline is honestly **83.3% (10/12)**: two held-out
  classes, `qc_anomaly` and `no_progress`, are currently **structurally unreachable**
  by `diagnose_failure` (no rule branch emits them yet) — this is deliberate, not a
  bug, so the guard has real headroom to catch the day those rules are added.
  **Honest scope:** this slice guards the **labeled failure-class detector corpus
  only**. Folding in the unlabeled C1 concordance / C3 plausibility corroboration
  signals (no ground-truth labels, so not classification-accuracy scoreable) and
  repair-loop (whole self-heal) accuracy into the same guard are **deferred**
  follow-on slices. The guard now runs in CI (`.github/workflows/ci.yml`, after the
  pytest step), so a detector or corpus change that regresses held-out accuracy fails
  the build. Local, deterministic, no network; `llm` is never the guard's default
  detector.

## [0.16.0] - 2026-07-05

### Added

- **Apache-2.0 license.** A top-level `LICENSE` (Apache License 2.0) and `NOTICE`
  file, `license`/`license-files`/`classifiers` in `pyproject.toml`, and a
  `[project.urls]` block (Homepage, Repository, Documentation, Issues, Changelog)
  so the PyPI page and GitHub license chip render correctly. `readme = "README.md"`
  so `pip install contig` users see the full project description on PyPI.
- **Real demo GIF** (`assets/contig-demo.gif`): an offline terminal capture of the
  run → self-heal (OOM → resource patch) → `PASS` verdict → signed `verify` loop,
  featured as the README hero (served from an absolute raw URL so it also renders
  on PyPI).

### Changed

- **Honest launch positioning.** Reconciled the project status across README badge,
  README body, and `CLAUDE.md` to "MVP · early access (v0.15.0)"; added a dynamic
  release badge and an Apache-2.0 license badge.
- **Supported-analyses table** now carries a `Maturity` column (RNA-seq validated
  end-to-end; the other assays wired with QC packs) and lists the somatic
  (tumor–normal) assay, matching the registry.
- **Quickstart** leads with the installed `contig …` form (matching the install
  section) and points source-checkout users to the `uv run` prefix once.
- `eval-detector --help` now mentions the env-gated `llm` detector; the illustrative
  pipeline revision in `docs/USAGE.md` no longer hardcodes a version that can drift.

### Removed

- Internal go-to-market material from the public tree: `demo/OUTREACH.md`,
  `demo/WHAT_THIS_PROVES.md`, the internal `root@vpn` validation-host references in
  two planning docs, and the "money moment on camera" framing in `demo/DEMO.md`.

## [0.15.0] - 2026-07-05

### Added

- **Somatic Strelka2-vs-Mutect2 cross-tool concordance** (capability C1 for the somatic
  assay — the second-caller concordance hook deferred by the v0.14.0 VAF slice). A somatic
  (tumor–normal) run's verdict now gains an independent **cross-tool concordance axis**,
  corroborating the run's **Mutect2** call set against the **Strelka2** call set that the
  *same* `nf-core/sarek` run already emitted (`--tools strelka,mutect2`) — so unlike germline
  concordance there is **no second caller to run and no user-supplied input**; both VCFs are
  already in the bundle. A new `verification/somatic_concordance.py` emits one
  `kind="concordance"` **`somatic_site_overlap`** check: the Jaccard overlap
  (`|A∩B| / |A∪B|`) of the two callers' **PASS** call sites, keyed on `(CHROM, POS, REF,
  ALT)`, where PASS means `FILTER ∈ {"PASS", "."}` (FILTER-aware parsing, so noisy filtered
  candidate calls are excluded). It is **sample-agnostic** — it reads no genotype or tumor
  column, sidestepping the fact that Strelka2 somatic SNVs carry no conventional per-sample
  `GT` (the germline `genotype_concordance` metric deliberately does **not** transfer).
  - **Auto-wired** into `_discover_qc` gated to `assay == "somatic_variant_calling"`,
    alongside (and independent of) the VAF-plausibility block: the Mutect2 VCF is located by a
    `mutect2` path component below the run dir (as the VAF slice already does) and the Strelka2
    VCF by a symmetric `strelka` component, with Strelka's split `*.somatic_snvs.vcf.gz` +
    `*.somatic_indels.vcf.gz` **unioned** into one call set.
  - **Corroboration only:** at most WARN (below a `0.90` overlap default), **never FAIL**, and
    structurally incapable of changing the verify exit code or promoting UNVERIFIED to PASS.
    Below a minimum of 10 union PASS sites the check is **UNVERIFIED, never a false pass**.
  - **Honest on ambiguity:** a single caller present (mutect2-only / strelka-only) skips
    cleanly; a multi-tumor-pair layout — or two callers whose single tumor–normal pair
    directories **differ** — yields one honest UNVERIFIED rather than corroborating an
    arbitrary or unrelated pair.
  - Deterministic, local, no raw-read egress, no tool execution; research-use only (a somatic
    verdict means "ran correctly and reproducibly," never a cancer diagnosis). Built
    test-first with synthetic two-caller VCF fixtures (no real nf-core/sarek run in CI).
    **Deferred:** Strelka2-native tumor-VAF agreement, FAIL severity until the overlap band is
    calibrated on real tumor–normal data, and an explicit `contig verify` concordance flag/echo
    (the auto-in-verdict surface covers slice 1).

## [0.14.0] - 2026-07-04

### Added

- **Somatic VAF-distribution biological-plausibility verification** (capability C4
  follow-on — the biological verdict for the somatic assay whose v0.13.0 slice was
  honestly structural-only). A somatic run now gains a biological axis alongside its
  structural checks, computed deterministically from the **tumor column of the run's
  Mutect2 VCF** by a new `verification/somatic_plausibility.py` and wired into
  `_discover_qc` gated to `assay == "somatic_variant_calling"`. Three checks:
  - `median_vaf` — median tumor variant allele fraction over biallelic records, read from
    the FORMAT `AF` (Mutect2 allele fraction) when present, else derived from `AD_alt/DP`
    (guarding `DP==0`), else the record contributes no VAF. The tumor sample is identified
    by the `##tumor_sample=` header mapped to its `#CHROM` column (never a guessed column).
    A somatic set pinned near VAF≈1.0 (germline leakage) or exactly ~0.5 (mis-paired
    normal) drifts out of the band. Multiallelic sites are excluded; indels are included.
  - `somatic_variant_count` — number of considered (biallelic) somatic records, with a
    deliberately wide band (target type varies by orders of magnitude) to catch only a
    grossly failed call set.
  - `pon_applied` — a panel-of-normals presence check keyed off the GATK command header:
    present with `--panel-of-normals`/`--pon` → PASS; header present without it → WARN;
    no recognizable `GATKCommandLine` header → UNVERIFIED (cannot tell).
  Both metric bands are **WARN-capped** (uncalibrated engineering defaults, no `fail_*`),
  in a new `SOMATIC_PLAUSIBILITY_PACK` that is imported directly (not registered in
  `_RULE_PACKS`). Every uncomputable path — no derivable VAF, an unidentifiable tumor
  column, a missing GATK header — yields **UNVERIFIED (never a false pass)**, mirroring the
  germline Ti/Tv slice. The `*.vcf.gz` locator selects the Mutect2 VCF by a path
  **component** below the run dir (so a "mutect2" in an ancestor workspace/run-id name
  cannot mis-select a Strelka VCF); if VCFs exist but none is Mutect2, one honest
  UNVERIFIED is emitted; if no VCF exists at all the gate skips silently (structural QC
  already covers a missing output). A somatic verdict remains "ran correctly and
  reproducibly," research use — never a cancer diagnosis. Additive to the verdict only: no
  detector/`FailureClass`, model, or persisted-record change; deterministic, no raw-read
  egress; fully covered by synthetic two-sample VCF fixtures (no real nf-core/sarek run in
  CI). **Deferred:** Strelka2-native VAF (tier-count derivation — non-Mutect2 VCFs degrade
  to UNVERIFIED), the Strelka2-vs-Mutect2 somatic concordance hook (C1), FAIL severity
  until the bands are calibrated on real data, and a cross-column swapped-pair smell test
  (the residual case where the `##tumor_sample=` header is present but mislabeled).

## [0.13.0] - 2026-07-04

- **Somatic (tumor–normal) variant calling assay** (capability C4 — a whole new assay
  end to end, the natural extension of the shipped germline sarek assay). A somatic goal
  now routes to a new `somatic_variant_calling` assay served by the same curated
  `nf-core/sarek` pipeline (`@3.5.1`) in somatic mode, with intake → plan → run → verify
  wired through the existing engine. Concretely:
  - **Explicit, persisted assay** (resolves the sarek pipeline-string collision): `contig
    run --assay <key>` carries the run's assay as a first-class input that **overrides**
    the legacy pipeline-derived lookup, is persisted on the `RunRecord` and the
    `launch.json` reproduce sidecar, and is re-applied by `rerun`/`resume`. Because two
    assays now share one pipeline (germline vs somatic sarek), the run no longer derives
    its assay from the pipeline string alone. The legacy `assay_for_pipeline` derivation
    is preserved as the fallback, so every existing run and every already-shipped bundle
    (no persisted assay) resolves exactly as before — a backward-compatible change.
  - **Somatic goal routing**: a `somatic_variant_calling` registry entry plus a
    `somatic`/`tumor`/`tumour`/`tumor-normal` keyword group ordered ahead of germline, so
    "somatic tumor/normal variant calling" routes to the somatic assay while germline
    goals still route to `variant_calling` (non-collision pinned by test).
  - **Sarek tumor/normal sample-sheet pre-flight**: a sarek-shaped sample sheet
    (`patient, sample, status, lane, fastq_1, fastq_2`) is validated for the paired
    structure at the launch chokepoint — `status ∈ {0,1}`, at least one patient with both
    a normal (0) and a tumor (1) row, multi-tumor/relapse allowed, and an unpaired-tumor
    or tumor-only sheet refused with a message pointing at germline. Somatic-gated;
    germline/RNA-seq sample-sheet validation is unchanged.
  - **Somatic launch**: a declarative per-assay `PipelineEntry.default_params` seam
    injects `--tools strelka,mutect2` for the somatic assay (sarek infers somatic mode
    from the paired sheet + somatic-capable callers), captured for reproduce; all other
    assays inject nothing and are unchanged. This proves the somatic launch command is
    correctly assembled — **not** that a real Mutect2 somatic run completes without a
    panel-of-normals / germline resource (that reference wiring, and VAF-distribution
    plausibility, panel-of-normals checks, and the second-caller Strelka2-vs-Mutect2
    concordance hook, are **deferred** to follow-on slices).
  - **Somatic verification**: a `somatic_variant_calling` structural output manifest
    (required + gzip-intact `*.vcf.gz`, mirroring germline) is added, evaluated at
    `contig verify` time; the methods paragraph labels somatic tumor–normal runs
    (research use). Live-run verification stays structural for now (no somatic rule pack
    or plausibility yet), so a somatic verdict is honestly structural-only and never a
    false pass.
  - Research-use only, on the user's compute (no raw-read egress); a somatic verdict
    means "ran correctly and reproducibly," never a cancer diagnosis. Built test-first
    across seven slices with synthetic fixtures — no real nf-core/sarek run in CI.

## [0.12.0] - 2026-07-02

### Added

- **RNA-seq cross-tool quantification concordance** (capability C1, RNA-seq slice —
  the second assay on the concordance axis after the germline slice shipped v0.2.0).
  `contig verify <run> --concordance-counts <matrix>` now corroborates a bulk RNA-seq
  run's own gene-count matrix against a **second, independent count matrix** supplied
  by the user, emitting three `kind="concordance"` checks from a new
  `verification/count_concordance.py`: `spearman_concordance` (per-gene **Spearman
  rank correlation**, WARN below 0.90), `fraction_agreeing` (share of shared genes
  whose summed counts agree within a 10% relative tolerance, WARN below 0.90), and
  `gene_overlap` (**informational, never WARN** — a second matrix built on a
  partial/subset annotation legitimately overlaps poorly, so overlap is context, not
  a verdict lever). Like germline concordance it is **at most WARN** (corroboration,
  not ground truth), **never changes the verify exit code**, and reports `unverified`
  (never a false pass) when the two matrices share fewer than 10 comparable genes (a
  Spearman over one or two genes is meaningless). The primary matrix is located by
  globbing the rnaseq structural manifest's count pattern `*salmon.merged.gene_counts*`
  (not the BAM); a non-rnaseq run, or a missing matrix, prints a clear skip note and
  changes no exit code. `--concordance-counts` is mutually exclusive with the germline
  `--concordance-vcf`/`--concordance-auto`. The Spearman and the count-matrix parser
  are **hand-rolled, stdlib-only** (no scipy/numpy dependency added): average-rank tie
  handling then Pearson of the ranks; the parser is gzip-transparent, sums counts
  across sample columns per gene, tolerates any gene-id + numeric-column TSV (so a
  STAR/featureCounts matrix can corroborate a Salmon one), skips the header row,
  accumulates duplicate gene ids, and never divides by zero on all-zero genes. The
  0.90 bands and 10% tolerance are **uncalibrated engineering defaults**, WARN-capped
  and absorbed by the UNVERIFIED-when-too-few-genes guarantee. Local, deterministic,
  no raw-read egress (operates on count matrices on the user's compute); fully covered
  by synthetic TSV fixtures (no real nf-core run in CI). **Deferred:** auto-running a
  second quantifier (Salmon vs STAR+featureCounts) behind an injectable seam — mirrors
  how the germline autorun (`--concordance-auto`) followed the user-supplied slice one
  release later (v0.4.0); single-cell concordance; a dashboard "corroborated by" line;
  and FAIL severity until the bands are calibrated on real data.

## [0.11.0] - 2026-07-01

### Added

- **Detect a bwa-mem2 unreadable/incompatible aligner index** (capability C2, self-heal
  breadth — the detector half of the next aligner-index kind after STAR, v0.10.0). When
  bwa-mem2 cannot read its index it prints `ERROR! Unable to open the file:
  <ref>.bwt.2bit.64` and exits non-zero; the engine now **classifies** this as
  `missing_index` (previously it degraded to an opaque `tool_crash`) via a new **narrow**
  detector branch AND-guarded on bwa-mem2's own sidecar token `.bwt.2bit.64` plus the
  `unable to open the file` phrase, so it can neither over-match a benign log line nor
  collide with the classic-BWA `bwa_idx_load_from_disk` branch nor swallow a
  wrong-reference. One golden `missing-index-bwamem2` corpus case is seeded (the
  shipped-corpus detector guard stays at 100%, now 23/23), feeding the eval flywheel
  (moat #2). The run still ends in an **honest FAIL** (`index_unresolvable`, verdict
  `fail`) — never a false pass — because the parser cannot resolve a build target for
  this signature. **Deferred (no live trigger — build/redirect intentionally not built):**
  actually rebuilding the bwa-mem2 index. nf-core/sarek auto-builds a missing index,
  AWS-iGenomes ships a classic BWA index (not bwa-mem2), and Contig exposes no flag to
  supply a broken index — so a bwa-mem2 index failure cannot be produced by a
  Contig-launched run today. This mirrors exactly how classic BWA shipped detector-only in
  v0.10.0. Local, deterministic (pure case-insensitive string matching over the run's own
  log; the corpus is a static asset), no raw-read egress; fully covered by injected
  fixtures — no real bwa-mem2 run in CI.

## [0.10.0] - 2026-07-01

### Added

- Self-heal a **missing or version-incompatible STAR aligner index** (capability C2,
  self-heal breadth — the next missing-index kind after the single-file family
  `.fai`/`.bai`/`.tbi`/`.csi`/`.dict`, now covering **directory-shaped aligner indexes**):
  when a run fails with either STAR's `could not open genome file …
  genomeParameters.txt` (missing/aborted index) or `Genome version … is INCOMPATIBLE with
  running STAR version` (stale index), the engine now **rebuilds** the index with `STAR
  --runMode genomeGenerate` from the run's resolved FASTA (+ GTF, via
  `params["fasta"]`/`params["gtf"]`) into a run-scoped scratch dir
  (`<run_id>/healed_index/star`) — the user's supplied index is never mutated — and
  **redirects** the retried run at the scratch index via `params["star_index"]`, recording
  `built_index_and_retried`. Bounded to ONE rebuild per run: a new-reason failure on the
  retry surfaces honestly rather than re-entering the builder or masking a pass. Honest
  `index_unresolvable` (no resolvable FASTA/genome dir) and `index_build_failed`
  (non-zero exit or an empty scratch dir) give-ups — never a false pass. The rebuilt
  STAR genome version is read back from `genomeParameters.txt` and recorded in the repair
  step's detail for provenance. `rerun`/`resume` re-derive the heal from the original
  (un-redirected) `fasta`/`gtf` manifest fields — `star_index` is never a manifest field
  and no scratch path is baked into `launch.json`, so reproduction is faithful. A classic
  **BWA missing-index** failure (`[E::bwa_idx_load_from_disk] fail to locate the index
  files`) is now also **detected** and classified `missing_index`, with a golden corpus
  case — but the build/redirect is **deferred**: no default supported pipeline invokes
  classic `bwa index` (sarek defaults to bwa-mem2; methyl-seq uses bwa-meth), so there is
  currently no live target to redirect. Local, deterministic, no raw-read egress (the
  index is built from a local FASTA/GTF on the user's own compute); fully covered by
  injected builder/executor fixtures — no real STAR/BWA/nf-core run in CI. **Deferred:**
  classic-BWA index build/redirect (would require a sarek `--aligner bwa-mem` target);
  bwa-mem2 index set + aligner-mismatch heal; a corrupt/partial STAR index signature (N1);
  directory-shaped BWA build (n/a while BWA stays detector-only).

## [0.9.0] - 2026-07-01

### Added

- Self-heal a **chr-prefix GTF naming mismatch** between the FASTA and GTF references
  (capability C2, reference/build-mismatch repair — first slice): when a `contig run`
  on real data is blocked at pre-flight by a disjoint contig-naming mismatch that is an
  unambiguous `chr`-prefix asymmetry (FASTA uses `chr1 …` while the GTF uses `1 …`, or
  vice versa), the engine now **auto-harmonizes** the GTF seqnames — a uniform `chr`-add
  or `chr`-strip applied to column 1 only, stream-written to
  `<runs_dir>/<run_id>/harmonized/<name>` — and **proceeds** with the harmonized copy,
  rather than refusing at pre-flight. The user's original GTF is never mutated. The
  transform is first validated by `plan_harmonization`: (a) one side must be entirely
  chr-prefixed while the other is entirely bare, and (b) after the transform the two
  contig sets must share at least one name. If either condition fails — a genuine
  wrong-assembly — the run is still refused, never a fabricated genome. The decision is
  recorded in the launch manifest (`harmonized_reference: bool`) and, when `_finalize`
  receives a non-null `harmonized_reference_direction`, in the run's `ReferenceIdentity`
  (`.harmonized = True`, `.harmonized_direction`). A WARN-level `reference_harmonized` QC
  breadcrumb is appended to `qc_results` so the rewrite is visible in every report and
  verdict surface. `rerun` and `resume` both re-enter `_dispatch_run` with the original
  (un-harmonized) GTF path, so the harmonization decision is re-derived from scratch —
  faithfully reproducible without baking a scratch file path into the manifest. Built on
  top of the C5 pre-flight mismatch detector shipped in v0.7.0, which classified and
  refused this chr-asymmetry class; it now also repairs it. Local, deterministic, no
  raw-read egress; fully covered by synthetic FASTA/GTF fixtures (no real nf-core run in
  CI). **Deferred:** the sample-data-vs-reference **assembly-signature** comparison/repair
  (raw FASTQ carries no contig naming and the finished bundle contains no aligned BAM, so
  there is no sample-side contig signal to compare at this stage); per-contig name mapping
  for ambiguous cases (e.g., `chrM`↔`MT`); known-sites/GTF-version consistency; and a
  runtime `reference_mismatch` `FailureClass`/detector-corpus case — eval capture is
  provenance-only in this slice.

## [0.8.0] - 2026-06-30

### Added

- Self-heal a missing GATK **sequence dictionary** (`.dict`) (capability C2,
  self-heal breadth — the next single-file kind on the shipped index-build seam,
  serving the germline assay where GATK/Picard refuse to run without a `.dict`
  beside the reference). When a run fails with a missing-`.dict` signature, the
  engine now resolves the source FASTA, builds the dictionary with
  `samtools dict -o <ref.dict> <ref.fa>` through the existing injectable
  `IndexBuilder` seam, and retries — recording `built_index_and_retried`. `.dict`
  is the first kind whose build input is **not** the indexed path minus its suffix
  (the dictionary `ref.dict` is built from a *companion* `ref.fasta`/`ref.fa`/
  `ref.fasta.gz`/`ref.fa.gz`), so the build table was generalized to
  `{ext: (derive_source, build_argv)}`: the four existing kinds keep a pure
  suffix-strip deriver (unchanged), while `.dict` uses a filesystem-probing deriver
  that resolves the companion FASTA relative to the dictionary's **own parent**
  directory (absolute-safe), tolerates a leading `file://` scheme some GATK builds
  print, and gives up honestly with `index_unresolvable` when no companion exists —
  never guessing a build target. The detector gained a **narrow** sequence-dictionary
  branch: GATK's wording is *"…Fasta dict file …/ref.dict … does not exist…"*, and
  `does not exist` is deliberately **not** in the generic missing-file keyword set,
  so the branch requires both a `.dict` token **and** an absence phrase — keeping a
  genuine wrong-reference/contig mismatch (a different, deferred failure class) from
  being misread as a buildable missing dict. A new **build-once-per-path** guard
  bounds the loop: an index path already built this run is not rebuilt, so a
  wrong-reference masquerading as a missing dict gives up after one build instead of
  burning the retry budget on identical rebuilds (a tightening that applies to every
  index kind). A failed `samtools dict` (non-zero exit) still gives up with
  `index_build_failed`; the verdict reduction and the near-zero false-pass guarantee
  are unchanged. One `missing-index-dict` golden case joins the detector corpus
  (detector eval stays 100%). Local, deterministic, no raw-read egress (the dict is
  built from a local FASTA on the user's compute); fully covered by injected
  builder/executor fixtures — no real `samtools`/GATK/nf-core run in CI. **Deferred
  (unchanged):** the BAM/CRAM form of `.csi`, directory-shaped STAR/BWA indexes,
  stale-index detection, and the C2 reference/build-*mismatch* repair (wrong
  reference, not a buildable missing dict).

## [0.7.0] - 2026-06-29

### Added

- Pre-flight reference-consistency check (capability C5, slice 2 — the mismatch
  detector that the v0.6.0 reference-identity *capture* slice was groundwork for): a
  `contig run` on real data with an explicit `--fasta`/`--gtf` is now refused before
  launch when the FASTA and GTF use **disjoint contig naming** (the notorious `chr1`
  in the FASTA vs `1` in the GTF), which otherwise runs to "success" and silently
  produces an empty count matrix that passes structural QC. The new
  `verification`-adjacent `reference_check` module parses the FASTA `>` headers and
  the GTF column 1 (both gzip-transparent, streamed) and applies a **disjoint-only**
  rule: a mismatch is reported only when the two contig-name sets are both non-empty
  and share *no* element — any overlap (including a GTF that is a strict subset of the
  FASTA, e.g. a partial/scaffold reference) passes, and an empty/unparseable file is
  treated as uncomparable and passes, so the check never produces a false refusal.
  The message names a deterministic sorted sample of each side and the `chr`-prefix
  asymmetry. The gate lives at the single launch chokepoint (`_dispatch_run`), so it
  protects both the CLI and the dashboard (which spawns the CLI); iGenomes
  (`--genome KEY`) runs carry no local files and skip cleanly. An honest escape hatch,
  `--allow-reference-mismatch`, proceeds anyway (still printing the warning) and is
  recorded in the launch manifest so `rerun`/`resume` reproduce the original intent
  faithfully (legacy manifests default to off). Local, deterministic, no network, no
  raw-read egress; fully covered by synthetic `tmp_path` fixtures (no nf-core run in
  CI). **Deferred:** the harder sample-data-vs-reference assembly-signature comparison
  (raw FASTQ has no contig naming and the finished bundle carries no aligned BAM),
  known-sites/BED-vs-reference consistency, GTF annotation-version resolution, seeding
  a `reference_mismatch` corpus class, and the C2 reference/build-mismatch *repair*
  this detector now feeds.

## [0.6.0] - 2026-06-29

### Added

- Reference-identity provenance (capability C5, capture slice — slice 1 of N): a run
  now records *which genome and annotation it ran against*, deepening the reproduce
  guarantee beyond pinned tools/params to the reference data itself. A new
  `ReferenceIdentity` model is captured at finalize from the run's parameters and
  serialized into `run_record.json`: explicit mode (`--fasta`/`--gtf`) records the
  paths plus their `sha256`; iGenomes mode (`--genome KEY`) records the key only and
  marks checksums unavailable — the pipeline downloads those files, so Contig has no
  local path to hash, and a run is never failed over an unhashable/missing reference
  (the checksum degrades to `None`, never a fabricated or zero hash). The identity is
  rendered in `contig methods` and the HTML provenance panel (iGenomes shows the key
  as pipeline-downloaded, never a blank hash). Capture-only: no QC/verdict change, no
  exit-code change. **Deferred:** the pre-flight reference/build **mismatch detector**
  (the next C5 slice, where the real feasibility risk lives), known-sites capture
  (not visible to Contig today — nf-core config assets, not CLI params),
  annotation/GTF version resolution (no reliable source — left null, not fabricated),
  and RO-Crate export of the identity. nf-core only (Snakemake runs carry no reference
  keys → identity is absent and the section is omitted cleanly). Hashes run on the
  user's compute (no raw-read egress); fully covered by synthetic fixtures (no real
  nf-core run in CI).
- RNA-seq biological-plausibility verification (capability C3, RNA-seq slice):
  extends the germline plausibility verdict to bulk RNA-seq. Two WARN-capped checks
  — `duplication_rate` (`percent_duplication`) and `rrna_contamination`
  (`percent_rRNA`) — live in a new `RNASEQ_PLAUSIBILITY_PACK` and are evaluated by
  `evaluate_rnaseq_plausibility`, which mirrors the germline pattern: present metrics
  are scored via the shared rule evaluator, and a metric absent from a sample's
  ingested MultiQC yields `unverified` (`value=None`, never a false pass), capped at
  WARN (corroboration, not a clinical claim). Wired into `_discover_qc` gated to
  `assay == "rnaseq"` with a MultiQC report present; other assays are unchanged. The
  metric slugs and bands are best-effort, uncalibrated engineering defaults — the
  UNVERIFIED-when-absent guarantee absorbs a wrong/missing slug. Deferred:
  gene-body-coverage evenness (needs a new RSeQC compute path), FAIL severity until
  bands are calibrated, and the single-cell/sex-check slices. Tests-only (no detector
  corpus change — plausibility is not a `FailureClass`); fully covered by synthetic
  metric fixtures (no real nf-core run in CI).

## [0.5.0] - 2026-06-28

### Added

- Self-heal the rest of the single-file index family (capability C2, missing-index
  follow-on): the `missing_index` self-heal now builds and retries a missing `.bai`
  (`samtools index`), `.tbi` (`tabix -p vcf`), and `.csi` (`bcftools index`), not just a
  `.fai`. The parser now returns the missing path and its extension, and a table maps each
  extension to its build command on the existing injectable `IndexBuilder` seam; the
  honest give-ups (`index_unresolvable` / `index_build_failed`) and the
  `built_index_and_retried` outcome are unchanged, as is the detector (it already
  classified these). One golden corpus case per new kind is seeded. Still single-file
  indexes only — `.dict` (needs a detector change and non-trivial source-FASTA
  resolution), the BAM/CRAM form of `.csi`, and directory-shaped STAR/BWA indexes remain
  deferred. Bounded by `max_attempts`, runs on the user's compute (no raw-read egress),
  fully covered by injected-builder/executor tests (no real `samtools`/`tabix`/`bcftools`/
  pipeline run).
- Self-heal a missing index (capability C2, missing-index slice): a `missing_index`
  failure is now actually recovered instead of re-run unchanged. When the
  `build_index` repair is applied, the loop parses the missing index path from the
  diagnosis, builds it (this slice: a missing FASTA `.fai` via `samtools faidx`
  through a new injectable `IndexBuilder` seam), and retries — recording a
  `built_index_and_retried` `RepairStep`. If the index path can't be parsed or the
  build itself fails, the loop gives up honestly (`index_unresolvable` /
  `index_build_failed` with a `RepairStep.detail` naming the path) — an honest FAIL,
  never a false pass. The build is bounded (one per applied patch, within
  `max_attempts`), runs on the user's compute (no raw-read egress), and is fully
  covered by injected-builder/executor tests (no real `samtools`/pipeline run).
  (`.bai`, `.tbi`, and `.csi` are added in the follow-on entry above; `.dict` and
  STAR/BWA remain deferred.)
- Bounded resource-aware self-heal retry (capability C2, resource-aware slice): the
  `oom` and `time_limit` repairs now scale memory/walltime only up to an absolute
  ceiling (defaults 128 GB / 72 h, code-overridable via `self_heal_run`'s
  `resource_ceiling`). When the scaled resource is already at its ceiling and the
  failure recurs, the loop gives up honestly with a distinct `gave_up_at_ceiling`
  outcome and a `RepairStep.detail` message naming the resource and the cap — an
  honest FAIL, never a false pass — and the case is still captured to the failure
  corpus. A scale that would overshoot is clamped to the cap; a pre-existing request
  already above the cap is never shrunk. Engine-wide (all assays); deterministic and
  fully covered by injected-executor tests (no real pipeline run).

## [0.4.0] - 2026-06-27

### Added

- Turnkey cross-tool concordance (follow-on to C1): `contig verify <run>
  --concordance-auto --bam <bam> --ref <ref>` runs a second variant caller
  (bcftools) on the BAM and reference to produce an independent call set, then
  corroborates the run's primary VCF against it. The second caller is behind an
  injectable seam, so it is never executed in CI; a missing binary, missing input,
  or caller failure prints a clear skip note (never a false pass) and never changes
  the exit code. Mutually exclusive with `--concordance-vcf`. Reuses the existing
  concordance machinery; germline only.

## [0.3.0] - 2026-06-26

### Added

- Germline biological-plausibility verification (capability C3, germline slice):
  `ts_tv` (transition/transversion ratio over biallelic SNVs) and `het_hom`
  (heterozygous/homozygous-alt genotype ratio) are computed deterministically from
  a germline run's VCF, activating the previously-dormant `VARIANT_RULE_PACK`
  plausibility rules. The checks run whether or not a MultiQC report exists, are
  capped at WARN (corroboration, not a clinical claim), and report `unverified`
  (never a false pass) when a ratio is uncomputable.

### Changed

- The `ts_tv_ratio` and `het_hom_ratio` rules in `VARIANT_RULE_PACK` are capped at
  WARN (their FAIL bands removed) until the bands are calibrated on real data;
  `mean_coverage` is unchanged.

## [0.2.0] - 2026-06-24

### Added

- Cross-tool concordance verification (capability C1, germline slice): corroborate a
  germline run's variants against a second, independent call set. A new `concordance`
  QC kind emits a `genotype_concordance` check (over shared sites) plus a
  `site_overlap` check; `contig verify --concordance-vcf <vcf>` runs them against the
  run's primary VCF. Concordance is at most WARN (corroboration, not ground truth)
  and never changes the verify exit code; an empty site intersection reports
  `unverified`, never a false pass. Surfaced in the text and HTML reports and the
  dashboard QC panel.

### Changed

- `QCStatus` gains `unverified` as a per-check status (previously run-level only).
  `overall_verdict` reduces a set of only-unverified checks to `unverified`, never
  `pass`, preserving the near-zero false-pass guarantee.

## [0.1.0] - 2026-06-24

The first tagged release: the Layer-2 engine (run, self-heal, verify, reproduce)
plus a local dashboard, feature-complete against the catalog and validated on real
compute. Pre-revenue, validation phase.

### Engine (CLI)

- Run a curated pipeline, self-heal recoverable failures, verify the output, and
  report an honest verdict (PASS / WARN / FAIL / UNVERIFIED): `contig run`, `show`,
  `list`, `plan`.
- Self-heal loop: detect, diagnose, propose typed patches, apply the safe ones, and
  retry, bounded and logged. Risky patches pause for human approval, with ranked
  options on an ambiguous decision (`contig approve`, `--choose`).
- Live observability and control: `contig status`, `watch`, `cancel`, `resume`,
  `rerun`; lifecycle events to `notifications.jsonl` plus a webhook and optional
  SMTP email.
- Verification: metric QC rule packs per assay plus structural and integrity checks
  (outputs present, non-empty, indexed, gzip and BAM integrity); a missing or corrupt
  required output FAILs the verdict.
- Reproducibility: a pinned, portable run record; `contig verify` re-hashes outputs;
  Ed25519 signed records (`contig keygen`); RO-Crate export and a methods paragraph
  (`contig export --rocrate`, `contig methods`); a self-contained HTML report
  (`contig show --html`).
- Cost and planning: `contig cost` for actuals and `contig estimate` for a pre-run
  estimate; resource actuals captured from the trace.
- The failure-corpus flywheel: capture, promote (`contig corpus-promote`), score
  (`contig eval-detector`, with a pluggable detector incl. an optional LLM detector),
  cluster (`contig clusters`), and track coverage (`contig coverage`) and an accuracy
  trend.
- Cross-run verification benchmarking: `contig benchmark` against a designated
  reference.
- Six assays (RNA-seq, single-cell RNA-seq, germline variant calling, methyl-seq,
  16S amplicon, shotgun metagenomics), two workflow engines (Nextflow and Snakemake),
  and three backends (local, AWS Batch, SLURM; local and SLURM live-validated).

### Dashboard

- A Next.js dashboard over the same engine: launch, live progress and the self-heal
  feed, the approval gate, verdict explainability, output-integrity and signature
  badges, compare, the corpus pending-review and the eval flywheel, cost, and the
  benchmark view.
- Auth0 authentication and role-based authorization, per-user run isolation, and team
  workspaces, with a documented local/test bypass.

### Packaging

- Installable as a Python package, a standalone binary per OS, a container image, and
  (where set up) via Homebrew. See the README for install options.

[0.43.0]: https://github.com/haqaliz/contig/releases/tag/v0.43.0
[0.42.0]: https://github.com/haqaliz/contig/releases/tag/v0.42.0
[0.41.0]: https://github.com/haqaliz/contig/releases/tag/v0.41.0
[0.40.0]: https://github.com/haqaliz/contig/releases/tag/v0.40.0
[0.39.0]: https://github.com/haqaliz/contig/releases/tag/v0.39.0
[0.38.0]: https://github.com/haqaliz/contig/releases/tag/v0.38.0
[0.37.0]: https://github.com/haqaliz/contig/releases/tag/v0.37.0
[0.36.0]: https://github.com/haqaliz/contig/releases/tag/v0.36.0
[0.35.0]: https://github.com/haqaliz/contig/releases/tag/v0.35.0
[0.34.0]: https://github.com/haqaliz/contig/releases/tag/v0.34.0
[0.33.0]: https://github.com/haqaliz/contig/releases/tag/v0.33.0
[0.32.0]: https://github.com/haqaliz/contig/releases/tag/v0.32.0
[0.31.0]: https://github.com/haqaliz/contig/releases/tag/v0.31.0
[0.30.0]: https://github.com/haqaliz/contig/releases/tag/v0.30.0
[0.29.0]: https://github.com/haqaliz/contig/releases/tag/v0.29.0
[0.28.0]: https://github.com/haqaliz/contig/releases/tag/v0.28.0
[0.27.0]: https://github.com/haqaliz/contig/releases/tag/v0.27.0
[0.26.0]: https://github.com/haqaliz/contig/releases/tag/v0.26.0
[0.25.0]: https://github.com/haqaliz/contig/releases/tag/v0.25.0
[0.24.0]: https://github.com/haqaliz/contig/releases/tag/v0.24.0
[0.23.0]: https://github.com/haqaliz/contig/releases/tag/v0.23.0
[0.22.0]: https://github.com/haqaliz/contig/releases/tag/v0.22.0
[0.21.0]: https://github.com/haqaliz/contig/releases/tag/v0.21.0
[0.20.0]: https://github.com/haqaliz/contig/releases/tag/v0.20.0
[0.19.0]: https://github.com/haqaliz/contig/releases/tag/v0.19.0
[0.18.0]: https://github.com/haqaliz/contig/releases/tag/v0.18.0
[0.14.0]: https://github.com/haqaliz/contig/releases/tag/v0.14.0
[0.13.0]: https://github.com/haqaliz/contig/releases/tag/v0.13.0
[0.12.0]: https://github.com/haqaliz/contig/releases/tag/v0.12.0
[0.10.0]: https://github.com/haqaliz/contig/releases/tag/v0.10.0
[0.9.0]: https://github.com/haqaliz/contig/releases/tag/v0.9.0
[0.7.0]: https://github.com/haqaliz/contig/releases/tag/v0.7.0
[0.6.0]: https://github.com/haqaliz/contig/releases/tag/v0.6.0
[0.1.0]: https://github.com/haqaliz/contig/releases/tag/v0.1.0
