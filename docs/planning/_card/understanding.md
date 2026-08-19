# Understanding — reproduce-local-tree-hash (C8 slice 9)

Phase-2 dig note. Grounds the PRD interview. All file:line refs verified in this worktree.

## What the work is really asking

Populate `ReproduceRecord.source_tree_sha256` for a **local** `contig reproduce <path>`
run. Today it is computed only inside `if repo_argument.kind == "remote":`
(`cli.py:1050-1061`), so a local run's signed record carries `source_url`,
`source_commit` **and** `source_tree_sha256` all `None` — it attests the verdict while
binding nothing about the code that produced it.

Slice 8 named this as its own deferral in three places:
`docs/planning/reproduce-checkout-hash/prd.md:217` ("Local-path checkout hashing
(deferred)"), `CAPABILITY_ROADMAP.md:1495`, and `CHANGELOG.md:715-716`.

This is Layer-2 reproducibility integrity (moat #1), stdlib-only, and — like slice 8 —
CI-observable with real fixture trees.

## The load-bearing contradiction the dig found

Slice 8 did **not** defer local hashing purely for scope. Its own dig argued *against*
it, and its PRD argued *for* it, from the same fact:

- **Against** — `docs/planning/reproduce-checkout-hash/understanding.md:89-99`: a local
  repo path is "dirty-by-design, unbounded, and often full of unrelated files (`.venv/`,
  data, outputs) — noisy and expensive to hash, **lower attestation value (no commit
  anyway)**."
- **For** — `docs/planning/reproduce-checkout-hash/prd.md:43` and `CHANGELOG.md:715-716`:
  the tree hash is "**groundwork** for the deferred local-path and shipped-`source/`
  integrity checks, **where there is no commit at all**."

Same fact — no commit — read as devaluing in one document and as motivating in the other.
**The PRD must pick one and say why.** This is Q1 below and it is the first question of
the interview, ahead of any implementation detail.

## Affected code (map from the dig)

- **CLI** `cli.py:819-1105` — the `reproduce` command. Ordering that matters:
  - `:921` classify → `:962` **local** `repo_path = Path(repo)` (the user's directory
    **as given**, no copy) vs `:966-975` **remote** `repo_path = <runs_dir>/<id>/source`
    (a prospective path).
  - `:1040-1061` **remote-only** fetch **and** `compute_tree_sha256(repo_path)` at `:1061`.
  - `:1071` `run_started_at = time.time()` — the freshness stamp.
  - `:1073-1085` `run_reproduction(...)`; `:1086-1097` **remote-only** `model_copy(update=
    {repo, source_url, source_commit, source_tree_sha256})`; `:1099` bundle write.
  - **The local branch has no analog to `:1061` at all.** The natural insertion point is
    immediately before `:1071`, still pre-executor.
- **Hash** `bundle.py:334-370` `compute_tree_sha256` — `os.walk(followlinks=False)`,
  prunes `.git` **by name at any depth** and any **symlinked directory**, skips symlinked
  and non-regular files, folds sorted `f"{posix_relpath}\0{sha256_file(p)}\n"` → one
  sha256. Any `OSError` (including via the deliberate `_raise` onerror at `:326-331`)
  returns **`None` for the whole digest — never partial**. Reusable **as-is**; this slice
  should not need to modify it unless Q2/Q3 force an exclusion or bound parameter.
- **Model** `models.py:687-706` — `source_url`/`source_commit`/`source_tree_sha256`, all
  `str | None = None`.
- **Signing** `signing.py:55-64` `canonical_record_bytes` — `model_dump(mode="json")` then
  `json.dumps(sort_keys=True, separators=(",",":"))`, **no field exclusion**.
- **Engine** `verification/reproduce.py:838-1214` — `run_reproduction`; the executor runs
  with **`repo_path` as its cwd** (`:1214`, retry `:1251`). `run_started_at` is used only
  as the freshness gate (`_require_fresh`, `:880-917`). It never touches
  `source_tree_sha256`.
- **Tests that pin today's behavior and must be deliberately rewritten:**
  `tests/test_reproduce_checkout_hash.py:499-520`
  `test_local_reproduce_records_no_source_tree_sha256`, plus the module docstring at
  `:17-20` ("Local runs never compute it."). The mirror-template for the new pre-run
  assertion is `test_source_tree_sha256_is_taken_pre_run_not_post_retry` (`:523-556`).

## What makes local genuinely different from remote (not just "the same, elsewhere")

These are the findings that make this more than a one-line `if`:

1. **No moment of freshness.** Remote's pre-stamp hash is meaningful because "a clone
   writes every file at clone time" (`cli.py:1040-1047`). A local directory has no such
   moment — the pre-run hash is of "whatever is already sitting there," including
   leftovers from a **previous** local reproduce run against the same repo.
2. **The run writes into the hashed directory.** For a local run the executor's cwd **is**
   the user's repo (`reproduce.py:1214`). So the recorded digest describes the tree's
   **inputs**, and the tree on disk **after** the run will not match it. True for remote
   too (slice 8's R3), but far more visible when it is the user's own working copy.
3. **`--runs-dir` defaults to the relative string `"runs"`** (`cli.py:834`), resolved
   against **CWD**, not against `repo_path`. The plausible invocation
   `cd my-repo && contig reproduce . --run ...` puts the bundle at `<repo>/runs/<id>`,
   i.e. **inside the tree we would hash**. This run's own bundle is written after the
   hash (`:1099` ≫ `:1071`), so it cannot corrupt its own digest — but the **second** run
   against that repo would hash the first run's bundle. Contig's own output would then
   contaminate Contig's own measurement.
4. **`compute_tree_sha256` prunes only `.git` and symlinks.** Pointed at a real working
   copy it will happily walk `.venv/`, `node_modules/`, `__pycache__/`, `runs/`. The dig
   confirms **no ignore-list concept exists anywhere in the repo** to reuse.
5. **No `source_commit` for local either.** No `git rev-parse` is ever run against an
   arbitrary local path (`fetch.py`'s rev-parse is inside `fetch_repo`, remote-only).

## Open questions for the interview

### Q1 — Does a local tree hash actually attest anything? (load-bearing; see above)

Honest analysis from the dig: **no `source/` copy is made for a local run**
(`cli.py:966-975` is the `else` branch only), so a third party handed a local bundle has
neither the tree nor a commit to fetch — they **cannot recompute the digest**. The
third-party-attestation framing that justified slices 6-8 does **not** transfer.

What it *does* buy, stated narrowly:
- **(a) Drift evidence over time on the same tree** — re-run later, a changed digest
  proves the inputs changed. Today nothing detects that.
- **(b) Tamper-evidence via the signature** — the digest rides the signed record.
- **(c) Removes an ambiguity**: `null` currently means both "local run" and "could not be
  computed." Populating it makes `null` mean only the latter.

Recommendation: **ship it, framed as (a)+(b)+(c), and explicitly disclaim third-party
attestation** — resolve the contradiction in favor of the PRD's framing, but write the
understanding note's caveat into the CHANGELOG. If (a)-(c) are not worth a slice, the
honest alternative is to **close this as won't-do and re-point at the `extract-claims`
PDF-intake alternate** rather than ship provenance theater.

### Q2 — What to exclude from a local tree walk

- (a) **Hash as-is** — simplest, zero new policy, but includes `.venv`/`node_modules` and,
  on a second run, a prior bundle.
- (b) **As-is, plus exclude the resolved runs dir when it falls inside `repo_path`** —
  targeted, defensible: that directory is *Contig's own artifact*, not the repo's code.
  Fixes finding 3 without inventing general ignore policy.
- (c) **A general ignore list** (`.venv`, `node_modules`, …) — **recommend against**: no
  precedent, invents policy, and a name-based denylist is a correctness hazard (excluding
  `node_modules` would hide a genuine dependency change from the digest).

Recommend **(b)**.

### Q3 — Bounding the walk

No precedent exists for bounding a *filesystem walk*. The nearest precedent is
`_MAX_MATCH_BYTES = 8 MiB` (`reproduce.py:51`), and its lesson is about *failure mode*,
not size: over-cap input is **UNVERIFIED or a refusal, never silent truncation** —
"Text over the cap is UNVERIFIED rather than silently truncated, which could report
'0 matches' for a pattern that does match past the cut" (`reproduce.py:46-50`).

Applied here: **if we bound, exceeding the bound must return `None`, never a partial
digest** — which is already `compute_tree_sha256`'s all-or-`None` contract. Options:
- (a) **Unbounded** — matches the function's current contract; risk is a long pre-run
  pause on a huge tree that reads like a hang.
- (b) **Bounded by cumulative bytes and/or file count → `None` + a stated reason.**

Recommend **(a) unbounded for this slice**, cost documented, unless the user wants the
bound; the walk is pre-run and `sha256_file` streams in 1 MiB chunks, so it is I/O-bound
but memory-safe.

### Q4 — Should local also capture `source_commit` (+ dirty flag)? — recommend OUT of scope

For a local directory that *is* a git checkout, `git rev-parse HEAD` plus a dirty
indicator would be **more** third-party-meaningful than a tree hash (they could fetch that
commit), and would arguably answer Q1 better than this slice does. But it means shelling
git at an arbitrary user directory, needs a non-git-directory fallback, and is a different
feature. **Flag it, defer it, name it in the CHANGELOG as the honest follow-on.**

### Q5 — Retiring the pinned test, deliberately

`test_local_reproduce_records_no_source_tree_sha256` (`:499-520`) and the module docstring
(`:17-20`) currently assert the exact behavior this slice inverts. Following the v0.50.0
precedent, that guard is **retired deliberately and replaced** by one pinning the new
contract — not deleted to go green.

## Signature question — settled, no break

`source_tree_sha256` is **already** an always-present key in the canonical payload
(`signing.py:55-64` dumps every declared field; `None` renders as `null`). Populating it
for local runs changes a **value**, not the key set. A previously-signed bundle re-derives
its canonical bytes from its own stored `null` and still verifies. **This slice is not a
fourth signature break** — and a regression test should pin exactly that, mirroring
`test_pre_slice_8_signature_over_a_record_without_tree_hash_no_longer_verifies` (`:355-381`).

## Guardrails check (CLAUDE.md)

Layer-2 reproducibility integrity ✓ · no Layer-1 NL→workflow ✓ · no wet-lab/clinical
credentials or proprietary data ✓ · stdlib-only, no new dependency (`hashlib`/`os` only;
declared deps stay `pydantic`/`typer`/`cryptography`) ✓ · honesty posture preserved
(degrade to `None`, never a partial or fabricated digest) ✓.

## Contradictions / risks surfaced, not papered over

1. **The Q1 contradiction** between slice 8's own PRD and its own dig note — must be
   resolved explicitly in this PRD.
2. **Third-party recomputation does not transfer to local** (no `source/` copy). The
   slice's value proposition is genuinely narrower than slices 6-8's and must be written
   that way.
3. **Contig's own `runs/` output can land inside the hashed tree** and contaminate the
   digest on the second run against the same repo.
4. **This is push, not demand-pull** — no design partner asked for it; organic frequency
   of local reproduce runs is unmeasured. Same honest posture as the last several slices.
