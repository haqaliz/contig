# Changelog

All notable changes to Contig are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims for
[semantic versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

### Added

- **Walltime-informed scaling for the `time_limit` self-heal** (capability C2, self-heal
  breadth — the symmetric walltime follow-on to v0.19.0's peak-RSS OOM memory scaling).
  When a task is killed for exceeding its wall-clock limit, the retry is no longer a blind
  `time × 2` guess: the engine parses the run's **own partial `trace.txt`** at heal-decision
  time and sizes the retry from the **longest observed `realtime`** across the trace rows —
  `target = ceil(max_realtime_sec / 3600 × 1.5)` hours (new pure
  `resource_sizing.realtime_informed_time_h`, mirroring `peak_informed_memory_gb`), threaded
  through a new `apply_patch(observed_target_h=…)` seam while the **72 h ceiling clamp, the
  never-shrink rule, and the `gave_up_at_ceiling` give-up stay exactly as before**.
  - **Honest about a weaker signal than memory — floored at blind, never worse.** Unlike an
    OOM'd task's `peak_rss` (a real high-water mark ≈ the task's demand), a walltime-killed
    task **never finished**, so its `realtime` is only a **lower bound** on the time needed
    and is **hard-censored at ≈ the current limit**. So the observed override is **floored at
    the blind `× 2` bump** (`max(observed, blind)`) — the one intentional asymmetry vs the
    memory branch — which means it **ties blind in the common censored case** and only rises
    in the **tail** (the trace carries a `realtime` above the current limit: a higher-label
    sibling process that also timed out, a mis-classified `time_limit`, or a grace/staging
    overrun). It is thus **never worse than today's behavior**, and a trace-less run, a
    snakemake run, or a dash/0 `realtime` degrades to the unchanged blind `× 2` fallback.
  - **Shipped mostly as a field instrument.** Every walltime heal records the observed
    `realtime`, the applied (post-floor/clamp) walltime, the evidence tier, and whether it
    **beat or tied blind** into `RepairStep.detail` — the instrument that will show, in the
    field, how often a walltime kill even carries a usable signal. **Revisit trigger:** after
    ≥ 20 observed walltime heals, if the tail case fires in < ~20% of them, do **not** invest
    further in walltime sizing (no sibling-rescue tier, no calibration) — redirect C2 effort
    to a new failure class. The decision trigger is a deliverable alongside the code.
  - **Deferred (deliberately):** the **same-process sibling rescue** (borrowing an uncensored
    sibling task's `realtime` when the killed row's own is censored) — unreachable while the
    trace parser sets `process == name` for every row, exactly as for the memory slice's
    deferred sibling rung; and factor/ceiling calibration on real data. Memory-only path
    untouched; Nextflow-only; no verdict / exit-code / `FailureClass` / model / parser
    change. Local, deterministic, no raw-read egress; fully covered by injected
    trace/executor fixtures (no real pipeline run in CI).

## [0.19.0] - 2026-07-06

### Added

- **Peak-RSS-informed memory scaling for the OOM self-heal** (capability C2, self-heal
  breadth — the "peak-RSS-informed scaling" slice deferred by v0.5.0's bounded-ceiling
  work). When a task is OOM-killed (`exit 137`), the retry is no longer a blind
  `memory × 2` guess: the engine now parses the run's **own partial `trace.txt`** at
  heal-decision time and sizes the retry to the failed task's **observed peak resident
  memory** — `target = ceil(peak_rss_mb / 1024 × 1.5)` binary GB — so a task that needs
  ~5× lands in **one** retry instead of climbing 2×→4×→8× and exhausting the bounded
  retry budget or the 128 GB ceiling first. A new pure `resource_sizing.peak_informed_memory_gb`
  computes the target from the trace (joining the `exit==137` task events to their
  `TaskResource` rows; multiple OOM'd tasks size off the **max** peak, since
  `process.resourceLimits` is global), and `apply_patch` gained an `observed_target_gb`
  seam that overrides the multiplier while the **ceiling clamp, the never-shrink rule, and
  the `gave_up_at_ceiling` give-up stay exactly as before**. Every heal records the
  observed peak, the sizing, and the evidence tier into `RepairStep.detail` (surfaced in
  `repair_history` and `repair_progress.jsonl`) — the instrument that will show, in the
  field, how often real OOM'd tasks even carry a usable `peak_rss`.
  - **Honest two-tier ladder (not the three-tier originally speced).** (a) the OOM'd
    task's own observed peak, else (b) **unavailable → today's blind `× 2` fallback runs
    unchanged**, so a signal-killed task whose trace row reports a `-`/0 peak, a
    trace-less run, or a snakemake run never regresses. A `peak_rss` of 0/absent is
    treated as **unknown, never "0 MB."** A sized target below the current request is
    expected (never-shrink holds the current value), so the retry is never *worse* than
    before.
  - **Deferred (deliberately, with a named blocker):** the **same-process sibling rescue**
    (borrowing a surviving shard's peak when the killed row's own peak is a dash) was cut
    rather than shipped dormant — it can never fire while the trace parser sets
    `process == name` for every row, so it first needs a coarse `process` column in the
    parser (which has a `progress.py` blast radius). Also deferred: **walltime** sizing to
    observed `realtime`, and folding the observed peak into the `FailureCase` corpus
    schema (telemetry rides in `RepairStep.detail` for now). Memory-only, Nextflow-only,
    no verdict / exit-code / `FailureClass` change. Local, deterministic, no raw-read
    egress; fully covered by injected trace/executor fixtures (no real pipeline run in CI).

## [0.18.0] - 2026-07-06

### Added

- **Per-contig alias harmonization for reference/build-mismatch repair** (capability
  C2, self-heal breadth — a follow-on of v0.9.0's chr-prefix GTF harmonizer). The
  reference pre-flight harmonizer is widened from pure `chr`-prefix add/strip to a
  **general per-contig rename map** driven by a **lookup against the actual FASTA
  contig set**: a new alias equivalence table treats the mitochondrion `M`↔`MT` as
  universal (a code constant) and consults a small **curated, extensible GRCh38
  scaffold table** (`src/contig/data/contig_aliases.tsv`, sourced from UCSC
  chromAlias) for common unplaced scaffolds; the loader fails loud on malformed or
  duplicate rows. `plan_harmonization` now resolves each GTF contig to whichever
  spelling actually exists in the FASTA (prefix variants ∪ alias group ∩ FASTA), so
  it handles the canonical UCSC-FASTA (`chrM`) + Ensembl-GTF (`MT`) case; the
  **residual case where the autosomes already match but the mito differs**
  (previously silently skipped because harmonization was gated behind the
  disjoint-only detector); pure-alias mismatches; and a hybrid FASTA (`chrMT`) via
  FASTA-lookup. It still **refuses (no harmonization) a genuine wrong-assembly**
  (disjoint after mapping) and now also **refuses a non-injective map** (two GTF
  contigs that would collapse onto one FASTA target) — never a silent contig merge.
  The CLI pre-flight is now driven by the plan itself (rather than the disjoint-only
  detector), with a strengthened overlap-increase post-check; `--allow-reference-
  mismatch` still harmonizes-first; `rerun`/`resume` continue to re-derive the plan
  from the original GTF path stored in the manifest, unchanged. **Honesty:** the
  WARN-level `reference_harmonized` breadcrumb now enumerates any GTF contigs that
  could not be matched to the FASTA and were left as-is, so a partial harmonization
  is visible rather than a relocated silent failure. Provenance-only eval capture —
  no new `reference_mismatch` `FailureClass` or detector-corpus case, matching
  v0.9.0. Local, deterministic, no raw-read egress; fully covered by synthetic
  FASTA/GTF fixtures (no real nf-core run in CI). **Deferred:** exhaustive
  per-assembly scaffold-table completeness (the shipped table is a seed, not
  exhaustive); network fetch of chromAlias; rewriting the FASTA (only the GTF is
  ever rewritten); and the sample-data-vs-reference assembly-signature comparison.

## [0.17.0] - 2026-07-05

### Added

- **Held-out regression guard for the diagnosis detector** (capability C6, eval
  flywheel — slice 1). A new frozen `src/contig/data/detector_corpus_holdout.jsonl`
  (12 newly authored `FailureCase`s, `source="holdout:synthetic"`, disjoint `case_id`s
  from the training corpus) is scored by a new `contig eval-guard` command, which
  reuses the shipped `evaluate_detector`/`get_detector` machinery (no reimplemented
  scoring) and **fails the build** (`exit 1`, `REGRESSION: ...`) when the current
  detector's held-out accuracy drops below a committed baseline
  (`src/contig/data/holdout_baseline.json`, one `EvalSnapshot` pinning `corpus_sha`,
  `detector`, and `contig_version` so a drop is attributable to a detector change vs
  a held-out-set change) minus a small float tolerance. `--update-baseline`
  (re)freezes the baseline as a deliberate, reviewed act — never an automatic side
  effect of running the guard. The guard also warns loudly (non-failing, stderr) on
  a held-out-sha mismatch (set changed but baseline not refreshed) or a
  detector-mismatch (baseline measured with a different detector than the one being
  guarded), and nudges (`consider --update-baseline`) when accuracy improves beyond
  tolerance. The committed baseline is honestly **83.3% (10/12)**: two held-out
  classes, `qc_anomaly` and `no_progress`, are currently **structurally unreachable**
  by `diagnose_failure` (no rule branch emits them yet) — this is deliberate, not a
  bug, so the guard has real headroom to catch the day those rules are added.
  **Honest scope:** this slice guards the **labeled failure-class detector corpus
  only**. Folding in the unlabeled C1 concordance / C3 plausibility corroboration
  signals (no ground-truth labels, so not classification-accuracy scoreable) and
  repair-loop (whole self-heal) accuracy into the same guard are **deferred**
  follow-on slices. The guard now runs in CI (`.github/workflows/ci.yml`, after the
  pytest step), so a detector or corpus change that regresses held-out accuracy fails
  the build. Local, deterministic, no network; `llm` is never the guard's default
  detector.

## [0.16.0] - 2026-07-05

### Added

- **Apache-2.0 license.** A top-level `LICENSE` (Apache License 2.0) and `NOTICE`
  file, `license`/`license-files`/`classifiers` in `pyproject.toml`, and a
  `[project.urls]` block (Homepage, Repository, Documentation, Issues, Changelog)
  so the PyPI page and GitHub license chip render correctly. `readme = "README.md"`
  so `pip install contig` users see the full project description on PyPI.
- **Real demo GIF** (`assets/contig-demo.gif`): an offline terminal capture of the
  run → self-heal (OOM → resource patch) → `PASS` verdict → signed `verify` loop,
  featured as the README hero (served from an absolute raw URL so it also renders
  on PyPI).

### Changed

- **Honest launch positioning.** Reconciled the project status across README badge,
  README body, and `CLAUDE.md` to "MVP · early access (v0.15.0)"; added a dynamic
  release badge and an Apache-2.0 license badge.
- **Supported-analyses table** now carries a `Maturity` column (RNA-seq validated
  end-to-end; the other assays wired with QC packs) and lists the somatic
  (tumor–normal) assay, matching the registry.
- **Quickstart** leads with the installed `contig …` form (matching the install
  section) and points source-checkout users to the `uv run` prefix once.
- `eval-detector --help` now mentions the env-gated `llm` detector; the illustrative
  pipeline revision in `docs/USAGE.md` no longer hardcodes a version that can drift.

### Removed

- Internal go-to-market material from the public tree: `demo/OUTREACH.md`,
  `demo/WHAT_THIS_PROVES.md`, the internal `root@vpn` validation-host references in
  two planning docs, and the "money moment on camera" framing in `demo/DEMO.md`.

## [0.15.0] - 2026-07-05

### Added

- **Somatic Strelka2-vs-Mutect2 cross-tool concordance** (capability C1 for the somatic
  assay — the second-caller concordance hook deferred by the v0.14.0 VAF slice). A somatic
  (tumor–normal) run's verdict now gains an independent **cross-tool concordance axis**,
  corroborating the run's **Mutect2** call set against the **Strelka2** call set that the
  *same* `nf-core/sarek` run already emitted (`--tools strelka,mutect2`) — so unlike germline
  concordance there is **no second caller to run and no user-supplied input**; both VCFs are
  already in the bundle. A new `verification/somatic_concordance.py` emits one
  `kind="concordance"` **`somatic_site_overlap`** check: the Jaccard overlap
  (`|A∩B| / |A∪B|`) of the two callers' **PASS** call sites, keyed on `(CHROM, POS, REF,
  ALT)`, where PASS means `FILTER ∈ {"PASS", "."}` (FILTER-aware parsing, so noisy filtered
  candidate calls are excluded). It is **sample-agnostic** — it reads no genotype or tumor
  column, sidestepping the fact that Strelka2 somatic SNVs carry no conventional per-sample
  `GT` (the germline `genotype_concordance` metric deliberately does **not** transfer).
  - **Auto-wired** into `_discover_qc` gated to `assay == "somatic_variant_calling"`,
    alongside (and independent of) the VAF-plausibility block: the Mutect2 VCF is located by a
    `mutect2` path component below the run dir (as the VAF slice already does) and the Strelka2
    VCF by a symmetric `strelka` component, with Strelka's split `*.somatic_snvs.vcf.gz` +
    `*.somatic_indels.vcf.gz` **unioned** into one call set.
  - **Corroboration only:** at most WARN (below a `0.90` overlap default), **never FAIL**, and
    structurally incapable of changing the verify exit code or promoting UNVERIFIED to PASS.
    Below a minimum of 10 union PASS sites the check is **UNVERIFIED, never a false pass**.
  - **Honest on ambiguity:** a single caller present (mutect2-only / strelka-only) skips
    cleanly; a multi-tumor-pair layout — or two callers whose single tumor–normal pair
    directories **differ** — yields one honest UNVERIFIED rather than corroborating an
    arbitrary or unrelated pair.
  - Deterministic, local, no raw-read egress, no tool execution; research-use only (a somatic
    verdict means "ran correctly and reproducibly," never a cancer diagnosis). Built
    test-first with synthetic two-caller VCF fixtures (no real nf-core/sarek run in CI).
    **Deferred:** Strelka2-native tumor-VAF agreement, FAIL severity until the overlap band is
    calibrated on real tumor–normal data, and an explicit `contig verify` concordance flag/echo
    (the auto-in-verdict surface covers slice 1).

## [0.14.0] - 2026-07-04

### Added

- **Somatic VAF-distribution biological-plausibility verification** (capability C4
  follow-on — the biological verdict for the somatic assay whose v0.13.0 slice was
  honestly structural-only). A somatic run now gains a biological axis alongside its
  structural checks, computed deterministically from the **tumor column of the run's
  Mutect2 VCF** by a new `verification/somatic_plausibility.py` and wired into
  `_discover_qc` gated to `assay == "somatic_variant_calling"`. Three checks:
  - `median_vaf` — median tumor variant allele fraction over biallelic records, read from
    the FORMAT `AF` (Mutect2 allele fraction) when present, else derived from `AD_alt/DP`
    (guarding `DP==0`), else the record contributes no VAF. The tumor sample is identified
    by the `##tumor_sample=` header mapped to its `#CHROM` column (never a guessed column).
    A somatic set pinned near VAF≈1.0 (germline leakage) or exactly ~0.5 (mis-paired
    normal) drifts out of the band. Multiallelic sites are excluded; indels are included.
  - `somatic_variant_count` — number of considered (biallelic) somatic records, with a
    deliberately wide band (target type varies by orders of magnitude) to catch only a
    grossly failed call set.
  - `pon_applied` — a panel-of-normals presence check keyed off the GATK command header:
    present with `--panel-of-normals`/`--pon` → PASS; header present without it → WARN;
    no recognizable `GATKCommandLine` header → UNVERIFIED (cannot tell).
  Both metric bands are **WARN-capped** (uncalibrated engineering defaults, no `fail_*`),
  in a new `SOMATIC_PLAUSIBILITY_PACK` that is imported directly (not registered in
  `_RULE_PACKS`). Every uncomputable path — no derivable VAF, an unidentifiable tumor
  column, a missing GATK header — yields **UNVERIFIED (never a false pass)**, mirroring the
  germline Ti/Tv slice. The `*.vcf.gz` locator selects the Mutect2 VCF by a path
  **component** below the run dir (so a "mutect2" in an ancestor workspace/run-id name
  cannot mis-select a Strelka VCF); if VCFs exist but none is Mutect2, one honest
  UNVERIFIED is emitted; if no VCF exists at all the gate skips silently (structural QC
  already covers a missing output). A somatic verdict remains "ran correctly and
  reproducibly," research use — never a cancer diagnosis. Additive to the verdict only: no
  detector/`FailureClass`, model, or persisted-record change; deterministic, no raw-read
  egress; fully covered by synthetic two-sample VCF fixtures (no real nf-core/sarek run in
  CI). **Deferred:** Strelka2-native VAF (tier-count derivation — non-Mutect2 VCFs degrade
  to UNVERIFIED), the Strelka2-vs-Mutect2 somatic concordance hook (C1), FAIL severity
  until the bands are calibrated on real data, and a cross-column swapped-pair smell test
  (the residual case where the `##tumor_sample=` header is present but mislabeled).

## [0.13.0] - 2026-07-04

- **Somatic (tumor–normal) variant calling assay** (capability C4 — a whole new assay
  end to end, the natural extension of the shipped germline sarek assay). A somatic goal
  now routes to a new `somatic_variant_calling` assay served by the same curated
  `nf-core/sarek` pipeline (`@3.5.1`) in somatic mode, with intake → plan → run → verify
  wired through the existing engine. Concretely:
  - **Explicit, persisted assay** (resolves the sarek pipeline-string collision): `contig
    run --assay <key>` carries the run's assay as a first-class input that **overrides**
    the legacy pipeline-derived lookup, is persisted on the `RunRecord` and the
    `launch.json` reproduce sidecar, and is re-applied by `rerun`/`resume`. Because two
    assays now share one pipeline (germline vs somatic sarek), the run no longer derives
    its assay from the pipeline string alone. The legacy `assay_for_pipeline` derivation
    is preserved as the fallback, so every existing run and every already-shipped bundle
    (no persisted assay) resolves exactly as before — a backward-compatible change.
  - **Somatic goal routing**: a `somatic_variant_calling` registry entry plus a
    `somatic`/`tumor`/`tumour`/`tumor-normal` keyword group ordered ahead of germline, so
    "somatic tumor/normal variant calling" routes to the somatic assay while germline
    goals still route to `variant_calling` (non-collision pinned by test).
  - **Sarek tumor/normal sample-sheet pre-flight**: a sarek-shaped sample sheet
    (`patient, sample, status, lane, fastq_1, fastq_2`) is validated for the paired
    structure at the launch chokepoint — `status ∈ {0,1}`, at least one patient with both
    a normal (0) and a tumor (1) row, multi-tumor/relapse allowed, and an unpaired-tumor
    or tumor-only sheet refused with a message pointing at germline. Somatic-gated;
    germline/RNA-seq sample-sheet validation is unchanged.
  - **Somatic launch**: a declarative per-assay `PipelineEntry.default_params` seam
    injects `--tools strelka,mutect2` for the somatic assay (sarek infers somatic mode
    from the paired sheet + somatic-capable callers), captured for reproduce; all other
    assays inject nothing and are unchanged. This proves the somatic launch command is
    correctly assembled — **not** that a real Mutect2 somatic run completes without a
    panel-of-normals / germline resource (that reference wiring, and VAF-distribution
    plausibility, panel-of-normals checks, and the second-caller Strelka2-vs-Mutect2
    concordance hook, are **deferred** to follow-on slices).
  - **Somatic verification**: a `somatic_variant_calling` structural output manifest
    (required + gzip-intact `*.vcf.gz`, mirroring germline) is added, evaluated at
    `contig verify` time; the methods paragraph labels somatic tumor–normal runs
    (research use). Live-run verification stays structural for now (no somatic rule pack
    or plausibility yet), so a somatic verdict is honestly structural-only and never a
    false pass.
  - Research-use only, on the user's compute (no raw-read egress); a somatic verdict
    means "ran correctly and reproducibly," never a cancer diagnosis. Built test-first
    across seven slices with synthetic fixtures — no real nf-core/sarek run in CI.

## [0.12.0] - 2026-07-02

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

[0.19.0]: https://github.com/haqaliz/contig/releases/tag/v0.19.0
[0.18.0]: https://github.com/haqaliz/contig/releases/tag/v0.18.0
[0.14.0]: https://github.com/haqaliz/contig/releases/tag/v0.14.0
[0.13.0]: https://github.com/haqaliz/contig/releases/tag/v0.13.0
[0.12.0]: https://github.com/haqaliz/contig/releases/tag/v0.12.0
[0.10.0]: https://github.com/haqaliz/contig/releases/tag/v0.10.0
[0.9.0]: https://github.com/haqaliz/contig/releases/tag/v0.9.0
[0.7.0]: https://github.com/haqaliz/contig/releases/tag/v0.7.0
[0.6.0]: https://github.com/haqaliz/contig/releases/tag/v0.6.0
[0.1.0]: https://github.com/haqaliz/contig/releases/tag/v0.1.0
