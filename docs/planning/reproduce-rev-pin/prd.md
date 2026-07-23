# PRD: reproduce-rev-pin (C8 slice 7)

**Type:** feat · **Owner:** aliz · **Branch:** `feat/reproduce-rev-pin/aliz`

Consume the pin slice 6 recorded: `contig reproduce <https-url> --allow-fetch --rev <ref>`
checks out a caller-chosen revision, making a remote reproduction **replayable** rather than
merely attributable.

---

## Problem Statement

Slice 6 (v0.47.0) taught `contig reproduce` to take an `https://` git URL and record
`source_url` + `source_commit` on the bundle. That made a remote verdict **attributable** —
the bundle finally says which revision of which repository produced it.

It did not make it **replayable**. Nothing in the product reads `source_commit` back. The
slice-6 PRD says so itself, as its own RISK-5:

> "With `--depth 1` and `--rev` deferred, **no code path reads `source_commit`** — only a
> human can act on it (`git checkout <sha>` by hand). So the slice's headline value is partly
> deferred to a follow-on that is not scheduled."
> — `docs/planning/reproduce-remote-intake/prd.md:229-233`

`CHANGELOG.md:114-118` states the same limit in the shipped release notes: "the pin is
auditable, not yet replayable… Do not read the recorded commit as making a run automatically
replayable; it makes it **attributable**."

Concretely, today a reviewer holding a Contig bundle that says
`source_commit: 5a8dce6c…` cannot hand that bundle back to Contig and get the same checkout.
The clone is always `--depth 1` of whatever `HEAD` happened to be at fetch time — so re-running
tomorrow, after the authors push one commit, silently reproduces a **different revision** than
the bundle attests to, with no error and no warning. That is the gap this slice closes.

### The honest framing: the pin is only worth what consumes it

Recording a fact nothing reads is speculative. Slice 6 took the bet that "the field is the
schema change, and schema changes are the expensive half" (`prd.md:234-236`). This slice is
the other half of that bet, and it is what retires RISK-5. Until it lands, C8's remote intake
is a provenance string; after it, it is a reproducibility guarantee.

---

## Goals & Success Metrics

**Goal.** A caller can name the revision to reproduce, and the bundle's `source_commit` is
then the revision they named — not an accident of fetch timing.

| Metric | Today | After |
|---|---|---|
| Code paths that consume `source_commit` | 0 | 1 (`--rev`, round-trips a bundle's pin) |
| Revision reproduced by a remote run | `HEAD` at fetch time, unchosen | caller-chosen SHA, tag, or branch |
| Re-running a v0.47.0 bundle at its attested revision | impossible in-product | `--rev <source_commit>` |
| v0.47.0 signed reproduce bundles that still verify | all | all (**no signature break** — see D2) |

**Non-metric:** we do not claim the *tree* is verified. As slice 6 established, only the
**record** is signed; the checkout is evidence, not attestation. `--rev` changes which tree is
fetched, not what is attested.

---

## User Personas & Scenarios

- **The reviewer.** Holds a colleague's Contig reproduce bundle. Runs
  `contig reproduce <source_url> --allow-fetch --rev <source_commit> --claims …` and gets the
  same checkout the bundle attests to — the round-trip that makes the bundle checkable by a
  third party rather than merely readable.
- **The paper author.** Reproduces their own analysis at the tagged release
  (`--rev v2.1`) rather than at a moving `main` that has drifted since submission.
- **The batch experimenter** (the "I ran 50 published papers' code" acquisition play,
  `CAPABILITY_ROADMAP.md:1353-1355`). Pins each repo to a revision so the batch is re-runnable
  and its results stay meaningful after the upstream repos move.

---

## Requirements

### Must-have

- **R1 — `--rev <ref>` selects the revision.** A new CLI option, default `None`. Accepts a
  full 40-hex SHA, a tag, or a branch name. When omitted, behaviour is **byte-identical to
  slice 6** (`git clone --depth 1`), pinned by the existing slice-6 tests left untouched.

- **R2 — `--rev` is legal only on the remote path.** `--rev` with a **local** repo argument is
  refused pre-run (exit non-zero, nothing written) naming the reason: there is nothing to check
  out. Silently ignoring it would let a caller believe they pinned a revision when they did
  not. `--rev` with a URL but no `--allow-fetch` hits the **existing** slice-6 refusal
  unchanged (the URL is refused first, naming `--allow-fetch`).

- **R3 — The fetch shape changes only when `--rev` is given.** With `--rev`, the targeted-fetch
  sequence replaces the clone:

  ```
  git init -q <dest>                       # or: git init in dest
  git remote add origin -- <url>
  git fetch --depth 1 origin -- <rev>
  git checkout --detach FETCH_HEAD
  git rev-parse HEAD
  ```

  The `--` terminator is **verified to be accepted** by both `git remote add` and `git fetch`
  (exit 0, URL and ref parsed correctly), so the second-line-of-defence discipline that
  `_git_clone_argv` established carries over to every step of the sequence.

  **Why targeted fetch and not `clone --depth 1 --branch <ref>`:** `--branch` accepts a tag or
  branch **only** and rejects a raw SHA — and a raw SHA is the single most important `--rev`
  input, since it is exactly what `source_commit` contains. Slice 6's RISK-2 named both options
  (`prd.md:217-219`); this is the ruling between them. Verified by experiment (see
  `_card/understanding.md`): the targeted fetch resolves a non-HEAD SHA, a tag, and a branch,
  and `rev-parse HEAD` then returns the exact SHA.

- **R4 — A requested full SHA must equal the resolved SHA.** When `--rev` is a 40-hex SHA, the
  post-checkout `git rev-parse HEAD` must equal it (case-insensitive compare, recorded
  lowercase). A mismatch is a **refusal**, not a recorded pin — the same reasoning as slice 6's
  `fullmatch` rule: "a fabricated or partially-parsed pin is worse than no pin." For a tag or
  branch there is nothing to compare against; whatever resolved is recorded.

- **R5 — `--rev` is validated purely, before any I/O.** A pure predicate (sibling of
  `classify_repo_argument`) refuses, in order: a leading `-` (**first and unconditionally** —
  the same RCE-shape reasoning that governs the repo argument; an option reaching `git fetch`
  in the ref position); empty/whitespace-only; whitespace or control characters anywhere; and
  the git refname-invalid forms `..`, `~`, `^`, `:`, `?`, `*`, `[`, `\`, a leading/trailing `/`
  or `.`, and a trailing `.lock`. A `--` terminator is **also** passed in the argv as the second
  line of defence, mirroring `_git_clone_argv`.

- **R6 — A remote that refuses fetch-by-commit is an honest refusal, not a fallback.**
  **[Decision D1, taken at the interview.]** If the fetch fails, exit non-zero with nothing
  written, surfacing git's own output. When the failure is the recognisable
  `not our ref` / `upload-pack` shape, the message additionally names the likely cause —
  the remote may not enable `uploadpack.allowReachableSHA1InWant` — and suggests passing a tag
  or branch instead. A **full-clone fallback is deliberately deferred**: it can pull gigabytes
  silently on exactly the large published repos this targets. Revisit trigger: the first real
  repo a user hits that refuses fetch-by-SHA.

- **R7 — The requested ref is recorded in the unsigned manifest only.**
  **[Decision D2, taken at the interview.]** `reproduce.json` gains `requested_rev` (emitted
  unconditionally, `null` when `--rev` was not passed, matching how `source_url`/`source_commit`
  are emitted). **No `models.py` change and no new signed field** — adding one would re-break
  signature verification for every v0.47.0 signed reproduce bundle, the second such break in two
  releases. The **resolved SHA in `source_commit` remains the attested fact**; the requested ref
  is invocation metadata, which is precisely what `reproduce.json` is for. This requires an
  additive `requested_rev: str | None = None` parameter on
  `bundle.write_reproduce_bundle` (`bundle.py:72`), since the manifest is currently derived
  purely from the record.

- **R8 — Every failure path leaves no litter.** Bad `--rev`, failed fetch, failed checkout,
  failed `rev-parse`, unvalidated SHA, or an R4 mismatch → exit non-zero, no bundle, no
  leftover directory, with cleanup scoped exactly as slice 6 scoped it (`fetch.py:230-241`:
  the parent is removed only if **this call** created it).

- **R9 — The fetch still precedes the run-start freshness stamp.** Unchanged from slice 6 and
  for the same reason (`cli.py:906-912`): a checkout writes every file at checkout time, so
  stamping first would silently disable the freshness guard on exactly the published repos it
  exists for. The `--rev` path must be inserted **in the same position**, not after.

### Should-have

- **S1 — Docs updated in the same slice.** `docs/USAGE.md` reproduce section, the C8 section
  and sequencing row of `docs/technical/CAPABILITY_ROADMAP.md` (which must stop listing `--rev`
  as deferred and must retire slice 6's RISK-5), and `CHANGELOG.md`. `FEATURES.md` is
  **not** touched — its reproduce mentions are the dashboard bundle feature, not this command
  (established in slice 6).
- **S2 — The refusal messages name the flag and the fix**, in the house style of the existing
  `--allow-fetch` / `--allow-install` refusals.

### Nice-to-have

- **N1 —** `--rev` echoed in the rendered reproduction output so a terminal reader sees which
  revision ran without opening the manifest.

---

## Technical Considerations

- **Blast radius:** `src/contig/runner.py` (new argv builders), `src/contig/fetch.py` (a pure
  `--rev` validator + a `fetch_repo` branch), `src/contig/cli.py` (the flag, the R2 guard,
  threading `requested_rev`), `src/contig/bundle.py` (the additive manifest parameter). **No
  `models.py` change. No engine (`reproduce.py`) change** — as in slice 6, the CLI resolves a
  URL to a local checkout path *before* calling `run_reproduction`, so the engine never learns
  about revisions.
- **No new dependency.** stdlib `subprocess` via the existing injected `Fetcher` seam; `git`
  is required only on the remote path, exactly as already.
- **The `Fetcher` seam already fits.** `Fetcher = Callable[[list[str], Path], tuple[int, str]]`
  (`runner.py:586`) runs *any* git argv in a cwd and returns `(exit_code, combined_output)`.
  The multi-step targeted fetch is four calls through the **same seam** — no seam change, and
  CI stays network-free with a scripted fetcher.
- **`git init` into the pre-created `dest`.** `fetch_repo` already wipes and re-creates `dest`
  as scratch it owns (`fetch.py:237-238`); `git init` in that directory is the natural
  substitute for `git clone`'s directory creation.
- **Detached HEAD is explicit.** `git checkout --detach FETCH_HEAD`, not bare
  `git checkout FETCH_HEAD` — the detached state should be intentional in the argv rather than
  incidental. `rev-parse HEAD` is unaffected.
- **Guardrail check (`CLAUDE.md`).** Layer 2 throughout: reproducibility infrastructure on the
  user's own compute. No NL→workflow authoring, no wet-lab/clinical dependency, no proprietary
  data.

---

## Risks & Open Questions

- **RISK-1 (highest): fetch-by-raw-SHA depends on server policy, and CI cannot see it.** The
  local experiment used the local file transport, which is permissive — it proves the *client*
  mechanics, **not** that a given host allows `want <sha>`. GitHub and GitLab enable
  `uploadpack.allowReachableSHA1InWant`; many self-hosted remotes do not. **Mitigation:** R6's
  honest refusal, plus the manual gate below exercising a real GitHub SHA. Tag/branch `--rev`
  has no such dependency and is the documented fallback for a hostile remote.
- **RISK-2: the R9 ordering is a one-line mistake that no unit test catches unless written
  first.** Identical in shape to slice 6's RISK-1. **Mitigation:** write the ordering
  regression test in RED before any fetch code, as slice 6 did.
- **RISK-3: multi-step fetch has more failure points than a single clone.** Four git
  invocations (`init`, `remote add`, `fetch`, `checkout`) each of which can fail. **Mitigation:**
  every step's non-zero exit is a refusal that surfaces git's output and cleans up (R8); each
  gets its own test.
- **RISK-4: no real-world exercise in CI, by design** — the standing C8 condition. Slice 6
  shipped a real bug a green suite missed (relative `--runs-dir` caused the clone to land in
  the wrong directory, `CHANGELOG.md:105-113`: "a green suite proved the wiring, never the
  invocation"). **Mitigation:** the manual gate below is **mandatory**, not optional, and it
  carries slice 6's never-run checklist too.
- ~~**OPEN-1**~~ **resolved into R5a — short SHAs are refused explicitly.** Verified by
  experiment: `git fetch --depth 1 origin -- <7-hex>` fails with
  `fatal: couldn't find remote ref 296569a` (exit 128). Git cannot fetch an abbreviated SHA at
  all. R5's refname rules would **not** catch it (a 7-hex string is a perfectly valid refname),
  so it would fall through to a confusing "couldn't find remote ref" that reads like a typo'd
  branch. **R5a:** a `--rev` that is 7-to-39 hex characters is refused pre-run, naming the
  cause — pass the **full 40-character** SHA. A genuine 7-hex *branch name* is vanishingly
  unlikely and is the acceptable false positive. (A full 40-hex SHA passes
  `git check-ref-format --allow-onelevel`, so R5's rules do not accidentally refuse the input
  that matters most.)
- **OPEN-2:** should a `--rev` that resolves to a commit **not** reachable from any branch
  (e.g. a gc-able dangling commit) be treated differently? Leaning no — `not our ref` already
  covers it as a refusal.

---

## Out of Scope

- **Full-clone fallback** for remotes refusing fetch-by-SHA (D1 defers it, with a named revisit
  trigger).
- **Signing or hashing the checkout tree** — the record is the attested artifact; the checkout
  stays evidence, per slice 6.
- **Fixing the disclosed slice-6 signature break** (pre-slice-6 signed reproduce bundles no
  longer verify). Disclosed, pinned by a test, and explicitly not this slice's business.
- **DOI resolution** — out of scope in C8 by design; stays refused with a message that says so.
- **Checkout pruning**, private-repo credentials, submodules, batch mode.
- **Paper-parsing, figure/plot claims** (hard-blocked: no plot-hash without breaking the
  stdlib-only contract), **dashboard card**, **C6 eval fold-in** — standing C8 deferrals.

---

## Testing & Determinism

Test-first. Layers, in order:

1. **Pure `--rev` validator** — accept/refuse table, leading-dash first, every refname-invalid
   form.
2. **Argv builders** — asserted exactly, as slice 6 asserts `_git_clone_argv`
   (`test_reproduce_remote_intake.py:207-231`), including `--` placement.
3. **`fetch_repo` with `--rev`** via a scripted fetcher: happy path (SHA / tag / branch), each
   of the four steps failing, the R4 SHA-mismatch refusal, and no-litter-on-failure.
4. **CLI ordering & refusals** — R2 local+`--rev`, the R9 fetch-before-stamp regression, and
   `requested_rev` reaching `reproduce.json`.
5. **Back-compat** — no-`--rev` remote run is byte-identical to slice 6; a v0.47.0 signed
   reproduce bundle still verifies (the R7/D2 guarantee), asserted explicitly.

**No real git, network, or repo in CI**, enforced by seam injection — the standing C8 condition.

---

## Post-merge validation (manual, not CI) — MANDATORY

**[Decision D3.]** This slice carries slice 6's outstanding checklist as well as its own,
because slice 6's was never run and slice 6 shipped a bug because of it.

Slice 6 (outstanding, from `docs/planning/reproduce-remote-intake/prd.md:265-269`):

- [ ] Clone ≥1 real public repo through the real seam; the SHA is recorded.
- [ ] A **relative** `--runs-dir` (the CLI default, `runs`) works — the v0.47.0 bug.
- [ ] A repo with **committed outputs** reports `UNVERIFIED`, not `REPRODUCED`.

Slice 7 (new):

- [ ] `--rev <full sha>` of a **non-HEAD, older** commit → `source_commit` equals that SHA.
- [ ] `--rev <tag>` → resolves; `requested_rev` is in `reproduce.json`; `source_commit` is the
      tagged commit.
- [ ] `--rev <branch>` → resolves to that branch's tip.
- [ ] `--rev <bogus sha>` → exit non-zero, **no bundle, no leftover directory**.
- [ ] `--rev` with a local repo path → refused pre-run.
- [ ] Round-trip: take a v0.47.0 bundle's `source_commit`, pass it as `--rev`, confirm the same
      revision is checked out.
