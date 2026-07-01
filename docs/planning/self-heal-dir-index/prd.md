# PRD — self-heal-dir-index (C2: STAR/BWA aligner-index self-heal)

- **Capability:** C2 (self-heal breadth) — the next missing-index kind on the shipped
  `IndexBuilder` seam, after the single-file family (`.fai/.bai/.tbi/.csi/.dict`).
- **Type/slug:** feat / `self-heal-dir-index`
- **Branch:** `feat/self-heal-dir-index/aliz`
- **Source:** inline brief from `contig-next`; deep-dig in
  [`understanding.md`](understanding.md). Confirmed scope decisions inline below.

### Confirmed decisions (interview + review gate)

1. **Index kinds:** STAR (directory-shaped) + classic BWA (5 sidecars beside the FASTA).
   bwa-mem2 deferred.
2. **STAR failure modes:** fully-missing/aborted **and** version-incompatible. Corrupt/
   partial deferred.
3. **Trigger:** inherit the shipped `missing_index` `needs_confirmation` approval gate.
4. **Build target:** **scratch + redirect.** Always build into a run-scoped scratch
   location and redirect the retried run at it; **never** mutate the user's supplied index
   in place. Mirrors the v0.9.0 harmonization scratch-file pattern. (Consequence: the
   retry must override the index param — see M12.)

## Problem Statement

When a `contig run` is handed a **pre-built aligner index** that is missing, aborted, or
built with an incompatible tool version, the pipeline fails hard at the alignment step.
Today Contig cannot recover: the failure isn't even classified as a buildable index —
STAR/BWA error strings match none of the existing single-file `missing_index` signatures,
so the run falls through to `missing_reference` (a misclassification) or degrades to
`tool_crash` (`detect.py:159-209,258`), yielding a dead-end FAIL verdict with no heal.

This is a **common, real** RNA-seq failure (STAR is the RNA-seq aligner): a half-finished
index from a killed/OOM'd prior run, a `--star_index` path pointing at the wrong dir, a
shared index missing files, or — most common of all with AWS-iGenomes — a STAR index
built with an old STAR version that breaks under a newer binary
(`Genome version ... is INCOMPATIBLE with running STAR version`). All of these heal by the
same action: **rebuild the index from the run's reference and retry.**

**Evidence it's real:** named as the next missing-index kind "on the same seam"
(`CAPABILITY_ROADMAP.md:138-139`); STAR version-incompatibility is a documented, recurring
nf-core/iGenomes problem (alexdobin/STAR #962, #747; nf-core/rnaseq usage docs — see
understanding.md). The single-file family it extends shipped through v0.8.0
(`CHANGELOG.md:46-78`).

## Goals & Success Metrics

- **G1 — Recover the failure autonomously.** A run failing on a missing or
  version-incompatible STAR index, or a missing BWA index, is detected, the index is
  rebuilt from the run's reference, and the run retries — recording
  `built_index_and_retried`. *Metric:* injected-failure fixtures for STAR-missing,
  STAR-version-incompatible, and BWA-missing each self-heal end-to-end in the test suite.
- **G2 — Never a false pass.** When the source reference can't be resolved or the build
  fails, give up honestly (`index_unresolvable` / `index_build_failed`) — an honest FAIL,
  never a fabricated success. *Metric:* fixtures for each give-up path assert the outcome
  and a non-passing verdict.
- **G3 — Raise unattended-completion** (Phase 1 headline metric, `ROADMAP.md:101,108`) by
  adding STAR/BWA to the recovered-failure catalog.
- **G4 — Compound the corpus** (moat #2): seed one golden detector-corpus case per new
  signature (STAR-missing, STAR-version-incompatible, BWA-missing) with
  `contig eval-detector` staying at 100% (`cli.py:1366`).
- **G5 — Reproducible heal.** The rebuilt STAR index records the STAR version used, so the
  heal does not silently re-introduce the version-mismatch class on a later reproduce.

## User Personas & Scenarios

- **A — lone computational biologist** (primary): points an nf-core/rnaseq run at a shared
  STAR index that turns out to be stale/old-version; instead of decoding a STAR FATAL ERROR
  and hand-rebuilding, Contig rebuilds and continues, pausing once for approval.
- **C — core facility:** maintains pre-built indices that drift out of version sync with
  tool upgrades; the self-heal absorbs the drift with an auditable repair record.

## Requirements

### Must-have (M)

- **M1 — Detect a buildable STAR index failure.** New, *narrow* detector branch(es) for:
  - missing/aborted: `could not open genome file` … `genomeParameters.txt`
  - version-incompatible: `Genome version:` … `is INCOMPATIBLE with running` STAR version
  Both classify as `missing_index` (reuse the existing `FailureClass`; rebuild is the heal
  for both). Stay narrow enough that a wrong-reference/contig-mismatch is NOT swallowed
  (mirror the `.dict` branch's deliberate narrowness, `detect.py:180-198`).
- **M2 — Detect a buildable BWA index failure.** `[E::bwa_idx_load_from_disk] fail to
  locate the index files` → `missing_index`.
- **M3 — Build a STAR index into scratch and retry.** Resolve the run's reference FASTA
  (+ GTF) — see M6 — `mkdir` a run-scoped scratch `--genomeDir` (e.g.
  `<run_dir>/healed_index/star/`), run `STAR --runMode genomeGenerate --genomeDir <scratch>
  --genomeFastaFiles <fa> [--sjdbGTFfile <gtf>]` through the injected `IndexBuilder` seam,
  redirect the retried run at the scratch dir (M12), and retry. Record
  `built_index_and_retried`. **Never** build over the user's supplied `--genomeDir`.
- **M4 — Build a BWA index into scratch and retry.** Resolve the source FASTA via the
  shared M6 reference-from-manifest resolution (the BWA error names no path, so do **not**
  rely on suffix-strip of the sidecar token alone — see M4-acceptance / OQ2-resolved),
  copy/symlink the FASTA into scratch, run `bwa index <scratch_fa>`, redirect (M12), retry.
- **M5 — Generalize the build dispatch** away from pure file-extension keys so a
  directory-shaped (STAR) and a multi-sidecar (BWA) kind can be dispatched. Extend the
  parser/`_INDEX_TOKEN_RE` (`self_heal.py:59,62`) to recognize STAR/BWA tokens and
  normalize a STAR inner-file token (`genomeParameters.txt`) to its parent **directory**,
  so the build-once guard key (`built_paths`, `:563,488,509`) matches the build target.
- **M6 — Resolve the run's reference (shared spine for STAR *and* BWA).** Neither STAR's
  `--genomeDir` nor the path-less BWA error gives a reliable source-FASTA path, so the
  deriver must read the run's resolved reference (FASTA + GTF) from the launch manifest /
  run params — net-new input to the `SourceDeriver` seam (`(index_path, ext, run_dir)`
  today). Reuse the v0.9.0 chr-prefix harmonization's reference-resolution path as
  precedent. **This is the central new plumbing, shared by M3 and M4.**
  - **M6-fallback (gap #1):** if the manifest does **not** expose the resolved reference
    in a reusable form, the heal degrades to an honest `index_unresolvable` give-up — it
    never grows unbounded or guesses. The tech-plan's first task is a spike confirming
    `LaunchManifest`/the resolve path carries the reference; if it doesn't, that spike's
    fallback is the give-up, and STAR-missing/BWA-missing simply don't heal (an honest
    FAIL) rather than blocking the slice.
- **M7 — Honest give-up.** If the reference FASTA can't be resolved →
  `index_unresolvable`; if the build exits non-zero → `index_build_failed`. Never a false
  pass. Bounded by the existing `built_paths` build-once guard and `max_attempts`.
- **M8 — Directory/sidecar success check.** After a STAR build, confirm `--genomeDir` is a
  non-empty directory containing the core files (`Genome, SA, SAindex,
  genomeParameters.txt`); after a BWA build, confirm the five sidecars exist. Today only
  `rc==0` and a file `.exists()` are checked (`:110,511`) — add `is_dir()`/non-empty.
- **M9 — Inherit the approval gate.** Reuse the shipped `missing_index` repair path — a
  `needs_confirmation` `reference` patch (`repair.py:56-65`) that pauses for approve/reject.
  No new trigger model.
- **M10 — Corpus seeds.** One golden `FailureCase` per new signature (STAR-missing,
  STAR-version-incompatible, BWA-missing) in `detector_corpus.jsonl`; `eval-detector`
  stays 100%.
- **M11 — Test-first, no real tools in CI.** Injected `IndexBuilder`/executor fixtures;
  no real STAR/BWA/nf-core invocation. Synthetic `tmp_path` index dirs/sidecars.
- **M12 — Redirect the retried run to the scratch index (scratch-decision consequence).**
  Because we build into scratch (never in place), the retry must override the run's index
  param to point at the scratch dir/prefix (e.g. the `--star_index` / bwa-index param the
  pipeline reads). The override lives on the *retried* run's `params` only; the scratch
  path is NOT baked into the persisted launch manifest (see M13). A STAR
  version-incompatible failure — where the user's original index is intact at the original
  path — is the case that makes this mandatory: without the redirect the retry re-reads the
  stale index and fails identically.
- **M13 — Reproduce/rerun re-derives the heal (gap #3a).** `rerun`/`resume` must re-enter
  the heal from the original (un-redirected) reference and rebuild into a fresh scratch
  dir — no scratch genomeDir path is persisted into the manifest. Mirrors the v0.9.0
  harmonization `rerun`/`resume` design (re-derive, don't bake a scratch path).
- **M14 — Clean give-up when the retry fails for a NEW reason (gap #3b).** The build-once
  guard (`built_paths`) must ensure that if the index rebuilds successfully but the retried
  run then fails for a *different* reason (not the index), the loop surfaces that new
  failure honestly rather than masking it or re-building the same index. Tested explicitly.

### Should-have (S)

- **S1 — Record the STAR version** used for the rebuild in the repair telemetry /
  provenance (the `genomeParameters.txt` `versionGenome` field or the builder's STAR
  `--version`), so a reproduce doesn't re-introduce the version-mismatch class (G5).
- **S2 — `argv_fn` widening** to receive `run_dir`/params if the directory builders need
  to create the output dir or pass extra flags (e.g. `--genomeSAindexNbases` for small
  genomes) — only if clean; otherwise keep the two-arg shape.

### Nice-to-have (N)

- **N1 — Corrupt/partial STAR index** signature (`FATAL GENOME INDEX FILE error ... is
  corrupt`) — deferred this slice (rarer; same rebuild heal, easy follow-on).
- **N2 — `--sjdbOverhang`/read-length awareness** for the STAR build argv.

## Technical Considerations

- **Seam fit (`self_heal.py`):** the build table `_INDEX_BUILD` (`:119-125`), the
  `(SourceDeriver, argv_fn)` tuple shape (already generalized for `.dict`), the
  `IndexBuilder` injection (`runner.py:83-126`, threaded `cli.py:498` → `self_heal.py:447,
  510`), the outcomes (`:480-519`), and the `built_paths` guard (`:563`) all extend
  cleanly. The dispatch key must move off pure file-extension.
- **Detector fit (`detect.py`):** add narrow STAR/BWA branches alongside the `.dict`
  branch; reuse `missing_index`. No new `FailureClass`.
- **Reproducibility:** STAR indices are version-bound (G5/S1); BWA indices are
  version-stable but aligner-specific (classic-`bwa` vs `bwa-mem2` — bwa-mem2 deferred).
- **No raw-read egress:** the index is built from a local FASTA/GTF on the user's compute.
- **Verification impact:** none to the verdict-reduction logic; this is a self-heal /
  execution-recovery change. The retry's output is verified by the existing QC/structural
  path as usual.

## Risks & Open Questions

- **R1 — Reference resolution plumbing (M6) is the real risk.** Threading the run's
  reference into the STAR/BWA deriver is net-new; if the launch manifest doesn't already
  carry the resolved FASTA/GTF in a reusable form, this grows. *Mitigation (now in M6 as
  M6-fallback):* tech-plan's first task is a spike confirming the resolve path exposes the
  reference; if not, the heal degrades to an honest `index_unresolvable` give-up rather
  than blocking the slice. **No longer an open cliff.**
- **R2 — Detector over-trigger.** A too-broad STAR/BWA branch could swallow a genuine
  wrong-reference. *Mitigation:* require a tool-specific token AND an absence/incompat
  phrase, mirroring the `.dict` branch; add a negative (wrong-reference) corpus/control
  case.
- **R3 — Build-once guard key vs build target divergence** for STAR (inner-file token vs
  parent dir). *Mitigation:* M5 normalizes the parsed token to the directory; M14 covers
  the retry-fails-for-a-new-reason path.
- **R4 — Redirect param name varies by pipeline** (M12). The index param the pipeline
  reads (`--star_index`, bwa-index input) is pipeline-specific. *Mitigation:* tech-plan
  identifies the param from the run's resolved params/registry; if it can't be identified,
  give up honestly (`index_unresolvable`) rather than guessing.
- **OQ1 — S1 sink:** exactly where the STAR version is recorded (RepairStep.detail vs a
  provenance field) — resolve in tech-plan.
- **OQ2 — RESOLVED (folded into M4/M6):** the path-less BWA error means BWA cannot rely on
  the sidecar token alone, so BWA shares M6's reference-from-manifest resolution; if that
  resolution fails, BWA give-up is `index_unresolvable`.

## Out of Scope

- **bwa-mem2** index set + the classic-vs-mem2 aligner-mismatch heal (deferred).
- **Corrupt/partial STAR** index signature (N1, deferred).
- **Auto-heal without approval** — we inherit the `needs_confirmation` gate (M9).
- Stale-index *detection* as a pre-flight check (this is runtime failure recovery).
- BAM/CRAM form of `.csi`; peak-RSS resource scaling; assembly-signature reference
  mismatch — separate C2 slices.
- Building Layer 1 (NL → workflow) — not the product.

## Acceptance (test-first, per the standing discipline)

For each of STAR-missing, STAR-version-incompatible, BWA-missing:
1. A `diagnose_failure` test: the tool's real error `log_text` classifies as
   `missing_index` (and a wrong-reference control does NOT).
2. A `self_heal_run` test with an injected builder: the failure is detected, the patch
   applied, the build invoked with the expected argv **into a scratch dir**, the retried
   run's index param **redirected to the scratch path** (M12), and the run retried with
   `built_index_and_retried`.
3. A give-up test: unresolvable reference → `index_unresolvable`; build exit≠0 →
   `index_build_failed`; redirect-param-unidentifiable → `index_unresolvable`; none yields
   a passing verdict.
4. A `detector_corpus.jsonl` golden case; `evaluate_detector` stays at 100%.

Plus, once across the slice:
5. **Reproduce (M13):** a `rerun`/`resume` of a healed run re-derives the heal from the
   original reference into a fresh scratch dir — no scratch path is read back from the
   persisted manifest.
6. **New-reason retry (M14):** index rebuilds successfully, but the retried run fails for a
   different reason — the loop surfaces that new failure honestly (does not re-build the
   same index, does not mask it as a pass).
7. **STAR version recorded (S1):** the rebuilt STAR index's STAR version is captured in the
   repair telemetry/provenance.
