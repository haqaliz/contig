# PRD: self-heal a plain-gzip'd (non-BGZF) reference FASTA

**Capability:** C2 (self-heal breadth) — first slice of the input-format-conversion class.
**Slug:** `self-heal-bgzip-reference` · **Branch:** `feat/self-heal-bgzip-reference/aliz`
**Status:** scope confirmed (interview 2026-07-08). Full build/redirect, sarek-scoped by construction.

---

## Problem Statement

A Contig-launched **nf-core/sarek** run (assays `variant_calling` germline and
`somatic_variant_calling`) fails hard when the user supplies a reference FASTA that was
compressed with plain `gzip` instead of `bgzip`. sarek 3.5.1 passes the reference
**directly** to `SAMTOOLS_FAIDX(fasta, ...)` (`subworkflows/local/prepare_genome/main.nf:54`)
with **no GUNZIP step anywhere in the pipeline** (verified against the pinned git tree —
sarek has no `modules/nf-core/gunzip`). `samtools faidx` rejects plain-gzip input:

```
[E::fai_build3_core] Cannot index files compressed with gzip, please use bgzip
[faidx] Could not build fai index <ref>.fa.gz.fai        (exit 1)
```

Today Contig's detector has no branch for this signature, so it falls through to the
opaque terminal `tool_crash` (confidence 0.4, "give up") at `detect.py:320-329`. The run
FAILs with no diagnosis and no recovery.

**Why it's real (not assumed):** confirmed three ways — (1) version-exact pinned pipeline
source (sarek 3.5.1 vs rnaseq 3.26.0), (2) the sarek git tree showing no gunzip module,
(3) a real local reproduction of the exact `samtools faidx` failure and its fix. Evidence
in `docs/planning/_card/understanding.md`.

**Why rnaseq is immune (and must be excluded):** nf-core/rnaseq 3.26.0 gates
`GUNZIP_FASTA` on `fasta.endsWith('.gz')` (`prepare_genome/main.nf:113-114`) and faidx's
the decompressed output — so the failure never reaches Contig on the rnaseq path. Wiring
a heal that assumes rnaseq would recreate the dormant-code trap that made the BWA
(v0.10.0) / bwa-mem2 (v0.11.0) detector-only.

## Goals & Success Metrics

- **G1 — Recover the failure autonomously.** A sarek run whose `--fasta` is a plain-gzip
  file self-heals: detect → recompress reference to plain uncompressed `.fa` in run
  scratch → redirect `params["fasta"]` → retry → run proceeds. Raises
  unattended-completion (ROADMAP Phase-1 headline metric, ≥70%) on the sarek assays.
- **G2 — Honest classification, no false pass.** The signature is diagnosed into a new
  `reference_not_bgzf` class instead of opaque `tool_crash`; every give-up path is an
  honest FAIL, never a masked pass.
- **G3 — Corpus fuel (moat #2).** One golden detector-corpus case + one held-out twin,
  keeping `eval-guard` meaningful; the class is structurally reachable by the detector
  (unlike `qc_anomaly`/`no_progress`).
- **G4 — Reproduce-safe.** `rerun`/`resume` re-derive the heal from the original
  (un-redirected) `fasta` in `launch.json`; no scratch path is ever persisted.

**Measured by:** the test suite (all acceptance criteria below are tests); a green
`eval-guard`/`heal-guard`; no change to any other assay's verdict.

## User Personas & Scenarios

- **Lone computational biologist / core-facility bioinformatician** running germline or
  somatic variant calling on their own reference genome. They `gzip ref.fa` out of habit
  (the universal Unix reflex) rather than `bgzip ref.fa`. Today: an opaque crash they must
  diagnose by hand. After: Contig recognizes it, fixes the reference on their compute, and
  the run completes unattended.

## Requirements

### Must-have
- **M1 — Detector branch.** A narrow branch in `diagnose_failure` (`detect.py`) matching
  the htslib signature `Cannot index files compressed with gzip, please use bgzip`
  (secondary anchor `fai_build3_core`), returning `Diagnosis(failure_class="reference_not_bgzf", ...)`
  with the offending FASTA path captured in `evidence`. Inserted before the `tool_crash`
  fallthrough. Assay-agnostic (the detector is assay-agnostic by design).
- **M2 — New FailureClass.** Add `reference_not_bgzf` to the `FailureClass` Literal
  (`models.py:208-225`). Propagates automatically to the LLM-prompt whitelist and corpus
  label type.
- **M3 — Repair patch.** `propose_patches` (`repair.py`) emits a `kind="reference"` patch
  carrying a recompress operation for this diagnosis.
- **M4 — Recovery helper.** A new `_recompress_reference(...)` in `self_heal.py`, modeled
  on `_build_star_index` (L566-673): resolves the failing `params["fasta"]`;
  **verifies the file's magic bytes are plain-gzip and NOT BGZF** (never mask a corrupt or
  already-BGZF file as a mis-compression); **decompresses to plain uncompressed `.fa`** in
  run-scoped scratch `<run_id>/healed_reference/<name>` via the injectable `IndexBuilder`
  seam; redirects the **in-memory** `params["fasta"]` to the scratch copy; records the
  recovery. Bounded by the existing `built_paths` one-per-run guard (L834). Dispatched
  from `_apply_patch_and_maybe_build` (L698-790) as a whole-file redirect (NOT a
  `_INDEX_BUILD` suffix-table row).
- **M5 — Honest give-ups.** No resolvable `params["fasta"]`, a file that is not actually
  plain-gzip, or a failed decompression → an honest FAIL give-up (distinct
  outcome/detail), never a false pass. Already-BGZF or uncompressed references are left
  untouched (they don't fail faidx).
- **M6 — Reproduce-safety.** `launch.json` continues to store the **original** `fasta`
  (already true, `cli.py:566`); the scratch path is never persisted; `rerun` re-enters
  `_dispatch_run` with the original path and re-derives the heal. Mirror the GTF
  harmonization pattern exactly (`cli.py:472-508,566,659`).
- **M7 — Detector corpus.** One golden `FailureCase` in `detector_corpus.jsonl` (real
  `faidx` `log_text`, `expected_class="reference_not_bgzf"`) + one twin in
  `detector_corpus_holdout.jsonl`.
- **M8 — Tests (TDD, injected seams).** Mirror the fai/dict fail-then-succeed pattern
  (`tests/test_self_heal.py:1566-1610,1737-1755`): (a) recompress success →
  recovery outcome, `params["fasta"]` redirected to scratch, exactly one recompress,
  re-run happened; (b) honest give-up when `params["fasta"]` absent; (c) honest give-up /
  no-op when the file is not plain-gzip; (d) one-recompress-per-run guard; (e) detector
  classification tests (live + holdout corpus). No real samtools/nf-core run in CI.

### Should-have
- **S1 — Recovery outcome label.** Reuse an existing self-heal outcome from the
  heal-guard taxonomy (`patched_and_retried` fits — we patched the reference param) OR add
  a distinct `recompressed_reference_and_retried`. Decide in the plan; if a new outcome,
  keep `heal-guard`'s `covered_classes`/baseline honest.
- **S2 — Provenance breadcrumb.** A WARN-level `reference_recompressed` QC breadcrumb (or
  a `RepairStep.detail` line) so the rewrite is visible in the verdict surface, mirroring
  the `reference_harmonized` breadcrumb (v0.9.0).

### Nice-to-have
- **N1 — heal-scenario.** A `heal_scenarios.jsonl` case exercising the loop end-to-end
  through `heal-guard` (C6 slice 2), promoting `reference_not_bgzf` to a covered class.

## Technical Considerations

- **Fix target = plain uncompressed `.fa`** (confirmed). Universally accepted by every
  downstream sarek tool (faidx, bwa/bwa-mem2 index, GATK `CreateSequenceDictionary`,
  MSIsensor) with zero per-tool bgzip-tolerance verification; one-step (`gunzip`); exactly
  mirrors the working rnaseq GUNZIP behavior. Trade-off accepted: ~3x transient scratch
  disk for a large reference.
- **Detector global, redirect condition-gated (confirmed).** The detector classifies the
  signature regardless of assay (corpus value + honest classification everywhere). The
  redirect only fires when `params["fasta"]` exists AND its magic bytes are plain-gzip —
  which is naturally sarek-only, since rnaseq's own gunzip means Contig never sees the
  failure there. No hardcoded assay allow-list; self-correcting if nf-core changes.
- **Reuses shipped seams:** `IndexBuilder` injectable seam + `default_index_builder`
  (`runner.py:217-260`); the `_build_star_index` scratch/redirect/`built_paths` structure;
  the GTF-harmonization reproduce-safety contract.
- **The real tools** (`samtools`, `bgzip`) are shelled out via the `IndexBuilder` seam and
  never run in CI (tests inject a fake builder). The decompression itself only needs
  `gunzip` (or Python's stdlib `gzip`), available everywhere.
- **eval-guard/heal-guard impact:** the new class is detector-reachable and comes with
  corpus cases, so held-out accuracy should hold or improve; refreeze the baseline
  deliberately via `--update-baseline` if it moves.
- **No raw-read egress; research-use only.** Recompression runs on the user's compute.

## Artifact / Run Contracts

- **New scratch:** `<runs_dir>/<run_id>/healed_reference/<name>.fa` (uncompressed). Wiped
  and recreated on heal; never persisted to `launch.json`.
- **In-memory redirect:** `params["fasta"]` → scratch path for the current process only.
- **launch.json:** unchanged shape; `fasta` stays the original path.
- **RepairStep:** records the detected signature, the original + scratch paths, and the
  recovery outcome for `repair_history` / `repair_progress.jsonl`.

## Risks & Open Questions

- **R1 — Frequency, not reachability.** The trigger is proven reachable but may be
  infrequent (users on iGenomes `--genome KEY` or pre-bgzip'd refs never hit it). Accepted:
  the incremental cost over detector-only is small (seams reused) and it converts a real
  failure into a real recovery. Revisit-if: no real user hits it after N field runs.
- **R2 — Magic-byte discrimination (top correctness risk).** Must reliably distinguish
  plain-gzip from BGZF (BGZF = a gzip member whose header carries an `FEXTRA` field with the
  `BC` subfield id at bytes 0x1f 0x8b 0x08 0x04 …) and from uncompressed, so we never
  (a) recompress a healthy BGZF ref or (b) mask a truncated/corrupt file as a mis-compression.
  **Acceptance tightened:** M8 test (c) must assert BOTH a valid-BGZF reference is left
  untouched (heal no-ops, no redirect) AND a non-gzip/truncated file gives up honestly —
  not merely "not uncompressed."
- **R3 — CLI reachability via the fasta/gtf coupling — RESOLVED FAVORABLY (2026-07-08).**
  `resolve_reference` (`reference.py:32-35`) does force `--fasta` AND `--gtf` together in
  explicit mode (an rnaseq-era assumption; sarek has no `gtf` param — `sarek@3.5.1`
  `nextflow_schema.json` defines `fasta` but not `gtf`). But sarek's `nextflow.config`
  sets no `validationFailUnrecognisedParams` override, and nf-schema defaults it to
  **false**, so the extra `--gtf` yields only a *warning* and the run proceeds — `--fasta`
  reaches `SAMTOOLS_FAIDX`. **The trigger IS reachable through the real CLI; the recovery
  is live, not dormant.** Residual: (a) relies on that nf-schema default (confirmed unset
  in 3.5.1 — re-confirm if the pin bumps); (b) the `resolve_reference` gtf-coupling is a
  latent quirk worth a *separate* follow-up, but **out of scope** here — this slice needs
  no change to it.
- **R4 — Outcome-label taxonomy.** Whether to reuse `patched_and_retried` or add a new
  outcome (S1) — a small blast-radius decision touching heal-guard; settle in the plan.
- **R5 — Large-reference decompression.** Uncompressed human genome ≈ 3 GB transient.
  Decompression must **stream** (not read the whole file into memory); the injected-builder
  CI test won't catch a real-perf/memory regression, so the real `gunzip`/`gzip`-stream path
  must be written to stream by construction. Scratch size acceptable; note in docs.
- **R6 — Orphaned sidecars.** If the user pre-built `.fai`/`.dict`/`.gzi` beside the `.gz`,
  redirecting to a fresh uncompressed `.fa` orphans them — harmless (sarek rebuilds its own
  indices from the redirected fasta), but state it so a reviewer isn't surprised.

## Out of Scope

- **rnaseq and all non-sarek assays** — excluded by construction (rnaseq gunzips; others
  don't take a faidx'd reference the same way).
- **CRAM↔BAM conversion** — the other half of the input-format class; a later slice.
- **BGZF fix target** — declined in favor of plain uncompressed.
- **Truncated/corrupt-gzip or wrong-assembly references** — different failure classes;
  this slice is plain-gzip→uncompressed only, and gives up honestly on anything else.
- **FAIL-severity band calibration** — not applicable (this is a recovery, not a QC band).
- **Any Layer-1 (NL→workflow) surface.**
