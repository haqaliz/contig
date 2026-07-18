# PRD — Claim-level output-locator for `contig reproduce` (C8 slice 1.5)

**Slug:** `reproduce-output-locator`
**Branch:** `feat/reproduce-output-locator/aliz`
**Capability:** C8 (`docs/technical/CAPABILITY_ROADMAP.md:1047-1082`) — the slice-1.5 deferred by the
v0.40.0 walking skeleton.
**Parent PRD:** `docs/planning/reproduce-published-work/prd.md` (slice 1).
**Status:** Interview complete (3 shaping decisions locked); pending prd-generator critique +
review-gate approval.

---

## Problem Statement

`contig reproduce` (C8 slice 1, shipped v0.40.0) binds each claim's observed value from **one flat,
Contig-shaped `results.json`** that the third-party repo's script must write — `{claim_id: value}`,
looked up by `claim.id` (`verification/reproduce.py:181-237`). That only reproduces **cooperative**
repos: ones you modify (or synthetic fixtures). Real cloned public repos don't emit a Contig-shaped
file, so today every claim against them degrades to `UNVERIFIED` — an honest but useless "I couldn't
check."

The reproduce PRD's own review gate names the fix directly
(`docs/planning/reproduce-published-work/prd.md:190-215`): a **claim-level output-locator** so each
claim points at *where its number already lives* in the repo's own output files — e.g.
`{"from": "out/summary.json", "path": "$.model.auc"}`. This is the first slice that lets
`contig reproduce` read numbers out of **real, unmodified repos that emit structured output**, i.e.
the first externally-credible slice.

**Evidence it's real:** the reproducibility-crisis numbers behind C8 (~3.2% of 27,271 biomedical
notebooks reproduce; `CAPABILITY_ROADMAP.md:1084-1090`); the slice-1 PRD's explicit greenlight
question ("is the first externally-credible slice actually skeleton + the output-locator together,
so it can read numbers out of repos as they already are?", `prd.md:210-215`). On-thesis Layer 2.

## Goals & Success Metrics

- **G1 — Claims can locate their own value in a repo's output.** A claim carrying
  `{"from": <repo-relative JSON>, "path": <expr>}` is bound from that file at that path and
  classified with the existing verdict. *Measured:* a fixture repo emitting `out/summary.json`
  (a shape Contig never dictated) yields `REPRODUCED`/`DIVERGED` per claim via the locator (engine +
  CLI tests).
- **G2 — Honest degradation is preserved end-to-end.** Every way a locator can fail to resolve →
  `UNVERIFIED`, never a false pass, never `DIVERGED`. *Measured:* fixtures for missing `from` file,
  unparseable JSON, unresolved `path`, non-numeric/non-finite target — each asserts `UNVERIFIED`.
- **G3 — Full back-compat with slice 1.** A slice-1 claims file (no `from`/`path`) behaves
  byte-identically — flat `--results` id lookup. *Measured:* the slice-1 reproduce test suite stays
  green unchanged; a mixed claims file (some located, some flat) resolves each correctly.
- **G4 — Safety: no read outside the repo.** An escaping/absolute `from` is refused before any run
  (exit non-zero, **no** record written); reaching the engine directly, it is `UNVERIFIED` (never
  read). *Measured:* a CLI test with `"from": "../secret.json"` exits non-zero and writes no bundle,
  mirroring the existing `--results` escape tests (`test_cli_reproduce.py:285,312`).
- **G5 — Zero new runtime dependencies; deterministic; no network.** *Measured:* `pyproject.toml`
  runtime deps unchanged (`pydantic`/`typer`/`cryptography`); the suite runs offline with a scripted
  executor and on-disk fixture files.

**Non-metric goal:** keep the `Claim`/`ClaimResult`/`ReproduceRecord` contract stable so slice 2
(env-resurrection) and a later TSV/CSV locator extend it, not reshape it.

## Users & Scenarios

- **A — lone computational biologist / reviewer** (primary). Clones a public repo, runs its script,
  and wants its headline numbers checked against the paper *without editing the repo to emit a
  Contig file*. Writes a claims file that points at the repo's own `out/*.json`, gets a per-claim
  verdict + signed record. This slice is the one that makes that possible.
- **D — biotech researcher / core facility.** Wants a defensible, signed artifact of which of a
  dependency-repo's numbers reproduced, read from the repo as-is.

## Requirements

### Must-have (slice 1.5)

- **M1 — Optional per-claim locator in the claims file.** A claim object may carry
  `"from": <string>` and `"path": <string>`. **All-or-nothing** — both present or both absent;
  exactly one present is a malformed-file error (rejected in `load_claims`, exit non-zero, no
  record). `from` is a repo-relative path to a JSON file; `path` is a value expression (M3).
- **M2 — Value binding branches on the locator.** In `run_reproduction`'s per-claim loop, a claim
  **with** a locator is bound from `repo/<from>` at `<path>`; a claim **without** one keeps the
  slice-1 behavior (look up `claim.id` in the flat `--results` file). A claims file may mix both.
  Per-`from`-file read/parse is cached within one run (multiple claims may share a file).
- **M3 — `path` expression = a minimal stdlib walker.** Dotted segments + `[n]` list indices, with
  a leading `$.` or `$` tolerated and stripped: `$.model.auc`, `model.auc`, `samples[0].mean_cov`,
  `metrics[2].value`. Walks nested `dict`/`list` from parsed JSON. A **new pure function**
  (`resolve_pointer(data, expr) -> object | None`) — the repo has no traversal helper today. Any
  unresolved step (missing key, index out of range, indexing a non-list, keying a non-dict, malformed
  expression) returns `None` (omit-never-guess, mirroring the repo's `_to_float` primitive).
- **M4 — Locator resolution → observed value.** For a located claim on a completed run: read
  `repo/<from>` as JSON; `resolve_pointer` to the target; the target must be a **finite number**
  (`bool` excluded, as slice 1 already excludes it) → `float` → `classify` (unchanged). A **numeric
  string** target (`"0.91"`) is **strictly `UNVERIFIED`**, not coerced — only real JSON numbers count
  as an observed value, matching slice-1's `isinstance(int, float)` rule (decision locked in the
  interview). Any failure — file missing, unparseable JSON, `path` unresolved, target non-numeric
  (incl. numeric string) or non-finite — → that claim `UNVERIFIED` with a clear message. Never
  `DIVERGED` for a resolution failure.
- **M5 — Path safety (reject pre-run).** Every located claim's `from`, joined to the repo and
  resolved, must stay inside the repo (reuse `(repo/from).resolve().relative_to(repo.resolve())` in
  `try/except ValueError`, the `--results` guard at `cli.py:745-753`). An escape/absolute path is
  refused **before any run**, exit non-zero, **no** record written. Defense-in-depth: if such a path
  reaches `run_reproduction` directly (bypassing the CLI, e.g. an engine caller), that claim is
  `UNVERIFIED` and the file is **never read** — no egress on any path.
- **M6 — `load_claims` validation extends, doesn't rewrite.** `from`/`path`, when present, must be
  non-empty strings; violations raise `ClaimsError` (the existing malformed-file contract: exit
  non-zero, nothing written). `load_claims` stays **repo-agnostic** (structural validation only) —
  containment (M5) is the CLI's job, since `load_claims` has no repo context. The `Claim` dataclass
  carries the locator on an aliased attribute (`from` is a Python keyword — JSON key `"from"` maps
  to an internal field such as a small `Locator(source, path)`).
- **M7 — Verdict / model / bundle reuse unchanged.** `classify`, `reduce_reproduction`,
  `ClaimResult`, `ReproduceRecord`, `write_reproduce_bundle`, signing, `render_reproduction`, and the
  `--fail-on-diverged` exit contract are all reused **as-is**. No model field changes (the locator
  lives on the input `Claim`, not on `ClaimResult`/`ReproduceRecord`); `claims_sha256` already
  captures the locators since they're part of the claims file bytes.

### Should-have

- **S1 — Message quality.** An `UNVERIFIED` from a locator names *why* (`from 'out/x.json' missing`,
  `path 'a.b[3]' did not resolve`, `value at 'a.b' is not a finite number: …`) so a user can fix the
  claims file. A `DIVERGED`/`WITHIN-TOLERANCE` still names observed-vs-stated + delta (slice-1
  behavior, unchanged).
- **S2 — `--results` help clarified.** Note it is the fallback for claims **without** a locator.

### Nice-to-have (explicitly later slices)

- **TSV/CSV locator** (row/column addressing) — the named next step after JSON.
- Environment resurrection (`ModuleNotFoundError` → install → retry) — **slice 2**.
- Paper-parsing to auto-extract claims + locators; figure/plot & table-cell claims (blocked on a
  dependency decision — no plot-hash, stdlib-only); remote `<doi|url>`; dashboard card; C6 fold-in.

## Technical Considerations

- **The whole change is localized.** New: a pure `resolve_pointer` walker + a per-claim locator
  branch in `run_reproduction`'s binding loop (`reproduce.py:181-237`) + `Claim`/`load_claims`
  fields + a CLI containment pre-check. Everything downstream of "observed value" is untouched.
- **Stdlib-only, mirroring existing parsers.** The walker follows the repo's omit-never-guess idiom
  (`_to_float`); no JSONPath/jq dependency (the runtime dep set is `pydantic`/`typer`/`cryptography`
  only, `pyproject.toml`). JSON is read with stdlib `json`; gzip is out of scope this slice (repo
  JSON outputs are plain — revisit with TSV).
- **Reproducibility/verification impact:** this widens *what* the signed verdict can be computed
  over (repos as-is), without weakening the honesty contract — `UNVERIFIED`-on-any-doubt is
  load-bearing and preserved.
- **Determinism/CI:** no real repo, no network — scripted executor + on-disk fixture output files in
  `tmp_path`, mirroring `tests/test_reproduce.py` and `tests/test_cli_reproduce.py`.

## Data Model / Artifact Contracts

- **Claims file (input), extended:**
  ```json
  [
    {"id": "auc", "value": 0.91, "tolerance": 0.05,
     "from": "out/summary.json", "path": "$.model.auc"},
    {"id": "n_variants", "value": 1204, "from": "out/qc.json", "path": "samples[0].n"},
    {"id": "mean_cov", "value": 30.4}
  ]
  ```
  The last claim (no `from`/`path`) uses the flat `--results` id lookup — back-compat.
- **`from`:** repo-relative path to a JSON file the repo produces. **`path`:** dotted + `[n]`
  expression, leading `$.`/`$` optional.
- **`ClaimResult` / `ReproduceRecord`:** unchanged. A located claim populates `observed`/`delta`/
  `status`/`message` through the same fields.

## Risks & Open Questions

- **R1 — Walker surface creep.** Full JSONPath (filters, wildcards, `..`) is out — dotted + `[n]`
  only. Guardrail: the grammar is fixed in M3; anything beyond it is an unresolved `path` →
  `UNVERIFIED`, not a silent partial match. Settle exact tokenization in tech-plan.
- **R2 — "Located but still UNVERIFIED" is common.** Many real repos emit numbers only to stdout,
  CSVs, notebooks, or plots — the locator does **not** help there (scope: structured JSON). Honest
  framing: the win is "reads repos that emit structured JSON," not "reads any repo." The manual
  go/no-go smoke (below) tests this on ≥1 real repo.
- **R3 — Engine-vs-CLI split for the safety check.** Containment must reject before running (M5), so
  it lives in the CLI (which has the repo path); `run_reproduction` keeps a defensive UNVERIFIED for
  an escaping `from` reaching it directly. Confirm the split in tech-plan; both must hold "no egress."
- **R4 — Mixed-file semantics.** A claim with a locator ignores `--results`; a claim without one
  ignores its (absent) locator. State explicitly so neither path shadows the other.

## Out of Scope (explicit)

- **TSV/CSV, stdout-scraping, notebook/prose parsing, figures/plots.** JSON structured output only;
  figures stay hard-blocked (no plot-hash; stdlib-only — `CHANGELOG.md:53-58`).
- **Environment resurrection** — slice 2. **Paper-parsing** to extract claims — later.
- **Any judgement on the paper's conclusions.** Computation-vs-numbers only.
- **Remote fetch, dashboard card, C6 eval fold-in** — later slices.

## Post-merge validation (not a CI test)

Per the slice-1 PRD's greenlight discipline (`prd.md:199-204`): after merge, run `contig reproduce`
against **≥1 real cloned public repo** that emits a JSON output, with a hand-written claims file
using the locator, and confirm the per-claim verdict is sensible. This is the honest proof the
locator earns its keep — the go/no-go signal for investing in slice 2. Manual, offline-optional, not
gated in CI.

## Guardrail check (`CLAUDE.md`)

Layer 2 only (a path resolver over verify output; never NL→workflow, never a conclusions verdict) ✅ ·
Moat = verification/reproducibility infra + corpus ✅ · Gets better as base models improve
(claim/locator extraction in later slices) ✅ · Founder's edge / stdlib-only ✅ · No raw-data egress
(repo-relative, escape-guarded; only hashes + claim diffs leave the box) ✅ · Test-first ✅.
