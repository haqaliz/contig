# Contig: Engine Capability Roadmap (next 6 months)

The dashboard roadmap in [`FEATURES.md`](../../FEATURES.md) is largely shipped.
This document is the next layer of work: the **scientific and execution
capabilities of the engine itself**, the things that make Contig *do more* as a
genomics and bioinformatics tool. It is a sequenced backlog so we can go through
it one capability at a time.

Everything here stays on the Layer-2 side of the wedge (run, self-heal, verify,
reproduce). Nothing here authors pipelines from English (Layer 1), and nothing
here needs wet-lab or clinical credentials. See the guardrails at the end.

---

## How to read this

- Capabilities are labelled **C1 ... C6** in build order. Each is independently
  shippable and leaves the engine more capable than before.
- **Time windows** (months 1 to 6) are guidance for sequencing, not commitments.
  Real demand-pull from a design partner reorders this freely.
- Every capability is built **test-first** (the repo's standing discipline): each
  one lists its acceptance as a failing test we write before the code.
- Every capability names the **eval data it captures**, because the accumulating
  failure-and-verification corpus is moat #2 and must compound with each feature.

### The single framing

The moat is the verified verdict and the self-heal loop. Each capability below
either makes the verdict *more trustworthy* (concordance, biological plausibility,
reference integrity), *recovers more failures autonomously* (self-heal breadth,
auto resource-scaling), or *widens what we can verify at all* (a new assay). A
better base model should make each of these stronger, never redundant.

---

## C1. Cross-tool concordance verification  ·  SHIPPED v0.2.0 (germline) + RNA-seq slice (Unreleased) + somatic slice (Unreleased)

**Shipped (slice 1) in v0.2.0.** The verdict gained a third axis alongside QC
thresholds and structural checks: `verification/concordance.py` computes a
deterministic `genotype_concordance` (over shared sites) plus a `site_overlap`
check, both `kind="concordance"`, surfaced via `contig verify --concordance-vcf
<vcf>` and grouped in the text/HTML reports and the dashboard QC panel. Concordance
is at most WARN (corroboration, not ground truth), never changes the verify exit
code, and reports `unverified` (never a false pass) when the two call sets share no
comparable site.

**Shipped (RNA-seq slice — Unreleased).** The concordance axis now extends to bulk
RNA-seq quantification via a new `verification/count_concordance.py` and `contig
verify --concordance-counts <matrix>`: the run's own gene-count matrix is corroborated
against a user-supplied second matrix with a per-gene **Spearman rank correlation**
(`spearman_concordance`, WARN below 0.90), a **fraction-agreeing** check (share of
shared genes within a 10% relative tolerance, WARN below 0.90), and an
**informational `gene_overlap`** (never WARN — a subset-annotation second matrix
legitimately overlaps poorly). Same contract as germline: at most WARN, never changes
the verify exit code, `unverified` (never a false pass) below 10 shared genes;
mutually exclusive with the germline flags. The Spearman and the gzip-transparent,
tolerant count-matrix parser are hand-rolled stdlib (no scipy/numpy added). **Deferred
to a follow-on slice:** auto-running a second caller/quantifier (today the user
supplies the second call set/matrix — mirrors the germline `--concordance-auto`
follow-on in v0.4.0), single-cell concordance, a dashboard "corroborated by" line, and
FAIL-severity once thresholds are calibrated on real data.

**Shipped (somatic slice — Unreleased).** The concordance axis now extends to the somatic
(tumor–normal) assay, and — uniquely — with **no user-supplied input and no second tool run**:
a single `nf-core/sarek` somatic run already emits both a Mutect2 and a Strelka2 call set
(`--tools strelka,mutect2`), so a new `verification/somatic_concordance.py` corroborates them
directly. It emits one `kind="concordance"` **`somatic_site_overlap`** check — the Jaccard
overlap of the two callers' **PASS** call sites keyed on `(CHROM, POS, REF, ALT)` (FILTER-aware:
`FILTER ∈ {"PASS", "."}`), **sample-agnostic** because Strelka2 somatic SNVs carry no
conventional per-sample `GT` (the germline `genotype_concordance` metric deliberately does not
transfer). It is **auto-wired** into `_discover_qc` gated to `assay ==
"somatic_variant_calling"` — the Mutect2 VCF located by a `mutect2` path component, the Strelka2
VCF by a symmetric `strelka` component with its split `*.somatic_snvs`/`*.somatic_indels` files
unioned. Same contract as the other slices: at most WARN (0.90 default), never FAIL, never
changes the exit code, **`unverified` (never a false pass)** below 10 union PASS sites; a
single-caller run skips, and a multi/mismatched tumor-pair layout yields one honest
`unverified` rather than an arbitrary compare. **Deferred to a follow-on slice:** Strelka2-native
tumor-VAF agreement, FAIL severity once the overlap band is calibrated on real data, and an
explicit `contig verify` concordance flag/echo (auto-in-verdict covers slice 1).

The original framing, for reference: today the verdict rests on QC thresholds,
structural checks, and (where a reference run exists) benchmarking against a
known-good prior run. Concordance adds an independent axis: run a **second,
independent tool** on the same input and treat agreement as corroboration of the
result. Disagreement is surfaced honestly, never hidden.

This is distinct from the shipped `contig benchmark` (which compares a run to a
designated *reference run* of the same pipeline). Concordance compares **two
different tools on the same data within one analysis**, so it catches tool-specific
error even when no reference run exists.

**Why it is moat.** No incumbent issues a correctness verdict at all, let alone a
cross-tool one. Concordance is a defensible verification primitive, it produces
rich evaluation data (agreement distributions per assay), and it gets better as
models get better at adjudicating *why* two tools disagree.

**What we build (per assay):**
- Germline variants: a second caller (for example bcftools or DeepVariant against
  the primary GATK HaplotypeCaller call set), reported as genotype concordance,
  Ti/Tv ratio agreement, and F1 of one call set against the other.
- RNA-seq quantification: a second quantifier (for example Salmon against
  STAR plus featureCounts, or kallisto), reported as per-gene rank correlation
  (Spearman) and the fraction of genes agreeing within a tolerance.
- Single-cell RNA-seq: cell-count and cluster-stability agreement across two
  quantifiers (for example STARsolo against alevin-fry).
- A new `verification.concordance` module and a `ConcordanceResult` model
  (metric, value, tolerance, status, the two tools compared), wired into
  `run_qc` and the verdict reduction. Concordance can move a verdict to WARN; it
  never alone promotes UNVERIFIED to PASS.
- Surfaced on the verdict card and in `contig show` as a named "corroborated by"
  line listing the metric and the second tool.

**Acceptance (test-first):** synthetic fixtures of two call sets / two count
matrices. A concordant pair yields a PASS concordance check with the metric
reported; a deliberately divergent pair yields WARN with the exact metric and the
two tool names in the message. Deterministic, no network.

**Eval data captured:** concordance metric per run and assay becomes a reference
distribution; runs whose tools disagree are flagged into the corpus as
verification-divergence cases.

**Dependencies:** none blocking. Reuses the existing QC and verdict plumbing.

---

## C2. Self-heal breadth plus auto resource-scaling  ·  months 2 to 3

**Shipped (resource-aware slice):** OOM/walltime retries now scale only up to a
bounded absolute ceiling (defaults 128 GB / 72 h) and give up honestly with a
`gave_up_at_ceiling` outcome + a `RepairStep.detail` message when the resource is
already at its cap; a bounded retry budget that provably terminates.
**Shipped (missing-index slice):** a `missing_index` failure now actually builds the
missing index and retries through a new injectable `IndexBuilder` seam — first a FASTA
`.fai` via `samtools faidx`, then (follow-on) the rest of the **single-file** family:
`.bai` via `samtools index`, `.tbi` via `tabix -p vcf`, and `.csi` via `bcftools index`,
dispatched by an extension→command table. Each records `built_index_and_retried` and
gives up honestly (`index_unresolvable` / `index_build_failed`) on an unparseable path or
a failed build — never a false pass; one golden corpus case is seeded per kind.
**Shipped (`.dict` slice — Unreleased):** a missing GATK **sequence dictionary** (`ref.dict`)
is now built with `samtools dict -o <ref.dict> <ref.fa>` and retried — the first kind
whose build input is **not** the indexed path minus its suffix (the dictionary is built
from a *companion* FASTA), so the table was generalized to `{ext: (derive_source,
build_argv)}`: the four prior kinds keep a pure suffix-strip deriver, while `.dict` uses a
filesystem-probing deriver that resolves the companion (`.fasta`/`.fa`/`.fasta.gz`/`.fa.gz`)
relative to the dictionary's own parent dir (absolute-safe), tolerates a `file://` URI, and
returns `index_unresolvable` when no companion exists. The detector gained a **narrow**
sequence-dictionary branch keyed on a `.dict` token **plus** an absence phrase (GATK's
"does not exist" is deliberately not in the generic missing-file set), so a wrong-reference
contig mismatch is not misread as a buildable missing dict. A new **build-once-per-path**
guard bounds the loop so a wrong-reference masquerade gives up after one build rather than
exhausting the retry budget. One `missing-index-dict` golden case is seeded.
**Shipped (chr-prefix GTF harmonization slice — Unreleased):** the reference/build-mismatch
**repair** for an unambiguous `chr`-prefix asymmetry (FASTA `chr1…` vs GTF `1…`, or vice
versa) now ships at pre-flight. `plan_harmonization` (a pure decision function) checks that
one side is entirely chr-prefixed while the other is entirely bare, and that after a uniform
`chr`-add or `chr`-strip the two contig sets intersect; only then does `harmonize_gtf`
stream-rewrite column 1 of the GTF into `<run_id>/harmonized/<name>` (user's original file
untouched) and allow the run to proceed. A wrong-assembly case — where the transform still
leaves two disjoint sets — is still refused. The decision is recorded in the launch manifest
(`harmonized_reference: bool`) and in `ReferenceIdentity` (`.harmonized`,
`.harmonized_direction`); `rerun`/`resume` re-derive it by re-entering `_dispatch_run` with
the original GTF path (no scratch path baked into the manifest). A WARN-level
`reference_harmonized` QC breadcrumb is appended in `_finalize` so the rewrite is visible in
every verdict surface. Built on top of the C5 mismatch detector (v0.7.0), which detected and
refused this class of mismatch; it now also repairs it.
**Shipped (per-contig alias harmonization slice — Unreleased):** the harmonizer is widened
from pure `chr`-prefix add/strip to a **general per-contig rename map** driven by a lookup
against the actual FASTA contig set. Mitochondrion `M`↔`MT` is treated as universal (a code
constant); a small curated, extensible GRCh38 scaffold table
(`src/contig/data/contig_aliases.tsv`, sourced from UCSC chromAlias) covers common unplaced
scaffolds, with the loader failing loud on malformed/duplicate rows. `plan_harmonization` now
resolves each GTF contig to whichever spelling actually exists in the FASTA (prefix variants ∪
alias group ∩ FASTA), so it also handles the case where the autosomes already match but the
mito spelling differs — previously silently skipped because harmonization was gated behind
the disjoint-only detector. A non-injective rename map (two GTF contigs collapsing onto one
FASTA target) is refused, never a silent contig merge; a genuine wrong-assembly is still
refused. The CLI pre-flight is now driven by the plan itself rather than the disjoint-only
detector, with a strengthened overlap-increase post-check. The `reference_harmonized`
breadcrumb now enumerates any GTF contigs left unmatched, so a partial harmonization stays
visible. Provenance-only eval capture, matching v0.9.0 — no new `reference_mismatch`
`FailureClass` or detector-corpus case.
**Shipped (STAR/BWA directory-index slice — Unreleased):** the missing-index family now
extends past single-file indexes to a **directory-shaped aligner index**. A missing/aborted
STAR index (`could not open genome file … genomeParameters.txt`) or a version-incompatible
one (`Genome version … is INCOMPATIBLE with running STAR version`) is rebuilt with `STAR
--runMode genomeGenerate` from the run's resolved FASTA(+GTF) into a run-scoped scratch dir
(`<run_id>/healed_index/star`, the user's supplied index never mutated); the retried run is
redirected at the scratch index via `params["star_index"]` and proceeds, recording
`built_index_and_retried`. Bounded to one rebuild per run; honest `index_unresolvable` /
`index_build_failed` give-ups; the STAR genome version is recorded in the repair step; and
`rerun`/`resume` re-derive the heal from the original `fasta`/`gtf` manifest fields (no
scratch path persisted). A classic BWA missing-index failure
(`[E::bwa_idx_load_from_disk] fail to locate the index files`) is now detected and
classified `missing_index` with a golden corpus case, but the **build/redirect is
deferred** — no default supported pipeline invokes classic `bwa index` (sarek defaults to
bwa-mem2; methyl-seq uses bwa-meth), so there is no live redirect target yet.
**Shipped (bwa-mem2 detector slice — v0.11.0):** a bwa-mem2 unreadable/incompatible index
failure (`ERROR! Unable to open the file: <ref>.bwt.2bit.64`) is now **detected** and
classified `missing_index` (previously an opaque `tool_crash`), via a narrow branch
AND-guarded on the bwa-mem2-only `.bwt.2bit.64` sidecar token so it neither over-matches
nor collides with the classic-BWA branch; one golden `missing-index-bwamem2` corpus case
is seeded (detector guard stays 100%). Like classic BWA, the **build/redirect is deferred
with no live trigger**: nf-core/sarek auto-builds a missing bwa-mem2 index, AWS-iGenomes
ships a classic BWA index (not bwa-mem2), and Contig exposes no flag to supply a broken
one — so the failure cannot be produced by a Contig-launched run today. The run ends in an
honest FAIL (`index_unresolvable`), never a false pass.
**Shipped (peak-RSS memory-scaling slice — Unreleased):** the OOM retry is no longer a
blind `memory × 2` guess. On `exit 137` the engine parses the run's **own partial
`trace.txt`** at heal-decision time (resolving the earlier "`resource_usage` is only
populated at finalize" blocker by parsing the trace directly in the loop rather than
waiting for the record) and sizes the retry to the failed task's **observed peak resident
memory** — `ceil(peak_rss_mb / 1024 × 1.5)` binary GB — so a task that needs ~5× lands in
one retry instead of climbing 2×→4×→8× and exhausting the bounded budget or the 128 GB
ceiling first. A new pure `resource_sizing.peak_informed_memory_gb` computes the target
(multiple OOM'd tasks size off the **max** peak, since `process.resourceLimits` is global),
and `apply_patch` gained an `observed_target_gb` seam that overrides the multiplier while
the **ceiling clamp, never-shrink, and `gave_up_at_ceiling` give-up stay unchanged**. The
observed peak, the sizing, and the evidence tier are recorded into `RepairStep.detail`. It
is an **honest two-tier ladder** — the OOM'd task's own observed peak, else **blind `× 2`
fallback** (a signal-killed task reporting a `-`/0 peak, a trace-less or snakemake run
never regresses; a 0/absent peak is treated as *unknown*, never "0 MB"). Memory-only,
Nextflow-only; no verdict/exit-code/`FailureClass` change; test-first with injected
trace/executor fixtures. **Deferred here:** the **same-process sibling-peak rescue** (cut
rather than shipped dormant — the trace parser sets `process == name` for every row, so a
sibling key can never diverge; it needs a coarse `process` column, which has a `progress.py`
blast radius); and folding the observed peak
into the `FailureCase` corpus schema (telemetry rides in `RepairStep.detail` for now).
**Shipped (walltime-scaling slice — Unreleased):** the symmetric follow-on for the
`time_limit` self-heal. A walltime-killed retry is sized from the run's own partial
`trace.txt` to the **longest observed `realtime`** — `ceil(max_realtime_sec / 3600 × 1.5)`
hours (new pure `resource_sizing.realtime_informed_time_h`) — through a new
`apply_patch(observed_target_h=…)` seam, with the 72 h ceiling, never-shrink, and
`gave_up_at_ceiling` give-up unchanged. **Honest about a weaker signal:** unlike an OOM'd
task's `peak_rss` (a real high-water mark), a walltime-killed task never finished, so its
`realtime` is a **censored lower bound ≈ the current limit** — so the observed override is
**floored at the blind `× 2` bump** (`max(observed, blind)`, the one intentional asymmetry
vs the memory branch). It therefore **ties blind in the common censored case** and only
rises in the **tail** (a trace `realtime` above the current limit: a higher-label sibling
that also timed out, a mis-classified `time_limit`, grace overrun) — **never worse than
today**. Shipped mostly as a **field instrument**: `RepairStep.detail` records the observed
`realtime`, the applied walltime, the tier, and beat-vs-tied-blind, with a committed
**revisit trigger** (≥ 20 heals, tail < ~20% → stop investing here, redirect C2). Two-tier
ladder (observed `realtime` → blind fallback); memory path untouched; Nextflow-only; no
verdict/exit-code/`FailureClass` change; test-first with injected fixtures. **Deferred:**
the same-process sibling-`realtime` rescue (same `process == name` blocker as memory) and
factor/ceiling calibration on real data.
**Deferred to later C2 slices:** bwa-mem2 **build/redirect** (detection shipped v0.11.0;
build blocked until a live trigger exists) and the classic-vs-mem2 aligner-mismatch heal;
classic-BWA index build/redirect (needs a supported `bwa index` target, e.g. sarek
`--aligner bwa-mem`); a corrupt/partial STAR index signature; the still-missing single-file
index kind (the BAM/CRAM form of
`.csi`) plus stale-index detection on the same seam; and the wider failure catalog — the
assembly-signature form of reference/build mismatch (no sample-side contig signal in raw
FASTQ or finished bundle), exhaustive per-assembly alias-table completeness beyond the
GRCh38 seed, known-sites/GTF-version consistency, a runtime `reference_mismatch`
detector-corpus case, format conversion, and pin conflict.

Expand the failure-mode catalog and repair strategies well past the current set,
and make repairs resource-aware. This is the most directly "gets better with
better models" surface and the richest corpus fuel.

**Why it is moat.** Unattended-completion rate is the headline reliability metric
(ROADMAP Phase 1). Every new recovered failure mode both raises that number and
adds a golden corpus case that improves the detector for everyone.

**What we build:**
- Resource-aware retry: out-of-memory detected, retry the failed process with
  scaled memory within a bounded ceiling; walltime exceeded, scale time; record
  the scaling as a structured patch with its rationale and expected signal.
- New repair strategies, each with a `FailureClass`, a detector corpus seed, and
  an injected-failure fixture: missing or stale index (build it), reference and
  genome-build mismatch (detect by contig-naming and assembly signature, propose
  the matching reference), input-format issues (detect and convert, for example
  bgzip or CRAM and BAM), container or dependency pin conflict (repin to a known
  good digest).
- A bounded retry budget so auto-scaling can never loop without converging.

**Acceptance (test-first):** for each new failure mode, an injected-failure
fixture that the engine must detect, diagnose, patch, and recover from without
human help; and a budget test proving the loop terminates.

**Eval data captured:** each new mode plus its fix lands in the failure-and-fix
corpus; repair success-rate analytics gain new classes.

**Dependencies:** builds on the existing detect, repair, self-heal loop.

---

## C3. Biological-plausibility verification  ·  SHIPPED v0.3.0 (germline) + RNA-seq slice (v0.6.0) + single-cell ingestion slice (Unreleased)

**Shipped (germline slice) in v0.3.0.** The germline plausibility rules (Ti/Tv and
het/hom ratios) already existed in `VARIANT_RULE_PACK` but were dormant because
their metrics were never ingested. `verification/variant_metrics.py` now computes
`ts_tv` and `het_hom` from the run's VCF and feeds them to the verdict on a path
independent of MultiQC, capped at WARN (corroboration, not a clinical claim), with
`unverified` when a ratio is uncomputable.

**Shipped (RNA-seq slice, Unreleased).** The plausibility axis now extends to bulk
RNA-seq: a `RNASEQ_PLAUSIBILITY_PACK` with two WARN-capped checks — `duplication_rate`
(`percent_duplication`) and `rrna_contamination` (`percent_rRNA`) — evaluated by
`verification/rnaseq_plausibility.py`, which emits `unverified` (never PASS) when a
metric is absent from the run's ingested MultiQC, wired into `_discover_qc` gated to
`assay == "rnaseq"`. Metric slugs/bands are best-effort and uncalibrated; the
UNVERIFIED-when-absent guarantee absorbs a wrong/missing slug. **Deferred:**
gene-body-coverage evenness (needs a new RSeQC compute path), doublet rate
(single-cell), sex-check, coverage-from-VCF, multi-sample, and FAIL severity until
the bands are calibrated on real data.

**Shipped (single-cell ingestion slice, Unreleased).** The single-cell (`scrnaseq`)
assay already had a biological pack (`SCRNASEQ_RULE_PACK`: recovered cells, median
genes per cell, fraction reads in cells) but it **silently no-oped** — its metrics were
read only from MultiQC general-stats, where the base `nf-core/scrnaseq@4.1.0` pipeline
does not put single-cell cell-level QC (default `simpleaf` emits AlevinQC/QCatch HTML;
the stock MultiQC STAR module does not parse STARsolo `Summary.csv`). A new
`verification/scrnaseq_metrics.py` now parses the aligner's own cell-QC artifact —
STARsolo `Summary.csv` and Cell Ranger `metrics_summary.csv` (comma-thousands +
percent→fraction unit normalization) — and a dedicated `_discover_qc` gate (Cell Ranger
preferred per sample) drives the pack, so the single-cell verdict fires for the first
time. The default simpleaf path degrades to an honest **UNVERIFIED** (no confirmed
machine-readable artifact; no HTML scraping). The dead `pct_reads_mito` check was removed
(base pipeline never produces it — needs downstream scanpy); the grossly-failed-capture
FAIL bands were kept (consistent with the sibling did-it-run packs). **Deferred:** a
structured QCatch-JSON recognizer for the default simpleaf path, and mitochondrial-fraction
/ doublet-rate plausibility (need a downstream scanpy/scDblFinder step).

Deepen the verdict scientifically with **assay-aware sanity checks** that encode
what a biologically reasonable result looks like, beyond generic QC thresholds.

**Why it is moat.** This is the verification layer getting *smarter about biology*,
which is exactly the judgement incumbents leave to the human. It scopes
verifiability honestly per assay (guardrail: no over-claiming).

**What we build (assay-specific checks wired into the verdict):**
- RNA-seq: rRNA-contamination fraction within expected bounds, gene-body coverage
  evenness, exonic-mapping fraction, library-complexity and duplication sanity.
- Germline variants: Ti/Tv ratio in the expected range for the capture, het/hom
  ratio sanity, sex-check concordance between reported and inferred sex, expected
  variant-count band for the assay.
- Single-cell RNA-seq: doublet-rate band, mitochondrial-fraction distribution,
  knee-point sanity on the barcode-rank curve, expected recovered-cell band.
- Each check is conservative, names its evidence, and degrades to UNVERIFIED
  (not PASS) when the inputs to the check are absent.

**Acceptance (test-first):** fixtures at and outside each plausibility band; a
result inside the band passes, a result outside drops the verdict with the named
biological reason; missing inputs yield UNVERIFIED, never PASS.

**Eval data captured:** plausibility outcomes per assay extend the reference
distributions and flag implausible-but-completed runs for review.

**Dependencies:** strengthened by C1 (concordance) but independent of it.

---

## C4. New assay, depth-first: somatic variant calling  ·  SHIPPED v0.13.0 (intake→launch→verify) + VAF plausibility slice (Unreleased) + Strelka2-vs-Mutect2 concordance slice (Unreleased)

**Shipped (slice 1) in v0.13.0.** A somatic (tumor–normal) assay is now on the engine end
to end: a `somatic_variant_calling` registry entry + routing served by `nf-core/sarek`
in somatic mode; an explicit, persisted `--assay` that resolves the germline-vs-somatic
pipeline-string collision at its root (carried on the `RunRecord`/`launch.json`, legacy
`assay_for_pipeline` kept as the backward-compatible fallback); a sarek tumor/normal
sample-sheet pre-flight (paired `status` validation, unpaired-tumor/tumor-only refused);
a declarative `PipelineEntry.default_params` seam that launches sarek somatic with
`--tools strelka,mutect2`; and a `somatic_variant_calling` structural manifest + methods
label. Research-use only, test-first with synthetic fixtures (no real nf-core run in CI).

**Shipped (VAF-plausibility slice — Unreleased).** The somatic verdict gained its biological
axis (C3-style, so the assay is no longer structural-only). A new
`verification/somatic_plausibility.py`, gated to `assay == "somatic_variant_calling"` in
`_discover_qc`, computes from the **tumor column of the run's Mutect2 VCF**: `median_vaf`
(median tumor allele fraction over biallelic records — FORMAT `AF`, else `AD_alt/DP`; tumor
identified by the `##tumor_sample=` header, never a guessed column), `somatic_variant_count`
(a deliberately wide band), and `pon_applied` (panel-of-normals presence from the GATK
command header). Both metric bands are **WARN-capped** in a new `SOMATIC_PLAUSIBILITY_PACK`
(uncalibrated defaults, no `fail_*`); every uncomputable path — no derivable VAF, an
unidentifiable tumor column, no GATK header — is **UNVERIFIED, never a false pass**. The
Mutect2 VCF is selected by a path component below the run dir; a VCF present but non-Mutect2
yields one honest UNVERIFIED, and no VCF skips silently. The second-somatic-caller
**concordance hook** (C1-style — Strelka2 vs Mutect2) has since **shipped** (see C1, somatic
slice). **Deferred to follow-on slices:** Strelka2-
native VAF (tier-count derivation — non-Mutect2 VCFs degrade to UNVERIFIED); FAIL severity
until bands are calibrated on real data; a cross-column swapped-pair smell test; and
panel-of-normals / germline-resource reference wiring for a real Mutect2 somatic run (today
the verification runs against injected fixtures).

The original framing, for reference: add one assay end to end rather than several
shallowly. Recommended:
**somatic (tumor and normal) variant calling** via an existing nf-core pipeline
(for example nf-core/sarek in somatic mode). It is a natural extension of the
shipped germline assay, it is high-value, and it is rich to verify.

**Why it is moat.** Each new assay brings new failure modes, new verification
logic, and new corpus data. Depth-first means we only add an assay we can
genuinely verify, per the standing rule.

**What we build (via the `ADD_AN_ASSAY` path):**
- Registry entry and planner match for the somatic goal; tumor and normal
  sample-sheet shape and pre-flight validation.
- Structural output manifest for the somatic outputs; QC and biological-plausibility
  checks (VAF distribution sanity, panel-of-normals filtering present, expected
  somatic-count band).
- A concordance hook (C1) against a second somatic caller.
- Seed corpus cases for the somatic-specific failure modes.

**Acceptance (test-first):** a planned somatic run on a public tumor and normal
test profile validates, produces the expected structural outputs, and yields a
scoped verdict; an injected somatic-specific failure self-heals.

**Eval data captured:** a whole new assay's worth of failure and verification
cases.

**Dependencies:** reuses C1, C2, C3 on the new assay.

---

## C5. Reference and input-data integrity  ·  month 5  ·  capture slice SHIPPED (Unreleased)

**Shipped (capture slice — slice 1 of N).** A run now records its **reference
identity** into provenance: a new `ReferenceIdentity` model captured at finalize from
the run's parameters and serialized into `run_record.json`. Explicit mode
(`--fasta`/`--gtf`) records the paths plus their `sha256`; iGenomes mode
(`--genome KEY`) records the key and marks checksums unavailable (the pipeline
downloads those files, so a run is never failed over an unhashable/missing reference —
the checksum degrades to `None`, never a fabricated hash). Rendered in `contig methods`
and the HTML provenance panel. Capture-only: no QC/verdict or exit-code change; nf-core
only (Snakemake carries no reference keys → identity absent, section omitted). This is
the dependency groundwork for the mismatch detector below and for C2's reference/build-
mismatch repair (`missing_reference` is already a `FailureClass`). **Deferred to later
C5 slices:** the pre-flight **mismatch detector** (contig-naming / assembly-signature
comparison — the meaty, riskier part); **known-sites** capture (not visible to Contig
today: nf-core config assets, not CLI params — needs a `--known-sites` design);
**annotation/GTF version** resolution (no reliable source — left null, not fabricated);
and **RO-Crate** export of the identity.

Make reference assets first-class and reproducibility-grade: pin, verify, and
record the genome build, annotation version, and known-sites resources, and
detect mismatches before they corrupt a run.

**Why it is moat.** Reference and build mismatch is a notorious silent-failure
class (a run "succeeds" against the wrong genome). Pinning and verifying
references both prevents a failure class (feeding C2's mismatch detector) and
deepens the reproduce guarantee (the manifest already pins tools and params; this
pins the *data* they ran against).

**What we build:**
- Capture reference identity into provenance: build name, annotation (GTF)
  version, and checksums of the reference and known-sites files.
- A pre-flight reference-integrity check: refuse or warn when the sample data's
  contig naming or assembly signature does not match the selected reference.
- Surface reference identity in the provenance panel and the methods output.

**Acceptance (test-first):** a run whose data and reference disagree is caught at
pre-flight with the exact mismatch named; the reference identity appears in the
bundle and reproduces on re-run.

**Eval data captured:** reference-mismatch cases join the corpus.

**Dependencies:** complements C2 (mismatch repair) and the shipped provenance work.

---

## C6. Eval flywheel as a continuous loop  ·  month 6

Turn the corpus, detector-eval, and model-swap machinery (already shipped as
discrete commands) into a **continuous, measured improvement loop**, and fold the
new C1 to C5 signals into it.

**Why it is moat.** This is ROADMAP Phase 3's data flywheel made concrete and
started early: verification and self-heal accuracy improving over time, measured
against a held-out internal benchmark, *learned from real failures* rather than
from a static model.

**What we build:**
- Feed concordance outcomes (C1), new repair outcomes (C2), and plausibility
  outcomes (C3) into the eval history alongside the detector scores.
- A held-out internal benchmark set and a single command that reports current
  verification and self-heal accuracy against it, trended over corpus versions.
- A regression guard: a corpus or detector change that lowers accuracy on the
  held-out set is flagged before it ships.

**Acceptance (test-first):** a frozen held-out set; a known-good detector scores
above a threshold; a deliberately worse detector is flagged as a regression.

**Slice 1 — SHIPPED (Unreleased).** A frozen held-out corpus
(`src/contig/data/detector_corpus_holdout.jsonl`, 12 cases, `source="holdout:synthetic"`,
`case_id`s disjoint from the training corpus) plus `contig eval-guard`: scores the
`rules` detector against the held-out set (reusing `evaluate_detector`/`get_detector`,
no reimplemented scoring) and fails the build when accuracy drops below a committed
baseline (`src/contig/data/holdout_baseline.json`, one `EvalSnapshot` pinning
`corpus_sha`/`detector`/`contig_version`); `--update-baseline` (re)freezes it as a
deliberate act; loud non-failing warnings on sha/detector mismatch; an improvement
nudge. The committed baseline is honestly **0.833 (10/12)** — `qc_anomaly` and
`no_progress` are currently structurally unreachable by `diagnose_failure` (no rule
branch emits them), a deliberate gap that leaves headroom for the nudge to fire once
those rules exist. **Honest scope, unchanged from the PRD:** this slice guards the
**labeled failure-class detector corpus only**. **Pending follow-on slices:** folding
the unlabeled C1 concordance / C3 plausibility corroboration signals and repair-loop
(whole self-heal) accuracy into one number (the "fold C1–C5 into one accuracy number"
framing above is *not yet built* — it needs its own labeling design since C1/C3 carry
no ground-truth labels); and a held-out-accuracy trend over corpus/detector versions
(mirroring `eval-detector --history`). The guard is wired into CI
(`.github/workflows/ci.yml`), so a regression fails the build.

**Eval data captured:** this *is* the capture loop; it closes over all the above.

**Dependencies:** consumes the outputs of C1 to C5.

---

## Sequencing summary

| ID | Capability | Window | Leverage |
|----|-----------|--------|----------|
| C1 | Cross-tool concordance verification | SHIPPED v0.2.0 + RNA-seq slice (Unreleased) + somatic slice (Unreleased) | Verdict trust, novel primitive (germline `--concordance-vcf` + RNA-seq `--concordance-counts` Spearman/fraction-agreeing/overlap + somatic auto `somatic_site_overlap` PASS-site Jaccard, Mutect2 vs Strelka2, no user input; auto-run second germline/RNA tool + single-cell deferred) |
| C2 | Self-heal breadth plus auto resource-scaling | M2 to M3 (resource-aware + single-file missing-index family `.fai`/`.bai`/`.tbi`/`.csi`/`.dict` shipped; chr-prefix GTF harmonization shipped; per-contig alias harmonization (mito `M`↔`MT` + GRCh38 scaffold seed) shipped; directory-shaped STAR index build+redirect shipped, classic BWA + bwa-mem2 detector+corpus-only (v0.11.0); peak-RSS-informed OOM memory scaling shipped (Unreleased, honest two-tier: own-peak → blind fallback; sibling rescue deferred); walltime-informed `time_limit` scaling shipped (Unreleased, floored at blind — censored realtime, tail-only win + field instrument); bwa-mem2/classic-BWA build+redirect, assembly-signature + exhaustive per-assembly alias completeness pending) | Unattended-completion rate, corpus fuel |
| C3 | Biological-plausibility verification | SHIPPED v0.3.0 (germline) + RNA-seq (v0.6.0) + single-cell ingestion (Unreleased) | Verdict gets smarter about biology (germline Ti/Tv, het/hom; RNA-seq dup/rRNA; single-cell cell-QC now *fires* via STARsolo/Cell Ranger ingestion — was a dormant no-op; mito/doublet deferred) |
| C4 | New assay: somatic variant calling | SHIPPED v0.13.0 (intake→launch→verify) + VAF/count/PON plausibility slice (Unreleased) + Strelka2-vs-Mutect2 concordance slice (Unreleased); Strelka2-native VAF, FAIL severity + PON reference wiring deferred | Breadth, depth-first, new corpus |
| C5 | Reference and input-data integrity | M5 (reference-identity **capture** slice shipped — explicit `sha256` + iGenomes key-only, rendered in methods/panel; pre-flight **mismatch detector**, known-sites, GTF version, RO-Crate pending) | Kills a silent-failure class, deepens reproduce |
| C6 | Eval flywheel as a continuous loop | M6 (held-out set + regression-guard slice 1 SHIPPED, Unreleased — honestly 0.833/10:12, two classes structurally unreachable; folding C1/C3 signals + repair-loop accuracy + CI wiring pending) | Compounding accuracy from real runs |

**One-line mantra:** make every verdict harder to fool, recover more failures
without a human, and let every run make the next verdict smarter.

---

## Guardrails (unchanged, restated so this track does not drift)

- **No Layer-1 workflow authoring as a product surface.** We consume nf-core and
  the planner's deterministic match; we do not generate pipelines from English.
- **No raw-read egress.** Concordance, plausibility, and reference checks all run
  on the user's compute; only hashes and metadata ever leave the machine.
- **Nothing requiring wet-lab or clinical credentials**, proprietary biological
  datasets, or EHR/regulatory integration.
- **No correctness over-claiming.** Concordance is corroboration, not ground
  truth; plausibility checks are scoped per assay; UNVERIFIED is never rendered as
  PASS.
- **Test-first.** Every capability lands with its failing test written first.

For the broader menu of analysis types these capabilities unlock (variant
annotation, pathogen and AMR research, epigenomics, long-read, assembly, and the
bright line against clinical diagnosis), see
[`USE_CASE_UNIVERSE.md`](USE_CASE_UNIVERSE.md).

See also: [`ARCHITECTURE.md`](ARCHITECTURE.md), [`ADD_AN_ASSAY.md`](ADD_AN_ASSAY.md),
[`ROADMAP.md`](../ROADMAP.md), and [`FEATURES.md`](../../FEATURES.md).
