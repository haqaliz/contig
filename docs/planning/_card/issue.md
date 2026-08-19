# Card: feat / reproduce-local-tree-hash

- **Type:** feat
- **Id/slug:** `reproduce-local-tree-hash`
- **Owner:** aliz
- **Branch:** `feat/reproduce-local-tree-hash/aliz`
- **Source:** inline brief (no GitHub issue — `gh issue list` returns "No Issues", consistent
  with the three prior cards) — carried from the `/contig-next` recommendation (2026-08-06),
  the next slice after `inert-repair-honesty` merged and shipped as v0.50.0.

## Brief

C8 slice 9: populate `ReproduceRecord.source_tree_sha256` for a **local**
`contig reproduce <path>` run, closing the gap slice 8 deferred in its own words.

Today `cli.py:1059-1061` hashes the checkout only under
`if repo_argument.kind == "remote"`, so a signed **local** bundle records
`source_url` / `source_commit` / `source_tree_sha256` all `null` and binds **nothing**
about the code that produced the verdict — on what was the only reproduce mode until
slice 6, and still the default.

Reuse the shipped pure `bundle.compute_tree_sha256` as-is; hash **pre-run**, before the
`run_started_at` stamp at `cli.py:1070`, so the run's own writes and any `--allow-install`
retry cannot change it.

Because the field has been in `canonical_record_bytes` since slice 8, this changes a
**value** and not the canonical schema — confirm with a test that pre-existing signed
bundles still verify, i.e. **no fourth signature break**.

**Known caveat to settle in the dig:** unlike a `--depth 1` clone, a local repo tree is
unbounded — decide explicitly whether to hash unconditionally, bound the walk and return
an honest `None` past a limit, or scope it; and state plainly in the write-up that a dirty
local tree's hash is evidence about *those bytes*, not a third-party-replayable pin.

Treat post-run hashing of the bundle's `source/` copy as a separate deferred item, **not**
this slice.

## Provenance of the pick (from `/contig-next`, 2026-08-06)

**Why it ranked first:**

- Closes a stated gap in the signed attestation, on the mode that is actually used
  (`cli.py:1059-1061`; local runs were the only mode until slice 6).
- Deferred as *scope*, not blocked — `CAPABILITY_ROADMAP.md:1495` and the slice-8
  write-up both name "local-path and shipped-`source/` tree hashing" as the intended
  follow-on, and slice 8 calls the local case "groundwork" it deliberately left.
- The pure function already exists and is tested (`bundle.py:334 compute_tree_sha256`) —
  this is placement + honesty rules, not new machinery.
- No fourth signature break: `source_tree_sha256` has been in `canonical_record_bytes`
  since slice 8 (`bundle.py:112`).
- Moat-aligned per `CLAUDE.md`: reproducibility/verification hardening, fully
  CI-observable with real fixture trees, stdlib-only, no new dependency.

**Alternates considered and not picked:**

- **PDF intake for `contig extract-claims`** (`CAPABILITY_ROADMAP.md:1907`, "Deferred:
  PDF/DOI/paper-fetching"). Higher user-facing value, but two unresolved feasibility
  questions: a dependency decision against the stdlib-only contract, and two-column PDF
  extraction quality degrading the deterministic vocabulary matcher.
- **`read_task_errors` work-dir blindness** (filed as C2 deferral **(a)**,
  `CAPABILITY_ROADMAP.md:451`; verified `runner.py:1077` hardcodes `run_dir/"work"` while
  `nfconfig.py:100` writes `workDir = target.work_dir`). Real bug, but small reachable
  population — the default work dir already resolves to `run_dir/work` (`cli.py:521`) and
  the flag's documented purpose is the `s3://` AWS Batch case the fix cannot help.

**Excluded for named blockers:** C6/C7 eval fold-in (labeling design); assembly-signature
mismatch (no sample-side contig signal); bwa-mem2/classic-BWA build+redirect (no live
trigger); stall-window calibration (never observed on a real run); C2 deferral **(b)**
`risk="destructive"` (verified unreachable — all 14 `risk=` sites in `repair.py` are
`safe`/`needs_confirmation`, so it is the inert shape v0.50.0 just cleaned up).
