# PRD — reproduce-locator-inference (C8: evidence-gated locator inference)

Status: draft for review. Owner: aliz. Branch: `feat/reproduce-locator-inference/aliz`.
Sources: `docs/planning/_card/issue.md` (contig-next handoff), `_card/understanding.md`
(Phase-2 dig, two-agent code map), `docs/technical/CAPABILITY_ROADMAP.md` C8.
Capability: **C8 follow-on slice** to paper-claim extraction (`contig extract-claims`).

---

## Problem Statement

`contig extract-claims` (`cli.py:1398`) turns a paper into a **locator-less** draft —
`{"id","value","tolerance"}` per claim (`cli.py:1574`) — plus a `.review.md` sidecar whose
job is to tell a human to hand-add a locator. `contig reproduce` then binds each claim
through one of five shipped resolvers.

**The hand-add step is the only manual link left in the paper → verdict chain.** Every other
link shipped: DOI/PDF intake, claim extraction, five locator families, the freshness guard,
remote intake, `--rev` pinning, tree hashing, and the reproduce-guard eval fold-in
(`CAPABILITY_ROADMAP.md:1762`, `:2397`). A user today runs `extract-claims` on a paper, gets
a draft, and must then open the repo and hand-write a locator per claim before Contig does
anything at all.

**Evidence it is real and unblocked:** `docs/planning/reproduce-paper-claims/prd.md:120`
files inference under "Nice-to-have (explicitly deferred, not this slice) — a separate,
harder slice; v1 emits locator-less drafts by design", and `CHANGELOG.md:1635` confirms the
shipped command emits "**No locator inference**". It is a scope deferral, not a blocker.

### The objection this slice must answer

`CHANGELOG.md:1618-1622` records locator-lessness as a **principled** choice:

> "the paper gives the *value*, not *where it lives in the repo's output*, so **inventing a
> `from`/`path` locator would be dishonest**; the user adds the locator during review."

That objection is correct as stated and **this slice does not overturn it.** It sidesteps it.
We never infer a locator *from the paper* — that would be invention. We search the repo's
**actual artifacts** for the claim's value and propose a binding site **only on unambiguous
evidence**; 0 or >1 candidates emit nothing. **Evidence-gated search, not guessing.**

---

## Goals & Success Metrics

**The guarantee is precision. Recall is measured and reported, never targeted.**

| # | Metric | Bar |
|---|---|---|
| G1 | Wrong locators proposed on the committed fixture corpus | **Exactly 0.** Hard gate. |
| G2 | Claims correctly bound on the fixture corpus | Reported honestly as `n/N`, no target |
| G3 | Ambiguous/absent claims | Emit **no** locator, with the candidate **count** named in the sidecar |
| G4 | Verdict contract | An inferred locator can never produce a verdict a hand-written identical locator would not |

G1 is the whole product. A false `REPRODUCED` from a locator bound to a coincidentally-equal
number is the worst outcome available to this repo and, unlike a false `UNVERIFIED`, is not
recoverable by re-running. Every ambiguous design call resolves toward emitting nothing.

**G1 is self-graded, and that is stated rather than glossed.** We author the fixture corpus,
so a zero there proves the code does what we intended — **not** that it is safe on a repo we
did not write. This is the same "synthetic, self-graded seed" limit the CHANGELOG records on
every shipped guard. The remedy is the repo's existing one: **a manual post-merge real-repo
gate**, run and recorded, exactly as every prior C8 slice has done
(`CAPABILITY_ROADMAP.md:2321`). Inference earns it more than any prior slice, because it is
the first C8 feature that makes a binding choice *on the user's behalf*.

**Non-metric, stated honestly:** this slice is **push, not demand-pull**. No design partner
asked for it; the friction removed is reasoned from the shipped surface, not observed in the
field. Organic `extract-claims` volume is unmeasured.

**Revisit trigger:** if the first 20 real `infer-locators` invocations across non-authored
repos bind **zero** claims, the feature is restated as taxonomy-only rather than quietly kept.

---

## Personas & Scenarios

- **Lone computational biologist** (primary ICP) wants to check whether a paper's headline
  numbers regenerate before building on it. Today: reads the paper, reads the repo, hand-writes
  a locator per claim. After: `extract-claims` → `infer-locators` → review the sidecar →
  `reproduce`.
- **Core facility / reviewer** doing CODECHECK-style verification at volume; the manual step is
  what makes it not worth doing for more than one paper.
- **Contig itself (GTM).** "I ran 50 published papers' code" (`CAPABILITY_ROADMAP.md:2340`) is
  only affordable if binding is not hand-done 50 times.

---

## Requirements

### Must-have

- **M1 — A new command, `contig infer-locators <repo> <claims.json>`.** Reads an existing
  draft, walks the repo, writes an updated claims file plus a review sidecar.
  `extract-claims` is **not modified** — see Technical Considerations for why this is load-bearing.
- **M2 — JSON locator inference.** Walk each candidate `.json`, enumerate every
  `(path_expr, numeric_leaf)` pair, match against the claim value, emit
  `{"from","path"}` on exactly one match. Path expressions must be re-resolvable by the
  **unchanged** `resolve_pointer` (`reproduce.py:129`) — pinned by a round-trip test.
- **M3 — Table locator inference.** Walk each candidate `.tsv`/`.csv`(`.gz`), enumerate cells,
  emit a **complete** `{"from","column","row",…}` on exactly one match, re-resolvable by the
  unchanged `resolve_cell` (`reproduce.py:263`).
- **M4 — The ambiguity rule.** 0 or >1 candidate sites ⇒ **no locator emitted**, claim left
  locator-less, the **count** recorded in the sidecar. Never an arbitrary pick. Mirrors
  `resolve_match`'s single `!= 1` branch (`reproduce.py:408`).
- **M5 — Scale reconciliation, disclosed.** Attempt both `v` and `v/100`; **report which
  matched** in the sidecar. If both match at *different* sites ⇒ ambiguous ⇒ emit nothing.
  Never silently rescale.
- **M6 — Round-trip invariant.** The emitted claims file round-trips through the **unchanged**
  `load_claims` before replacing anything; a `ClaimsError` writes nothing and exits non-zero.
  Mirrors `cli.py:1583-1601` exactly.
- **M7 — Never raises.** Unreadable / malformed / oversized artifacts are skipped as
  honest non-candidates, never crash the sweep, never abort the other claims.
- **M8 — Safe walk.** Mirror `compute_tree_sha256` discipline: `os.walk(followlinks=False)`,
  prune `.git` at any depth, skip symlinks. Emitted `from` paths are repo-relative **by
  construction** and must survive the existing CLI containment guard (`cli.py:1219-1231`) —
  pinned by a test.
- **M9 — Refuse low-information values.** Coincidence is not uniform across values: `0`, `1`,
  `0.5`, `0.05`, `100` and other small/round numbers appear all over a real repo, while
  `0.9134` essentially does not. Inference **refuses to bind** a claim whose value falls below
  an information threshold (a small deny-list plus "integer with ≤ 2 significant digits"),
  recording the refusal and its reason in the sidecar. This removes most of R1's residual
  without costing recall on the claims that actually matter. The threshold is an
  **uncalibrated engineering default**, deliberately conservative, and is named as such.

### Should-have

- **S1 — `--force` / refuse-to-overwrite** parity with `extract-claims` (`cli.py:1476-1480`).
- **S2 — Per-claim sidecar provenance:** which artifact and coordinate matched, which scale
  (`raw` / `÷100`), and for a miss the candidate **count** and reason.
- **S3 — A file-count / size bound** on the sweep so a huge repo degrades honestly rather than
  hanging. Reuse `_MAX_MATCH_BYTES` (8 MiB, `reproduce.py:52`) per artifact.
- **S4 — `--dry-run`** printing what would be bound without writing.

### Nice-to-have (explicitly not this slice)

- `pattern` and notebook inference (**deferred, blocker named below**).
- Multi-key/predicate row match; `occurrence`/`group` selectors.
- A dashboard surface for inference.
- C6 eval fold-in of inference outcomes.

---

## Technical Considerations

### Why a separate command, not a flag on `extract-claims`

Three independent reasons, all verified:

1. `extract-claims` takes exactly one positional, `paper` (`cli.py:1398`). It has **no repo
   argument** — a paper and a repo are different inputs arriving at different times.
2. `tests/test_cli_extract_claims.py:104` asserts `set(entry.keys()) == {"id","value",
   "tolerance"}` — an **exact-set** assert whose stated purpose is to break when a key is
   added. Writing locator keys into the shipped draft is therefore a **disclosed contract
   change**; a separate command leaves that tripwire and the shipped contract untouched.
3. A separate command is re-runnable against a repo fetched later and works on hand-written
   drafts, not only extracted ones.

### The freshness guard cannot be weakened — structurally, not by discipline

The card worried that inference reads mtime-stale artifacts the freshness guard refuses to
bind. **The two cannot interact.** `_require_fresh` is a **closure nested inside
`run_reproduction`** (`reproduce.py:890`), closing over `run_started_at` (`:853`). It is not
a module-level function and is **not importable**; all five call sites are inside that one
function (`:948`, `:1011`, `:1080`, `:1180`, `:1333`).

So a pre-run, out-of-engine inference pass cannot touch it even by accident. The honest
framing, which the sidecar must state in these words: **inference proposes a binding site,
never evidence.** The value matched during inference never reaches a verdict; a locator
becomes a verdict only when a fresh run rebinds it under the wholly unchanged guard.
**Pinned by a test:** an inferred locator over a stale artifact still yields `UNVERIFIED` at
reproduce time.

### Why `pattern` / notebook are deferred (the blocker, named)

JSON and table invert by **coordinate enumeration** — the coordinate is read off the artifact.
`pattern` and notebook have no coordinate: a regex must be **authored**. That collides with
`resolve_match`'s strict exactly-one rule (`reproduce.py:368`, `!= 1` at `:408`) — a
synthesized regex that matches twice binds to nothing, and busy log files are exactly where
double matches live. This is a real technical blocker, not a preference.

### `load_claims` traps the emitted locator must not hit

`load_claims` (`reproduce.py:538`) enforces ten xor rejections (`:590-:787`):

- `header`/`delimiter` count as table fields **on their own** → a partial table locator trips
  `:703`/`:590`, and the round-trip then kills the **whole** file. **Emit complete locators or
  none** (independent of M4, and separately tested).
- `column` xor `row` rejected `:703`; `cell` requires both `from` and `pattern` `:609`/`:613`.
- Unknown keys are ignored unless one of the eight locator keys — but provenance stays in the
  **sidecar**, per the shipped schema-minimal design.

### No `models.py` change — by construction

All five types are frozen dataclasses local to `verification/reproduce.py`: `Locator` `:157`,
`TableLocator` `:170`, `PatternLocator` `:189`, `NotebookLocator` `:204`, `Claim` `:519`.
Not pydantic, not in `models.py`.

### Match rule

Rounding-aware equality: a candidate matches when it equals the claim value **rounded to the
claim's own printed precision** (paper `0.91` vs repo `0.9134` → compare at 2dp). Exact
equality misses nearly every rounded paper value; the claim's `tolerance` band is far too
loose and would explode ambiguity. This deliberately trades recall for more "ambiguous, emitted
nothing" outcomes — the safe direction. Float-repr recovery of printed precision is a known
implementation risk (R3).

### Dependency / reproducibility impact

Stdlib only (`json`, `csv`, `gzip`, `os`, `re`) — the `pydantic`/`typer`/`cryptography`
contract holds. **No** verdict, exit-code, `FailureClass`, signing, or bundle change. **No**
network. Local filesystem only, no raw-read egress. Purely upstream of the unchanged
`load_claims → run_reproduction → verdict → bundle` path. Two dispatch chains exist
(`reproduce.py:1343-1355`, `reproduce_guard.py:88-95`); we add no family, but emitted locators
must classify correctly in both — cheap test.

---

## Risks & Open Questions

- **R1 — A wrong locator producing a false REPRODUCED.** *The* risk. Mitigations: strict
  exactly-one (M4), complete-or-nothing (M3), scale ambiguity collapsing to nothing (M5), and
  G1 as a hard zero gate. Residual: a repo where the true value and a coincidental value are
  the *same number* in two places yields ambiguity → no locator (safe), but a repo where only
  the coincidental value exists yields a confident wrong bind. **Not fully eliminable by
  search alone** — the sidecar must present every inferred locator as *proposed, pending human
  review*, never as settled. **M9 removes the bulk of it** by refusing the low-information
  values where coincidence actually lives.
- **R2 — Recall may be low enough to be useless.** If real repos are ambiguous everywhere,
  inference proposes almost nothing. Measured, not assumed; the revisit trigger above fires.
  **Mitigated by sequencing:** the evidence gate after aspect 2 (below) measures this on a real
  repo *before* the CLI is built, so a dead end costs two pure modules, not the slice.
- **R6 — The stale-coordinate / fresh-path mismatch. Probably the largest real-world source of
  misses, and invisible to a fixture corpus.** Inference reads
  `results/2024-06-01/metrics.json` because that is what is on disk; the fresh run writes
  `results/2026-09-20/metrics.json`. The inferred locator then points at a file the run never
  rewrites, so the freshness guard correctly reports **UNVERIFIED** — for every claim, forever,
  on any repo that timestamps or versions its output directory. This is not a bug in the guard
  or in the matcher: it is an emergent property of inferring coordinates from *stale* artifacts
  and then binding under a *freshness* rule. A self-authored corpus cannot see it, because we
  would naturally write fixtures whose paths agree.
  **Decision: accept and disclose, do not guess.** Pre-run we cannot know what path the fresh
  run will write, and a "looks like a date/version directory" heuristic would be exactly the
  guessing this slice refuses everywhere else. So the sidecar states, per claim, the exact path
  whose rewriting the locator depends on. **Revisit trigger: the first real repo it blocks** —
  the same trigger, in the same words, the freshness guard itself shipped with
  (`CAPABILITY_ROADMAP.md:2397`). The real-repo manual gate is where this will most likely
  first appear, and that gate's record must report it explicitly.
- **R3 — Float precision recovery.** Deriving "the claim's printed precision" from a parsed
  float has repr edge cases (`0.1+0.2`). Settle in the aspect spec; may need the draft's raw
  token rather than the float.
- **R4 — Id instability across regeneration.** `merge_claims` re-uniquifies ids
  (`claim_extraction.py:445-457`), so draft ids are not stable across toggling the LLM assist.
  Fine against a fixed draft file; the sidecar must not imply ids are durable.
- **R5 — Sweep cost on a large repo.** Bounded by S3; unmeasured on a real repo.
- **Open:** exact sidecar wording; whether `--dry-run` (S4) ships in v1; whether the fixture
  repo tree lives at `tests/fixtures/<repo>/` (the repo's first) or stays inline.

---

## Out of Scope (explicit)

- **`pattern` and notebook inference** — blocker named above.
- **Any modification to `contig extract-claims`** or its draft contract.
- **Any change to** the verdict, locator, bundle, signing, or exit-code contracts; the
  freshness guard; `models.py`; or either dispatch chain.
- **Figure/plot and table-image claims** — hard-blocked (no plot-hash, stdlib-only).
- **Auto-verification of inferred claims** — inference only ever produces a **proposal a human
  reviews**, exactly as extraction only ever produces a draft.
- **Network, DOI resolution, repo fetching** — the repo argument is a local path.
- **C6 eval fold-in** of inference outcomes.

---

## Proposed aspect decomposition (for `tech-plan`)

1. **`candidate-sweep`** — the pure, never-raises repo walk + artifact enumeration
   (safe-walk discipline, size bounds, gzip-transparent), yielding
   `(artifact, coordinate, numeric_value)` candidates. Fully CI-testable, no CLI.
2. **`match-and-propose`** — the pure matcher: rounding-aware equality, dual-scale attempt,
   the exactly-one rule, and locator construction (complete-or-nothing). No I/O.
   **⛔ EVIDENCE GATE — after aspect 2, before aspect 3.** Aspects 1 and 2 are pure and need
   no CLI, so they can be pointed at one **real published repo** plus a real `extract-claims`
   draft and asked a single question: *how many claims bind, how many are ambiguous, how many
   are refused, and is any bind wrong?* Report the numbers honestly, including any R6
   fresh-path mismatch observed. Only then decide whether aspect 3 ships as designed, ships
   narrowed, or does not ship. **This exists so that a dead end costs two pure modules rather
   than the whole slice** — R2 is otherwise a risk we would only measure after building
   everything.

3. **`cli-command`** — `contig infer-locators`: argument/flag surface (Click-param
   introspection, never `--help` scraping), the `load_claims` round-trip invariant, atomic
   `os.replace`, exit codes, sidecar rendering, `--force`/`--dry-run`.
   *Gated on the evidence gate above.*
