# Understanding — feat/reproduce-freshness-guard (C8, follow-on to slice 5)

Phase-2 dig note. Read after `issue.md`. Everything below is verified against the code in
this worktree (branched from `origin/master` @ v0.45.0), not from memory.

---

## 1. What the work is really asking

The notebook locator (slice 5) shipped a **freshness guard**: a `.ipynb` binds a claim only
when its mtime is `>= run_started_at`, i.e. only when *this run* rewrote it. The reason is
stated in the code itself (`reproduce.py:1058-1078`): a committed notebook holds the
*authors'* stored outputs, so reading them reports a false `REPRODUCED`.

**That reason is not notebook-specific.** A committed `results.json`, a committed `de.tsv`,
or a committed `train.log` produces exactly the same false `REPRODUCED`. The notebook slice
knew this and named it as its own deferred slice — `reproduce-notebook-locator/prd.md:213-215`
(R2): *"Guard scope is deliberately inconsistent. Slices 1.5 and 3 have the same
stale-artifact hole (a committed `results.json` or `de.tsv` reproduces just as falsely).
Widening the guard to them would change shipped behavior and belongs in its own slice."*

This slice is that widening. It is a **verdict-honesty fix to already-shipped code**, not a
new feature: it removes a live false-`REPRODUCED` class rather than adding a capability.

## 2. The real scope is FIVE binding surfaces, not the three in the brief

The brief named the JSON, table, and pattern-file locators. The dig found a fourth
unguarded read and confirms a fifth is immune:

| # | Binding path | Code | Reads disk? | Guarded today? |
|---|---|---|---|---|
| 1 | JSON `path` locator (slice 1.5) | `_observe_located`, `reproduce.py:879-…` | yes | **no** |
| 2 | TSV/CSV `column`/`row` locator (slice 3) | `_observe_table_located` | yes | **no** |
| 3 | Pattern locator **with** `from` (slice 4) | `_observe_pattern_located`, `:974-1056` | yes | **no** |
| 4 | **Flat `--results` `results.json`** (slice 1) | `run_reproduction`, `:1226-1234` | yes | **no** |
| 5 | Pattern locator **without** `from` (stdout mode) | `_observe_pattern_located`, `:998-1000` | **no** | n/a — immune |
| 6 | Notebook `cell`+`pattern` (slice 5) | `_observe_notebook_located`, `:1058-1104` | yes | **yes** |

**Surface 4 is the dig's main correction to the brief.** The original cooperative-repo path
— the one slice 1 shipped and the one every "just write a `results.json`" repo uses — reads
`repo/results.json` off disk at `:1226-1234` with no freshness check whatsoever. It is the
*oldest* instance of the hole and the brief did not name it. Leaving it out would ship a
guard that is still inconsistent, which is precisely the defect R2 filed.

**Surface 5 is immune by construction**, confirmed at `reproduce.py:998-1000`: with
`loc.source is None` the text is `run_output`, a closure variable holding the run's own
captured stdout/stderr. It touches the filesystem "not at all" and cannot be stale — the
run produced it by definition. It needs no guard and must not be given one.

## 3. What already exists and is reused unchanged

- **The guard mechanism**: `reproduce.py:1089-1104` — one `stat()` for both size and mtime,
  size bound checked **first** (`:1094`), then `stat.st_mtime < run_started_at` (`:1100`),
  message *"was not rewritten by this run (mtime predates run start)"*.
- **The timestamp**: `cli.py:850` already stamps `run_started_at = time.time()`
  unconditionally — after all pre-run validation, before the executor, and deliberately
  **not** re-stamped on an `--allow-install` retry (`cli.py:846-849`) — and passes it at
  `:863`. **No CLI change is needed for this slice.**
- **The shared field**: all four locator dataclasses (`:149-212`) expose `.source`
  (`str`, or `str | None` for `PatternLocator`). A single freshness helper keyed on a
  resolved path serves every branch.
- **Containment**: each observer already resolves under `repo_root` and refuses escapes.
- **A single insertion point, verified.** All three unguarded observers share a
  byte-for-byte identical prologue — `resolved = (repo_path / loc.source).resolve()`, then
  `resolved.relative_to(repo_root)` in a `try/except ValueError`, then a cache-keyed read:
  JSON `:884-904`, table `:942-950`, pattern-file `:1002-1032`. The guard slots in
  immediately **after** the containment check and **before** the cache-keyed read in each,
  which is also what makes the two parse-cache call-count assertions (§5) drop to 0. The
  flat `--results` path (`:1226-1234`) has a different shape — no containment step, since
  the path is not user-authored — so it needs its own `stat()` call rather than the shared
  helper's full prologue.
- **Everything downstream**: `classify`, `ClaimResult`, `ReproduceRecord`, the bundle, the
  signer, `--fail-on-diverged`. No `models.py` change expected, no new dependency
  (`stat()` is stdlib), no new claim-file syntax.

## 4. The decision the brief flagged — and what the dig found

### 4a. Default-on vs. opt-out

**Recommendation: guard on by default, no opt-out flag.**

An opt-out is a hole the exact size of the defect. The legitimate-sounding case ("my repo
doesn't rewrite that file") is not legitimate: if the run did not produce the artifact, the
claim is not reproducing anything — `UNVERIFIED` is the true answer. This matches how slice
5 reasoned about a fudge tolerance (`prd.md:202-208`: *"a tolerance is exactly the size of
the hole it opens"*). **Open question for the interview**, not settled unilaterally.

### 4b. The `raise`-when-unstamped rule is the real fork

`_observe_notebook_located` **raises** `ValueError` when `run_started_at is None`
(`:1080-1081`), on the stated grounds that a `None` default meaning "guard off" is a silent
bypass. That rule is itself pinned by a test (`test_reproduce.py:2490-2494`).

`run_started_at` is a **defaulted** parameter (`float | None = None`, `:847`). Copying the
raise to the other four surfaces means every call site must stamp it. Measured blast radius:

- **Copy the raise** → ~42 tests in `test_reproduce.py` need `run_started_at` threaded.
- **Tolerate `None`** (skip the check when unstamped) → 21 tests, but reintroduces a silent
  bypass for any future caller that forgets — the exact thing slice 5 refused.

Given there is exactly **one production caller** (`cli.py:852`) and it always stamps, the
raise is affordable; the cost is mechanical test churn, not risk. A middle path worth
raising in the interview: make `run_started_at` a **required keyword** so a missing stamp is
a `TypeError` at every call site at once, rather than a runtime `ValueError` reachable only
on the locator branch.

### 4c. Ordering within each observer

The size check must stay **before** the mtime check (as at `:1094` vs `:1100`), or
`test_run_reproduction_pattern_claim_oversized_file_is_unverified_and_not_read`
(`test_reproduce.py:2230`, asserts the byte count in the message) changes meaning. More
generally the guard should fire **before** parse but its message will now pre-empt several
existing failure messages — 6 tests assert on those (see §5).

## 5. Blast radius, measured

From the test-map dig (all counts verified against the files):

- **15 tests flip** `reproduced`/`within-tolerance`/`diverged` → `unverified`: 4 JSON
  (`test_reproduce.py:1282, 1291, 1303, 1405`), 7 table (`:1480, 1502, 1523, 1541, 1707,
  1726, 1766`), 4 pattern-file (`:1968, 2105, 2205, 2297`). Cause: the `_write_*` helpers
  (`:1269, :1468, :1859`) write the fixture *before* the run and `_run` (`:1255`) never
  passes `run_started_at`.
- **6 tests keep `unverified` but assert a message** the guard would pre-empt
  (`:1331, 1600, 1617, 1634, 2277, 2230`).
- **2 of the 15 also assert a parse-cache call count** (`:1726` table parsed once, `:2205`
  file read once) — a pre-parse guard drops those counts to 0, so the assertion, not just
  the status, changes.
- **CLI e2e churn is ~zero**: every locator e2e already writes its fixture *inside* the fake
  executor (`test_cli_reproduce.py:403, 643, 779`), so those files are naturally fresh —
  which is itself evidence the guard matches how a real run behaves.
- **The fix pattern already exists** and is copyable verbatim: module-level `_RUN_START`
  (`test_reproduce.py:2343`), an mtime-stamping writer `_write_notebook` (`:2364`), and
  `run_started_at=_RUN_START` through `_run`'s `**overrides`.

There is no `conftest.py` in `tests/`; helpers are file-local, so the new stamping helpers
follow the same convention.

## 6. Ambiguities / open questions for the interview

1. **Opt-out flag: none (recommended) or `--allow-stale-artifacts`?** §4a argues none.
2. **Is the flat `--results` path in scope?** The dig says yes (§2, surface 4) — excluding
   it re-files R2 rather than closing it. Confirm.
3. **`run_started_at`: required keyword, or keep defaulted + raise on the guarded branches?**
   §4b. Required-keyword is louder but touches more call sites at once.
4. **Message wording**: reuse *"was not rewritten by this run (mtime predates run start)"*
   verbatim per surface, with the artifact kind swapped (`results file`/`locator file`/
   `table`), or one uniform noun? Consistency helps; per-kind nouns match existing messages.
5. **Does the flat-results guard fire per-claim or once per run?** The file is read once at
   `:1226`; a stale one should mark **every** flat claim `unverified` with the freshness
   reason, not the existing *"results file is missing or unparseable"* message, which would
   be actively misleading (the file parses fine — it is just stale).

## 7. Guardrail check (`CLAUDE.md`)

- **Layer 2, squarely.** This is verify/reproduce hardening — "make every verdict harder to
  fool" (`CAPABILITY_ROADMAP.md:1325`). Nothing here authors a workflow from English.
- **Moat #1 (verification infrastructure).** It removes a false-pass class from the verdict,
  which is the durable asset; a better base model does not make it redundant.
- **No wet-lab/clinical/proprietary-data dependency.** Pure engine work.
- **Stdlib-only holds** — `stat()`, already used.
- **Honesty contract preserved**: every new failure path is `UNVERIFIED`, never `DIVERGED`,
  matching the shipped rule that formatting/availability problems must not be misread as a
  failed reproduction.

## 8. Honest limits this slice inherits (must be restated, not "fixed")

- **R1** — coarse-mtime filesystems can yield a false `UNVERIFIED`. Accepted deliberately;
  **no fudge tolerance**. A false `UNVERIFIED` is honest and recoverable; a false
  `REPRODUCED` is not.
- **R1a** — the guard proves *rewritten*, not *recomputed*. A `--run` of
  `cp committed.json out.json` passes while computing nothing. It closes the dominant honest
  hole, not adversarial self-deceit.
