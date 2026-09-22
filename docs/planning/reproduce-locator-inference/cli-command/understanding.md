# Understanding — cli-command (C8 locator-inference aspect 3 of 3)

Unit: `feat/reproduce-locator-cli/aliz`. Source: inline brief (confirmed
2026-09-21), PRD `docs/planning/reproduce-locator-inference/prd.md` (M1, S1-S4,
aspect-3 decomposition L274-293), amended spec + gate records under
`match-and-propose/`. Phase-2 dig by an explore agent, verified against the
code in THIS worktree (`origin/master`) and the matcher worktree (PR #41).

## What the work is really asking

Aspect 1 (candidate sweep) and aspect 2 (match-and-propose, incl. the M10
semantic filter) are shipped and gate-verified (6/20 binds, 0 wrong on a real
repo). Aspect 3 is the **command surface**: `contig infer-locators <repo>
<claims.json>` reads an existing extract-claims draft, sweeps the repo, matches
evidence-gated locators, and writes an updated claims file + review sidecar —
so the human's job shrinks to reviewing proposals instead of hand-writing
locators. The PRD's decision rule was satisfied ("ships narrowed"), so this
aspect is unblocked.

## Verified code surface (this worktree)

- **Template command**: `extract-claims` at `src/contig/cli.py:1397-1628` —
  Click def (1397-1418), pre-flight guard order (1436-1485: arg classification
  → DOI/fetch gate → `--out == input` clobber guard → overwrite guard →
  parent-dir check), input stat/read guards (1488-1562), the load-bearing
  write flow (1572-1601: draft → temp → **unchanged `load_claims` round-trip** →
  `os.replace`; ClaimsError → exit 1, nothing written), sidecar renderer
  `_review_sidecar` (1340-1394), empty/success echoes (1617-1628). Exit 1 on
  every refusal; exit 0 on success and on empty extraction.
- **Containment**: the locator-`from` guard is `cli.py:1221-1232`
  (resolve → `relative_to(repo_root)`, ValueError → exit 1). The sweep emits
  `source` repo-relative by construction; the CLI's output must survive this
  guard (M8 pin).
- **Repo argument**: `fetch.py:110-155` `classify_repo_argument` — leading-`-`
  refusal (RCE shape), https-only remote, DOI/other-scheme refusals, else
  local. `infer-locators` is **local-only by PRD**; call it and accept only
  `kind == "local"`, then `is_dir()` (mirror `cli.py:1155-1159`).
- **Tests**: `typer.testing.CliRunner` + module-level runner; Click-param
  introspection pattern (`typer.main.get_command(app).commands[...]` +
  `p.opts`) at `test_cli_extract_claims.py:285-295`; docstring-not-help
  assertions (`test_cli_reproduce.py:446-456`); exit-code assertions.
- **No `--dry-run` precedent anywhere in `src/`** — net-new flag, S4.

## The one genuine design gap (found in the dig)

**Metric words do not survive to disk.** The draft JSON is `{id, value,
tolerance}` only (`cli.py:1574-1577`), the review sidecar renders
`id`/`value`/`unit`/`origin`/`source_text` but **not** `metric`
(`cli.py:1384-1393`), and `load_claims`' `Claim` has no metric field
(`reproduce.py:518-535`). Modifying `extract-claims` is PRD-out-of-scope
(`prd.md:263`), and re-deriving words from the id slug is lossy
(uniquification suffixes `auc_2` → `auc2`, collapsed multi-word phrases,
lowercasing). So the CLI needs its own input for the M10 mapping.

**Interview decisions (2026-09-21):**
1. `--metrics <json>` — **optional**; absent → value-only mode (byte-identical
   fallback) with an honest echo; present → validated dict (claim_id →
   non-empty str list); garbage → exit 1 naming the reason.
2. `--dry-run` **ships in v1** — prints the outcome summary + sidecar text +
   sweep skips without writing anything; exit 0.
3. `--out` **required** (mirror extract-claims), refuse `--out == input`
   (clobber guard), refuse overwrite without `--force`. The input claims file
   is never modified.

## Ambiguities / open items for the spec

- What the CLI echoes on success: binds/ambiguous/refused/no_candidates counts
  + skip count (sweep completeness honesty) — recommend a compact summary.
- The written sidecar: matcher `sidecar_text` + skips list + mode note
  (semantic vs value-only) + metrics-source note. The existing
  `extract-claims` sidecar and the infer sidecar coexist (`<out>.review.md` is
  the infer one; extract's is `<draft>.review.md` — different files, no
  collision).
- Empty binds (all ambiguous/refused): still write the updated claims file
  (locator-less, byte-identical to input except whitespace?) — recommend
  writing it (the review file carries the counts), exit 0.
- Skips disclosure: sidecar section "Sweep skips (N)" listing source+reason —
  the sweep's never-silent-loss guarantee surfaces at the CLI.

## Contradictions surfaced (not papered over)

- The PRD's aspect-3 prose assumed metric words come "from the extractor's
  metric field/sidecar" — neither carries them (gap above). The `--metrics`
  flag is the resolution; the PRD's "M10 metric-word source is an aspect-3
  wiring concern" (`match-and-propose/spec.md`) is exactly this wiring, and it
  is a NEW CLI input, not a modification of extract-claims.
- The matcher module + its API citations live on PR #41's branch, not this
  worktree's base. Implementation waits on the merge (or a rebase of this
  branch onto the matcher branch); planning docs proceed regardless.

## Guardrails check (CLAUDE.md)

Layer 2 (verify/reproduce machinery — proposes binding sites for existing
resolvers, authors nothing) ✓. Founder's edge ✓. Test-first, deterministic,
no network in CI (local paths only; `--metrics`/`--out` are files) ✓. Not
blocker-deferred: the pattern/notebook/figures blockers are untouched, and the
evidence gate for THIS aspect has passed (recorded) ✓.