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

## C1. Cross-tool concordance verification  ·  SHIPPED v0.2.0 (germline) + RNA-seq slice (Unreleased) + somatic slice (Unreleased) + single-cell slice (Unreleased)

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
to a follow-on slice:** auto-running a second germline caller for RNA-seq's sibling assays, single-cell concordance, a dashboard "corroborated by" line, and
FAIL-severity once thresholds are calibrated on real data (the RNA-seq quantifier autorun itself is now shipped — see the autorun slice below).

**Shipped (RNA-seq autorun slice — Unreleased).** The RNA-seq concordance axis is now
turnkey: `contig verify --concordance-counts-auto --reads <sheet> --index <kallisto-index>`
produces the second matrix itself by running a second, independent quantifier (**kallisto**)
behind an injectable seam (`verification/count_quantifier.py`, mirroring the germline
`second_caller.py`), then feeds it into the shipped `evaluate_count_concordance`. This is the
exact follow-on the RNA-seq slice named — it mirrors how the germline autorun
`--concordance-auto` (v0.4.0) followed the user-supplied `--concordance-vcf`. kallisto is
**never run in CI** (injected seam; the subprocess path is covered by a manual gate only),
but the transcript→gene collapse is a **pure, CI-tested** function. Same contract: at most
WARN, never changes the exit code, `unverified` below 10 shared genes; the four concordance
flags are mutually exclusive; every unrunnable path is an honest skip note. **Still deferred:**
a persisted-sheet `--reads` fallback, an in-seam index build from a `--transcriptome`,
single-cell concordance, a dashboard "corroborated by" line, and FAIL-severity on calibrated
bands.

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

**Shipped (single-cell slice — Unreleased).** The concordance axis now reaches the last wired
assay without it: bulk-RNA-seq's count concordance is extended to **single-cell** via `contig
verify --concordance-sc-counts <matrix>`. The dict-based core of `count_concordance.py` was
factored out (`stats_from_counts`/`results_from_counts`, byte-identical RNA-seq behavior), and a
new pure-stdlib `verification/sc_count_concordance.py` reads the run's own `matrix.mtx`(.gz)
triplet (siblings resolved, gene axis inferred from the MatrixMarket dims vs the feature/barcode
counts) and **sums counts across all cells to a per-gene pseudobulk** `{gene_id: total}`, fed into
that unchanged core against a user-supplied second matrix (a `.mtx` triplet or a dense pseudobulk
gene TSV, chosen by extension sniff). Same contract as every C1 slice — `spearman_concordance` and
`fraction_agreeing` at most WARN (< 0.90), informational `gene_overlap`, `unverified` below 10
shared genes, never changes the exit code; a located-but-unparseable matrix is one honest
`sc_count_concordance` UNVERIFIED, an `.h5ad`-only run skips. Pure-stdlib (no `anndata`/`h5py`),
`filtered/`-over-`raw/` primary preference. **Deferred:** `.h5ad` parsing (dependency-gated);
cell-count and cluster-stability agreement (need a downstream clustering step Contig doesn't run);
FAIL severity on calibrated bands; a dashboard "corroborated by" line. (The second-quantifier
**autorun** has since shipped — see the single-cell autorun slice below.)

**Shipped (single-cell autorun slice — Unreleased).** The single-cell concordance axis is now
turnkey: `contig verify --concordance-sc-counts-auto --reads <sheet> --index <STAR genome dir>
--whitelist <path> [--chemistry 10xv3]` produces the second matrix itself by running a second,
independent single-cell quantifier (**STARsolo**) behind an injectable seam
(`verification/sc_count_quantifier.py`, mirroring the RNA-seq `count_quantifier.py`), then feeds
its native `matrix.mtx` into the shipped `evaluate_sc_count_concordance` core unchanged. This is
the exact follow-on the single-cell slice named — it mirrors the RNA-seq kallisto autorun
`--concordance-counts-auto` (v0.24.0). STARsolo emits gene-level counts natively, so there is **no
transcript→gene collapse** (unlike kallisto); the pure `starsolo_command` argv builder pins the
`(cDNA, CB)` `--readFilesIn` order (the reverse of the sample sheet's `(fastq_1, fastq_2)`) and is
CI-asserted-not-executed, while STARsolo itself is **never run in CI** (injected fake; manual
gate). Same contract: at most WARN, never changes the exit code, `unverified` below 10 shared
genes; the six concordance flags are mutually exclusive; the corroboration line names **STARsolo**
as the second tool; every unrunnable path (non-`scrnaseq`, missing input, quantifier failure,
primary matrix absent → no pointless spawn) is an honest skip. The barcode whitelist/chemistry are
user-supplied because Contig persists no chemistry/whitelist/aligner today. **Still deferred:**
auto-deriving inputs from the run record; cell-count and cluster-stability agreement; FAIL
severity on calibrated bands (the pseudobulk-washout of benign cross-tool cell-calling divergence
is an unproven assumption — hence WARN-only); a dashboard "corroborated by" line; and
`.h5ad`/AnnData second-matrix parsing.

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
- Single-cell RNA-seq: **shipped (user-supplied slice)** as pseudobulk gene-level
  concordance (`--concordance-sc-counts`); cell-count and cluster-stability agreement across
  two quantifiers (for example STARsolo against alevin-fry) remain deferred.
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
**Shipped (input-format conversion — bgzip-reference slice — Unreleased):** the **first
slice of the input-format-conversion class**. A Contig-launched **nf-core/sarek** run
(`variant_calling` germline + `somatic_variant_calling`) whose `--fasta` was compressed
with plain `gzip` instead of `bgzip` fails `samtools faidx`
(`Cannot index files compressed with gzip, please use bgzip`) — previously an opaque
`tool_crash`. **rnaseq is deliberately excluded**: its own `PREPARE_GENOME` gunzips a
`.gz` fasta before faidx ever runs, so the failure never reaches Contig there; sarek 3.5.1
has no gunzip module, so it is reachable through the real CLI (the forced `--gtf` from
`resolve_reference` is only an nf-schema warning on sarek, not a validation failure). A new
`_recompress_reference` **stream-decompresses** the reference with stdlib `gzip` (no
external tool) to a plain **uncompressed `.fa`** in run-scoped scratch
`<run_id>/healed_reference/`, redirects the in-memory `params["fasta"]`, and retries —
reusing the STAR-index scratch/redirect seam and the GTF-harmonization reproduce-safety
contract (empirically verified: `launch.json` keeps the original `fasta`; `rerun`/`resume`
re-derive). A new `_gzip_kind` classifier discriminates plain-gzip from BGZF via the
FEXTRA `BC` subfield, so a **valid BGZF reference is left untouched**. New `FailureClass`
`reference_not_bgzf` with a narrow detector branch (anchored on the faidx-specific
message, not the bare "please use bgzip" tabix/bcftools emit for VCFs); one golden
corpus case + a held-out twin (held-out accuracy 83.3%→84.6%, refrozen baseline). Patch is
`kind="reference"`, `risk="needs_confirmation"` (not auto-approved `safe`). Every give-up —
no fasta, already-BGZF, decompress failure, already-recompressed-this-run — is an honest
FAIL, bounded to one recompress per run. Test-first with an injected executor and tiny
real gzip/hand-crafted-BGZF fixtures; no real nf-core/sarek or samtools run in CI.
**Deferred:** CRAM↔BAM conversion (the other half of this class); a BGZF fix target
(declined for plain-uncompressed); `safe`-vs-gated auto-approval; a `heal-guard` scenario
for the new class; and the `resolve_reference` `--fasta`/`--gtf` coupling quirk this slice
tolerates rather than fixes.
**Deferred to later C2 slices:** bwa-mem2 **build/redirect** (detection shipped v0.11.0;
build blocked until a live trigger exists) and the classic-vs-mem2 aligner-mismatch heal;
classic-BWA index build/redirect (needs a supported `bwa index` target, e.g. sarek
`--aligner bwa-mem`); a corrupt/partial STAR index signature; the still-missing single-file
index kind (the BAM/CRAM form of
`.csi`) plus stale-index detection on the same seam; and the wider failure catalog — the
assembly-signature form of reference/build mismatch (no sample-side contig signal in raw
FASTQ or finished bundle), exhaustive per-assembly alias-table completeness beyond the
GRCh38 seed, known-sites/GTF-version consistency, a runtime `reference_mismatch`
detector-corpus case, CRAM↔BAM conversion (the input-format-conversion class's second
half), and pin conflict.

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

## C3. Biological-plausibility verification  ·  SHIPPED v0.3.0 (germline) + RNA-seq slice (v0.6.0) + single-cell ingestion slice (Unreleased) + germline sex-check slice (Unreleased) + RNA-seq mapping-composition slice (Unreleased) + germline variant-count slice (Unreleased) + germline plausibility FAIL-severity slice (Unreleased) + somatic empty-call-set FAIL floor slice (Unreleased; the remaining VAF/RNA-seq FAIL bands **declined by design** — see below) + RNA-seq plausibility ingestion fix slice (Unreleased; `duplication_rate` corrected to its real MultiQC key/unit, shipped informational-only — no band)

**Shipped (germline slice) in v0.3.0.** The germline plausibility rules (Ti/Tv and
het/hom ratios) already existed in `VARIANT_RULE_PACK` but were dormant because
their metrics were never ingested. `verification/variant_metrics.py` now computes
`ts_tv` and `het_hom` from the run's VCF and feeds them to the verdict on a path
independent of MultiQC, originally capped at WARN (corroboration, not a clinical
claim), with `unverified` when a ratio is uncomputable. (Ti/Tv and het/hom have
since gained gross-implausibility FAIL bands — see the germline plausibility
FAIL-severity slice below.)

**Shipped (RNA-seq slice, Unreleased).** The plausibility axis now extends to bulk
RNA-seq: a `RNASEQ_PLAUSIBILITY_PACK` with two WARN-capped checks — `duplication_rate`
(`percent_duplication`) and `rrna_contamination` (`percent_rRNA`) — evaluated by
`verification/rnaseq_plausibility.py`, which emits `unverified` (never PASS) when a
metric is absent from the run's ingested MultiQC, wired into `_discover_qc` gated to
`assay == "rnaseq"`. Metric slugs/bands are best-effort and uncalibrated; the
UNVERIFIED-when-absent guarantee absorbs a wrong/missing slug. **Deferred:**
gene-body-coverage evenness (needs a new RSeQC compute path), doublet rate
(single-cell), coverage-from-VCF, and multi-sample. **FAIL severity for this pack is
settled, not deferred: declined by design** — every RNA-seq metric has a legitimate protocol
occupying its extreme (deep/high-input libraries legitimately exceed 90% duplication;
total-RNA / ribo-depletion legitimately retains rRNA), so "extreme" and "unusual protocol"
are the same number, and no amount of calibration separates them; and both of this pack's
slugs are still `# slug unverified` — they have never once resolved against a real
`nf-core/rnaseq` MultiQC report, so a band there would be severity on code that has never
fired. Full reasoning in the somatic empty-call-set FAIL floor slice below. (The
**sex-check** and **mapping-composition** slices have since shipped — see below.)

**Shipped (RNA-seq mapping-composition slice, Unreleased).** The RNA-seq axis now catches
where reads fall relative to gene annotation — the gDNA-contamination / failed-enrichment
smell that passes alignment QC but yields a meaningless matrix. This is the
"exonic-mapping fraction" item the v0.6.0 slice deferred. Because the composition fractions
are **not** in Contig's MultiQC general-stats ingest (verified against a real
`multiqc_data.json`), a new dedicated parser `verification/rnaseq_metrics.py` reads RSeQC's
own `read_distribution.txt` (the artifact `nf-core/rnaseq@3.26.0` writes by default),
mirroring the scrnaseq/methylseq/ampliseq/mag dedicated-gate pattern. It emits three
per-sample WARN-capped checks from the `Tag_count` column — `exonic_fraction` =
`(CDS+5'UTR+3'UTR)/Total Assigned Tags`, `intronic_fraction` = `Introns/Total Assigned
Tags`, `unassigned_fraction` = `(Total Tags−Total Assigned Tags)/Total Tags` (two
intentional denominators; the nested TSS/TES windows never summed) — via a new
`RNASEQ_COMPOSITION_PACK` (unregistered) and an **additive** `_discover_qc` gate that keeps
`rnaseq` on its existing MultiQC pack path (`rnaseq` stays out of
`_DEDICATED_METRIC_ASSAYS`) and prefers the published `results/` copy over a `work/` copy.
Same contract as every C3 slice: at most WARN, never FAIL, never changes the exit code;
omit-never-guess on uncomputable metrics; a located-but-unparseable artifact →
`rnaseq_composition_qc:<sample>` **UNVERIFIED**; no artifact → silent skip. **Deferred:**
gene-body-coverage evenness (non-default RSeQC module), cross-sample aggregation, and a
dashboard card. **FAIL severity for this pack is settled, not deferred: declined by design** —
nuclear / FFPE / 3'-biased libraries are legitimately intron-dominated and non-model annotation
legitimately leaves most tags unassigned, so here too "extreme" and "unusual protocol" are the
same number; and the one genuinely broken case, `unassigned_fraction == 1.0`, is already caught
more honestly by `RNASEQ_RULE_PACK`'s `assignment_rate fail_below: 40` on the did-it-run tier —
a second FAIL would be redundant, not new signal. Full reasoning in the somatic empty-call-set
FAIL floor slice below.

**Shipped (germline sex-check slice, Unreleased).** The verdict now catches
sex-chromosome **discordance**. A new `verification/sex_plausibility.py` infers
karyotypic sex from the germline VCF — an **X-heterozygosity ratio** over
biallelic non-PAR X genotypes (PAR excluded via GRCh37/GRCh38 coordinates, the
build detected from the VCF `##contig` header, falling back to unmasked when
undetermined) plus **Y-variant presence** (corroboration only; Y-*absence* is
uninformative and never forces a discordant call). It emits one WARN-capped
`sex_plausibility` result (low X-het → XY, high X-het + no Y → XX, high X-het +
Y present or a mid-band ratio → **discordant/WARN**, too-few-X → **UNVERIFIED**)
plus an informational `x_het_ratio`, gated to `variant_calling` in `_discover_qc`
and reusing the same primary VCF as `variant_metrics`. The inferred sex is
captured into a new `SexInference` provenance record on the `RunRecord` (C5
pattern; located identically to the QC path so the verdict and provenance can
never disagree), rendered in `contig methods` and the HTML panel ("undetermined"
when indeterminate — never a fabricated call; always a research-use inference,
never a clinical determination), and round-tripped through reproduce with
back-compat. At most WARN, never FAIL, never changes the exit code. **Deferred:**
reported-vs-inferred concordance (needs a sample-sheet sex column — so this slice
catches only cross-sex swaps and aneuploidy), per-sample multi-sample sex,
FAIL severity on calibrated bands, and a dashboard card.

**Shipped (germline variant-count slice, Unreleased).** The germline verdict now
catches a grossly-off **call-set size** — a near-zero count from failed/truncated
calling, or an absurd count — that previously passed silently. `variant_metrics.py`
gains `variant_count` = `len(parse_vcf(vcf))` (distinct primary-sample
`(CHROM,POS,REF,ALT)` sites; a duplicated line dedups to one, a multiallelic record
is one site, not PASS-filtered), reusing the same reader as `ts_tv`/`het_hom`. Always
an `int`, so unlike the two ratios it is always computable. One WARN-only
`variant_count` rule joins `VARIANT_RULE_PACK` (`warn_below: 10`,
`warn_above: 20_000_000`, no `fail_*` — a wide uncalibrated band whose upper bound is a
**soft "absurd-count" tripwire, not a validated ceiling**), selected in
`evaluate_variant_plausibility` by adding it to `_PLAUSIBILITY_CHECKS`/`by_metric`, so it
rides the **existing** germline plausibility gate (no `runner`/`_discover_qc` edit) and
emits `variant_count:<sample>` with `expected_range` `[10, 20000000]` alongside the two
ratios. Contract as shipped in this slice: at most WARN, never changes the exit
code — though the germline plausibility FAIL-severity slice below later gives
`variant_count` a `fail_below: 1` empty-call-set floor (an empty set becomes FAIL, a
strictly stronger signal than the prior WARN). The always-int count means a **real 0 rides
the band and never routes into the `ts_tv`/`het_hom` UNVERIFIED branch** (an empty call set
is not mistaken for "nothing to check"); no VCF at all → silent skip (structural QC owns a
missing output). Verdict-only: no new module, provenance record, `FailureClass`, model, or
dashboard card. **Deferred:** band calibration on real cohorts, capture-aware bands
(panel/WES/WGS differ by orders of magnitude), per-sample multi-sample counts, a dashboard
card, and the C6 fold-in.

**Shipped (germline plausibility FAIL-severity slice, Unreleased).** The germline
plausibility axis gains its **first FAIL severity**: `ts_tv_ratio` (`fail_below 1.2` /
`fail_above 3.6`), `het_hom_ratio` (`fail_below 1.0` / `fail_above 3.0`), and
`variant_count` (`fail_below 1` only — no `fail_above`; the `warn_above 20_000_000` upper
bound stays a soft WARN ceiling) now drive `record.verdict` → **FAIL** on a
grossly-implausible germline call set (a noise-level Ti/Tv ~0.5, or an empty/near-empty
call set — now FAIL, not the prior WARN). The WARN bands are unchanged, so a legitimate WGS
(Ti/Tv ~2.0, het/hom ~1.5) or WES (Ti/Tv ~3.0–3.3) run stays PASS/WARN and never
false-FAILs. Pure data change to the three `VARIANT_RULE_PACK` dicts — the scorer
(`_status_for`), evaluator, verdict reducer (`overall_verdict`), report, provenance, and
dashboard consume it unchanged. The bands are **WES-safe gross-implausibility engineering
tripwires** (same honesty tier as `mean_coverage fail_below`), **not** a clinical or
biological claim. **Verdict-only (at the time of this slice):** the `contig run`/`verify`
exit code was unchanged — no QC verdict, including pre-existing FAIL packs like
`mean_coverage`, moved the exit code; wiring that is a deliberate, separately-scoped
follow-on. *(Update: that CLI exit-code wiring has since shipped as the opt-in
`--fail-on-verdict` flag on `contig run`/`verify` — a FAIL verdict exits `1` when the flag
is set, WARN/UNVERIFIED/PASS stay `0`; the **default** exit code remains unchanged, so this
slice's "verdict-only" claim holds unless a caller opts in.)* This slice left FAIL severity
for the sibling plausibility packs deferred; *(update: that item is now **settled, not
pending** — the somatic empty-call-set floor below shipped the one band that could be
derived honestly, and the somatic-VAF and RNA-seq bands are **declined by design**, with
reasons. The annotation pack (C7 M3) and the sex-check axis remain WARN-only and are not
covered by that decision.)* **Deferred:** capture-type-aware (WGS/WES/panel) bands and
tighter band calibration on real cohorts (the WES-safe bands are deliberately gross-only).

**Shipped (somatic empty-call-set FAIL floor slice, Unreleased) — and the rest declined by
design.** The germline slice above left "FAIL severity for the somatic/RNA-seq/composition
packs" open; a dig proved that item was **one line of ship and the rest a will-not-do**, so
it is settled here rather than deferred a sixth time (it had been re-deferred across the
germline v0.3.0, RNA-seq v0.6.0, somatic-VAF, composition, and variant-count slices).
**Shipped:** `somatic_variant_count` gains `fail_below: 1` — a somatic run with no biallelic
records called (almost always an empty or truncated call set) now FAILs the verdict, the
failure `--fail-on-verdict` (v0.36.0) previously could not catch on this assay. The band's
shape and rationale mirror the germline `variant_count` floor; the counted population
differs, since `somatic_variant_count` counts biallelic records only while germline
`variant_count` counts distinct sites including multiallelic ones. The escalation is the
narrowest possible: `warn_below: 10` is unchanged, so 1–9 records still
WARN and only the exactly-zero case moves. There is deliberately **no `fail_above`** — a
hypermutator (MSI-high, POLE-mutant) or a WGS tumor legitimately exceeds the soft `100000`
ceiling. It is an engineering tripwire ("an empty call set is a broken run"), the same tier
as `mean_coverage fail_below`, **not** a biological or clinical claim.
**Declined by design — these are not waiting on calibration, and no amount of calibration
would fix them:**
- **Somatic VAF (`median_vaf`, `strelka_median_vaf`):** germline Ti/Tv could ship FAIL bands
  because its expected value is *physically constrained* (~2.0 WGS, ~3.0–3.3 WES) with noise
  at a *distinguishable* ~0.5. A tumor VAF has no such structure — its expected value is a
  function of **purity and clonality, which the engine never observes** (no purity estimate,
  no ploidy, no copy-number, no target type). A low median VAF is legitimate science
  (low-purity tumor, subclonal population), so any `fail_below` would FAIL a real sample.
  `strelka_median_vaf` adds a second, independent reason: the tier1 ratio is arithmetically
  bounded to [0,1] given non-negative tier counts — which the VCF spec guarantees — since
  `strelka_vaf.py:95-98,121-124` reject `denom <= 0` and the numerator is one of the two
  summands. A `fail_above: 1.0` is therefore **dead code for every real input**.
- **`pon_applied`:** structurally unbandable — a 3-state string from a header search, not a
  numeric metric, emitted with `value=None` and never entering `evaluate()` at all (it is
  appended alongside the pack's results, not routed through it, so no band on it could ever
  fire). PON absence is also a legitimate configuration Contig itself does not wire.
- **RNA-seq (`RNASEQ_PLAUSIBILITY_PACK`, `RNASEQ_COMPOSITION_PACK`):** two independent
  blockers, though the *engineering* one has since narrowed to a single metric. *Biology:*
  every metric has a legitimate protocol occupying its extreme — deep/high-input libraries
  legitimately exceed 90% duplication, total-RNA/ribo-depletion legitimately retains rRNA,
  nuclear/FFPE/3' libraries are legitimately intron-dominated, non-model annotation
  legitimately leaves most tags unassigned. "Extreme" and "unusual protocol" are the same
  number, and the packs see no prep or annotation-quality signal that separates them — this
  reason stands alone and needs no engineering support. *Engineering (now `percent_rRNA`
  only):* at the time this record was first written, both `percent_duplication` and
  `percent_rRNA` were absent from the repo's only real-shaped MultiQC report — FAIL severity
  on a metric that never arrives is severity on dead code. **The RNA-seq plausibility
  ingestion fix slice (below) removes half of that claim:** `duplication_rate` was keyed on
  the wrong case (`percent_duplication` vs MultiQC's actual `PERCENT_DUPLICATION`) and banded
  on the wrong unit (0–100 vs Picard's true 0–1 fraction) — a data bug, not an absent metric —
  and now resolves against every real report that ran Picard MarkDuplicates. It no longer
  qualifies for the "dead code" argument, so its declined band rests on the biology reason
  alone, which now also covers WARN, not just FAIL: the fix shipped `duplication_rate`
  **informational-only, with no band at all** (a deep/high-input library legitimately exceeds
  90% duplication, so even a WARN would flag a legitimate protocol). `percent_rRNA`
  (`rule_pack.py:337`, still commented "slug unverified") keeps the full engineering
  argument — it genuinely has no default machine-readable source in `nf-core/rnaseq` (see the
  ingestion fix slice below for the research). *Also:* the one genuinely broken composition
  case, `unassigned_fraction == 1.0`, is already caught more honestly by `RNASEQ_RULE_PACK`'s
  `assignment_rate fail_below: 40` on the did-it-run tier — a second FAIL is redundant, not
  new signal.
The decision is recorded in the pack comments (`rule_pack.py`) as well as here, so the reason
travels with the code. **Known caveat (disclosed, not fixed):** `verdict` is a
`@computed_field` serialized into the signed canonical payload, so re-verifying an affected
old bundle re-reduces the verdict under the new band and its Ed25519 signature no longer
matches. The blast radius is only bundles whose verdict actually flips — empty somatic call
sets, i.e. broken runs — and it is a pre-existing property of any rule-pack edit, inherited
unchanged from v0.35.0. **Accepted, eyes open:** a legitimately mutation-free targeted panel
would FAIL (the engine has no target-type signal; `--fail-on-verdict` is opt-in, and the
revisit trigger is the first real-world report of one). **Honest limit:** no real nf-core/sarek
run in CI — the floor catches a failure that is *reasoned* (a truncated/crashed Mutect2 step
yields 0 records) rather than *observed*, with the germline sibling as the existence proof.
**Surfaced here, then fixed (see the RNA-seq plausibility ingestion fix slice below):** at
the time this record was first written, `RNASEQ_PLAUSIBILITY_PACK` was **dormant, not a
silent no-op** — `evaluate_rnaseq_plausibility` already emitted an explicit `unverified`
result per absent metric per sample (four on the repo's own demo fixture) on every real
rnaseq run. That is *not* the single-cell/methylseq defect class: those packs ran through
the bare `evaluate()`, which silently **skips** a metric it can't find, producing no result
at all — dormant but honest is a different failure mode from silent. Only half of the live
defect matched that class, too: `duplication_rate`'s wrong key/unit was a pure data bug — the
key was reachable in MultiQC all along, misspelled by case, with a live unit ambiguity on top
(the pack declared 0–100 while Picard's native `PERCENT_DUPLICATION` is a 0–1 fraction) — so
no dedicated parser was needed, unlike the single-cell/methylseq fixes below. `percent_rRNA`
is the metric that genuinely matches the single-cell defect class (no default
machine-readable source in `nf-core/rnaseq` at all), and it remains unfixed and out of scope
(see the ingestion fix slice below).

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

**Shipped (RNA-seq plausibility ingestion fix slice, Unreleased).** The RNA-seq slice above
shipped `duplication_rate` keyed on `percent_duplication`, banded `warn_above: 80.0` on a
declared 0–100 scale — and it had never once fired on a real `nf-core/rnaseq` run, for two
compounding reasons, not one. MultiQC republishes Picard MarkDuplicates' own field name
verbatim as **`PERCENT_DUPLICATION`** (uppercase); `qc_ingest.py`'s general-stats merge
(`qc_ingest.py:14-22`) is an exact-key match with no case normalization, so the lowercase slug
missed forever. And Picard's own javadoc is explicit that the value is "the fraction of
mapped sequence that is marked as duplicate" — a raw **0–1** fraction, with no `x100` anywhere
in its formula, despite the "PERCENT" in its name; a 70%-duplicated sample reads `0.707214`,
not `70.0`. Fixing the key alone would have been worse than the bug: an unrescaled fraction
against the old 0–100 band would have silently PASSed every real report. `duplication_rate`
now keys `PERCENT_DUPLICATION` and carries `"unit": "fraction"`; the check ships
**informational-only — no band at all** (see below), so it always PASSes when present and
in range. A new guard in `rnaseq_plausibility.py` (any rule carrying `"unit": "fraction"`)
refuses a value present-but-outside-`[0,1]` as `unverified` rather than rescaling it — `0.5`
is ambiguous between "50%" and "0.5%," and refusing beats guessing — so a wrong key was
already safe (unverified) and a wrong unit is now safe too: **every known way for this check
to be wrong degrades to honest, never a silent lie.** `_expected_range` (`rule_pack.py:554`)
previously assumed every check had a `warn_below`/`warn_above` and rendered the literal string
`">= None"` for a band-less rule; it now returns `None` for a check with neither bound, which
`duplication_rate` is the repo's first rule to exercise. The fabricated
`percent_duplication: 95.0` test fixture — a shape nf-core never emits — was re-pointed to a
realistic `PERCENT_DUPLICATION: 0.707214` one; that fixture is why a green suite masked a
dead check for six releases (v0.6.0 through v0.37.0): it proved the wiring, never the
ingestion. `rrna_contamination` is untouched.

**The band: declined by design, not pending calibration.** `duplication_rate` ships with no
WARN or FAIL band at all, per the pack's own docstring: a deep/high-input library
legitimately exceeds 90% duplication, so *any* band — not just FAIL — would flag a legitimate
protocol as a problem. A band becomes justifiable only if real per-protocol duplication
distributions are collected, or the pack gains a library-prep/input-amount signal that could
separate "deep library" from "broken library"; neither exists today.

**Honest limit (reasoned, not observed — same tier as the somatic FAIL floor's disclosure).**
The corrected key and unit are read from MultiQC's and Picard's own source, not from an
observed run: **no real `nf-core/rnaseq multiqc_data.json` exists in this repo** to confirm
against — `demo/sample-run`'s is synthetic (`demo/make_sample_run.py:59,105` hand-writes
`uniquely_mapped_percent`/`percent_assigned`/`total_reads` only, no `PERCENT_DUPLICATION` key
at all). The `[0,1]` guard is what makes that acceptable: if the reasoning is wrong in either
direction, the check degrades to `unverified` rather than scoring a mis-keyed or mis-scaled
value as a false PASS. MarkDuplicates is also legitimately absent under
`--with_umi`/`--skip_markduplicates`; that no-key path already reports `unverified`, not a
false pass.

**Deferred/known debt, named:**
- **`rrna_contamination`'s `percent_rRNA` remains a guessed slug** — researched, and there is
  genuinely no default machine-readable rRNA source in `nf-core/rnaseq`: SortMeRNA is off by
  default (`remove_ribo_rna = false`); featureCounts biotype QC depends entirely on the user's
  GTF carrying a `gene_biotype` attribute, is silently skipped when absent (common for NCBI
  GTFs), and even when it runs emits per-biotype **counts** as custom content, not a
  general-stats percentage; and its artifact name is **unconfirmed for 3.26.0**, since the
  workflow appears refactored since the name was last observed. Recommended follow-on: drop
  the check, or build a dedicated parser that degrades to `unverified` rather than keep a
  guessed slug in place.
- **`runner.py:412`'s `multiqc is not None` gate:** a run with **no MultiQC report at all**
  makes both RNA-seq plausibility checks vanish rather than reporting `unverified` — the
  composition gate (`runner.py:428`) correctly gates on assay alone, so this is a real,
  pre-existing honesty gap, deferred rather than fixed here.
- **Informational checks are now verdict-neutral — SHIPPED (Unreleased).** Resolved by an
  additive `QCResult.informational` marker (default `False`, back-compat like `QCKind`) plus
  an `overall_verdict` that reduces over the non-informational results only. The design fork
  as originally posed ("add a verdict-neutral status, *or* exclude band-less rules from
  `overall_verdict`") was drawn on the wrong axis: `QCResult` carried no band information, so
  the reducer could not identify a band-less rule either way — both options needed a new
  field, so the orthogonal marker (not a fifth `QCStatus` value, which would have rippled
  through the persisted vocabulary and five TS `Record<>` maps) was chosen. Two corrections
  the build surfaced, recorded so the record is true:
  - **The set was undercounted.** The item claimed `duplication_rate` was "the only band-less
    rule" and treated `gene_symbol_concordance`/`x_het_ratio` as a footnote — but those two,
    plus a third (`gene_overlap`, then undocumented), are informational by a *different*
    mechanism (hardcoded always-pass, not band-less config). So "decide before a **second**
    band-less rule lands" had already been missed by three. All four are now marked, and a
    test enumerates the set so a fifth is a deliberate act.
  - **The motivating example does not flip.** A `PERCENT_DUPLICATION`-only RNA-seq report was
    said to "reduce to `pass` with nothing biological verified" — but the parenthetical
    "(already reduced to `pass` via `min_sample_count`)" was the real story: `min_sample_count`
    is an asserting check that floors every RNA-seq run at `pass`, so this slice does **not**
    change that run's verdict. The slice is defensive (the invariant is now true and guarded),
    not a closed false-pass class. See CHANGELOG "Honest scope".

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
  variant-count band for the assay _(shipped, Unreleased)_.
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

## C4. New assay, depth-first: somatic variant calling  ·  SHIPPED v0.13.0 (intake→launch→verify) + VAF plausibility slice (Unreleased) + Strelka2-vs-Mutect2 concordance slice (Unreleased) + Strelka2-native VAF slice (Unreleased) + empty-call-set FAIL floor slice (Unreleased; VAF FAIL bands **declined by design**)

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
command header). Both metric bands shipped **WARN-capped** in a new `SOMATIC_PLAUSIBILITY_PACK`
(uncalibrated defaults, no `fail_*`); every uncomputable path — no derivable VAF, an
unidentifiable tumor column, no GATK header — is **UNVERIFIED, never a false pass**. The
Mutect2 VCF is selected by a path component below the run dir; a VCF present but non-Mutect2
yields one honest UNVERIFIED, and no VCF skips silently. The second-somatic-caller
**concordance hook** (C1-style — Strelka2 vs Mutect2) has since **shipped** (see C1, somatic
slice). *(Update: `somatic_variant_count` has since gained a `fail_below: 1` empty-call-set
floor — see the FAIL-floor slice below. The **VAF** bands stay WARN-capped, no longer as a
deferral but as a **decision**: a tumor VAF's expected value is a function of purity and
clonality that the engine never observes, so any `fail_below` would FAIL a legitimate
low-purity or subclonal sample. `pon_applied` is structurally unbandable — a 3-state string,
not a numeric metric.)* **Deferred to follow-on slices:** a cross-column swapped-pair smell
test; and panel-of-normals / germline-resource reference wiring for a real Mutect2 somatic
run (today the verification runs against injected fixtures).

**Shipped (Strelka2-native VAF slice — Unreleased).** The deferred "Strelka2-native VAF
(tier-count derivation — non-Mutect2 VCFs degrade to UNVERIFIED)" item above has since
**shipped**: a `strelka_median_vaf` metric, computed independently of Mutect2's `AF`/`AD` from
Strelka2's own documented tier1 counts (SNV: `tier1({ALT}U) / (tier1({REF}U) +
tier1({ALT}U))` over `AU`/`CU`/`GU`/`TU`; indel: `tier1(TIR) / (tier1(TAR) + tier1(TIR))` over
`TAR`/`TIR`), pooled across the SNV+indel VCF pair and identified by the **literal** `TUMOR`
column name (Strelka2 emits no `##tumor_sample=` header). It fires **alongside** — not instead
of — Mutect2's `median_vaf`, as independent cross-caller corroboration of tumor VAF, riding the
same WARN-capped `SOMATIC_PLAUSIBILITY_PACK` band and wired via the same `select_caller_vcfs`
locator the concordance hook uses. **Still deferred:** the cross-column swapped-pair smell
test, and panel-of-normals / germline-resource reference wiring — unchanged from the slice
above. *(Update: this metric's WARN cap is now **declined by design**, not deferred. Beyond
inheriting `median_vaf`'s purity/clonality reason, a `fail_above: 1.0` here would be dead code
for every real input — the tier1 ratio is arithmetically bounded to [0,1] given non-negative
tier counts, which the VCF spec guarantees (`strelka_vaf.py:95-98,121-124` reject
`denom <= 0`, and the numerator is one of the two summands).)*

**Shipped (empty-call-set FAIL floor slice, Unreleased).** `somatic_variant_count` gains
`fail_below: 1`, so a somatic run with **no biallelic records called** (almost always a
truncated or crashed Mutect2 step yielding an empty call set, though a VCF whose calls are
all multiallelic would also read `0`) now FAILs the verdict instead of WARNing — the germline
equivalent of that exact failure already FAILed, and under `--fail-on-verdict` (v0.36.0) the
somatic run previously still exited `0`. `warn_below: 10` is unchanged, so 1–9 records still
WARN and only the exactly-zero case escalates; there is deliberately **no `fail_above`** (a
hypermutator or WGS tumor legitimately exceeds the soft `100000` ceiling). An engineering
tripwire, not a biological or clinical claim. The durable half of the slice is the
**declined-by-design** record for every other proposed band — see C3, which carries the full
reasoning, the signature caveat, and the accepted risks.

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
**labeled failure-class detector corpus only**. **Pending follow-on slices (at the
time):** folding the unlabeled C1 concordance / C3 plausibility corroboration
signals and repair-loop (whole self-heal) accuracy into one number (the "fold
C1–C5 into one accuracy number" framing above is *not yet built* — it needs its
own labeling design since C1/C3 carry no ground-truth labels); and a
held-out-accuracy trend over corpus/detector versions (mirroring
`eval-detector --history`). The guard is wired into CI
(`.github/workflows/ci.yml`), so a regression fails the build.

**Slice 2 — SHIPPED (Unreleased).** The repair-loop half of slice 1's pending
list. A `contig heal-guard` command and a `HealScenario` driver
(`src/contig/heal.py`) replay a frozen `src/contig/data/heal_scenarios.jsonl`
(7 synthetic cases) through the **real** `self_heal_run`
detect→diagnose→patch→retry loop — the detector and `propose` are never
stubbed (PRD R2) — via scripted executor/index-builder/poll seams. It guards
the loop's **outcome-match rate** (right `FailureClass` diagnosed *and* the
scenario's declared terminal outcome reached), a different axis from slice 1's
detector-only classification accuracy, against a committed baseline
(`src/contig/data/heal_baseline.json`, pinning
`corpus_sha`/`covered_classes`/`contig_version`); `--update-baseline`
(re)freezes it as a deliberate act; a loud sha-mismatch warning; an
improvement nudge. The committed baseline is honestly **outcome-match 1.0
(7/7)** over the 5 classes the frozen set currently covers (`bad_param`,
`missing_index`, `oom`, `time_limit`, `tool_crash`); `recovery_rate` (4/7) is
reported alongside as an **informational-only sub-metric, never guarded**
(some declared outcomes are an honest give-up: `gave_up`,
`index_unresolvable`, `approval_timed_out`). **Honest scope:** 7 SYNTHETIC
scenarios, not a field recovery rate; `qc_anomaly`/`no_progress` remain
structurally unreachable, and the wider failure-class catalog (container,
download, disk, permission, missing-reference families) has no scenario yet.
Wired into CI immediately after `eval-guard`. **Still pending:** folding the
unlabeled C1/C3 corroboration signals into one eval number, and a
held-out-accuracy trend over corpus/loop versions.

**Eval data captured:** this *is* the capture loop; it closes over all the above.

**Dependencies:** consumes the outputs of C1 to C5.

---

## C7. Research-use variant annotation & prioritization  ·  M1 + M2 + M3 + M4 + M5 (surface + provenance) SHIPPED (Unreleased) — germline structural verify + provenance, somatic gate, annotation plausibility (both assays), VEP-vs-SnpEff concordance (both assays), "corroborated by" surface + cache/build provenance; M5 C6 eval fold-in still deferred

Add an **annotation** assay: run the annotation step (VEP / SnpEff against ClinVar, gnomAD)
that attaches functional and population context to a call set, and **verify it ran correctly
and reproducibly**. This is the closest capability to "disease work" that stays strictly
Layer-2. Contig surfaces *what the databases reported, attributed to the tool and its DB
version, as research output*; it never adjudicates pathogenicity, issues a clinical verdict,
or makes a diagnosis. See the bright line in [`USE_CASE_UNIVERSE.md`](USE_CASE_UNIVERSE.md)
(lines 33–48, 75–78) and `CLAUDE.md` constraint #4.

**Shipped (M1 slice, Unreleased):** the germline structural verifier is live. A new
`verification/annotation_structural.py` reads the annotated VCF's bytes and emits two
WARN-capped, `kind="structural"` checks — `annotation_present` (a `CSQ`/`ANN` field is
declared and at least one record carries it) and `annotation_complete` (fraction of records
carrying the annotation field; 1.0 → PASS, <1.0 → WARN) — degrading to UNVERIFIED (never a
false pass) when no annotated VCF is found. The annotation tool + version is parsed straight
from the VCF header into a new `AnnotationProvenance` model (C5 provenance pattern), attached
at `_finalize` alongside `reference_identity` and rendered in `contig methods`. Enablement is
one declarative `default_params={"tools": "haplotypecaller,vep"}` line on the germline
`variant_calling` registry entry, injected non-destructively (a user's own `--tools` wins) and
re-injected on rerun/resume. Research-use only: Contig verifies the annotation *executed*,
never adjudicates significance. **Live-cache caveat:** enabling `--tools …,vep` makes sarek
produce an annotated VCF, but a real run's annotation step may still require a VEP/SnpEff cache
(`--vep_cache`/`--download_cache`) or a `--step annotate` entry point that Contig does not yet
wire — when that annotation output is absent the verifier reports UNVERIFIED, so a missing
cache surfaces honestly rather than as a silent success. Test-first; no real VEP/SnpEff/sarek
run in CI.

**Shipped (M2 slice, Unreleased):** the somatic assay gets the same structural verifier and
provenance capture as germline. The `somatic_variant_calling` registry entry's
`default_params` widens `tools` from `strelka,mutect2` to `strelka,mutect2,vep`, injected
non-destructively (a user's own `--tools` wins) and re-applied on rerun/resume — the same
seam M1 used. The shipped M1 structural verifier and `AnnotationProvenance` capture are now
gated to a new `VARIANT_ASSAYS` constant covering both `variant_calling` and
`somatic_variant_calling`, so a somatic run's annotated VCF is verified identically to
germline. Provenance capture at `_finalize` is now gated to the two variant assays (was
unconditional) — a tightening for every other assay; unchanged for both variant assays, and
never dropped for a genuine variant run even when the assay can't be resolved (falls back to
attempting capture rather than silently skipping it).

**Shipped (M3 slice, Unreleased):** annotation plausibility, both assays. A new
`verification/annotation_plausibility.py` parses the consequence terms out of the VEP `CSQ`
or SnpEff `ANN` INFO field (the CSQ subfield index is resolved from the header `Format:`
string; ANN uses SnpEff's fixed layout; multi-transcript comma-separated entries and
`&`-joined terms are both handled) and computes two metrics over the records carrying the
field: `real_consequence_fraction` (share whose most-severe consequence is a real,
non-intergenic term) and `intergenic_fraction`, collapsing each variant to a single
most-severe consequence via a small fixed severity ordering (an unknown non-empty term ranks
as real, never intergenic). A new WARN-capped `ANNOTATION_PLAUSIBILITY_PACK` (not registered
in `_RULE_PACKS`) drives two checks wired into `_discover_qc` for both variant assays:
`annotation_real_fraction` (WARN below 0.10) and `annotation_consequence_distribution` (WARN
above 0.95 intergenic — the "~100%-intergenic" smell). The annotated VCF is located once and
fed to both the structural and plausibility verifiers. The bands are uncalibrated engineering
defaults, deliberately loose so a legitimate high-intergenic run doesn't cry wolf; at most
WARN, never FAIL, no exit-code change; every uncomputable/absent path — no annotated VCF, an
unresolvable CSQ `Format:`, zero annotated records — is UNVERIFIED, never a false pass.
Research-use only: a statistical sanity signal on the consequence distribution, never a
per-variant biological/clinical judgement. Same carried live-cache caveat as M1; no real
VEP/SnpEff/sarek run in CI.

**Why it is moat.** A new assay that compounds the failure/verification corpus (moat #2)
while reusing the shipped three verification axes — structural (C4-style), plausibility
(C3-style), concordance (C1-style) — and the C5 reference-identity provenance pattern. No new
verification primitive, no models, no proprietary data: VEP/SnpEff + the annotation databases
are consumed as-is and get better on their own, so a better base model makes the orchestrator
better, never redundant (`CLAUDE.md` #2/#3).

**What we build (milestones, germline-first per depth-first discipline):**
- **M1 — enable annotation + structural verify (germline).** Enable sarek's built-in
  annotation (`--tools …,vep`) on `variant_calling`; a new `verification/annotation_structural.py`
  verifies the annotated VCF exists and every input variant carries an annotation record
  (`CSQ`/`ANN` INFO present); annotation tool + cache/DB version captured into provenance
  (C5 pattern) and rendered in `contig methods`/HTML. UNVERIFIED (never PASS) when absent.
- **M2 — same verifier, somatic. SHIPPED (Unreleased).** Gate M1's structural verifier +
  provenance to `somatic_variant_calling` (Mutect2/Strelka2 VCFs). New assay gate only.
- **M3 — annotation plausibility (C3-style, both assays). SHIPPED (Unreleased).**
  Annotated-fraction band + consequence-type distribution sanity; WARN-capped,
  UNVERIFIED-when-absent.
- **M4 — annotation concordance (C1-style, both assays). SHIPPED (Unreleased).** VEP vs
  SnpEff per-variant agreement as corroboration, auto-run in the verdict (no CLI flag). A new
  `verification/annotation_concordance.py` enables SnpEff alongside VEP
  (`default_params.tools` → `…,vep,snpeff` on both variant assays, injected non-destructively,
  re-applied on rerun/resume) so one sarek run emits both annotation sets, then emits two
  `kind="concordance"` checks over shared variants keyed on `(CHROM,POS,REF,ALT)`:
  `consequence_concordance` (most-severe-term agreement, **WARN-capped < 0.90, never FAIL**)
  and `gene_symbol_concordance` (**informational-only, always PASS** — VEP/SnpEff symbol
  sources diverge too much for an honest WARN). Both reuse the shipped M3 CSQ/ANN most-severe-
  consequence parser (M3's single-key driver is untouched — M4 owns its own dual-key parse).
  Discovery handles a **two-file** layout (separate VEP/SnpEff VCFs) and a **single-VCF-both**
  layout (one VCF with both `CSQ` and `ANN`), recording the detected layout. Gene-symbol
  normalization is fixed and minimal (case-fold + strip, empty/`.` → unresolvable, no alias
  table); resolvable-only denominator. `RunRecord.annotation_identity` is now a **list**
  capturing both annotators' tool + version (a back-compat validator keeps pre-M4 single-object
  bundles loading), rendered in `contig methods` + an HTML provenance panel. Honest throughout:
  at most WARN, never changes the `verify` exit code; only-one-annotator (e.g. missing SnpEff
  cache), annotation absent, too few shared/resolvable variants, or an ambiguous layout →
  **UNVERIFIED, never a false pass**. Test-first, no real VEP/SnpEff/sarek in CI.
- **M5 — surface + eval fold-in. Surface + provenance SHIPPED (Unreleased); eval
  fold-in DEFERRED.** A pure `verification/annotation_surface.py::corroborated_by_line`
  *reads* M4's `consequence_concordance`/`gene_symbol_concordance` results (never
  recomputes) into a single "Corroborated by VEP and SnpEff: …" line — gene-symbol half
  marked informational, omitted (returns `None`) whenever consequence concordance is
  absent/UNVERIFIED — rendered on the **text report, HTML report, `contig methods`, and
  the Next.js dashboard** concordance card. `AnnotationProvenance` gains a `db_version`
  parsed honestly from the VCF header (VEP `cache="…"` basename token, SnpEff
  `##SnpEffCmd`/`##SnpEffGenomeVersion` genome token; absent → `None`, never fabricated),
  labelled **"cache/build"** (not "database version" — it is the annotator cache/build id,
  not a per-database release), rendered in methods + the HTML provenance panel + dashboard,
  and **round-tripped through the reproduce bundle** with pre-M5 back-compat (legacy
  bundles default `db_version` to `None`). Research-use only; no real VEP/SnpEff/sarek in
  CI. **Still deferred:** folding annotation concordance/plausibility outcomes into the C6
  eval corpus — blocked pending a labeling design for the unlabeled annotation signals.

**Acceptance (test-first):** synthetic annotated-VCF fixtures (tiny VEP-`CSQ` / SnpEff-`ANN`
samples); an annotated call set with records passes the structural check with the tool + DB
version reported; an annotation-missing VCF yields UNVERIFIED, never PASS. Deterministic, no
network, no real VEP/SnpEff/sarek run in CI.

**Eval data captured:** annotation-coverage and (later) concordance/plausibility outcomes per
run and assay join the corpus.

**Dependencies:** reuses C1, C3, C4, C5. Verify-only; research *prioritization* is a
deferred follow-on, not this capability.

**Guardrail:** research-use verification only — no pathogenicity/clinical verdict of our own,
ever. See [`../planning/variant-annotation-assay/prd.md`](../planning/variant-annotation-assay/prd.md).

---

## C8. Reproduce & verify *existing published* work  ·  first slice SHIPPED v0.40.0 + output-locator slice 1.5 SHIPPED v0.41.0  ·  M7+

Point the shipped run → self-heal → verify → reproduce engine at a **third-party,
already-published** bioinformatics repository (a paper + its code/data) and report which of
the paper's stated numbers, tables, and figures **actually regenerate** — ending in a signed,
re-runnable verdict, exactly like a first-party run. This is not a new assay; it is the same
Layer-2 engine turned around to face *other people's* published analyses.

**Shipped (first slice — walking skeleton, v0.40.0).** `contig reproduce <repo> --run "<cmd>"
--claims <file>` runs a repo's script and reports a **per-claim** verdict — `REPRODUCED` /
`WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED` — over **scalar numeric** claims, ending in a
signed, re-runnable bundle. A new `verification/reproduce.py` (`load_claims`/`classify`/
`run_reproduction`/`reduce_reproduction`) + `ClaimResult`/`ReproduceRecord` models drive it;
classification **reuses `benchmark._relative_delta`** (`|Δ| ≤ 1e-9` → REPRODUCED, else
`rel_delta ≤ tolerance` → WITHIN-TOLERANCE, else DIVERGED; non-finite / missing / non-zero-exit →
UNVERIFIED, never a false pass). The regenerated value is bound from a repo-written flat
`results.json` `{claim_id: value}`. The record is signed by the **existing generic**
`_maybe_write_signature` (no fork, no `RunRecord` pollution) when `CONTIG_SIGNING_KEY` is set, plus
a `reproduce.json` invocation manifest; `runner.default_command_executor(cmd, cwd)` runs the script
in the repo dir. `--fail-on-diverged` is an opt-in exit-code gate. **Honest scope:** research-use,
computation-vs-numbers only (never the paper's conclusions), no raw-read egress; slice 1
reproduces **cooperative** repos (those that emit `results.json`) and degrades an uncooperative one
to UNVERIFIED; test-first, **no real third-party repo or network in CI**. **Deferred:** the
claim-level output-locator to read numbers out of a repo as-is (slice 1.5 — now **shipped**, see
below); **environment resurrection** (`ModuleNotFoundError` → install → retry, reusing C2) (slice
2); paper-parsing to extract claims; **figure/plot and table-cell claims** (see the correction
below); remote `<doi|url>`; a dashboard card; and the C6 eval fold-in.

**Shipped (output-locator — slice 1.5, v0.41.0).** A claim may now carry an optional locator
`{"from": <repo-relative JSON file>, "path": <expression>}` naming where its number already lives
in the repo's own **structured JSON** output, instead of requiring the repo to hand-write a flat
Contig-shaped `results.json`. This is the exact slice the slice-1 review gate named as what turns
`contig reproduce` from a fixtures/cooperative-repo demo into a tool that reads **real, unmodified
cloned repos** — the "externally-credible" step. A new pure stdlib walker
(`verification/reproduce.py::resolve_pointer` + `_parse_path`) — dotted segments + `[n]` list
indices, leading `$.`/`$` tolerated, strict dict/list `isinstance` guards, **never raises** (any
unresolved/malformed step → `None`) — resolves the value; `run_reproduction` branches so a located
claim binds from its own file (parsed once, cached per run) and classifies through the **unchanged**
`classify`, while a locator-less claim keeps the byte-identical slice-1 flat lookup (mixed files
allowed). Every locator failure — missing/unparseable/non-UTF-8 `from` file, unresolved `path`,
non-numeric target **including a numeric *string* (strictly UNVERIFIED, never coerced)**, bool, or
non-finite — is `UNVERIFIED`, never a false pass, never `DIVERGED`. Safety: an escaping/absolute
`from` is refused at the CLI **before any run** (exit non-zero, no record) reusing the `--results`
containment guard, and the engine defensively never reads outside the repo. No new dependency
(stdlib-only holds); no model/verdict/exit-code contract change; `claims_sha256` already covers the
locators. **JSON only** this slice — stdout/CSV/notebook/figure numbers still degrade to UNVERIFIED
honestly. **Deferred:** a TSV/CSV locator (the named next step); slice 2 (environment resurrection)
and everything after it (unchanged from the slice-1 list above). Test-first (walker → `load_claims`
→ engine → CLI); deterministic; no real repo or network in CI.

**Correction to the build surface below (verified against the code, 2026-07-18):** the sentence
"reuses the existing float-tolerance / plot-hash / seed-aware diffing" was only one-third true.
The **float-tolerance** compare is real (`benchmark._relative_delta`) and is reused; **plot-hash
does not exist anywhere in the repo**, and adding perceptual-image-hashing would break the
deliberate stdlib-only dependency contract (`pydantic`/`typer`/`cryptography` only); **seed-aware
diffing** is not a named mechanism (the closest thing is a tolerance band absorbing run-to-run
noise). That is the hard technical reason **figure/plot claims are out of scope** until a
deliberate dependency decision — not a preference.

**Why it is moat.** Two compounding wins, both already prized by the ROADMAP:
- **The strongest quantified pain of the whole verification thesis.** Of **27,271**
  biomedical-paper notebooks, only **~879 (~3.2%)** reproduced the original result
  (Samuel & Mietchen, *GigaScience* 2024); Pimentel's 1.4M-notebook study finds **~4%**
  reproduce their own outputs; the best agent scores **21%** on CORE-Bench (code+data
  *provided*). CODECHECK proves the demand exists but is done **by hand**. No tool parses a
  paper to extract every numeric claim and aligns it to a *generated* artifact.
- **The cheapest acquisition channel we have (Principle #5).** "I ran 50 published papers'
  code — here is how many reproduced, and why" is Biostars / r/bioinformatics / nf-core
  reputation in a bottle, and a free, viral top-of-funnel that feeds paying Layer-2 usage.

A better base model makes the claim-extraction and the environment-resurrection *better*,
never redundant — the verdict and the reproduce guarantee are the durable part.

**What we build:**
- **Environment resurrection (the load-bearing piece).** Reconstruct a runnable environment
  for an *uncooperative* existing repo from a **traced real execution** (observed imports /
  loaded versions), not a trusted manifest — ModuleNotFoundError / ImportError + dependency
  installs are ~76% of reproduction failures. Reuses and extends C2's self-heal and the
  container/pin machinery.
- **Claim-to-artifact alignment.** Parse the paper (or a claims file) for numeric
  claims — a reported statistic, a table cell, a figure — and semantically diff each against
  the regenerated artifact with the existing float-tolerance / plot-hash / seed-aware diffing.
- **A per-claim verdict** (`REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`) and a
  signed, re-runnable bundle — the same honesty contract as every verdict (UNVERIFIED is never
  rendered as reproduced).
- A **`contig reproduce <repo|doi>`** surface (CLI + dashboard card), community-facing and free.

**Acceptance (test-first):** a synthetic repo whose script regenerates a known figure/number
yields a `REPRODUCED` verdict per claim; a deliberately drifted dependency or altered constant
yields `DIVERGED` with the exact claim and the observed-vs-stated values named; a repo with an
unresolvable environment yields `UNVERIFIED`, never a false reproduce. Deterministic, no network.

**Eval data captured:** every reproduction attempt (the environment-repair chain, the
per-claim diff outcome) is a labeled corpus case — a whole new, publicly-sourced stream of
failure-and-fix data feeding C6.

**Dependencies:** builds on C2 (self-heal / environment repair), C5 (input-data integrity),
C6 (eval flywheel), and the shipped reproduce bundle. Verify-and-reproduce only.

**Guardrail:** we report whether the *computation* reproduces the paper's stated numbers; we
never issue a scientific judgement on whether the paper's *conclusions* are correct. No
raw-data egress — runs on the user's / CI compute; only hashes and claim diffs leave the box.

---

## Sequencing summary

| ID | Capability | Window | Leverage |
|----|-----------|--------|----------|
| C1 | Cross-tool concordance verification | SHIPPED v0.2.0 + RNA-seq slice (Unreleased) + somatic slice (Unreleased) + single-cell slice (Unreleased) | Verdict trust, novel primitive (germline `--concordance-vcf` + RNA-seq `--concordance-counts` Spearman/fraction-agreeing/overlap + somatic auto `somatic_site_overlap` PASS-site Jaccard, Mutect2 vs Strelka2, no user input + single-cell `--concordance-sc-counts` pseudobulk gene-level Spearman/fraction-agreeing over a stdlib `.mtx` triplet loader + single-cell **autorun** `--concordance-sc-counts-auto` running STARsolo behind an injectable seam, turnkey; single-cell cluster-stability deferred) |
| C2 | Self-heal breadth plus auto resource-scaling | M2 to M3 (resource-aware + single-file missing-index family `.fai`/`.bai`/`.tbi`/`.csi`/`.dict` shipped; chr-prefix GTF harmonization shipped; per-contig alias harmonization (mito `M`↔`MT` + GRCh38 scaffold seed) shipped; directory-shaped STAR index build+redirect shipped, classic BWA + bwa-mem2 detector+corpus-only (v0.11.0); peak-RSS-informed OOM memory scaling shipped (Unreleased, honest two-tier: own-peak → blind fallback; sibling rescue deferred); walltime-informed `time_limit` scaling shipped (Unreleased, floored at blind — censored realtime, tail-only win + field instrument); **input-format-conversion class's first slice shipped (Unreleased): bgzip'd (non-BGZF) reference FASTA self-heal, sarek-scoped (rnaseq immune by construction), stream-decompress to uncompressed `.fa` + retry; CRAM↔BAM conversion is the deferred second half**; bwa-mem2/classic-BWA build+redirect, assembly-signature + exhaustive per-assembly alias completeness pending) | Unattended-completion rate, corpus fuel |
| C3 | Biological-plausibility verification | SHIPPED v0.3.0 (germline) + RNA-seq (v0.6.0) + single-cell ingestion (Unreleased) + germline sex-check (Unreleased) + RNA-seq mapping-composition (Unreleased) + germline variant-count (Unreleased) + germline plausibility FAIL-severity (Unreleased) + somatic empty-call-set FAIL floor (Unreleased) + RNA-seq plausibility ingestion fix (Unreleased) | Verdict gets smarter about biology (germline Ti/Tv, het/hom, sex-check, variant-count band — germline Ti/Tv, het/hom, and variant-count now **FAIL** on gross implausibility via WES-safe bands; somatic `variant_count` now **FAILs** on an empty call set; a FAIL verdict reaches the exit code only under the opt-in `--fail-on-verdict`; RNA-seq `duplication_rate` now correctly keyed to MultiQC's `PERCENT_DUPLICATION`/a 0-1 fraction — informational-only, no band by design — after never once firing under its old wrong key/unit; `rRNA` remains a guessed slug, WARN-capped; + exonic/intronic/unassigned read-composition from RSeQC read_distribution; single-cell cell-QC now *fires* via STARsolo/Cell Ranger ingestion — was a dormant no-op; gene-body-coverage/mito/doublet deferred; **somatic-VAF and RNA-seq FAIL severity declined by design, not deferred** — tumor VAF's expectation depends on unobserved purity/clonality, and every RNA-seq extreme is a legitimate protocol; annotation-pack FAIL severity is a separate C7 item, still deferred) |
| C4 | New assay: somatic variant calling | SHIPPED v0.13.0 (intake→launch→verify) + VAF/count/PON plausibility slice (Unreleased) + Strelka2-vs-Mutect2 concordance slice (Unreleased) + Strelka2-native VAF slice (Unreleased) + empty-call-set FAIL floor (Unreleased — `somatic_variant_count fail_below: 1`; **VAF/PON FAIL bands declined by design, not deferred**: tumor VAF depends on unobserved purity/clonality, `strelka_median_vaf` is bounded to [0,1] so a ceiling is dead code, `pon_applied` is a non-numeric 3-state string); swapped-pair smell test + PON reference wiring deferred | Breadth, depth-first, new corpus |
| C5 | Reference and input-data integrity | M5 (reference-identity **capture** slice shipped — explicit `sha256` + iGenomes key-only, rendered in methods/panel; pre-flight **mismatch detector**, known-sites, GTF version, RO-Crate pending) | Kills a silent-failure class, deepens reproduce |
| C6 | Eval flywheel as a continuous loop | M6 (detector held-out guard slice 1 SHIPPED, Unreleased — honestly 0.833/10:12, two classes structurally unreachable; repair-loop outcome-match guard slice 2 SHIPPED, Unreleased — honestly 1.0/7:7, 5 classes covered; both wired into CI; folding C1/C3 signals + held-out-accuracy trend pending) | Compounding accuracy from real runs |
| C7 | Research-use variant annotation & prioritization | M1 + M2 + M3 + M4 + M5 surface+provenance SHIPPED (Unreleased) — germline structural verify + provenance, somatic annotation gate, annotation plausibility (both assays), VEP-vs-SnpEff concordance (both assays: `consequence_concordance` WARN-capped + `gene_symbol_concordance` informational, auto in the verdict, both VCF layouts, annotator-version provenance pair), M5 "corroborated by" line across text/HTML report + `contig methods` + dashboard (reads M4 results, never recomputes) + `AnnotationProvenance.db_version` cache/build token (VEP `cache=` / SnpEff genome) rendered and round-tripped through reproduce with pre-M5 back-compat; **M5 C6 eval fold-in still DEFERRED** (blocked on labeling design) (germline+somatic `annotation_present`/`annotation_complete` structural checks via `VARIANT_ASSAYS`, `AnnotationProvenance` tool+cache/build capture, `--tools …,vep` enablement on both assays, `annotation_real_fraction`/`annotation_consequence_distribution` plausibility checks, all WARN-capped/UNVERIFIED-when-absent; live run may still need a VEP/SnpEff cache Contig does not yet wire — absent annotation degrades to UNVERIFIED, never a false pass; verify-only, prioritization deferred) | Disease-research breadth on-thesis, new corpus; run+verify annotation, never a clinical verdict |

| C8 | Reproduce & verify *existing published* work | first slice SHIPPED v0.40.0 + output-locator slice 1.5 SHIPPED v0.41.0 · M7+ | Turns the engine on third-party papers (repo+claims → per-claim `REPRODUCED`/`WITHIN-TOLERANCE`/`DIVERGED`/`UNVERIFIED`); strongest quantified pain (~3.2% of 27,271 notebooks reproduce), a free viral community-trust channel, and a new publicly-sourced corpus stream. **Shipped:** `contig reproduce <repo> --run --claims` walking skeleton — scalar per-claim verdict reusing `benchmark._relative_delta`, values bound from a repo-written `results.json`, signed re-runnable bundle via the generic signer, `--fail-on-diverged`; cooperative-repos-only, UNVERIFIED-when-unresolved, no real repo/network in CI. **+ Output-locator (slice 1.5):** a claim may carry `{"from": <repo JSON>, "path": "$.a.b[0]"}` to read numbers out of a repo's own **structured JSON as-is** (a new stdlib dotted+`[n]` `resolve_pointer` walker that never raises; located claims classify through the unchanged core; numeric-string strictly UNVERIFIED; escaping `from` refused pre-run + engine never reads outside the repo; JSON-only, full back-compat, no new dep). **Deferred:** TSV/CSV locator (next step), env-resurrection from a traced execution (reuses C2), paper-parsing, figure/plot & table-cell claims (**plot-hash does not exist and can't be added without breaking the stdlib-only dep contract**), remote `<doi|url>`, dashboard card, C6 fold-in |

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
