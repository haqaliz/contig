# Spec — cli-command (C8 locator-inference aspect 3 of 3)

Unit: `feat/reproduce-locator-cli/aliz`. Parent PRD:
`docs/planning/reproduce-locator-inference/prd.md` (M1, S1-S4; aspect-3
decomposition L274-293). Prerequisites: aspects 1-2 shipped (candidate sweep +
match-and-propose incl. the M10 semantic filter, gate-verified 6/20 binds, 0
wrong). Interview decisions (2026-09-21): `--metrics` optional with value-only
fallback; `--dry-run` ships in v1; `--out` required with clobber guard.

## Problem slice and user outcome

The paper → verdict chain's last manual link is hand-writing a locator per
claim. Aspects 1-2 proved the matcher can propose evidence-gated locators
correctly on a real repo. This aspect puts it on the command line:
`contig infer-locators <repo> <claims.json>` reads an existing draft, sweeps
the repo, matches, and writes an **updated claims file** (bound claims gain
locator keys) plus a **review sidecar** — the human's job becomes reviewing
proposals, never writing coordinates. `extract-claims` is NOT modified; the
draft contract is untouched.

## In-scope requirements

- **M1 — The command.** `contig infer-locators <repo> <claims.json> --out
  <out.json> [--metrics <metrics.json>] [--force] [--dry-run]`.
  - `<repo>`: **local directory only** (PRD out-of-scope: no network/DOI/
    fetching). Classify via the shipped `classify_repo_argument` and accept
    only `kind == "local"` (a URL/DOI gets the honest refusal, not a "not a
    directory"); leading-`-` refusal stands; then `is_dir()` (mirror
    `cli.py:1155-1159`).
  - `<claims.json>`: read through the **unchanged `load_claims`** — a
    `ClaimsError` (or missing/unreadable file) exits 1 naming the reason,
    nothing written.
  - `--out`: **required**, mirror extract-claims. Guards in extract-claims
    order: `--out == input` clobber refusal (only when both resolve; OSError →
    false), overwrite refusal without `--force`, parent-dir existence check.
    The input claims file is never modified.
  - `--metrics <json>`: **optional**. A JSON object mapping claim id →
    non-empty string list; validated at load (non-dict, non-list words, empty
    lists, unknown ids are fine — unknown ids just fall back). Garbage
    (unparseable JSON, non-dict root, non-string ids/words) → exit 1 naming
    the reason. Absent → value-only mode (metrics=None), with an honest echo:
    "no --metrics given; running value-only (semantic filter off)".
  - `--dry-run`: **ships in v1**. Performs the full read+sweep+match, prints
    the outcome summary + full sidecar text + sweep skips, writes nothing,
    exit 0.
- **The write path (the load-bearing invariant).** Bound outcomes are
  assembled into claim dicts — the original `{id, value, tolerance}` keys
  preserved **semantically verbatim** (carried through the parsed `Claim`
  values; the written file is a fresh JSON serialization, so "identical"
  means same keys/values, not same bytes) plus the locator keys
  (`from`+`path`, or `from`+`column`+`row`+`header`, no `delimiter`);
  non-bound claims keep their id/value/tolerance unchanged. The assembled
  file is written via **`tempfile.mkstemp(dir=<out parent>, suffix=".tmp")`**
  (same-filesystem, so `os.replace` is atomic — the extract-claims pattern,
  `cli.py:1586-1601`), round-tripped through the **unchanged `load_claims`**
  (ClaimsError → "internal error" exit 1, temp removed in `finally`, nothing
  committed), then `os.replace`. A semantic-identity test pins that a
  non-bound claim's keys/values are untouched across the write (not a byte
  comparison). All the match-and-propose M6 discipline, enforced at the CLI.
- **`--dry-run` writes nothing, not even the temp**: the full
  read+sweep+match runs, the summary + sidecar + skips print, and no file is
  created, renamed, or removed (pinned by a test asserting the out path is
  absent and the input is unmodified after the run).
- **The review sidecar.** `<out>.review.md` (suffix rule mirroring
  extract-claims `cli.py:1603-1606`): the matcher's `sidecar_text(outcomes,
  claims)` verbatim + a "Sweep skips (N)" section (source + reason per skip —
  the sweep's never-silent-loss guarantee surfaced at the CLI) + a mode note
  (semantic vs value-only) + the metrics-source note ("metric words are
  proposals, pending human review" — same framing as the sidecar header).
- **Echo summary.** On success (and dry-run): bound/ambiguous/
  refused_low_information/no_candidates counts + skip count + output path.
  When `--metrics` was given, the echo also names **how many claim ids had
  metric words and how many ids went unmatched** — a stale `--metrics` map
  (ids renamed by extraction regeneration, PRD R4) degrades claims to the
  value-only fallback, and that degradation must be visible, not silent.
  Exit 0. A zero-bind outcome still writes the updated claims file
  (locator-less; the review file carries the counts) and exits 0 — honest
  "nothing proposed" is a valid result, mirroring extract-claims' empty-draft
  exit-0 precedent.
- **S1/S4 parity + introspection.** `--force`/refuse-to-overwrite parity with
  extract-claims; `--dry-run` flag; flags asserted by **Click-param
  introspection** (the `test_cli_extract_claims.py:285-295` pattern), never
  `--help` scraping.
- **Never raises at the CLI.** Every failure path is an exit 1 with a named
  reason and nothing written; no traceback leaks.

## Out-of-scope boundaries

- No modification to `extract-claims` or its `{id, value, tolerance}` draft
  contract (pinned by `test_cli_extract_claims.py:104`).
- No network, DOI resolution, repo fetching, `--allow-fetch`-style machinery
  (PRD out-of-scope: repo is a local path).
- No `models.py`/verdict/bundle/signature change; no edit to `reproduce.py`,
  `locator_inference.py`, `locator_match.py`, `claim_extraction.py`
  (import-only). No new dependency (stdlib).
- `pattern`/notebook inference (blocked), figure/plot claims (hard-blocked) —
  unchanged.
- No auto-verification of inferred claims: the output is a proposal the human
  reviews, then runs `contig reproduce` (unchanged) on the updated claims
  file. The freshness guard decides every verdict, untouched.

## Acceptance criteria (testable)

1. `infer-locators <repo> <draft> --out <out>` on a fixture repo with a
   single-site JSON match → out file gains the `from`+`path` locator on that
   claim; all other claims byte-identical; exit 0.
2. Table match (header mode) → complete locator keys (`from`+`column`+`row`+
   `header`), no `delimiter`; exit 0.
3. Ambiguous/refused/no_candidates claims → no locator keys; the counts echo;
   exit 0 (zero binds still writes + exits 0).
4. Round-trip invariant: every written out file passes the unchanged
   `load_claims` (universal over the fixture corpus) — pinned.
5. Guards: `--out == input` → exit 1, nothing written; existing `--out`
   without `--force` → exit 1; `--force` → overwrites; missing parent dir →
   exit 1; missing/unparseable `<claims.json>` → exit 1 naming the reason;
   non-directory `<repo>` → exit 1; URL/DOI repo arg → exit 1 with the
   https/DOI refusal wording; leading-`-` repo arg → exit 1 (RCE refusal).
6. `--metrics`: valid map drives semantic matching (a claim that binds only
   via the M10 filter binds); absent → value-only with the echo; garbage
   (non-dict, non-JSON, non-str words) → exit 1; unknown ids → fallback, no
   error.
7. `--dry-run`: full read+sweep+match happens, summary + sidecar + skips
   printed, NOTHING written (out absent, input untouched), exit 0.
8. Sidecar: contains the matcher sidecar lines, the skips section (N +
   source + reason), the mode note; deterministic content.
9. Echo summary lines: counts for all four reasons + skip count; with
    `--metrics`, the matched-ids and unmatched-ids counts.
10. Click-param introspection pins the command's flags/args (the
    `test_cli_extract_claims.py:285-295` pattern).
11. Full suite green; guard baselines unmoved; no signature/model change.
12. `--dry-run` writes nothing: out path absent, input untouched, no temp
    left behind, exit 0.
13. Semantic identity, not bytes: a non-bound claim's `{id, value,
    tolerance}` keys/values are unchanged across the write (fresh
    serialization allowed).
14. Metrics staleness visibility: a `--metrics` map with an unknown id →
    that claim falls back to value-only AND the echo names the unmatched id
    count.

## Dependencies and sequencing

- Consumes (import-only): `sweep_repo`/`Candidate`/`SweepSkip`
  (`locator_inference.py`, in this base), `match_claims`/`MatchOutcome`/
  `sidecar_text` (`locator_match.py` — **on PR #41, NOT in this base**),
  `load_claims`/`Claim` (`reproduce.py`), `classify_repo_argument`
  (`fetch.py`).
- **Blocker (named, real): the matcher module is unmerged.** Implementation
  of this aspect's code cannot start until PR #41 merges (or this branch is
  rebased onto `feat/reproduce-locator-matcher/aliz`). Planning docs proceed
  now; the plan's Phase 0 explicitly checks for `locator_match.py` presence
  before any code.
- The evidence gate (aspect 2→3) has passed and is recorded
  (`match-and-propose/evidence-gate-semantic-20260921.md`): ships narrowed.
- No new gate required for this aspect (it adds no matching behavior), but the
  plan's final phase re-runs `infer-locators` on the gate repo as a
  **manual smoke** (real repo, real draft, real metrics map) — recorded, not
  in CI.

## Risks / open questions (carried)

- **R4 (id instability)** — ids are not stable across extract-claims
  regeneration; `--metrics` keyed by id inherits this. Mitigation: the sidecar
  names the mapping; a human re-keying after regeneration is the documented
  flow (same as the PRD's own sidecar caveat).
- **Metric-word noise** (measured at the gate: "padj" vs `p.adjust`, "called
  by both" vs `n_recovered`) — the CLI cannot fix vocabulary; the sidecar
  renders the semantic_match names so the human sees what narrowed the pool.
- **Zero-bind runs are the honest default** on dense repos — the echo + sidecar
  make the counts visible, never a silent empty proposal.
- **`--dry-run` semantics**: reads + matches (no network, cheap) — no I/O
  side effects beyond reads; pinned by the nothing-written assertion.