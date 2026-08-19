# PRD — reproduce-local-tree-hash (C8 slice 9)

**Status:** drafted, pending review-gate approval · **Owner:** aliz · **Branch:**
`feat/reproduce-local-tree-hash/aliz` · **Source:** `/contig-next` handoff, no GitHub
issue (`gh issue list` → "No Issues") · **Capability:** C8 (Reproduce & verify existing
published work) · **Baseline:** 2377 passed, 1 skipped, green.

## Problem Statement

`contig reproduce <local-path> --run --claims …` produces a **signed** `ReproduceRecord`
that attests the per-claim verdict while binding **nothing about the code that produced
it**. For a local run the record's `source_url`, `source_commit` **and**
`source_tree_sha256` are all `None` — nothing in the local branch ever sets them
(`cli.py:1048-1061`, `cli.py:1086-1097`; both populate sites are gated on
`repo_argument.kind == "remote"`).

**Who has the problem.** The local-path mode is `contig reproduce`'s *original* mode — the
only one that existed until slice 6 added `--allow-fetch` — and remains the default for
anyone reproducing a repo they already have on disk. It is the mode Contig's own ICP (a
lone computational biologist checking a colleague's or their own prior analysis) reaches
for first.

**Cost of the status quo.** A local reproduce bundle records *that* a verdict was reached
but not *over what*. Re-running the same repo a month later, after the code changed,
produces a second bundle indistinguishable from the first in its inputs. Nothing detects
the drift. And because `source_tree_sha256: null` currently means **both** "this was a
local run" and "the digest could not be computed," the field cannot be read as evidence at
all for local bundles.

**Evidence it's real.** This is a self-disclosed gap, named by slice 8 in three places:
`docs/planning/reproduce-checkout-hash/prd.md:217` ("Local-path checkout hashing
(deferred)"), `CHANGELOG.md:715-716`, and `CAPABILITY_ROADMAP.md:1495`.

## What this slice does and does NOT claim — resolved deliberately

Slice 8's own artifacts contradict each other on whether local hashing is worth doing, and
this PRD resolves it explicitly rather than inheriting either framing:

- **Against** — `docs/planning/reproduce-checkout-hash/understanding.md:89-99`: a local
  path is "dirty-by-design, unbounded, and often full of unrelated files … noisy and
  expensive to hash, **lower attestation value (no commit anyway)**."
- **For** — `docs/planning/reproduce-checkout-hash/prd.md:43`, `CHANGELOG.md:715-716`: the
  tree hash is "groundwork for the deferred local-path … integrity checks, **where there
  is no commit at all**."

**Resolution: build it, on the narrow framing, and disclaim the broad one.**

**What it does NOT buy — stated first, so it cannot be over-read.** No `source/` copy is
made for a local run (`cli.py:966-975` constructs that path in the remote `else` branch
only). A third party handed a local bundle therefore has neither the tree nor a commit to
fetch, and **cannot recompute the digest**. The third-party-verifiability argument that
justified slices 6–8 **does not transfer to local runs**, and this slice must not be
described as if it does.

**What it does buy, precisely:**

1. **Drift evidence over time.** Two local runs of the same repo whose recorded digests
   differ prove the inputs changed. Today nothing detects this.
2. **Tamper-evidence.** The digest rides the already-signed `ReproduceRecord`, so altering
   the recorded claim about the inputs invalidates the signature.
3. **Disambiguation.** After this slice, `source_tree_sha256: null` on a local record
   means only "could not be computed" — a real signal — instead of the useless
   "local run, or failure, indistinguishable."

## Goals & Success Metrics

Every metric is test-backed, per the repo's test-first discipline.

- **G1 — A local run records a real digest.** `contig reproduce <local-dir> --run --claims
  …` records a 64-char lowercase-hex `source_tree_sha256` on the signed record and echoes
  it in the unsigned `reproduce.json` manifest. *Metric:* a CLI-level test asserts the
  recorded value equals `compute_tree_sha256` over an independently-materialized copy of
  the same tree.
- **G2 — The digest is taken pre-run.** A local run's executor cwd **is** the user's repo
  (`reproduce.py:1214`), so anything the run writes — including an `--allow-install` retry
  — must not change the recorded value. *Metric:* mirroring
  `test_source_tree_sha256_is_taken_pre_run_not_post_retry` (`:523-556`), a scripted
  executor writes a new file into the repo during the run; the recorded digest must equal
  the pre-run tree and differ from the post-run tree.
- **G3 — Contig's own output never contaminates the digest.** When the resolved
  `--runs-dir` falls inside the repo path, it is excluded from the walk. *Metric:* a
  local run whose `--runs-dir` is inside the repo records the **same** digest as an
  otherwise-identical run whose `--runs-dir` is outside it.

  **Metric correction (found in self-critique).** The obvious formulation — "two
  successive runs record the same digest" — is **unsatisfiable and would be a false
  test**: run 1's executor writes `results.json` into the repo (the executor's cwd *is*
  the repo, `reproduce.py:1214`), so run 2's pre-run tree legitimately differs by that
  file regardless of any runs-dir exclusion. The test must isolate the runs-dir
  contribution specifically, not compare two sequential runs.
- **G4 — No fourth signature break.** *Metric:* a test proves a record signed while
  `source_tree_sha256` was `None` still verifies, and that the canonical **key set** is
  unchanged by this slice.
- **G5 — No regression.** Full suite green from the 2377-passed/1-skipped baseline; no new
  dependency; no CLI signature change.

## User Personas & Scenarios

- **A — lone computational biologist (primary).** Reproduces a colleague's repo sitting on
  their laptop. Months later re-runs it and wants to know whether the divergence is
  because the *code* changed or because the *result* changed. Today the bundle cannot tell
  them; after this slice the recorded digest can.
- **C — core facility.** Archives reproduce bundles as an audit trail. A bundle whose
  input fingerprint is `null` is a weaker archival record than one that pins the bytes.

## Requirements

### Must-have (this slice)

- **R1 — Populate on the local branch.** Compute `compute_tree_sha256(repo_path,
  exclude=…)` (see R3 for the parameter) for `repo_argument.kind == "local"` and carry it
  onto the returned `ReproduceRecord`. The remote branch's **recorded digest** is
  **byte-identical** to today (R3's parameter is a provable no-op on that branch).
- **R2 — Pre-run placement.** The hash is taken **before** `run_started_at = time.time()`
  (`cli.py:1071`) and therefore before the executor runs. It must **not** move, re-order,
  or re-stamp the freshness guard — that ordering is load-bearing for the
  false-`REPRODUCED` protection and is verified by mutation in slice 6/7/8's tests.
- **R3 — Exclude Contig's own runs directory when it is inside the repo, via one
  universal rule on both branches (see R-7).** `--runs-dir` defaults to the relative
  string `"runs"` resolved against **CWD** (`cli.py:834`), so `cd my-repo && contig
  reproduce . …` writes the bundle to `<repo>/runs/<id>`. `compute_tree_sha256` gains an
  optional `exclude: Path | None` parameter; the CLI resolves `--runs-dir` and passes it
  on **both** the local and remote call sites whenever it is a descendant of the tree
  being hashed. Remote's runs dir is structurally never a descendant of `repo_path` (it is
  `repo_path`'s parent), so the parameter is a **provable no-op there** — pinned by a test
  asserting remote's digest is unchanged with the parameter passed vs. omitted. **No
  general ignore list** beyond this one named exclusion — `.venv`, `node_modules`,
  `__pycache__` are hashed like any other content, because a name-based denylist could
  hide a genuine dependency change from the digest.
- **R4 — Honest degradation, unchanged.** Reuse `compute_tree_sha256`'s existing
  all-or-`None` contract: a missing/non-directory root or any `OSError` yields `None` for
  the whole digest — **never a partial or fabricated one** (`bundle.py:345-349`, and the
  deliberate `_raise` onerror at `:326-331`). A `None` digest must **never** fail the run
  or change the exit code.
- **R5 — Manifest echo.** `reproduce.json` continues to emit `source_tree_sha256`
  unconditionally; for a local run it now carries the digest instead of `null`.
- **R6 — Retire the pinning test deliberately.**
  `test_local_reproduce_records_no_source_tree_sha256` (`tests/test_reproduce_checkout_hash.py:499-520`)
  and the module docstring's "Local runs never compute it." (`:17-20`) assert exactly the
  behavior this slice inverts. They are **replaced by tests pinning the new contract**, in
  the same commit — following the v0.50.0 precedent for retiring a guard deliberately
  rather than deleting it to go green.
- **R7 — Tests-first, real fixture trees.** No mocks of the hash itself; real directories
  under `tmp_path`, matching slice 8's fully-CI-observable posture. The command executor
  stays the existing injected seam.

### Should-have

- The CHANGELOG entry states the "not third-party recomputable" limit in its own words,
  not only the capability.

### Explicitly NOT in this slice

- **Local `source_commit` / dirty-state capture.** For a local dir that *is* a git
  checkout, `git rev-parse HEAD` plus a dirty flag would be **more** third-party-meaningful
  than a tree hash, and is arguably the better answer to the value objection above. It
  needs git shelled at an arbitrary user directory and a non-git fallback design. **Named
  as the honest follow-on**, deferred, not silently omitted.
- Bounding the walk (see R-2).
- Hashing the bundle's post-run `source/` copy (slice 8's deferral, still deferred).

## Technical Considerations

- **Chokepoint.** `cli.py`'s `reproduce` body, immediately before `:1071`. The remote path
  hashes at `:1061` right after `fetch_repo`; local has no fetch, so the pre-stamp point is
  the equivalent moment. Local `repo_path` is `Path(repo)` — the user's directory as given
  (`cli.py:962`), not a copy.
- **Carrying the value onto the record.** The remote branch uses
  `record.model_copy(update={…})` at `:1086-1097`. The local branch needs the same
  mechanism for `source_tree_sha256` **only** — `repo`, `source_url` and `source_commit`
  stay as they are for local (`repo` is already the local path string; the other two stay
  `None`).
- **Signing — settled, no break.** `canonical_record_bytes` (`signing.py:55-64`) dumps
  every declared field and `json.dumps(sort_keys=True)`; `source_tree_sha256` is therefore
  **already** an always-present key rendering as `null`. Populating it changes a **value**,
  not the key set, so a previously-signed bundle re-derives its own canonical bytes from
  its own stored `null` and still verifies. This is **not** a fourth signature break, and
  G4 pins that.
- **Reproducibility impact.** Deepens the reproduce guarantee on its most-used mode; no
  change to verdict logic, classification, tolerance, locators or the freshness guard.
- **Dependency contract.** `hashlib`/`os`/`pathlib` only. Declared deps stay
  `pydantic`/`typer`/`cryptography` — no new dependency, consistent with the stated
  stdlib-only contract (`CHANGELOG.md:1463`).
- **No raw-read egress**; the walk is local and nothing leaves the machine.

## Data Model / Artifact Contract

No model change. `ReproduceRecord.source_tree_sha256: str | None = None` already exists
(`models.py:706`). Only its **population rule** widens: remote-only → remote **and** local.
`reproduce.json`'s unsigned echo is unchanged in shape.

## Risks & Open Questions

- **R-1 — The value is narrower than slices 6–8's (accepted, disclosed).** Not
  third-party-recomputable; the honest claim is drift evidence + tamper-evidence +
  disambiguation. Mitigation: say so plainly in the CHANGELOG, and do not reuse the
  "attestation" vocabulary from slice 8 for the local case. **Revisit trigger:** if the
  local-commit follow-on ships, revisit whether the tree hash is still carrying weight for
  local or has become redundant.
- **R-2 — Unbounded walk cost (accepted, documented).** Unlike a `--depth 1` clone, a local
  tree is unbounded; a large repo means a pre-run pause that could read as a hang. Decided:
  **no bound this slice**, matching `compute_tree_sha256`'s existing contract
  (`sha256_file` streams in 1 MiB chunks, so it is I/O-bound, not memory-bound). If a bound
  is ever added, the precedent (`_MAX_MATCH_BYTES`, `reproduce.py:46-50`) requires that
  exceeding it yields `None` with a stated reason — **never a silently truncated digest**.
- **R-3 — "Rewritten, not recomputed" (carried, not solved).** A tree hash attests bytes
  present at hash time, not that they were scientifically produced. Same boundary the
  freshness guard drew; carried from slice 8's R1.
- **R-4 — The recorded digest will not match the tree after the run.** A local run's
  executor writes into the hashed directory itself, so the on-disk tree post-run differs
  from the recorded digest by design (the record describes the **inputs**). Slice 8 has the
  same property for remote (its R3) but it is far more visible here, on the user's own
  working copy. Must be documented so nobody reads it as a bug.
- **R-5 — Symlink-heavy local trees.** `compute_tree_sha256` skips symlinked files and
  prunes symlinked dirs. A real working copy is far likelier than a fresh clone to contain
  symlinks (venvs, caches), so more content is silently outside the digest for local than
  for remote. Behavior is unchanged and correct; the limit is worth stating.
- **R-6 — Push, not demand-pull.** No design partner asked for this; the organic frequency
  of local reproduce runs is **unmeasured and not claimed**. Consistent with the honest
  posture of the last several slices. **Committed revisit trigger, both directions:** every
  success metric here is a unit test — nothing measures whether a recorded local digest is
  ever *consulted*. If the next 20 recorded reproduce runs contain no local run whose
  digest differs from a prior run's over the same repo, the drift-evidence claim (value
  #1) is restated as unexercised and no further local-provenance breadth is built on push
  alone. If instead a digest difference does surface a real code drift, that is the
  evidence to justify the deferred local-commit follow-on.

- **R-7 — R3's exclusion forks the published algorithm — RESOLVED.**
  `compute_tree_sha256`'s algorithm is deliberately **published so a third party can
  recompute it byte-for-byte** (`bundle.py:335-349`). A local-only exclusion would give
  `source_tree_sha256` two silent definitions depending on which branch produced it.
  **Resolved: one universal rule on both paths.** `compute_tree_sha256` gains an optional
  `exclude: Path | None` parameter (an absolute directory to prune, alongside the existing
  `.git`/symlink pruning); the CLI passes the resolved `--runs-dir` **on both the local and
  remote branches** whenever it resolves to a descendant of `repo_path`. For remote, the
  runs dir is never a descendant of the (prospective, then freshly-cloned) `repo_path` —
  it is `repo_path`'s own **parent** (`<runs_dir>/<id>/source`, `cli.py:966-975`) — so the
  exclusion provably never fires there; a test pins that remote's digest is byte-identical
  with and without the parameter passed. The field keeps a single published definition:
  "the walk, minus `.git`, symlinks, and Contig's own runs directory when nested inside
  the hashed tree" — true on both branches, not a local-only carve-out.
- **Open:** none blocking — Q1 (ship, narrow framing), Q2 (exclude the runs dir, no general
  ignore list) and Q3 (unbounded) were settled in the interview.

## Out of Scope

- Local `source_commit` / dirty-state capture (named follow-on, deferred).
- Bounding or progress-reporting the walk.
- Post-run / shipped-`source/` tree hashing (slice 8 deferral, unchanged).
- A general path ignore-list or `.gitignore` parsing.
- Any change to `RunRecord` signing, remote-path behavior, DOI resolution, figure/plot
  claims, PDF paper-parsing, private-repo credentials, submodules, checkout pruning, the
  dashboard card, or the C6 fold-in — all unchanged C8 deferrals.
- Layer-1 (NL→workflow) — not touched.

## Guardrails check (CLAUDE.md)

Layer-2 reproducibility integrity ✓ · no NL→workflow authoring ✓ · no wet-lab/clinical
credentials or proprietary data ✓ · stdlib-only, no new dependency ✓ · honesty posture
preserved — degrade to `None`, never partial or fabricated, and the value claim is
deliberately narrowed rather than inherited ✓.
