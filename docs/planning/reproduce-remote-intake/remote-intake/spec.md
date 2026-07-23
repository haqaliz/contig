# Aspect spec: remote-intake

Parent PRD: [`../prd.md`](../prd.md). Single aspect — the slice is one cohesive change and
splitting it would create artificial seams between the flag, the fetch, and the pin.

## Problem slice and user outcome

`contig reproduce` accepts only a local directory (`cli.py:781-784`). A reviewer who wants to
reproduce a published paper must clone by hand, and the resulting bundle names no commit
(`models.py:669-678`, `bundle.py:89-96`) — so a remote reproduction is not auditable.

**Outcome:** `contig reproduce https://github.com/lab/paper-code --allow-fetch --run "…"
--claims claims.json` clones the repo, runs it, and writes a bundle that names the exact
commit the verdict was computed over.

## In scope

- `https://`-only remote intake behind an opt-in `--allow-fetch` (default off).
- A `Fetcher` seam in `runner.py` + `default_fetcher` + fixed argv builders.
- Shallow clone (`--depth 1`) into `<runs_dir>/<reproduce_id>/source/`.
- `git rev-parse HEAD` → validated 40-hex SHA → recorded on the record and in `reproduce.json`.
- Additive `source_url` / `source_commit` fields with pre-slice-6 back-compat.
- Honest pre-run refusals (no `--allow-fetch`, non-`https` scheme, leading `-`, DOI) and honest
  post-fetch failures (git absent, clone fails, unresolvable SHA), each leaving no bundle.
- Docs sweep: `CHANGELOG.md`, `CAPABILITY_ROADMAP.md` (C8 section, `:1377`, row `:1404`),
  `docs/USAGE.md`.

## Out of scope

DOI resolution, `--rev`, ssh/`git://`/`file://`, batch mode, credentials/private repos, tree
hashing of the checkout, dashboard card, C6 fold-in. See PRD → Out of Scope.

## Acceptance criteria (testable)

1. A pure classifier maps a repo argument to `local` / `remote` / a named refusal; every
   refusal shape (`-`-leading, `ssh://`, `git://`, `file://`, `ext::`, `git@host:`, `doi:`,
   bare `10.`) is covered.
2. A remote URL **without** `--allow-fetch` exits non-zero naming the flag; no bundle exists.
3. `_git_clone_argv` / `_git_rev_parse_argv` produce exact fixed argv; the real
   `default_fetcher` is **asserted on, never executed**.
4. A scripted fetcher that populates a fixture tree and returns a canned SHA yields a record
   with `source_url` = the URL and `source_commit` = that SHA, both present in `reproduce.json`.
5. **The freshness regression (G3):** a cloned tree whose committed `results.json` holds a
   value *exactly equal* to the claim reports `unverified`, not `reproduced`.
6. A `rev-parse` returning non-40-hex output → refusal, no bundle.
7. A failed clone leaves **no** `<runs_dir>/<reproduce_id>/` directory behind.
8. A non-empty clone destination is refused rather than cloned into.
9. A pre-slice-6 `reproduce_record.json` (no `source_*` keys) still loads, fields defaulting
   to `None`.
10. Every pre-existing reproduce test passes unchanged; a local-path record differs only by
    the two new `None` fields.

## Dependencies and sequencing

No external dependency. Phases 1–2 are independent and parallelizable; 3 depends on 2;
4 is independent; 5 depends on 1, 3, 4; 6 (docs) depends on 5.

## Risks specific to this aspect

- **Ordering (PRD RISK-1 / R2):** the clone must precede the `run_started_at` stamp, and the
  containment checks must be evaluated against the *prospective checkout path* so they still
  run before the clone. Both are addressed explicitly in the plan.
- The real `default_fetcher` is never exercised in CI (house style); the post-merge manual
  smoke test is the only real-network validation.
