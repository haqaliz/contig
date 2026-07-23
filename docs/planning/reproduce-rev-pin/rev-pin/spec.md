# Aspect spec: rev-pin

Parent PRD: [`../prd.md`](../prd.md). Single aspect — the flag, the targeted fetch, and the
manifest field are one cohesive change; splitting them would create artificial seams exactly
as slice 6 judged for `remote-intake`.

## Problem slice and user outcome

`contig reproduce` always clones `HEAD` at fetch time (`runner.py:658-668`,
`git clone --depth 1`). The commit it records (`fetch.py:251-262`) is therefore an accident of
*when* the command ran, and no code path reads it back — slice 6's own RISK-5
(`../reproduce-remote-intake/prd.md:226-234`). Re-running tomorrow, after the authors push,
silently reproduces a different revision than the bundle attests to.

**Outcome:** `contig reproduce https://github.com/lab/paper-code --allow-fetch --rev <sha|tag|branch>
--run "…" --claims claims.json` checks out the revision the caller named, and `source_commit`
is that revision — so a v0.47.0 bundle's pin can be handed back to Contig and re-run.

## In scope

- `--rev <ref>` (default `None`), legal **only** with a remote URL; refused pre-run on a local
  repo argument.
- A pure `--rev` validator (sibling of `classify_repo_argument`): leading `-` first and
  unconditionally, then empty/whitespace/control chars, git refname-invalid forms, and the
  7-to-39-hex short-SHA refusal (R5a).
- New fixed argv builders for `git init` / `git remote add` / `git fetch --depth 1` /
  `git checkout --detach`, each carrying the `--` terminator where git accepts it.
- A `fetch_repo` branch: targeted fetch when `--rev` is given, the **unchanged** `git clone
  --depth 1` when it is not.
- R4 equality check: a requested full 40-hex SHA must equal the resolved `rev-parse HEAD`.
- R6 honest refusal when the remote refuses fetch-by-commit, naming
  `uploadpack.allowReachableSHA1InWant` and suggesting a tag/branch. **No full-clone fallback.**
- `requested_rev` in `reproduce.json` only, via an additive `write_reproduce_bundle` parameter
  (`bundle.py:72`). **No `models.py` change, no new signed field.**
- Docs sweep: `CHANGELOG.md`, `CAPABILITY_ROADMAP.md` (C8 section + sequencing row — must stop
  listing `--rev` as deferred and must retire slice 6's RISK-5), `docs/USAGE.md`
  (table `:59`, reproduce section `:216-263`). **Not `FEATURES.md`.**

## Out of scope

Full-clone fallback, short-SHA support, signing/hashing the checkout tree, fixing the disclosed
slice-6 signature break, DOI resolution, checkout pruning, credentials/private repos,
submodules, batch mode, dashboard card, C6 fold-in. See PRD → Out of Scope.

## Acceptance criteria (testable)

1. A pure validator maps a `--rev` string to accept / a named refusal; every refusal shape is
   covered (leading `-`, empty, whitespace, control char, `..`, `~`, `^`, `:`, `?`, `*`, `[`,
   `\`, leading/trailing `/` or `.`, trailing `.lock`, and 7-to-39-hex).
2. A full 40-hex SHA, a tag name, and a branch name are all **accepted** by the validator.
3. `--rev` with a **local** repo path exits non-zero naming the reason; no bundle exists.
4. `--rev` with a URL but no `--allow-fetch` hits the **existing** slice-6 refusal unchanged
   (the URL is refused first, naming `--allow-fetch`).
5. Each new argv builder produces exact fixed argv, including `--` placement; the real
   `default_fetcher` is **asserted on, never executed**.
6. A scripted fetcher yields, for `--rev <sha>`, a record whose `source_commit` == that SHA,
   and a `reproduce.json` carrying `requested_rev` == the requested ref.
7. `requested_rev` is emitted **unconditionally** — present and `null` when `--rev` was omitted.
8. R4: a scripted `rev-parse` returning a **different** SHA than the requested full SHA →
   refusal, no bundle.
9. Each of the four git steps failing in turn → refusal surfacing git's output, **no bundle and
   no leftover directory**, with the `parent_created_here` scoping honoured
   (`fetch.py:230-241`).
10. R6: a fetch failure whose output carries the `not our ref` / `upload-pack` shape produces
    the message naming `allowReachableSHA1InWant` and suggesting a tag/branch.
11. **The ordering regression (mirrors slice 6's G3):** with `--rev`, the checkout still
    precedes the `run_started_at` stamp — a checked-out tree whose committed `results.json`
    holds a value *exactly equal* to the claim reports `unverified`, not `reproduced`.
12. A no-`--rev` remote run is byte-identical to slice 6; every pre-existing reproduce test
    passes unchanged.
13. A v0.47.0 signed reproduce bundle **still verifies** (the D2 guarantee), asserted
    explicitly.

## Dependencies and sequencing

No external dependency; no new runtime dependency. The validator (1–2) and the argv builders
(5) are independent and parallelizable; the `fetch_repo` branch (6, 8, 9, 10) depends on the
argv builders; the CLI wiring (3, 4, 7, 11) depends on the `fetch_repo` branch; back-compat
(12, 13) is independent; docs depend on everything.

## Risks specific to this aspect

- **Server policy is invisible to CI (PRD RISK-1).** Fetch-by-raw-SHA needs
  `uploadpack.allowReachableSHA1InWant`; the local experiment used the permissive local
  transport and proves client mechanics only. R6 + the manual gate are the mitigation.
- **Ordering (PRD RISK-2).** The checkout must precede `run_started_at` exactly as the clone
  does (`cli.py:906-929`); criterion 11 is written in RED first.
- **Four git calls, four failure points** (PRD RISK-3) vs. slice 6's one clone — criterion 9
  covers each individually rather than in aggregate.
- The real `default_fetcher` is never exercised in CI (house style); the **mandatory** manual
  gate in the PRD — which carries slice 6's never-run checklist as well — is the only
  real-network validation.
