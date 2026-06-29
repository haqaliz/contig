# Changelog

All notable changes to Contig are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims for
[semantic versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

## [0.6.0] - 2026-06-29

### Added

- Reference-identity provenance (capability C5, capture slice — slice 1 of N): a run
  now records *which genome and annotation it ran against*, deepening the reproduce
  guarantee beyond pinned tools/params to the reference data itself. A new
  `ReferenceIdentity` model is captured at finalize from the run's parameters and
  serialized into `run_record.json`: explicit mode (`--fasta`/`--gtf`) records the
  paths plus their `sha256`; iGenomes mode (`--genome KEY`) records the key only and
  marks checksums unavailable — the pipeline downloads those files, so Contig has no
  local path to hash, and a run is never failed over an unhashable/missing reference
  (the checksum degrades to `None`, never a fabricated or zero hash). The identity is
  rendered in `contig methods` and the HTML provenance panel (iGenomes shows the key
  as pipeline-downloaded, never a blank hash). Capture-only: no QC/verdict change, no
  exit-code change. **Deferred:** the pre-flight reference/build **mismatch detector**
  (the next C5 slice, where the real feasibility risk lives), known-sites capture
  (not visible to Contig today — nf-core config assets, not CLI params),
  annotation/GTF version resolution (no reliable source — left null, not fabricated),
  and RO-Crate export of the identity. nf-core only (Snakemake runs carry no reference
  keys → identity is absent and the section is omitted cleanly). Hashes run on the
  user's compute (no raw-read egress); fully covered by synthetic fixtures (no real
  nf-core run in CI).
- RNA-seq biological-plausibility verification (capability C3, RNA-seq slice):
  extends the germline plausibility verdict to bulk RNA-seq. Two WARN-capped checks
  — `duplication_rate` (`percent_duplication`) and `rrna_contamination`
  (`percent_rRNA`) — live in a new `RNASEQ_PLAUSIBILITY_PACK` and are evaluated by
  `evaluate_rnaseq_plausibility`, which mirrors the germline pattern: present metrics
  are scored via the shared rule evaluator, and a metric absent from a sample's
  ingested MultiQC yields `unverified` (`value=None`, never a false pass), capped at
  WARN (corroboration, not a clinical claim). Wired into `_discover_qc` gated to
  `assay == "rnaseq"` with a MultiQC report present; other assays are unchanged. The
  metric slugs and bands are best-effort, uncalibrated engineering defaults — the
  UNVERIFIED-when-absent guarantee absorbs a wrong/missing slug. Deferred:
  gene-body-coverage evenness (needs a new RSeQC compute path), FAIL severity until
  bands are calibrated, and the single-cell/sex-check slices. Tests-only (no detector
  corpus change — plausibility is not a `FailureClass`); fully covered by synthetic
  metric fixtures (no real nf-core run in CI).

## [0.5.0] - 2026-06-28

### Added

- Self-heal the rest of the single-file index family (capability C2, missing-index
  follow-on): the `missing_index` self-heal now builds and retries a missing `.bai`
  (`samtools index`), `.tbi` (`tabix -p vcf`), and `.csi` (`bcftools index`), not just a
  `.fai`. The parser now returns the missing path and its extension, and a table maps each
  extension to its build command on the existing injectable `IndexBuilder` seam; the
  honest give-ups (`index_unresolvable` / `index_build_failed`) and the
  `built_index_and_retried` outcome are unchanged, as is the detector (it already
  classified these). One golden corpus case per new kind is seeded. Still single-file
  indexes only — `.dict` (needs a detector change and non-trivial source-FASTA
  resolution), the BAM/CRAM form of `.csi`, and directory-shaped STAR/BWA indexes remain
  deferred. Bounded by `max_attempts`, runs on the user's compute (no raw-read egress),
  fully covered by injected-builder/executor tests (no real `samtools`/`tabix`/`bcftools`/
  pipeline run).
- Self-heal a missing index (capability C2, missing-index slice): a `missing_index`
  failure is now actually recovered instead of re-run unchanged. When the
  `build_index` repair is applied, the loop parses the missing index path from the
  diagnosis, builds it (this slice: a missing FASTA `.fai` via `samtools faidx`
  through a new injectable `IndexBuilder` seam), and retries — recording a
  `built_index_and_retried` `RepairStep`. If the index path can't be parsed or the
  build itself fails, the loop gives up honestly (`index_unresolvable` /
  `index_build_failed` with a `RepairStep.detail` naming the path) — an honest FAIL,
  never a false pass. The build is bounded (one per applied patch, within
  `max_attempts`), runs on the user's compute (no raw-read egress), and is fully
  covered by injected-builder/executor tests (no real `samtools`/pipeline run).
  (`.bai`, `.tbi`, and `.csi` are added in the follow-on entry above; `.dict` and
  STAR/BWA remain deferred.)
- Bounded resource-aware self-heal retry (capability C2, resource-aware slice): the
  `oom` and `time_limit` repairs now scale memory/walltime only up to an absolute
  ceiling (defaults 128 GB / 72 h, code-overridable via `self_heal_run`'s
  `resource_ceiling`). When the scaled resource is already at its ceiling and the
  failure recurs, the loop gives up honestly with a distinct `gave_up_at_ceiling`
  outcome and a `RepairStep.detail` message naming the resource and the cap — an
  honest FAIL, never a false pass — and the case is still captured to the failure
  corpus. A scale that would overshoot is clamped to the cap; a pre-existing request
  already above the cap is never shrunk. Engine-wide (all assays); deterministic and
  fully covered by injected-executor tests (no real pipeline run).

## [0.4.0] - 2026-06-27

### Added

- Turnkey cross-tool concordance (follow-on to C1): `contig verify <run>
  --concordance-auto --bam <bam> --ref <ref>` runs a second variant caller
  (bcftools) on the BAM and reference to produce an independent call set, then
  corroborates the run's primary VCF against it. The second caller is behind an
  injectable seam, so it is never executed in CI; a missing binary, missing input,
  or caller failure prints a clear skip note (never a false pass) and never changes
  the exit code. Mutually exclusive with `--concordance-vcf`. Reuses the existing
  concordance machinery; germline only.

## [0.3.0] - 2026-06-26

### Added

- Germline biological-plausibility verification (capability C3, germline slice):
  `ts_tv` (transition/transversion ratio over biallelic SNVs) and `het_hom`
  (heterozygous/homozygous-alt genotype ratio) are computed deterministically from
  a germline run's VCF, activating the previously-dormant `VARIANT_RULE_PACK`
  plausibility rules. The checks run whether or not a MultiQC report exists, are
  capped at WARN (corroboration, not a clinical claim), and report `unverified`
  (never a false pass) when a ratio is uncomputable.

### Changed

- The `ts_tv_ratio` and `het_hom_ratio` rules in `VARIANT_RULE_PACK` are capped at
  WARN (their FAIL bands removed) until the bands are calibrated on real data;
  `mean_coverage` is unchanged.

## [0.2.0] - 2026-06-24

### Added

- Cross-tool concordance verification (capability C1, germline slice): corroborate a
  germline run's variants against a second, independent call set. A new `concordance`
  QC kind emits a `genotype_concordance` check (over shared sites) plus a
  `site_overlap` check; `contig verify --concordance-vcf <vcf>` runs them against the
  run's primary VCF. Concordance is at most WARN (corroboration, not ground truth)
  and never changes the verify exit code; an empty site intersection reports
  `unverified`, never a false pass. Surfaced in the text and HTML reports and the
  dashboard QC panel.

### Changed

- `QCStatus` gains `unverified` as a per-check status (previously run-level only).
  `overall_verdict` reduces a set of only-unverified checks to `unverified`, never
  `pass`, preserving the near-zero false-pass guarantee.

## [0.1.0] - 2026-06-24

The first tagged release: the Layer-2 engine (run, self-heal, verify, reproduce)
plus a local dashboard, feature-complete against the catalog and validated on real
compute. Pre-revenue, validation phase.

### Engine (CLI)

- Run a curated pipeline, self-heal recoverable failures, verify the output, and
  report an honest verdict (PASS / WARN / FAIL / UNVERIFIED): `contig run`, `show`,
  `list`, `plan`.
- Self-heal loop: detect, diagnose, propose typed patches, apply the safe ones, and
  retry, bounded and logged. Risky patches pause for human approval, with ranked
  options on an ambiguous decision (`contig approve`, `--choose`).
- Live observability and control: `contig status`, `watch`, `cancel`, `resume`,
  `rerun`; lifecycle events to `notifications.jsonl` plus a webhook and optional
  SMTP email.
- Verification: metric QC rule packs per assay plus structural and integrity checks
  (outputs present, non-empty, indexed, gzip and BAM integrity); a missing or corrupt
  required output FAILs the verdict.
- Reproducibility: a pinned, portable run record; `contig verify` re-hashes outputs;
  Ed25519 signed records (`contig keygen`); RO-Crate export and a methods paragraph
  (`contig export --rocrate`, `contig methods`); a self-contained HTML report
  (`contig show --html`).
- Cost and planning: `contig cost` for actuals and `contig estimate` for a pre-run
  estimate; resource actuals captured from the trace.
- The failure-corpus flywheel: capture, promote (`contig corpus-promote`), score
  (`contig eval-detector`, with a pluggable detector incl. an optional LLM detector),
  cluster (`contig clusters`), and track coverage (`contig coverage`) and an accuracy
  trend.
- Cross-run verification benchmarking: `contig benchmark` against a designated
  reference.
- Six assays (RNA-seq, single-cell RNA-seq, germline variant calling, methyl-seq,
  16S amplicon, shotgun metagenomics), two workflow engines (Nextflow and Snakemake),
  and three backends (local, AWS Batch, SLURM; local and SLURM live-validated).

### Dashboard

- A Next.js dashboard over the same engine: launch, live progress and the self-heal
  feed, the approval gate, verdict explainability, output-integrity and signature
  badges, compare, the corpus pending-review and the eval flywheel, cost, and the
  benchmark view.
- Auth0 authentication and role-based authorization, per-user run isolation, and team
  workspaces, with a documented local/test bypass.

### Packaging

- Installable as a Python package, a standalone binary per OS, a container image, and
  (where set up) via Homebrew. See the README for install options.

[0.6.0]: https://github.com/haqaliz/contig/releases/tag/v0.6.0
[0.1.0]: https://github.com/haqaliz/contig/releases/tag/v0.1.0
