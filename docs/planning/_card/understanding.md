# Understanding: feat reproduce-rev-pin (C8 slice 7)

Phase-2 dig note. Written before any PRD work.

## What the work is really asking

Slice 6 (v0.47.0) made a remote reproduction **attributable**: the bundle records
`source_url` + `source_commit`. It did not make it **replayable** — nothing in the product
reads `source_commit` back (`CHANGELOG.md:114`; the slice-6 PRD flags this itself as
**RISK-5**, "the pin has no in-product consumer yet… the slice's headline value is partly
deferred to a follow-on that is not scheduled", `docs/planning/reproduce-remote-intake/prd.md:226-234`).

This slice is that follow-on: `contig reproduce <url> --allow-fetch --rev <ref>` checks out a
**caller-chosen** revision, and the resulting `source_commit` is the revision the caller asked
for. That closes the loop — take a bundle, read its pin, re-run at exactly that revision.

## Affected code (all read in this worktree)

| Area | File:line | Note |
|---|---|---|
| Fetch seam type | `src/contig/runner.py:580-586` | `Fetcher = Callable[[list[str], Path], tuple[int, str]]` — returns `(exit_code, combined_output)`, unlike the bare-int `IndexBuilder`/`Installer` |
| Clone argv | `src/contig/runner.py:658-668` | `["git","clone","--depth","1","--",url,str(dest)]`; the `--` terminator is the second line of defence behind the leading-dash refusal |
| HEAD argv | `src/contig/runner.py:671-673` | `["git","rev-parse","HEAD"]` |
| Default fetcher | `src/contig/runner.py:676-694` | merges stderr into stdout; converts a missing `git` binary into `(127, msg)` rather than raising |
| Argument classifier | `src/contig/fetch.py:102-147` | pure; ordered leading-dash → https → DOI → other-scheme → scp-like → local |
| Fetch orchestration | `src/contig/fetch.py:194-264` | `dest.absolute()` first; refuse non-empty dest; `parent_created_here` cleanup scoping; clone → rev-parse → `_FULL_SHA_RE.fullmatch` |
| CLI command | `src/contig/cli.py:715-961` | flags, ordering, containment guards, the clone-before-stamp comment at `:906-912` |
| Record fields | `ReproduceRecord.source_url` / `.source_commit` | additive, default `None`, emitted unconditionally in `reproduce.json` |
| Tests | `tests/test_reproduce_remote_intake.py` (25.9K) | scripted-fetcher pattern; argv builders asserted exactly (`:207-231`) |

## The load-bearing question — resolved by experiment, not by reasoning

`git clone --depth 1` cannot check out an arbitrary SHA. The slice-6 PRD anticipated this
(**RISK-2**, `prd.md:217-219`: "a `--rev` follow-on will need `--depth 1 --branch <ref>` or a
targeted fetch"). Those two options are **not** equivalent:

- `git clone --depth 1 --branch <ref>` accepts a **tag or branch only** — it rejects a raw SHA,
  which is the single most important `--rev` input (it is what `source_commit` contains).
- A **targeted fetch** handles all three.

I ran the targeted-fetch shape locally against a scratch repo (scratchpad, not in the repo):

```
git init -q . && git remote add origin <url>
git fetch --depth 1 origin <rev>     # <rev> = full SHA | tag | branch
git checkout --detach FETCH_HEAD
git rev-parse HEAD                    # → the exact 40-hex SHA
```

- full SHA of a **non-HEAD, older** commit: works, `rev-parse HEAD` returns exactly that SHA.
- tag (`v1`): works, resolves to the tagged commit.
- nonexistent SHA: **exit 128**, `fatal: git upload-pack: not our ref <sha>` — a clean,
  distinguishable refusal (verified with the exit code unmasked by a pipe).

So one mechanism covers SHA, tag, and branch. **Recommendation: targeted fetch, and leave the
no-`--rev` path on the existing `git clone --depth 1` byte-identical** so every slice-6 test
and behaviour is untouched.

**The residual, honest risk:** fetch-by-raw-SHA depends on the server enabling
`uploadpack.allowReachableSHA1InWant`. My local test used the local file transport, which is
permissive — it proves the *client* mechanics, **not** the server policy. GitHub and GitLab
enable it; many self-hosted remotes do not. Fetching by **tag or branch** has no such
dependency. This needs an explicit decision (below) and must not be glossed.

## Open questions for the review gate

1. **Server refuses fetch-by-SHA — fall back, or refuse?**
   (a) honest refusal naming the reason and suggesting a tag/branch; (b) fall back to a full
   (non-shallow) clone + `git checkout <rev>`, which always works but can be very large.
   My lean is **(a) for this slice** — bounded, fixed argv, matches the command's standing
   "refuse, write nothing" ethos — with (b) recorded as the follow-on and a revisit trigger.
2. **Where does the *requested* ref get recorded?** `source_commit` holds the *resolved* SHA;
   for a tag or branch the requested ref is otherwise lost. Adding a third record field
   (`source_rev`) would **re-break signature verification for every v0.47.0 signed reproduce
   bundle**, exactly as slice 6 did (the canonical payload gains a key). The alternative is
   recording it only in the unsigned `reproduce.json` invocation manifest, which costs nothing.
   This is a real trade (fidelity vs. a second break in two releases) and belongs at the gate.
3. **Does `--rev` with a *local* repo refuse, or is it silently ignored?** Refusing pre-run is
   consistent with every other guard in this command. Confirm.

## Contradictions / things to flag

- Nothing in the brief contradicts the code. One correction to the brief itself: it proposed
  `git checkout FETCH_HEAD`; it should be `git checkout --detach FETCH_HEAD` to make the
  detached state explicit rather than incidental.
- **Do not "fix" the disclosed signature break** from slice 6 (pre-slice-6 signed reproduce
  bundles no longer verify). It is disclosed and pinned by a test.
- Slice 6's **manual post-merge smoke test was never run** (`prd.md:265-269` defines it: clone
  ≥1 real public repo, confirm the SHA is recorded, and confirm a repo with committed outputs
  reports `UNVERIFIED` not `REPRODUCED`). Slice 6 shipped a real bug a green suite missed
  (relative `--runs-dir` → clone into the wrong directory, `CHANGELOG.md:105`). This slice
  must carry both smoke tests, not just its own.

## Guardrail check (`CLAUDE.md`)

Layer 2 throughout — reproducibility infrastructure on the user's own compute. No NL→workflow
authoring, no wet-lab/clinical dependency, no proprietary data, no new runtime dependency
(stdlib `subprocess` only; `git` required only on the remote path, as already).
