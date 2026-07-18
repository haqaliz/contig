# Understanding — feat/reproduce-output-locator (C8 slice 1.5)

Phase 2 dig. Extends the shipped C8 slice-1 walking skeleton (v0.40.0). All paths under
`src/contig/` in this worktree.

## What the work is really asking

Slice 1 (`verification/reproduce.py`, shipped) binds each claim's observed value from **one
flat, Contig-shaped `results.json`** the repo's script must write: `{claim_id: value}`, looked
up by `claim.id` (`reproduce.py:181-237`). That only reproduces **cooperative** repos — ones you
modify to emit that file. The reproduce PRD's own review gate
(`docs/planning/reproduce-published-work/prd.md:190-215`) names the fix: a **claim-level
output-locator** so each claim points at where its number already lives in the repo's own output
files. That is this slice — it makes `contig reproduce` "externally credible" (works on real,
unmodified cloned repos that emit structured output).

**The whole change is localized to the value-binding step.** `classify` (the tolerance verdict),
`reduce_reproduction` (the pure reduction), `ClaimResult`/`ReproduceRecord` (models), the signed
bundle, and the exit-code contract are all **reused unchanged**. Only *how the observed value is
obtained* generalizes.

## The exact seam to generalize

`run_reproduction` (`reproduce.py:133-259`), specifically the per-claim value-binding loop
(`reproduce.py:181-249`):

- **Today:** read `repo/<results_path>` once; for each claim, `results[claim.id]` → numeric →
  `classify`, else `unverified`.
- **This slice:** a claim may carry an **optional locator** `{from: <repo-relative file>, path:
  <expression>}`. When present → open that file (repo-relative, escape-guarded), extract the value
  at `path`, then the SAME `classify`. When absent → the current flat-`results.json` id lookup
  (full back-compat: a slice-1 claims file behaves identically).

`Claim` (`reproduce.py:32-42`, a frozen dataclass) gains optional `from`/`path` fields;
`load_claims` (`reproduce.py:45-89`) parses + validates them; the CLI `reproduce`
(`cli.py:713-806`) is largely untouched (it already validates + hashes claims and calls
`run_reproduction`).

## Reuse map (low risk — the skeleton was built for this)

- **`classify` (`reproduce.py:92-130`)** — unchanged. Same 4-state verdict, same finite/None
  guards, same tight-epsilon REPRODUCED rule. The locator only feeds it an `observed float | None`.
- **`ClaimResult` / `ReproduceRecord` (`models.py:646-677`)** — unchanged. `observed=None`
  already models "uncomputable". A locator that can't resolve → `observed=None` → `unverified`,
  exactly the existing honesty contract.
- **`reduce_reproduction` (`reproduce.py:262-282`)** — unchanged (counts what results say; never
  upgrades).
- **Path-escape guard already exists** for `--results` (`cli.py:745-753`: resolve repo-relative,
  reject absolute / `..`-escaping via `relative_to`). The locator's `from` files must reuse this
  exact guard — no raw-data egress outside the repo.
- **`write_reproduce_bundle` + signing** — unchanged; the record is still signed for free.
- **CLI `--results`** — stays as the default flat-map path for **locator-less** claims.

## Design shape (to confirm in the interview)

- **Locator = per-claim, optional.** `{"id","value","tolerance"?, "from"?, "path"?}`. `from` and
  `path` are all-or-nothing (both or neither). A claims file may mix located and flat claims.
- **`path` expression = a minimal stdlib walker**, not a JSONPath dependency (stdlib-only
  contract). A small dotted/bracket subset — `$.a.b`, `a.b`, `a[0].c` — walking nested
  dict/list. Any unresolved step → `unverified` (omit-never-guess), never a guess.
- **Per-file read caching** within one run (several claims may share one `from` file).
- **Structured outputs only (JSON this slice).** TSV row/column addressing is a live scope
  question (see below); stdout-scraping / prose / figures are firmly out (figures need a plot-hash
  dep that does not exist — `CHANGELOG.md:53-58`).

## Honesty degradations (every one → `unverified`, never a false pass / never `diverged`)

Missing `from` file · `from` file unparseable · `path` resolves to nothing / wrong shape ·
resolved value non-numeric or non-finite · (safety) `from` escapes the repo. All carry a clear
per-claim message. Non-zero script exit still short-circuits every claim to `unverified`
(unchanged).

## Open questions for the interview (things the code can't decide)

1. **TSV in scope for slice 1.5, or JSON-only?** Handoff says "JSON/TSV". JSON-only is the tighter
   walking slice; TSV needs a row/column addressing syntax. *(Recommend: JSON-only now, TSV a
   named next step.)*
2. **`path` syntax surface.** `$.a.b[0]` (JSONPath-lite, leading `$` optional) vs plain dotted
   `a.b.0`. *(Recommend: minimal dotted + `[n]` index, leading `$.`/`$` tolerated.)*
3. **Locator field names.** `from`/`path` (matches the PRD example
   `prd.md:196`) vs `file`/`pointer`. *(Recommend: `from`/`path`, per the PRD.)*
4. **Where a bad `from` path is caught.** A *structurally* malformed locator (wrong types) → reject
   the whole claims file in `load_claims` (consistent with existing claim validation). A *runtime*
   miss (file absent / path not found) → per-claim `unverified`. An **escaping/absolute `from`** →
   reject at load (safety, like `--results`) or per-claim `unverified`? *(Recommend: reject at load
   — it's a safety refusal, not a verdict.)*
5. **Does `--results` stay?** Yes — the default for locator-less claims. Confirm no removal.

## Guardrail check (`CLAUDE.md`)

- **Layer 2 only** ✅ — verify-and-reproduce; a path resolver, not workflow authoring, not a
  conclusions verdict.
- **No raw-data egress** ✅ — `from` files are repo-relative + escape-guarded; only hashes + claim
  diffs leave the box.
- **Founder's edge / stdlib-only** ✅ — pure-Python nested-structure walk, no new deps —
  *provided we hold the JSON(/TSV)-structured, no-image line.*
- **Test-first** ✅ — synthetic repo-output fixtures, scripted executor, no network, no real
  nf-core in CI.

## Contradiction / scope guard carried from slice 1

Figures/plots and table-cell claims stay out: no plot-hash exists and adding perceptual-image
hashing breaks the stdlib-only dep contract (`CHANGELOG.md:53-58`,
`CAPABILITY_ROADMAP.md:1075-1082`). This slice does **not** relax that — it stays on structured
numeric outputs. This slice does **not** relax that — it stays on structured numeric outputs.

## Interview decisions (locked)

1. **JSON-only** this slice; TSV/CSV is a named next step.
2. **`path` syntax = dotted + `[n]` index**, leading `$.`/`$` tolerated (`$.model.auc`,
   `samples[0].mean_cov`). A new pure stdlib walker.
3. **Escaping/absolute `from` → rejected pre-run** (exit non-zero, no record), reusing the
   `--results` containment guard; a runtime miss (file/path absent) is per-claim `unverified`.

## Parsing-survey agent confirmations (grounding for the plan)

- **No dotted/JSONPath traversal helper exists** anywhere (grep clean) — this slice introduces the
  first. `json.loads` used only at `qc_ingest.py:6`, `reproduce.py:55,185`.
- **`_to_float` omit-never-guess primitive** appears three times (`rnaseq_metrics.py:33`,
  `mag_metrics.py:47`, `methylseq_metrics.py:40`): `try: float(text.strip()) except (ValueError,
  AttributeError): return None`. Mirror it — the walker returns `None` on any miss, never guesses.
- **Containment guard is canonical**: `(base/rel).resolve().relative_to(base.resolve())` in
  `try/except ValueError` (`cli.py:745-753` for `--results`; no `is_relative_to` in the repo). The
  `from` field reuses exactly this.
- **The single branch site** is `run_reproduction` `reproduce.py:181-237` (flat `results[claim.id]`
  lookup). `classify` (`reproduce.py:92`) + `_relative_delta` (`benchmark.py:195`) are unchanged.
- **`from` is a Python keyword** — the claims-file JSON key is `"from"`, but the internal
  `Claim` attribute must be aliased (e.g. a small `Locator(source, path)` on the claim).
- **Test patterns:** `tests/test_reproduce.py` (`_fake_executor(exit_code, results,
  results_path)` closure, kwarg-injected), `tests/test_cli_reproduce.py` (monkeypatch
  `contig.cli.default_command_executor`; `CliRunner`; two path-escape tests at `:285,:312` that
  must stay green), `tests/test_reproduce_models.py`, `tests/test_reproduce_bundle.py`. No conftest;
  `tmp_path`.
- **CLI renders via `render_reproduction` (`cli.py:803`), not `reduce_reproduction`** — note when
  touching output.
