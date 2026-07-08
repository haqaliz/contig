# Task 6 report — docs: record the recompress-reference slice (bgzip reference) [C2]

**Aspect:** `recompress-reference` (self-heal-bgzip-reference) · **Phase:** 6 (docs-only
half of the plan; the breadcrumb half of Phase 6 was NOT done here — see Scope)
**Branch:** `feat/self-heal-bgzip-reference/aliz`
**Scope:** `CHANGELOG.md` + `docs/technical/CAPABILITY_ROADMAP.md` only. No code, no
tests, no breadcrumb — per explicit task instructions this is a documentation-only slice.

## What was verified before writing anything

Read, in order, to ground every claim made in the docs:

- `CHANGELOG.md` v0.19.0–v0.22.0 for house voice (named what shipped, named what's
  deferred and why, "no real run in CI" honesty convention, bold lead sentence naming the
  capability + slice).
- `docs/technical/CAPABILITY_ROADMAP.md` C2 section and the "Sequencing summary" table, to
  match the existing "Shipped (... slice — Unreleased):" paragraph pattern and see exactly
  where the input-format-conversion / CRAM-BAM / "format conversion" placeholders already
  lived in the deferred lists (they needed updating now that the first slice shipped).
- `docs/planning/self-heal-bgzip-reference/prd.md` (authoritative problem statement,
  goals, requirements, risks, out-of-scope) and
  `docs/planning/self-heal-bgzip-reference/recompress-reference/plan_20260708.md`
  (authoritative design decisions: fix target, outcome-label taxonomy, patch risk level,
  decompression mechanism).
- The actual shipped code, to confirm the plan was followed exactly and nothing drifted:
  - `src/contig/self_heal.py:699-812` — `_gzip_kind` (BGZF `BC`-subfield walk) and
    `_recompress_reference` (stream-decompress via stdlib `gzip.open` +
    `shutil.copyfileobj`, `built_paths` one-per-run guard, honest give-up outcomes
    `reference_recompress_unresolvable` / `reference_recompress_failed`, success outcome
    `recompressed_reference_and_retried`).
  - `src/contig/self_heal.py:857-858` — dispatch branch in `_apply_patch_and_maybe_build`.
  - `src/contig/detect.py:330`, `src/contig/models.py:213`, `src/contig/repair.py:66` —
    `reference_not_bgzf` FailureClass, detector branch, repair patch
    (`kind="reference"`, `operation={"recompress_reference": True}`,
    `risk="needs_confirmation"`).
  - `src/contig/data/detector_corpus.jsonl` (`reference-not-bgzf`) and
    `detector_corpus_holdout.jsonl` (`holdout-reference-not-bgzf`);
    `src/contig/data/holdout_baseline.json` — `accuracy: 0.8461538461538461` (11/13),
    up from the prior committed 83.3% (10/12), confirming the refreeze actually happened.
  - `docs/planning/self-heal-bgzip-reference/recompress-reference/task-5-report.md` — the
    reproduce-safety phase report, confirming empirically (not assumed) that
    `launch.json` keeps the original `fasta` and that a temporary leak was injected and
    reverted to prove the guard test is load-bearing.
  - Confirmed **no breadcrumb** exists (`grep reference_recompressed src/contig/self_heal.py`
    → no match; only the pre-existing `reference_harmonized` breadcrumb from v0.9.0 was
    found) and **no heal-guard scenario** exists yet
    (`grep reference_not_bgzf src/contig/data/heal_scenarios.jsonl src/contig/data/heal_baseline.json`
    → no match) — so both are documented as deferred/not-yet-done, not silently implied
    shipped.
  - Git log confirms only 5 of the plan's 7 phases are committed on this branch so far
    (`ab1e1b4` detect, `515568f` repair, `4d968a2` helper, `2ad8ca2` dispatch, `3badaeb`
    reproduce-safety test) — Phase 6's breadcrumb and Phase 7's heal-scenario are not on
    the branch. This task covers only the docs half of Phase 6.

## Changes made

### 1. `CHANGELOG.md`

Added one `### Added` entry under `## [Unreleased]` (before `## [0.22.0]`), matching the
depth/voice of the v0.19.0–v0.22.0 entries:

- Names the capability (**C2**) and that this is the **first slice of the
  input-format-conversion class**.
- States the failure precisely (`samtools faidx` → "Cannot index files compressed with
  gzip, please use bgzip"), the prior opaque `tool_crash` fallthrough, and the exact
  rnaseq-vs-sarek reachability asymmetry (rnaseq's `PREPARE_GENOME` gunzips first; sarek
  3.5.1 has no gunzip module; the forced `--gtf` from `resolve_reference` is only an
  nf-schema warning on sarek, not a validation failure).
- Describes the fix mechanism (`_recompress_reference`, stdlib `gzip` stream-decompress,
  scratch `<run_id>/healed_reference/`, in-memory `params["fasta"]` redirect, seam reuse)
  and the `_gzip_kind` BGZF-safety discriminator.
- Names the new `FailureClass` `reference_not_bgzf`, the narrow detector anchor (excluding
  the VCF-only tabix/bcftools "please use bgzip" message), the corpus additions, and the
  concrete held-out-accuracy move (83.3%→84.6%, refrozen baseline).
- Names the patch shape (`kind="reference"`, `risk="needs_confirmation"`, not `safe`).
- Enumerates every honest give-up outcome and the one-recompress-per-run bound.
- States "no raw-read egress; research-use only" and "no real nf-core/sarek or samtools
  run in CI," matching house convention.
- **Deferred, named explicitly:** CRAM↔BAM conversion, the declined BGZF fix target,
  `safe`-vs-gated auto-approval, the missing `heal-guard` scenario, and the
  `resolve_reference` `--fasta`/`--gtf` coupling quirk as a separate follow-up.

### 2. `docs/technical/CAPABILITY_ROADMAP.md`

- Inserted a new **"Shipped (input-format conversion — bgzip-reference slice —
  Unreleased):"** paragraph in the C2 section, in the same voice/format as the other
  "Shipped (... slice — Unreleased):" paragraphs immediately above it (walltime-scaling,
  peak-RSS scaling, etc.), covering the same facts as the changelog entry but at
  roadmap-appropriate density, and updated the "**Deferred to later C2 slices:**"
  paragraph's tail to read "...a runtime `reference_mismatch` detector-corpus case,
  CRAM↔BAM conversion (the input-format-conversion class's second half), and pin
  conflict" — replacing the old bare "format conversion" placeholder now that the first
  slice of that class has shipped.
- Updated the C2 row of the "Sequencing summary" table to append: "input-format-conversion
  class's first slice shipped (Unreleased): bgzip'd (non-BGZF) reference FASTA self-heal,
  sarek-scoped (rnaseq immune by construction), stream-decompress to uncompressed `.fa` +
  retry; CRAM↔BAM conversion is the deferred second half."

No version bump (per instructions — that happens at merge time). No code, test, or
breadcrumb changes.

## Validation

```
uv run pytest
1227 passed, 1 skipped in 11.36s
```

Identical to the pre-existing baseline (Task 5 also reported 1227/1 skipped) — a docs-only
change does not add or remove tests, confirmed nothing broke.

## Commit

```
docs(heal): record recompress-reference slice (bgzip reference) [C2]
```

## Concerns / notes

- **Phase 6's breadcrumb (should-have S2) and Phase 7's heal-scenario (nice-to-have N1)
  from the plan are still not implemented on this branch.** This task deliberately did
  NOT add them (explicit instruction: docs-only, no breadcrumb). The changelog and roadmap
  entries both name these as deferred rather than implying they shipped, so the docs stay
  honest against the actual code state. If a future task adds the breadcrumb and/or the
  heal-guard scenario, both docs entries will need a follow-up amendment (or a new
  changelog/roadmap entry) rather than silent backfill.
- The held-out accuracy figure (84.6%, 11/13) was read directly from the committed
  `src/contig/data/holdout_baseline.json` rather than recomputed — it reflects the
  baseline as of the Phase 1 commit (`ab1e1b4`) and has not changed since (no detector or
  corpus changes happened in Phases 2–5).
- No other files were touched; `docs/planning/_card/issue.md` and
  `docs/planning/_card/understanding.md`, which showed as modified in the pre-task `git
  status`, were left exactly as found (out of scope for this docs task and not touched by
  it).
