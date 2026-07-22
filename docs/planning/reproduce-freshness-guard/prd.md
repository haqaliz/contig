# PRD — `contig reproduce` freshness guard, all binding surfaces

**Slug:** `reproduce-freshness-guard` · **Branch:** `feat/reproduce-freshness-guard/aliz`
**Capability:** C8 (Reproduce & verify existing published work), follow-on to slice 5.
**Type:** verdict-honesty fix to shipped code — not a new capability.

Source brief: `docs/planning/_card/issue.md`. Phase-2 dig: `docs/planning/_card/understanding.md`.
Every code reference below was verified against this worktree (branched from `origin/master`
@ v0.45.0), not recalled.

---

## Problem Statement

`contig reproduce` binds a claim's observed value by reading a file out of the cloned repo.
For four of its five disk-reading paths, **it never checks that the run produced that file.**
A number the authors committed to the repo therefore classifies as `REPRODUCED` — the tool
reports that a computation reproduced when it never ran.

This is not a hypothetical. Slice 5 (notebooks) hit it, fixed it *for notebooks only*, and
filed the rest as its own slice — `docs/planning/reproduce-notebook-locator/prd.md:213-215`
(R2): *"Guard scope is deliberately inconsistent. Slices 1.5 and 3 have the same
stale-artifact hole (a committed `results.json` or `de.tsv` reproduces just as falsely).
Widening the guard to them would change shipped behavior and belongs in its own slice."*

The code states the reasoning itself at `reproduce.py:1058-1067`: a committed artifact holds
the *authors'* stored outputs, so reading them reports a false `REPRODUCED` — "the exact
failure the verdict contract prevents."

**Why it matters beyond correctness.** C8's stated payoff is a community-facing, viral
credibility play — *"I ran 50 published papers' code — here is how many reproduced"*
(`CAPABILITY_ROADMAP.md:1270-1274`). Run today, that headline would be **inflated by every
repo that committed its outputs**. A reproducibility tool publishing inflated
reproducibility numbers is a worse-than-useless outcome.

**Honest limit on that argument (unverified base rate).** We do **not** know what share of
published repos commit their outputs — no such number was measured, and none is cited here.
The known-adjacent figure is about *notebooks specifically*: of 27,271 biomedical-paper
notebooks only ~3.2% reproduced the original result (Samuel & Mietchen 2024,
`CAPABILITY_ROADMAP.md:1266-1270`), which is a reproduction rate, **not** a
committed-artifact rate. The case for this slice therefore rests on the defect being
**possible and silent**, not on an unmeasured frequency. Anyone citing a base rate later
must measure it first.

### Evidence the hole is real and load-bearing

- 4 of 5 disk-reading binding paths are unguarded (table in Requirements → M1).
- The guard already exists and is proven for the 5th (`reproduce.py:1089-1104`).
- Every CLI e2e test already writes its fixture *inside* the fake executor
  (`test_cli_reproduce.py:403, 643, 779`) — i.e. the test suite already models a real run as
  one that rewrites its artifacts. The guard formalizes what the tests assume.

## Goals & Success Metrics

| Goal | Metric |
|---|---|
| No binding path can report `REPRODUCED` from an artifact the run did not write | **0** unguarded disk-reading paths (from 4). Enforced by one headline test per surface. |
| The guard is non-bypassable | No flag, no config, no silent skip. An unstamped `run_started_at` **raises** rather than degrading. A test per surface pins this. |
| Honesty contract preserved | Every new failure is `UNVERIFIED`, never `DIVERGED`. Asserted per surface. |
| No collateral behavior change | Stdout-mode pattern claims byte-identical; all non-freshness failure paths keep their existing messages and ordering. |
| Real runs are unaffected | The 6 CLI e2e locator tests pass **unmodified** (their executors already write fresh files). This is the slice's own evidence that it does not break legitimate use. |

**Non-metric (deliberate):** we do not target a "% of real repos still reproducing" number.
We have no corpus of real cloned repos in CI, and inventing one would be the kind of
unverified claim `CLAUDE.md` forbids.

## User Personas & Scenarios

- **The skeptical reviewer / reproducibility-curious researcher** (C8's target). Points
  `contig reproduce` at a published repo. Today, if the authors committed `results.json`,
  they get `REPRODUCED` for a script that may not even run. They would have no way to know.
  After: `UNVERIFIED`, naming the reason.
- **Contig itself, publishing the C8 acquisition study.** The "N of 50 papers reproduced"
  number must survive adversarial scrutiny — the first reader who notices a counted repo
  ships its outputs discredits the whole study.
- **The lone computational biologist** (core ICP) reproducing a collaborator's analysis
  before building on it. A false `REPRODUCED` here propagates into their own work.

## Requirements

### Must-have

**M1 — Guard all four disk-reading binding surfaces.** Confirmed scope decision.

| # | Surface | Code | Action |
|---|---|---|---|
| 1 | JSON `path` locator (slice 1.5) | `_observe_located` `:879-927` | add guard |
| 2 | TSV/CSV table locator (slice 3) | `_observe_table_located` `:929-972` | add guard |
| 3 | Pattern locator **with** `from` (slice 4) | `_observe_pattern_located` `:974-1056` | add guard |
| 4 | Flat `--results` `results.json` (slice 1) | `run_reproduction` `:1226-1234` | add guard |
| 5 | Pattern locator **without** `from` (stdout) | `:998-1000` | **exempt — must NOT be guarded** |
| 6 | Notebook (slice 5) | `:1058-1104` | unchanged, already guarded |

Surface 5's exemption is a requirement, not an omission: with `loc.source is None` the text
is `run_output`, a closure over the run's own captured stdout/stderr. It touches no
filesystem and cannot be stale — the run produced it by definition. A regression test must
pin that a stdout claim still binds with **no** freshness consideration.

**M2 — The freshness rule, identical to slice 5.** An artifact resolves only when
`stat().st_mtime >= run_started_at`. Strictly `<` fails. **No fudge tolerance** (R1).

**M3 — Guard fires before parse, after containment.** All three locator observers share a
byte-identical prologue (resolve → `relative_to(repo_root)` → cache-keyed read: `:884-904`,
`:942-950`, `:1002-1032`). The guard slots **after** containment, **before** the cache-keyed
read, so a stale file is never parsed. For the pattern observer, the existing size check
(`:1011-1022`) must stay **before** the mtime check, preserving `:1094`-then-`:1100` ordering
from the notebook branch.

**M4 — Unstamped `run_started_at` raises.** Confirmed decision: keep the signature
`run_started_at: float | None = None` (`:847`) and raise `ValueError` on any guarded branch
when it is `None`, exactly as `:1080-1081` does today. A `None` meaning "guard off" is a
silent bypass of a false-pass guard and is rejected.

**M5 — The flat-results stale message must be distinct.** A stale-but-valid `results.json`
must **not** reuse `"results file '<path>' is missing or unparseable"` (`:1287`) — the file
parses fine; it is stale. That wording would send a user to debug the wrong thing. A stale
flat results file marks **every** flat claim `unverified` with the freshness reason.

**M6 — `UNVERIFIED`, never `DIVERGED`.** A freshness failure is an availability/provenance
problem, never evidence the number is wrong.

**M7 — Test migration.** Measured, mechanical, no behavior invented:
- 15 tests flip status → `unverified` (JSON `:1282, 1291, 1303, 1405`; table `:1480, 1502,
  1523, 1541, 1707, 1726, 1766`; pattern-file `:1968, 2105, 2205, 2297`). Each migrates to
  the shipped notebook pattern: module-level `_RUN_START` (`:2343`), an mtime-stamping
  writer (`:2364`), `run_started_at=_RUN_START` via `_run`'s `**overrides` (`:1255`).
- 6 tests assert messages the guard now pre-empts (`:1331, 1600, 1617, 1634, 2277, 2230`) —
  fixtures must be stamped fresh so they keep testing what they were written to test.
- 2 of the 15 also assert parse-cache call counts (`:1726`, `:2205`) that a pre-parse guard
  drops to 0.
- ~42 located tests total need `run_started_at` threaded once M4 lands.
- The 6 CLI e2e locator tests must pass **unmodified**.

**M8 — One headline test per newly-guarded surface**, mirroring
`test_run_reproduction_notebook_stale_exact_match_is_unverified` (`:2415`): a stale artifact
whose stored value matches the claim **exactly** is `UNVERIFIED`, not `REPRODUCED`. This is
the test that would have caught the bug, so it is the test that proves the fix.

### Should-have

- **S1 — CLI docstring** documents the freshness requirement once, covering all locator forms
  (it currently reads as notebook-specific).
- **S2 — CHANGELOG + `CAPABILITY_ROADMAP.md` C8 entry** record the behavior change and close
  R2 explicitly, so the "deliberately inconsistent" note is not left contradicting the code.
- **S3 — Make the staleness reason distinguishable (the revisit trigger's only evidence
  source).** R2 commits to revisiting "on the first real repo where a legitimate run is
  blocked" — but that trigger can never fire if a stale-artifact `UNVERIFIED` is
  indistinguishable from a missing-file or unparseable-file one. At minimum, freshness
  failures must carry a **consistent, greppable message stem** (the shipped notebook wording
  *"was not rewritten by this run"* is the natural choice) so a user or a future C8 study can
  count them without new telemetry. A structured field on `ClaimResult` would be stronger but
  costs a `models.py` change this slice otherwise avoids — deferred unless the interview
  disagrees.

### Nice-to-have (explicitly later)

- Surfacing staleness distinctly in the rendered report (vs. other `UNVERIFIED` reasons).
- A `--run`-produced-file inventory (would strengthen R1a; needs its own design).
- Extending freshness to remote/`<doi|url>` intake — that intake does not exist yet.

## Technical Considerations

- **No CLI change.** `cli.py:850` already stamps `run_started_at = time.time()`
  unconditionally, after pre-run validation, before the executor, and deliberately not
  re-stamped on an `--allow-install` retry (`:846-849`); it is passed at `:863`.
- **No `models.py` change, no new claim-file syntax, no new dependency.** `stat()` is stdlib
  and already used. The stdlib-only contract holds.
- **One production caller.** `run_reproduction` is called once outside tests (`cli.py:852`),
  so the M4 contract change is contained; the other 19 call sites are tests.
- **Shared helper.** All four locator dataclasses (`:149-212`) expose `.source`, so one
  helper serves the three locator branches. Surface 4 needs its own `stat()` — it has no
  containment step, the path not being user-authored in the same way.
- **`--allow-install` interaction is already correct and must not regress.** The stamp is
  taken once before the first run; a retry that rewrites an artifact yields an mtime after
  the stamp, so it resolves. Pinned today by `:2497` for notebooks; needs an equivalent for
  at least one newly-guarded surface.
- **Reproducibility/verification impact — this is the point.** The guard extends "the
  artifact was produced by the run being verified" from one locator to all of them.

## Risks & Open Questions

- **R1 — mtime granularity (inherited, accepted, do NOT "fix").** On a coarse-mtime
  filesystem a genuinely regenerated file could report an mtime marginally before the run
  start, yielding a false `UNVERIFIED`. Accepted deliberately: a false `UNVERIFIED` is honest
  and recoverable, a false `REPRODUCED` is not. No fudge tolerance — *"a tolerance is exactly
  the size of the hole it opens"* (`reproduce-notebook-locator/prd.md:202-208`). Restated
  here so it is not later quietly widened.
- **R1a — proves *rewritten*, not *recomputed* (inherited, accepted).** A `--run` of
  `cp committed.json out.json`, a `touch`, or a restored cache passes while computing
  nothing. This closes the dominant *honest* hole, not adversarial self-deceit — the same
  boundary slice 1's "re-runnable" drew. The guarantee must never be stated more strongly.
- **R2 — the usability risk, and the one most likely to make this slice look wrong in
  hindsight.** Legitimate runs that do not rewrite an artifact exist: a `make`/`snakemake`
  target already up to date, a repo writing into a timestamped output dir, or a `--run` that
  executes only the final step of a multi-step analysis while the claim addresses an earlier
  artifact. Those now return `UNVERIFIED`. **Decision: ship strict with no opt-out** — if the
  run did not produce the artifact, `UNVERIFIED` is the true answer, and a flag would be a
  hole the exact size of the defect. **Accepted with eyes open**, and the revisit trigger is
  named: the first real repo where a legitimately-reproducing run is blocked by the guard.
  Consequence to state plainly in any published C8 study: reported numbers count only claims
  bound to artifacts the run itself wrote.
- **R4 — symlinked artifacts (named, not yet decided).** The observers call
  `Path.resolve()`, which **follows symlinks**, so `stat()` reads the *target's* mtime. A repo
  whose output path is a symlink into a shared cache or a scratch mount would be judged on the
  target's mtime — plausibly stale even when the run legitimately produced it. This is a
  distinct case from R2 (there the file genuinely was not rewritten; here it may have been).
  No fixture in the suite exercises it. The tech-plan should decide explicitly whether to
  `stat()` the symlink itself (`follow_symlinks=False`), and either way pin the behavior with
  a test rather than inherit it accidentally.
- **R5 — clock skew (distinct from R1).** R1 is about mtime *granularity*; this is about the
  run-start stamp and the file mtime coming from **different clocks** — `time.time()` on the
  orchestrating host vs. an mtime written over NFS/SMB by a machine whose clock differs.
  Symptom is identical (false `UNVERIFIED`), cause and remedy are not. Same accepted posture
  as R1 — no tolerance — but recorded separately so a future debugger is not sent to the
  wrong explanation.
- **R3 — message pre-emption.** The guard fires before existing failure checks, so some
  currently-reported reasons become unreachable for stale files. Mitigated by stamping the 6
  affected fixtures fresh (M7) so they keep exercising their original path.
- **Open question (deferred, not blocking):** should a *missing* artifact and a *stale*
  artifact stay distinct messages? Current lean: yes — "missing" and "not rewritten by this
  run" send a user to different fixes.

## Out of Scope

- Any opt-out flag or per-claim override (R2 decision).
- Content-hash or before/after-diff freshness. A deterministic rerun writes identical bytes,
  so hashing would report a false *stale* — strictly worse than mtime here.
- Any fudge tolerance on the mtime comparison (R1).
- Guarding the stdout-mode pattern locator (M1, surface 5 — immune by construction).
- Changing the notebook branch's shipped behavior beyond factoring out a shared helper.
- Paper-parsing, remote `<doi|url>`, dashboard card, C6 eval fold-in — standing C8 deferrals.
- Figure/plot claims — hard-blocked (no plot-hash, stdlib-only; `CAPABILITY_ROADMAP.md:1256-1263`).

## Acceptance (test-first)

1. Per newly-guarded surface (4): a **stale artifact whose value matches the claim exactly**
   is `UNVERIFIED` with a message naming staleness — never `REPRODUCED`. (M8)
2. Per newly-guarded surface: a **fresh** artifact (mtime ≥ run start) classifies exactly as
   it does today — `reproduced` / `within-tolerance` / `diverged` unchanged.
3. A stdout-mode pattern claim binds with no freshness consideration and is byte-identical
   to today. (M1 surface 5)
4. Any guarded branch with `run_started_at=None` **raises `ValueError`**. (M4)
5. A stale flat `results.json` marks every flat claim `unverified` with the freshness reason,
   **not** the "missing or unparseable" message. (M5)
6. The oversized-file message still names the byte count — size check before mtime. (M3)
7. An `--allow-install` retry that rewrites an artifact resolves it, on at least one newly
   guarded surface. (Technical Considerations)
8. All 6 CLI e2e locator tests pass **unmodified**.

Deterministic throughout: fixture files with `os.utime`-stamped mtimes, injected
`run_started_at`, scripted executors. **No real repo, network, or pip in CI.**
