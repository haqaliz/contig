# PRD — reproduce-checkout-hash (C8 slice 8)

**Status:** drafted, pending review-gate approval · **Owner:** aliz · **Branch:**
`feat/reproduce-checkout-hash/aliz` · **Source:** `/contig-next` handoff (no GitHub
issue) · **Capability:** C8 (Reproduce & verify existing published work)

## Problem Statement

`contig reproduce` fetches a third-party repository (`--allow-fetch`, and with slice
7 a pinned `--rev`), records the resolved commit as `source_commit`, and copies the
checkout into the bundle at `source/`. But the `source/` tree itself is **unhashed
and unsigned**. Slice 6 disclosed this in its own words:

> "The checkout is evidence, not attestation … the `source/` tree is unsigned and
> unhashed and can be modified afterwards with nothing detecting it, so the commit
> SHA is the attested fact and `source/` is a convenience copy for inspection …
> hashing the tree is deliberately a separate slice."
> — `docs/technical/CAPABILITY_ROADMAP.md:1373-1376`

**Who has the problem.** A third party checking a Contig reproduce bundle — the
exact audience slices 6/7 were built for ("makes a reproduction claim checkable by a
third party at all", `CAPABILITY_ROADMAP.md:1346`). Today they can trust the recorded
commit but have **no attested fingerprint of the bytes that produced the verdict**.

**Cost of the status quo.** The reproduce bundle's whole value proposition is a
"signed, re-runnable, third-party-checkable verdict." An unattested checkout is a
hole in that proposition: the bundle can assert a clean `source_commit` while the
`source/` tree shipped alongside it was altered after the run, with nothing
detecting the divergence. This is the strongest remaining integrity gap in the
actively-shipping C8 track.

**Evidence it's real.** It is a self-disclosed gap in the codebase
(`CAPABILITY_ROADMAP.md:1373-1376`, `:1394`), not a hypothesized one.

**What the hash adds over `source_commit` (be precise — a git commit already binds
its tree).** For a remote run pinned by a **full SHA**, `source_commit` already
cryptographically commits to the tree, so re-cloning and checking `git rev-parse
HEAD` largely proves the same thing. The tree hash's marginal, non-redundant value
is in the cases the commit does **not** cover: (a) a `--rev` **tag or branch**, which
slice 7 explicitly left **"not attested"** (`CAPABILITY_ROADMAP.md:1421-1422`) — the
tree hash attests the actual content regardless of a mutable ref; (b) **git-free
verification** — an auditor can recompute the digest from files alone, without git or
the network; and (c) it is the **groundwork** for the deferred local-path and
shipped-`source/` integrity checks, where there is no commit at all. This is the
honest framing the PRD commits to, rather than overclaiming novelty for the
full-SHA case.

## Goals & Success Metrics

**Goal.** Record a deterministic, attested content hash of the fetched checkout tree
on the reproduce bundle, so the bytes that produced the verdict are tamper-evident
and independently recomputable.

**Success (all test-backed, per the repo's test-first discipline):**

1. A remote (`--allow-fetch`) reproduce run records `source_tree_sha256` on the
   signed `ReproduceRecord`; a local-path run records `None`.
2. The hash is **deterministic** — the same checkout tree yields the same digest
   across runs and platforms (sorted POSIX-relative paths; `.git/` excluded).
3. Modifying any file in the checkout tree changes the digest (CI-observable:
   fixture tree → hash → mutate → assert different digest). This is the tamper
   signal.
4. The hash is **signed**: it rides `canonical_record_bytes`, so a bundle editor
   cannot change the recorded hash without invalidating the signature (tamper-evident
   *record*). Note the honest scope in R3: this attests the commit↔tree linkage,
   verifiable by re-clone — it does **not** make the bundle's post-run `source/` copy
   self-checkable (that copy has run outputs added).
5. **Recompute algorithm is documented, so "independently recomputable" is real, not
   aspirational.** The exact walk + fold (sorted POSIX-relative paths, `.git/`
   excluded, `sha256_file` per file, folded as `"<relpath>\0<hex>\n"` lines →
   `sha256`) is written into the CHANGELOG entry and the helper docstring so a third
   party can reproduce the digest byte-for-byte without reading Contig's source. No
   `contig`-side recompute/verify verb ships this slice (deferred).
6. Back-compat: a pre-slice-8 reproduce record JSON (no `source_tree_sha256` key)
   still **loads** (field defaults to `None`), pinned by a test.
7. The disclosed cost is pinned honestly: a pre-slice-8 **signed** bundle no longer
   **verifies**, asserted by an explicit test (mirrors the slice-6 disclosure).

**Non-metric (out):** no claim about run-to-run *scientific* reproducibility; this
attests bytes, not recomputation (see Risks).

## User Personas & Scenarios

- **Reproduction auditor / skeptic** (Biostars / r/bioinformatics / nf-core
  reviewer, CODECHECK-style checker). Receives a Contig reproduce bundle claiming
  "N of the paper's numbers reproduced." Wants to confirm the `source/` tree in the
  bundle is the exact tree that produced the verdict and matches `source_commit`.
  With slice 8 they recompute `source_tree_sha256` over the shipped/​re-cloned tree
  and confirm it matches the signed record.
- **The reproduce operator** (lone computational biologist running `contig
  reproduce <url> --allow-fetch --rev …`). Gets a bundle whose checkout is now
  attested with no new flag and no workflow change.

## Requirements

### Must-have

- **M1 — `compute_tree_sha256(root)` helper** in `bundle.py`, next to
  `compute_output_checksums` (`bundle.py:303-318`). Deterministic digest over the
  tree: `rglob` → `is_file()` filter → **exclude any path under `.git/`** → sort by
  POSIX-relative path → per-file `sha256_file` (`models.py:17-23`) → fold the sorted
  `"<relpath>\0<hexdigest>\n"` lines into one top-level `sha256`. Pure, stdlib-only.
- **M2 — Honest degradation.** An unreadable file or an un-walkable tree yields
  `None` (whole-hash), never a fabricated or partial digest — mirroring
  `compute_reference_identity`'s `None`-on-error posture (`bundle.py:142-175`). A
  missing root → `None`.
- **M3 — Signed record field.** Add `source_tree_sha256: str | None = None`
  (additive, back-compat default) to `ReproduceRecord` (`models.py:680`). It rides
  the existing `canonical_record_bytes` signature (`signing.py:55-64`) — no signing
  code change.
- **M4 — CLI wiring, remote-only, pre-run.** In the `reproduce` command
  (`cli.py`), compute the tree hash **after `fetch_repo` succeeds and before the
  `run_started_at = time.time()` stamp** (`cli.py:952`↔`:962`), over `repo_path`
  (the `source/` checkout), and only on the `repo_argument.kind == "remote"` branch.
  Attach it via the existing remote `model_copy(update=…)` (`cli.py:977-987`)
  alongside `source_url`/`source_commit`. Local-path runs leave it `None`.
- **M5 — Manifest echo.** Emit `source_tree_sha256` in the unsigned `reproduce.json`
  manifest too (`bundle.py:100-110`), derived from the record (like `source_url`/
  `source_commit`), so a reader inspecting the plain manifest sees it without
  loading the signed record.
- **M6 — Tests (test-first).** RED before GREEN throughout:
  - helper determinism + `.git/` exclusion + mutation-changes-digest +
    unreadable→`None` (pure, CI-observable, no git);
  - remote run records the hash / local run records `None`;
  - the hash is computed pre-stamp (a retry that mutates the tree does **not** change
    the recorded hash — modeled on `test_reproduce_env_resurrection.py:235-254`);
  - back-compat load of a record without the key;
  - the disclosed signature-break test (pre-slice-8 signed bundle no longer
    verifies), mirroring `test_reproduce_rev_pin.py:517`'s shape but asserting the
    opposite outcome for a signed-record field.

### Should-have

- **S1 — Symlink safety.** A symlink inside the tree is never traversed out of the
  checkout (defense-in-depth, cf. locator containment guards). Lean: skip symlinks /
  do not follow, recorded honestly; settle the exact rule in the plan.
- **S2 — `contig methods` / provenance surface.** Render the checkout hash in the
  human provenance surface next to `source_commit` if it fits cleanly. Nice-to-have
  if it expands scope.

### Nice-to-have (explicitly deferred, not in this slice)

- Local-path checkout hashing (needs an exclusion story for `.venv/`/data/outputs).
- Hashing the bundle's `source/` copy **as shipped** (post-run) for a shipped-tree
  integrity check distinct from provenance attestation.
- Dashboard card surfacing.
- A per-file manifest (like `compute_output_checksums`) rather than a single digest.

## Technical Considerations

- **Pipeline position.** Reproduce/verify layer (C8), Layer-2 moat work. No
  orchestration or Layer-1 surface touched.
- **Reproducibility/verification impact (the point).** Deepens the reproduce
  guarantee: the bundle now attests *which bytes* produced the verdict, not only
  *which commit* was nominally fetched. New corpus signal available downstream (a
  recorded tree hash that disagrees with a re-clone of `source_commit` = a
  dirty/tampered checkout).
- **Determinism.** Reuse the `compute_output_checksums` walk shape (sorted `rglob` +
  POSIX-relative keys). Fold into one digest for a compact signed field.
- **Signing (accepted cost).** `canonical_record_bytes` signs every model field with
  no exclusion, so the new field breaks pre-slice-8 **signed** reproduce bundles
  (they still load). This is the **third** consecutive signature break (slice 6 added
  `source_url`/`source_commit`; the somatic FAIL-floor changed `verdict`). Chosen
  deliberately: an unsigned "tamper-evidence" hash is close to self-defeating, and
  slice 6 set the precedent that attestation-worthy provenance goes on the signed
  record. Bounded: signing is opt-in via `CONTIG_SIGNING_KEY`. Disclosed in the
  CHANGELOG and pinned by a test.
- **No new dependency.** stdlib `hashlib` only — preserves the reproduce path's
  stdlib-only contract (the same contract that keeps figure/plot claims out of
  scope, `CAPABILITY_ROADMAP.md:1434-1438`).
- **CI-observability (a differentiator).** Unlike every prior C8 slice ("no real
  git/network/repo in CI — reasoned, not observed"), the core of slice 8 is fully
  testable in CI: build a real fixture tree on disk, hash it, mutate it, assert the
  digest changes. Only the CLI-remote wiring rides the injected `Fetcher` seam.

## Data Model / Artifact Contract

- `ReproduceRecord.source_tree_sha256: str | None = None` (signed).
- `reproduce.json` gains a `source_tree_sha256` key (unsigned echo), `null` for
  local runs — matching how `source_url`/`source_commit`/`requested_rev` are emitted
  unconditionally.
- Value: lowercase hex `sha256` string, or `None`.

## Risks & Open Questions

- **R1 — Honest-limit: "rewritten, not recomputed" (carried, not solved).** A tree
  hash attests the *bytes present at hash time*, not that they were scientifically
  recomputed. Same boundary the freshness guard drew. Stated plainly in the
  CHANGELOG; not a defect.
- **R2 — Third signature break.** Accepted and disclosed (see Technical
  Considerations). Revisit trigger: if a fourth break looms, reconsider an
  `exclude_none` canonicalization holistically (currently rejected — it would break
  `RunRecord` too).
- **R3 — Pre-run vs shipped-tree semantics.** We hash the checkout **pre-run**, so
  the recorded hash attests "the tree as checked out" and verifies against a
  re-clone of `source_commit`. It intentionally does **not** attest the bundle's
  `source/` copy *after* the run wrote outputs into it — hashing the shipped
  post-run tree is a distinct, deferred feature (nice-to-have). Documented so a
  reader doesn't expect the shipped `source/` to match the recorded digest.
- **R4 — Symlinks / unreadable files.** Handled by S1 + M2; exact rule settled in
  the plan. Must never traverse out of the checkout or fabricate a digest.
- **R4a — Determinism corner cases (settle in the plan).** `rglob` order is not
  guaranteed → we sort POSIX-relative paths (fixed). `.git/` exclusion must match
  `.git` as **any path component**, not only the top level. Empty directories
  contribute no files, so two trees differing only by an empty dir hash identically —
  accepted and documented. Filename **unicode normalization** and **case
  sensitivity** are inherited from the filesystem (a cross-platform re-clone on a
  case-insensitive FS could differ) — documented as an honest limit, not solved this
  slice. The fold delimiter is `\0` (NUL, illegal in POSIX paths) so no path/hex
  string can forge a boundary.
- **R5 — Large trees.** A shallow clone is bounded, but hashing is O(bytes). No
  streaming concern (`sha256_file` is chunked). No perf target for this slice; note
  if a real repo is pathological.

## Out of Scope

- Local-path checkout hashing (deferred).
- Post-run / shipped-`source/` tree integrity hashing (deferred, distinct feature).
- Signing or hashing anything beyond the checkout tree (e.g. per-file manifest).
- Dashboard card, `contig methods` surfacing beyond the optional S2.
- Any change to `RunRecord` signing, DOI resolution, figure/plot claims,
  paper-parsing, checkout pruning, private-repo creds, submodules — all unchanged
  C8 deferrals.
- Layer-1 (NL→workflow) — not touched.

## Guardrails check (CLAUDE.md)

Layer-2 reproducibility integrity ✓ · no NL→workflow authoring ✓ · no
wet-lab/clinical credentials or proprietary data ✓ · stdlib-only, no new dependency
✓ · honesty posture preserved (unreadable/absent tree → `None`, never a fabricated
hash) ✓ · gets better with better base models is N/A (pure integrity plumbing) but
is not made redundant by them either ✓.
