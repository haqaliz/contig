# Changelog

All notable changes to Contig are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims for
[semantic versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

### Added

- **RNA-seq cross-tool quantification concordance** (capability C1, RNA-seq slice —
  the second assay on the concordance axis after the germline slice shipped v0.2.0).
  `contig verify <run> --concordance-counts <matrix>` now corroborates a bulk RNA-seq
  run's own gene-count matrix against a **second, independent count matrix** supplied
  by the user, emitting three `kind="concordance"` checks from a new
  `verification/count_concordance.py`: `spearman_concordance` (per-gene **Spearman
  rank correlation**, WARN below 0.90), `fraction_agreeing` (share of shared genes
  whose summed counts agree within a 10% relative tolerance, WARN below 0.90), and
  `gene_overlap` (**informational, never WARN** — a second matrix built on a
  partial/subset annotation legitimately overlaps poorly, so overlap is context, not
  a verdict lever). Like germline concordance it is **at most WARN** (corroboration,
  not ground truth), **never changes the verify exit code**, and reports `unverified`
  (never a false pass) when the two matrices share fewer than 10 comparable genes (a
  Spearman over one or two genes is meaningless). The primary matrix is located by
  globbing the rnaseq structural manifest's count pattern `*salmon.merged.gene_counts*`
  (not the BAM); a non-rnaseq run, or a missing matrix, prints a clear skip note and
  changes no exit code. `--concordance-counts` is mutually exclusive with the germline
  `--concordance-vcf`/`--concordance-auto`. The Spearman and the count-matrix parser
  are **hand-rolled, stdlib-only** (no scipy/numpy dependency added): average-rank tie
  handling then Pearson of the ranks; the parser is gzip-transparent, sums counts
  across sample columns per gene, tolerates any gene-id + numeric-column TSV (so a
  STAR/featureCounts matrix can corroborate a Salmon one), skips the header row,
  accumulates duplicate gene ids, and never divides by zero on all-zero genes. The
  0.90 bands and 10% tolerance are **uncalibrated engineering defaults**, WARN-capped
  and absorbed by the UNVERIFIED-when-too-few-genes guarantee. Local, deterministic,
  no raw-read egress (operates on count matrices on the user's compute); fully covered
  by synthetic TSV fixtures (no real nf-core run in CI). **Deferred:** auto-running a
  second quantifier (Salmon vs STAR+featureCounts) behind an injectable seam — mirrors
  how the germline autorun (`--concordance-auto`) followed the user-supplied slice one
  release later (v0.4.0); single-cell concordance; a dashboard "corroborated by" line;
  and FAIL severity until the bands are calibrated on real data.

## [0.11.0] - 2026-07-01

### Added

- **Detect a bwa-mem2 unreadable/incompatible aligner index** (capability C2, self-heal
  breadth — the detector half of the next aligner-index kind after STAR, v0.10.0). When
  bwa-mem2 cannot read its index it prints `ERROR! Unable to open the file:
  <ref>.bwt.2bit.64` and exits non-zero; the engine now **classifies** this as
  `missing_index` (previously it degraded to an opaque `tool_crash`) via a new **narrow**
  detector branch AND-guarded on bwa-mem2's own sidecar token `.bwt.2bit.64` plus the
  `unable to open the file` phrase, so it can neither over-match a benign log line nor
  collide with the classic-BWA `bwa_idx_load_from_disk` branch nor swallow a
  wrong-reference. One golden `missing-index-bwamem2` corpus case is seeded (the
  shipped-corpus detector guard stays at 100%, now 23/23), feeding the eval flywheel
  (moat #2). The run still ends in an **honest FAIL** (`index_unresolvable`, verdict
  `fail`) — never a false pass — because the parser cannot resolve a build target for
  this signature. **Deferred (no live trigger — build/redirect intentionally not built):**
  actually rebuilding the bwa-mem2 index. nf-core/sarek auto-builds a missing index,
  AWS-iGenomes ships a classic BWA index (not bwa-mem2), and Contig exposes no flag to
  supply a broken index — so a bwa-mem2 index failure cannot be produced by a
  Contig-launched run today. This mirrors exactly how classic BWA shipped detector-only in
  v0.10.0. Local, deterministic (pure case-insensitive string matching over the run's own
  log; the corpus is a static asset), no raw-read egress; fully covered by injected
  fixtures — no real bwa-mem2 run in CI.

## [0.10.0] - 2026-07-01

### Added

- Self-heal a **missing or version-incompatible STAR aligner index** (capability C2,
  self-heal breadth — the next missing-index kind after the single-file family
  `.fai`/`.bai`/`.tbi`/`.csi`/`.dict`, now covering **directory-shaped aligner indexes**):
  when a run fails with either STAR's `could not open genome file …
  genomeParameters.txt` (missing/aborted index) or `Genome version … is INCOMPATIBLE with
  running STAR version` (stale index), the engine now **rebuilds** the index with `STAR
  --runMode genomeGenerate` from the run's resolved FASTA (+ GTF, via
  `params["fasta"]`/`params["gtf"]`) into a run-scoped scratch dir
  (`<run_id>/healed_index/star`) — the user's supplied index is never mutated — and
  **redirects** the retried run at the scratch index via `params["star_index"]`, recording
  `built_index_and_retried`. Bounded to ONE rebuild per run: a new-reason failure on the
  retry surfaces honestly rather than re-entering the builder or masking a pass. Honest
  `index_unresolvable` (no resolvable FASTA/genome dir) and `index_build_failed`
  (non-zero exit or an empty scratch dir) give-ups — never a false pass. The rebuilt
  STAR genome version is read back from `genomeParameters.txt` and recorded in the repair
  step's detail for provenance. `rerun`/`resume` re-derive the heal from the original
  (un-redirected) `fasta`/`gtf` manifest fields — `star_index` is never a manifest field
  and no scratch path is baked into `launch.json`, so reproduction is faithful. A classic
  **BWA missing-index** failure (`[E::bwa_idx_load_from_disk] fail to locate the index
  files`) is now also **detected** and classified `missing_index`, with a golden corpus
  case — but the build/redirect is **deferred**: no default supported pipeline invokes
  classic `bwa index` (sarek defaults to bwa-mem2; methyl-seq uses bwa-meth), so there is
  currently no live target to redirect. Local, deterministic, no raw-read egress (the
  index is built from a local FASTA/GTF on the user's own compute); fully covered by
  injected builder/executor fixtures — no real STAR/BWA/nf-core run in CI. **Deferred:**
  classic-BWA index build/redirect (would require a sarek `--aligner bwa-mem` target);
  bwa-mem2 index set + aligner-mismatch heal; a corrupt/partial STAR index signature (N1);
  directory-shaped BWA build (n/a while BWA stays detector-only).

## [0.9.0] - 2026-07-01

### Added

- Self-heal a **chr-prefix GTF naming mismatch** between the FASTA and GTF references
  (capability C2, reference/build-mismatch repair — first slice): when a `contig run`
  on real data is blocked at pre-flight by a disjoint contig-naming mismatch that is an
  unambiguous `chr`-prefix asymmetry (FASTA uses `chr1 …` while the GTF uses `1 …`, or
  vice versa), the engine now **auto-harmonizes** the GTF seqnames — a uniform `chr`-add
  or `chr`-strip applied to column 1 only, stream-written to
  `<runs_dir>/<run_id>/harmonized/<name>` — and **proceeds** with the harmonized copy,
  rather than refusing at pre-flight. The user's original GTF is never mutated. The
  transform is first validated by `plan_harmonization`: (a) one side must be entirely
  chr-prefixed while the other is entirely bare, and (b) after the transform the two
  contig sets must share at least one name. If either condition fails — a genuine
  wrong-assembly — the run is still refused, never a fabricated genome. The decision is
  recorded in the launch manifest (`harmonized_reference: bool`) and, when `_finalize`
  receives a non-null `harmonized_reference_direction`, in the run's `ReferenceIdentity`
  (`.harmonized = True`, `.harmonized_direction`). A WARN-level `reference_harmonized` QC
  breadcrumb is appended to `qc_results` so the rewrite is visible in every report and
  verdict surface. `rerun` and `resume` both re-enter `_dispatch_run` with the original
  (un-harmonized) GTF path, so the harmonization decision is re-derived from scratch —
  faithfully reproducible without baking a scratch file path into the manifest. Built on
  top of the C5 pre-flight mismatch detector shipped in v0.7.0, which classified and
  refused this chr-asymmetry class; it now also repairs it. Local, deterministic, no
  raw-read egress; fully covered by synthetic FASTA/GTF fixtures (no real nf-core run in
  CI). **Deferred:** the sample-data-vs-reference **assembly-signature** comparison/repair
  (raw FASTQ carries no contig naming and the finished bundle contains no aligned BAM, so
  there is no sample-side contig signal to compare at this stage); per-contig name mapping
  for ambiguous cases (e.g., `chrM`↔`MT`); known-sites/GTF-version consistency; and a
  runtime `reference_mismatch` `FailureClass`/detector-corpus case — eval capture is
  provenance-only in this slice.

## [0.8.0] - 2026-06-30

### Added

- Self-heal a missing GATK **sequence dictionary** (`.dict`) (capability C2,
  self-heal breadth — the next single-file kind on the shipped index-build seam,
  serving the germline assay where GATK/Picard refuse to run without a `.dict`
  beside the reference). When a run fails with a missing-`.dict` signature, the
  engine now resolves the source FASTA, builds the dictionary with
  `samtools dict -o <ref.dict> <ref.fa>` through the existing injectable
  `IndexBuilder` seam, and retries — recording `built_index_and_retried`. `.dict`
  is the first kind whose build input is **not** the indexed path minus its suffix
  (the dictionary `ref.dict` is built from a *companion* `ref.fasta`/`ref.fa`/
  `ref.fasta.gz`/`ref.fa.gz`), so the build table was generalized to
  `{ext: (derive_source, build_argv)}`: the four existing kinds keep a pure
  suffix-strip deriver (unchanged), while `.dict` uses a filesystem-probing deriver
  that resolves the companion FASTA relative to the dictionary's **own parent**
  directory (absolute-safe), tolerates a leading `file://` scheme some GATK builds
  print, and gives up honestly with `index_unresolvable` when no companion exists —
  never guessing a build target. The detector gained a **narrow** sequence-dictionary
  branch: GATK's wording is *"…Fasta dict file …/ref.dict … does not exist…"*, and
  `does not exist` is deliberately **not** in the generic missing-file keyword set,
  so the branch requires both a `.dict` token **and** an absence phrase — keeping a
  genuine wrong-reference/contig mismatch (a different, deferred failure class) from
  being misread as a buildable missing dict. A new **build-once-per-path** guard
  bounds the loop: an index path already built this run is not rebuilt, so a
  wrong-reference masquerading as a missing dict gives up after one build instead of
  burning the retry budget on identical rebuilds (a tightening that applies to every
  index kind). A failed `samtools dict` (non-zero exit) still gives up with
  `index_build_failed`; the verdict reduction and the near-zero false-pass guarantee
  are unchanged. One `missing-index-dict` golden case joins the detector corpus
  (detector eval stays 100%). Local, deterministic, no raw-read egress (the dict is
  built from a local FASTA on the user's compute); fully covered by injected
  builder/executor fixtures — no real `samtools`/GATK/nf-core run in CI. **Deferred
  (unchanged):** the BAM/CRAM form of `.csi`, directory-shaped STAR/BWA indexes,
  stale-index detection, and the C2 reference/build-*mismatch* repair (wrong
  reference, not a buildable missing dict).

## [0.7.0] - 2026-06-29

### Added

- Pre-flight reference-consistency check (capability C5, slice 2 — the mismatch
  detector that the v0.6.0 reference-identity *capture* slice was groundwork for): a
  `contig run` on real data with an explicit `--fasta`/`--gtf` is now refused before
  launch when the FASTA and GTF use **disjoint contig naming** (the notorious `chr1`
  in the FASTA vs `1` in the GTF), which otherwise runs to "success" and silently
  produces an empty count matrix that passes structural QC. The new
  `verification`-adjacent `reference_check` module parses the FASTA `>` headers and
  the GTF column 1 (both gzip-transparent, streamed) and applies a **disjoint-only**
  rule: a mismatch is reported only when the two contig-name sets are both non-empty
  and share *no* element — any overlap (including a GTF that is a strict subset of the
  FASTA, e.g. a partial/scaffold reference) passes, and an empty/unparseable file is
  treated as uncomparable and passes, so the check never produces a false refusal.
  The message names a deterministic sorted sample of each side and the `chr`-prefix
  asymmetry. The gate lives at the single launch chokepoint (`_dispatch_run`), so it
  protects both the CLI and the dashboard (which spawns the CLI); iGenomes
  (`--genome KEY`) runs carry no local files and skip cleanly. An honest escape hatch,
  `--allow-reference-mismatch`, proceeds anyway (still printing the warning) and is
  recorded in the launch manifest so `rerun`/`resume` reproduce the original intent
  faithfully (legacy manifests default to off). Local, deterministic, no network, no
  raw-read egress; fully covered by synthetic `tmp_path` fixtures (no nf-core run in
  CI). **Deferred:** the harder sample-data-vs-reference assembly-signature comparison
  (raw FASTQ has no contig naming and the finished bundle carries no aligned BAM),
  known-sites/BED-vs-reference consistency, GTF annotation-version resolution, seeding
  a `reference_mismatch` corpus class, and the C2 reference/build-mismatch *repair*
  this detector now feeds.

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

[0.10.0]: https://github.com/haqaliz/contig/releases/tag/v0.10.0
[0.9.0]: https://github.com/haqaliz/contig/releases/tag/v0.9.0
[0.7.0]: https://github.com/haqaliz/contig/releases/tag/v0.7.0
[0.6.0]: https://github.com/haqaliz/contig/releases/tag/v0.6.0
[0.1.0]: https://github.com/haqaliz/contig/releases/tag/v0.1.0
