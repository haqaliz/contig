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
FAIL severity on calibrated bands; a dashboard "corroborated by" line. (The
second-quantifier **autorun** has since shipped — see the single-cell autorun slice
below.) *(The pre-band capture prerequisite for calibration shipped in the
`eval-concordance-capture` slice — calibration itself remains gated on real-run
accumulation.)*

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
**Shipped (heartbeat stall watchdog — the `no_progress` slice — Unreleased):** the first
handling for a run that **never exits**. `default_executor` is a blocking `subprocess.run`, so
nothing observed a run in flight: a hang — a deadlocked tool, a wedged network mount, a
container stuck on a socket — never returned, never raised `PipelineExecutionError`, and never
reached the detector. It sat there consuming the user's compute until a human noticed, which is
the failure mode most directly opposed to the ROADMAP's unattended-completion metric. An
**opt-in** watchdog now supervises the child: `--detect-stalls` (default **off**) plus
`--stall-timeout` (seconds, default **3600**). `--stall-timeout` without `--detect-stalls` is
**refused, not silently ignored** (the C8 slice-7 `--rev` posture); because `3600.0` is both the
default and a legal explicit value, "was it passed?" is read off Click's
**`get_parameter_source`**, not off the value — pinned by a test that passes the default
*explicitly* and asserts refusal, which a value-comparison implementation would fail while
passing every other test in the diff. **A composite heartbeat, so a healthy-but-slow run is
never touched:** the run counts as alive if **any** of `trace.txt` (mtime+size),
`.nextflow.log` (mtime+size), or `run.log` (size) moved since the last poll, and a stall
requires **all three** silent for the whole window — a trace-only signal goes dark for the
entire duration of any single long task, which would make a legitimate 14-hour WGS alignment a
false positive. The decision is a **pure** function (`stall.py::evaluate_stall`, in the
`resource_sizing.py` mould) over two fingerprints, an injected clock, and the timeout — no
subprocess, no sleeping, no filesystem — and a non-positive timeout **can never stall**, so a
mis-wired watchdog fails safe. **The observer cannot be hung by the failure it detects:**
`stat()` against a hard-mounted unresponsive NFS blocks in uninterruptible sleep, and a wedged
mount is a headline stall cause, so the read runs in a **daemon** thread under a 5 s deadline
and a missed deadline keeps the previous fingerprint — which reads as "no progress observed".
The run.log verdict write is bounded the same way, since it lands on the same possibly-wedged
mount. **Termination:** `Popen(start_new_session=True)`, poll, and on a stall write the verdict
to `run.log` **before** killing (it is the detector's only evidence that the run stalled rather
than merely crashed), then SIGTERM → 5 s grace → SIGKILL over the child's **process group** —
Nextflow's JVM and tool children, not just the launcher — **at most once per attempt**. The
30 s poll wait is taken in short slices and abandoned the moment the child exits, so the
self-heal loop's fast failures (bad argv, missing reference) are not charged a full interval per
attempt. **The `no_progress` detector branch sits AHEAD of the OOM check, deliberately**,
reversing a standing "OOM wins outright" comment: `detect.py` matches `any(e.exit == 137)` from
the **events alone**, so a dying Nextflow writing an exit-137 trace row as it is torn down would
beat any branch placed below it, whatever the log says. The branch keys on three phrase-level
needles — "no forward progress", "no new output or trace update", "terminating the stalled run" —
**every one of them a phrase `stall_message` itself emits**, pinned by a test so no future needle
can be added that Contig never writes. What makes the branch **generalize** is not a needle
written for the corpus but the fact that **our own wording is ordinary English**: the
independently authored frozen `holdout-no-progress-1` fixture, whose text credits a **non-Contig**
actor ("the progress monitor terminated it as stalled"), hits two of our three needles
**verbatim** and classifies through exactly the rule our own message does. That is the strongest
available evidence the rule is not fitted to our string. (A fourth needle, "terminated it as
stalled", was carried for a while on the belief that the fixture needed it; it was **dropped as
redundant** once measurement showed the fixture classifies without it, removing the most generic
phrase in the tuple at zero cost to classification.) **First-party uniqueness is nonetheless
given up, and the residual risk is real and unenforced:** phrases generic enough for an
independent author to hit are generic enough for a third-party tool to emit, nothing constrains
them to output Contig wrote, so foreign text containing one classifies as `no_progress` — and
because this branch sits above the OOM check it out-ranks a genuine `exit == 137` (measured: an
exit-137 event whose log reads `java: watchdog reports no forward progress in scheduler loop`
classifies `no_progress`, not `oom`). We take that trade knowingly, and keep the tuple as small
as the shipped fixtures allow, because every phrase in it is false-positive surface charged
against **every** diagnosis Contig makes.
A module-level test pins that the emitted message contains none of `killed` / `oom` /
`out of memory` / `time limit`, and a control test proves a **genuine** OOM (both the exit-137
and the "out of memory" text paths) still classifies `oom` when no stall sentinel is present.
`propose_patches` gains a `no_progress` → `kind="retry"`, `risk="safe"` patch: `self_heal_run`
already passes `-resume`, so the retry reuses cached tasks, is bounded by `--max-attempts`, and
ends in an honest `gave_up` rather than a dressed-up recovery. **A regression this slice caused
and then fixed, recorded because it is exactly the harm the feature exists to prevent, entering
by a different door:** detaching the child into its own session (necessary so the watchdog can
`killpg` the pipeline without killing Contig itself) silently removed it from the group
`contig cancel` reaps, and left Ctrl-C stopping the *supervisor* while the pipeline kept burning
compute — an orphaned child was reproduced empirically, by pid. Both were caught in review and
fixed before merge: the child's pgid is published into `status.json` and `cancel_run` reaps it,
and the executor terminates the group on `BaseException` before re-raising. **Wiring, small by
design:** `self_heal.py` is **unchanged** — the CLI builds the watchdog through the existing
`Executor` seam (one production line), so all 38 test injection sites keep working untouched,
and with the flag absent the executor is the unmodified `default_executor`. **D4 — the settings
are deliberately NOT persisted to `LaunchManifest`:** a stall is a property of the machine and
its I/O, not of the analysis, and baking a timeout into a reproducible manifest would make
replay depend on the original host's speed. Because the settings are runtime-only rather than
replayed from the manifest, they have to be passed again on each invocation — so a **follow-on
slice** put the same two flags on `rerun` and `resume` behind one shared validator, since the
most natural gesture after a stall (`contig resume <id>`) had otherwise run *without* the
watchdog. All three commands validate identically and **before** any filesystem work, so a flag
mistake reports the flag mistake rather than a missing manifest. **Honest limits, stated as
limits:** (1) this is **push, not demand-pull** — no design partner asked for it and **no real
Contig run has ever been observed to hang**; the architectural gap was documented
(`ARCHITECTURE.md:203`, the `FailureClass` literal, a frozen held-out fixture), but the
**frequency is unmeasured** and nothing here claims otherwise. (2) The **1-hour default window
is reasoned, not calibrated** — no measurement of real inter-heartbeat gaps exists; the observed
idle seconds, the configured window, and which surfaces were silent ride in the stall message as
the field instrument that can later replace the guess with data. (3) **No real Nextflow anywhere
in CI.** The terminate mechanics *are* genuinely exercised against **real child processes**
(a hanging child is terminated and its exit code asserted `-15`, explicitly `!= 137`; a
SIGTERM-ignoring child is SIGKILLed after the grace; a Ctrl-C leaves no orphan; the executor's
**real** run.log bytes are fed through the shipped `diagnose_failure`) — but what a SIGTERMed
**Nextflow** returns, and what it writes into `trace.txt` for in-flight tasks, is **reasoned**
and remains for the manual pre-merge gate, as does whether `-resume` correctly re-runs a
SIGKILLed task rather than treating a partial output as cached. (4) **The accuracy move is
partly self-graded:** we made reachable a class whose fixture we wrote. It evidences that a
documented taxonomy gap closed; it is **not** evidence that the watchdog helps a real user, and
the two must not be conflated. (5) **A failing observer degrades to "no progress observed"** —
so a buggy *injected* observer can get a HEALTHY run terminated after enough polls, where
previously it crashed loudly. The shipped `read_heartbeat` catches every `OSError`, so this is
theoretical today, but it is a **real semantic loss recorded as a trade, not a free win**: a
timeout means the filesystem is wedged (evidence *about the run*), while an exception means the
observer is broken (**no** evidence about the run), and collapsing them discards that
distinction. (6) `proc.wait()` after SIGKILL is **unbounded** on a child wedged in
uninterruptible sleep; `lifecycle._terminate_process_group` carries the same pre-existing
exposure. (7) `poll_interval` is a **sleep, not a deadline** — a slow observation extends the
effective period rather than being subtracted from it (immaterial at 30 s against a 1 h window).
(8) **Cancel timing changed:** `wait_seconds` is now spent once **per process group**, so
cancelling a watchdog run can take up to **2×** as long; deliberately not restructured (cancel
is a rare admin action), only documented. (9) **Nextflow is the tested scope.** The seam sits
above the engine branch in `_build_engine_run`, so the mechanism applies to Snakemake for free
via `run.log` liveness alone — that is **untested and must not be advertised as support**, and
is not silently refused either. **Deferred / revisit trigger:** calibrating the window on real
runs; a stall-specific escalation (widen the window per attempt, or give up after two stalls at
the same point) — no precedent to reuse; a dashboard surface; per-task stall detection
(Nextflow owns task-level retry); and **on-by-default operation**, whose revisit trigger is
committed: the first real report of a false positive keeps it off/loosens it, N real stalls
recovered makes it worth reconsidering.
**Shipped (stale-index slice — Unreleased):** an index that is OLDER than the data it
indexes — the htslib `hts_idx_load3` family's `[E::hts_idx_load3] The index file is older
than the data file: X` — previously died as an opaque `tool_crash` (the message carries no
absence phrase, so the generic missing-index branch missed it entirely), and its inverse,
an absence+staleness mashup ("is missing **or** older than the data file"), was swallowed
by the generic branch and aimed a rebuild at an index that already exists. A new detector
branch now classifies the stale flavor `missing_index` **first**: AND-guarded on a
freshness phrase (`"older than"`) **plus** an index token (`.fai`/`.bai`/`.tbi`/`.csi` or
"index file"), ordered **before** the generic notfound branch so a "missing or older"
message classifies stale-first (the rebuild+replace repair covers both flavors), emitting
`root_cause="An index file is older than the data it indexes."` at confidence 0.85. The
repair dispatches on **evidence, not a model change**: `_is_stale_evidence` scans the
diagnosis's evidence lines for the freshness phrase, so `Diagnosis` gains no field and the
signed record is untouched — **no signature break**. The stale sidecar is rebuilt into
run-scoped scratch (`<run_id>/healed_index/<kind>`, fresh-wiped, STAR precedent) by
**symlinking the resolved source into scratch** and running the **unchanged** `_INDEX_BUILD`
argv against the symlink, so the tool's sidecar lands in scratch next to its input; only on
rc 0 **and** a produced artifact (honest "exited 0 but produced no index" give-up
otherwise) does `os.replace` atomically swap the user's stale file — a cross-device
`OSError` falls back to a same-dir dot-temp copy + rename (same filesystem by
construction), fallback failure is an honest `index_build_failed`, and the user's file is
**never half-written**. Build-once-per-path bounds the loop; `index_unresolvable` covers
an unparseable path or unresolvable source. Success reuses the `built_index_and_retried`
outcome literal with old/new mtimes and the applied argv in `RepairStep.detail`. One
golden `stale-bai` corpus case (`case_id: "stale-bai"`, seeded per the family's one-per-kind
tradition) and one `stale-index-heal` heal-guard scenario (21 scenarios, `covered_classes`
15 unchanged — `missing_index` was already covered, this adds a scenario not a class;
baseline refrozen as a deliberate act, `corpus_sha 4afc3513…`). The scenario's real repair
caught and fixed an integration bug the unit tests could not: the dangling scratch
**symlink** to the data file would trip the retry's QC `**/*.bam` glob on an otherwise
green run, so the scratch kind-dir is removed on success (the `healed_index` root is kept
when non-empty, so a STAR scratch sitting alongside survives). Read honestly — push, not
demand-pull: organic frequency is unmeasured and no real Contig-launched run has ever
produced this failure (the field corpus has only ever diagnosed
`oom`/`tool_crash`/`missing_index`/`unknown`); the needle is **reasoned, not observed**
(no real nf-core in CI; a non-matching stale message still degrades to `tool_crash`); and
`samtools faidx` silently rebuilds a stale `.fai`, so the hard-fail surface this actually
helps is the htslib `hts_idx_load3` family (`.bai`/`.csi`/`.tbi`), with `.fai` covered
defensively. The wrong-reference index masquerade stays out of scope (mtime cannot
distinguish it).
**Shipped (alignment-format detector slice — Unreleased):** the input-format-conversion
class's second half (CRAM↔BAM) ships as the **detector-only** `alignment_format_mismatch`
slice, by the bwa-mem2 verdict: **no Contig-launched run can produce a CRAM/BAM format
failure today** — the samplesheet models are FASTQ-only (`samplesheet.py:11-15, 18-32`; a
BAM/CRAM sarek sheet is refused at pre-flight as missing `fastq_1`), the launch argv is
mechanically `--key value` over params, and even a hypothetical alignment-input seam would
be suppressed by sarek's wired `--fasta` reference. A new `FailureClass` literal (18 → 19)
plus a narrow branch — AND-guarded on a CRAM-specific decode phrase (`cram_decode_slice` /
`for cram decoding` / `required for cram`) plus a `.cram` token, placed after the
`reference_not_bgzf` branch and before the `tool_crash` fallthrough, confidence 0.85 — names
the class that previously died as a 0.4 `tool_crash`. Two control tests pin the boundaries
both ways (a stale-index log still classifies `missing_index`; a CRAM line containing an
absence phrase still classifies `alignment_format_mismatch`). One golden training case
(htslib framing) + one **independently authored holdout twin** (GATK framing, written
before the needles); `eval-guard` refrozen deliberately at **92.9% (13/14)** — a
composition change, not an improvement, only miss unchanged (`holdout-qc-anomaly-1`). One
heal-guard give-up scenario drives the real loop to honest `gave_up` (no patch by design);
`covered_classes` 15 → **16**, outcome-match still 1.0 over 22 scenarios; both baselines
refrozen via `--update-baseline` as deliberate acts. Dashboard `FAILURE_CLASSES` synced
(19, Python order). **Honest limits:** push, not demand-pull; organic frequency unmeasured;
needle reasoned-not-observed; self-graded fixtures; **recovers nothing** — the CRAM→BAM
conversion repair stays deferred behind a committed revisit trigger (first real CRAM-format
failure in a Contig-launched run, or an alignment-input seam), BAM→CRAM out of scope. No
verdict/exit-code/manifest/signature change; no new dependency.
**Deferred to later C2 slices:** bwa-mem2 **build/redirect** (detection shipped v0.11.0;
build blocked until a live trigger exists) and the classic-vs-mem2 aligner-mismatch heal;
classic-BWA index build/redirect (needs a supported `bwa index` target, e.g. sarek
`--aligner bwa-mem`); a corrupt/partial STAR index signature; the still-missing single-file
index kind (the BAM/CRAM form of `.csi`); and the wider failure catalog — the
assembly-signature form of reference/build mismatch (no sample-side contig signal in raw
FASTQ or finished bundle), exhaustive per-assembly alias-table completeness beyond the
GRCh38 seed, known-sites/GTF-version consistency, a runtime `reference_mismatch`
detector-corpus case, CRAM↔BAM conversion (the input-format-conversion class's second
half), and pin conflict. Also deferred, filed by the inert-repair-honesty slice (C2), none
fixed here: ~~**(a)** `read_task_errors` hardcodes `Path(run_dir)/"work"` (`runner.py:1077`)
while Nextflow is actually given `target.work_dir` (`nfconfig.py:100`) — the detector goes
blind on a custom `--work-dir`;~~ **CLOSED (Unreleased, `self-heal-custom-work-dir` — see
the CHANGELOG).** `read_task_errors` now takes the work dir as a **required** argument and
`run_dir` is removed (a retained fallback would have been production-dead code keeping the
wrong-place lookup reachable); a remote work dir yields a self-labelled,
salient-token-bearing note instead of `""`; and both halves of the `self_heal.py:1310` log
expression were made raise-safe. The citation above was stale — the real site was
`runner.py:1198`. Honest limits: **push, not demand-pull**; **reasoned, not observed** (no
real Nextflow/Batch in CI, the real-run smoke is a manual gate); and **AWS Batch remains
structurally undiagnosable** (an `s3://` work dir cannot be read locally at all) — the
slice makes that limit visible, it does not fix it; **(b)** `risk="destructive"` is a no-op to the engine — no
code branches on it and `--auto-approve` has no carve-out, so only the dashboard honors it;
**(c)** `_write_pending_choice` (the ambiguous-choice gate) has no advisory branch and still
writes `operation` unconditionally — unreachable today, since all four advisory classes are
single-candidate at confidence ≥ 0.7 while `_is_ambiguous` needs <0.5 or >1 candidate, and if
one ever reached it `apply_patch`'s advisory guard raises loudly rather than silently
re-enacting; **(d)** PRD R-Open-4 — `dashboard/lib/derive.ts`'s `FAILURE_CLASSES` (the corpus
relabel dropdown's source of truth, server-validated in
`dashboard/app/api/corpus/promote/route.ts`) still omits `disk_full`, `permission_denied`,
`download_failed`, `reference_not_bgzf`, and `missing_dependency` — pre-existing, not
introduced by this slice, but now more than a stale mirror: a human reviewing a pending case
cannot promote it labelled `disk_full` or `permission_denied`, two of the four classes this
slice just made advisory-honest, so the relabel channel that would let a human correct a
misdiagnosed case before it is counted has no route to either label, leaving the §"Revisit
trigger" (a) grouping of `runs/pending_corpus.jsonl` by `failure_class` dependent solely on
the detector's raw (possibly wrong) diagnosis for these two classes;
**((d) is now CLOSED — verified Unreleased: `dashboard/lib/derive.ts:278-299` mirrors all 20 `FailureClass` literals, including `disk_full`, `permission_denied`, `download_failed`, `reference_not_bgzf` and `missing_dependency`. The prose above is stale; do not re-pick it.))**
**(e)** the enacted
`container_unavailable` wait leaves no trace in the record — `self_heal.py:1452-1458` sleeps
`wait_seconds` but `RepairStep.detail` stays `None`, so no surface says "waited 15s". This is
an *under*-claim (the record says less than what happened), and fixing it is a behaviour
change deliberately left out of this slice's scope.

**Resolved (Unreleased) — the five INERT repair strategies (filed by the C6 catalog-coverage
slice against C2), four made honest advisories, one genuinely enacted.** `propose_patches`
used to emit a patch for `disk_full`, `permission_denied`, `conda_solve_failed`,
`platform_unsupported` and `container_unavailable` whose stated operation was performed by
**nothing**, so the loop recorded propose → "apply" → `patch_applied=True` → retry →
**`Repaired`** having done nothing. Two mechanisms: the first four were `kind="env"` patches
whose operation string-merged into `target.backend_options` (`self_heal.py:610-613`) where
`nfconfig.py:71-98` reads only `queue`/`region`/`partition`/`account`/`qos`/`time` — so
`clean_work_dir`, `fix_permissions`, `relax_or_pin_env` and `use_native_arch_backend` were
written and never read; `container_unavailable` was `kind="retry"` (`repair.py:50`), for which
`apply_patch` is a **documented** no-op, so its `wait_seconds: 15` never reached
`backend_options` at all. That was **one layer below** the bug v0.49.0 fixed: `patch_applied`
was already honest about *enactment*, but enacting a no-op still rendered as a repair on every
surface.

**The first question was propose-vs-don't, not how-to-implement, and it resolved differently
per class.** `repair.py:173-176` already said of `permission_denied` that *"only a human can
decide and do that safely"*, and `platform_unsupported`'s own rationale said re-running here
won't help — so the four `env` classes became a new `Patch.kind = "advisory"`: a diagnosis
plus human-executable guidance, never machine-applicable, with the inert operation withdrawn
rather than reassigned. The self-heal loop now branches on `kind == "advisory"` **before** the
applier; `apply_patch` raises if one ever reaches it (defensive, unreachable in practice). An
approved advisory records the deliberately observational `advisory_acknowledged_and_retried`
(Contig cannot verify the human actually fixed anything, only that they approved and the retry
ran) with `patch_applied=False` and `recovered=False` — the recovery is attributed to the
human, which is what happened. `--auto-approve` (no human in the loop) now makes an advisory
`gave_up` honestly with the rationale and **no retry**, rather than re-entering the same false
claim through the unattended path. The approval gate (`pending_approval.json`) stops
serializing an `operation` dict for work Contig will not do. `container_unavailable` was the
weakest member and did split from the other four: a bare retry is a legitimate fix for a
transient runtime outage, so only its decorative field was dishonest, not its premise — it now
**genuinely waits** `wait_seconds` through an injected clock seam (precedent: the stall
watchdog's `sleeper: Callable[[float], None]`, `runner.py:679`) threaded through
`self_heal_run` **and** `heal.py`'s evaluator, so CI never really sleeps.

`heal-guard` `covered_classes` moved **11 → 15** (`disk_full`, `permission_denied`,
`conda_solve_failed`, `container_unavailable` newly covered; `platform_unsupported` stays
deliberately **un**covered — reaching it needs a failed event with `exit is None`
(`detect.py:355`), but `AttemptSpec.exit` is a required `int` (`models.py:543`) used as both
the trace column (`heal.py:82`) and the executor return code (`heal.py:100`), an additive
model/driver change out of scope here), guarded outcome-match held at **1.0** over 20
scenarios, `heal_baseline.json` refrozen as a deliberate act
(`--update-baseline`, never a hand-edit). The pinning guard that reddened on any change
(`tests/test_repair.py::test_five_inert_patch_operations_are_still_consumed_by_nothing`) is
**retired deliberately**, not deleted for green, and replaced by one pinning the new contract:
no advisory carries a withdrawn operation key, and `wait_seconds` is consumed.

**Read honestly, against our own interest — every metric that could flatter this is either
unmoved or moved for a reason that is not "more failures recovered."** This is push, not
demand-pull, and now demonstrably so: **0 of 20** pending-corpus cases and **0 of 15** real
runs were ever diagnosed into any of these five classes — the only classes ever diagnosed in
the field remain `oom`, `tool_crash`, `missing_index`, `unknown`. `eval-guard` **cannot move
and did not**: nothing here touches a detector or a corpus, and the pending-corpus append
(`self_heal.py:1124-1133`) happens **before** `propose` (`:1134`), so proposer changes write zero
bytes to it — unmoved at 92.3% (12/13), same known miss. The informational `recovery_rate`
move (9/16 → 10/20) is **corpus composition**, not loop behaviour, and stays never-guarded.
Every scenario is self-graded — we authored the fixtures for the classes we then grade — with
no real nf-core run in CI. Withdrawing the four inert operations is also a **provenance
change**, not only a proposer change: those keys were written into every affected run's
`record.target.backend_options` and now never are. And **this recovers nothing new for a
user** except a transient Docker-daemon blip.

**Revisit trigger, in both directions**, following the `no_progress` and `qc_anomaly`
precedent, because G1–G4 all reduce to "a test we wrote asserts behaviour we defined" and none
of them distinguishes *made the record honest* from *made the record differently-shaped*.
**(a)** If the next 20 diagnosed failures appended to the pending corpus contain **no** case in
any of the five classes, the advisory abstraction is restated as taxonomy-only, and no further
breadth is built for these classes on push alone — counted by grouping
`runs/pending_corpus.jsonl` by `failure_class`, no new instrumentation. **(b)** If
`container_unavailable` fires and the enacted wait does **not** recover it, the wait is
removed rather than lengthened — a longer guess would be the same unvalidated reasoning at a
bigger number.

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
FAIL severity on calibrated bands, and a dashboard card. *(The pre-band capture
prerequisite for calibration shipped in the `eval-concordance-capture` slice —
calibration itself remains gated on real-run accumulation.)*

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

## C4. New assay, depth-first: somatic variant calling  ·  SHIPPED v0.13.0 (intake→launch→verify) + VAF plausibility slice (Unreleased) + Strelka2-vs-Mutect2 concordance slice (Unreleased) + Strelka2-native VAF slice (Unreleased) + empty-call-set FAIL floor slice (Unreleased; VAF FAIL bands **declined by design**) + swapped-pair smell-test slice (Unreleased)

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
test (since **shipped**, see below); and panel-of-normals / germline-resource reference wiring
for a real Mutect2 somatic run (today the verification runs against injected fixtures).

**Shipped (Strelka2-native VAF slice — Unreleased).** The deferred "Strelka2-native VAF
(tier-count derivation — non-Mutect2 VCFs degrade to UNVERIFIED)" item above has since
**shipped**: a `strelka_median_vaf` metric, computed independently of Mutect2's `AF`/`AD` from
Strelka2's own documented tier1 counts (SNV: `tier1({ALT}U) / (tier1({REF}U) +
tier1({ALT}U))` over `AU`/`CU`/`GU`/`TU`; indel: `tier1(TIR) / (tier1(TAR) + tier1(TIR))` over
`TAR`/`TIR`), pooled across the SNV+indel VCF pair and identified by the **literal** `TUMOR`
column name (Strelka2 emits no `##tumor_sample=` header). It fires **alongside** — not instead
of — Mutect2's `median_vaf`, as independent cross-caller corroboration of tumor VAF, riding the
same WARN-capped `SOMATIC_PLAUSIBILITY_PACK` band and wired via the same `select_caller_vcfs`
locator the concordance hook uses. **Still deferred (at the time):** the cross-column
swapped-pair smell test (since **shipped**, see below), and panel-of-normals /
germline-resource reference wiring — unchanged from the slice above. *(Update: this metric's WARN cap is now **declined by design**, not deferred. Beyond
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

**Shipped (swapped-pair smell-test slice — Unreleased).** The deferred "cross-column
swapped-pair smell test" named by both slices above has since **shipped**: a
`normal_median_vaf` metric reads the median VAF over the **NORMAL** column of the same Mutect2
VCF (same biallelic record set and `_vaf_from_sample` derivation as the tumor `median_vaf`,
only the column index differs). A new `##normal_sample=` header resolver in
`somatic_plausibility.py` mirrors the shipped `##tumor_sample=` resolver — never a positional
guess; a missing header or unmatched name resolves to `None`. One WARN-capped
`normal_median_vaf` rule rides the same `SOMATIC_PLAUSIBILITY_PACK` (`warn_above: 0.30` only,
no `warn_below`/`fail_*` — a low normal VAF is the healthy expected case), evaluated by a new
`evaluate_swap_plausibility()` over a `by_metric` dict containing only this key, so it never
re-emits the pack's other rules (the same `by_metric`-isolation trick the Strelka2-native
slice used). Wired into the somatic `_discover_qc` gate on the already-located Mutect2 VCF (no
re-glob), immediately alongside the tumor-VAF evaluator. Honest contract identical to every
sibling slice: at most WARN, never FAIL, never changes the exit code; UNVERIFIED (never a
false pass) when the normal column is unresolvable or no normal VAF is derivable; no Mutect2
VCF → silent skip. **What it does and does not catch, stated honestly:** a high normal-column
VAF is a *smell*, not a swap determination — a true tumor/normal swap, a sheet mislabel, and
heavy tumor-in-normal contamination all produce the same number, so the message names all
three and asserts none. It is also **not** the whole swap surface: a genuinely swapped pair
often *depletes* the PASS call set (Mutect2 filters true somatic sites as germline once the
tumor is passed as the normal), and that shape is already caught by `somatic_variant_count`'s
`fail_below: 1` floor above — this metric's yield is the intermediate case those two miss. No
new dependency, model, `FailureClass`, or reproduce-contract change; stdlib only; test-first
with synthetic fixtures, **no real nf-core/sarek or GATK run in CI**. **Deferred:** FAIL
severity and real-cohort band calibration; a directional tumor-vs-normal ratio/delta metric;
panel-of-normals / germline-resource reference wiring; a Strelka2-native normal VAF (this
slice is Mutect2-only, matching the tumor `median_vaf` it extends); and a dashboard
"corroborated by" surface for the swap signal.

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
those rules exist. *(Superseded: `no_progress` became reachable in the
heartbeat-stall-watchdog slice and `qc_anomaly` in the verdict-trigger slice — see "Both
guards moved" and "`qc_anomaly` closed" below. **`eval-guard` moved only for
`no_progress`**: `qc_anomaly` is now reachable in the loop but its held-out case is
log-text shaped and stays a deliberate MISS, so the held-out number is 92.3%, not 100%.)* **Honest scope, unchanged from the PRD:** this slice guards the
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
held-out-accuracy trend over corpus/loop versions. *(Superseded twice. First: `no_progress`
and then `qc_anomaly` are now covered — see below — so **no failure class is structurally
unreachable any more**. Second: the catalog-coverage slice took `covered_classes` to **11**
over **16** scenarios, closing the container/download/missing-reference families named just
above; disk and permission remain uncovered **because their repairs are inert**, with the
reason recorded below. Also superseded: the **held-out-accuracy trend shipped** —
`holdout_history.jsonl`, `heal_history.jsonl`, `--snapshot`/`--history` on both guards, and
two dashboard trend cards. Only the C1/C3 fold-in is still pending.)* *(Superseded a third
time by the `eval-corroboration-fold-in` slice (Unreleased): the fold-in is now **shipped**
— a labeled verification corpus (`verify_corpus_holdout.jsonl`, 22 synthetic cases with a
deliberate known-miss keeping the baseline below 1.0), `contig verify-guard` (verdict-match
rate guarded against `verify_baseline.json`, wired into CI after `heal-guard`, with
`--update-baseline`/`--snapshot`/`--history`), a real-run capture channel (`RunRecord.
verification_inputs` pre-band metric capture, pending `VerificationCase`s from QC-driven
WARN/FAIL runs, `contig verify-case-promote` into the golden corpus), and the dashboard
`FAILURE_CLASSES` taxonomy completed to all 18 literals. Honest scope as shipped: the
guarded number is over a **synthetic, self-graded** seed; the corpus only becomes
non-tautological as real runs are labeled through the promote channel (band-sensitive by
construction — a mutation control pins that a band change flips a stored value's verdict);
concordance-family *capture* remains deferred (PRD R4a); the dashboard trend card is a
deferred nice-to-have.)* *(Superseded a fourth time by the `eval-concordance-capture`
slice (Unreleased): the R4a deferral now **closes for the run-dir-derived families** —
`somatic_plausibility`, `annotation_plausibility`, `concordance_somatic_overlap`, and
`concordance_consequence` are captured into `RunRecord.verification_inputs` straight
from `_discover_qc` (the two plausibility capture gaps close with them), guarded by
round-trip / per-kind status-consistency / family-key enumeration pins; the guards did
not move (95.5% / 92.9% / 100%, no baseline refreeze). `concordance_spearman`
(RNA-seq/single-cell) and `concordance_genotype` (germline) capture **remains
deferred**: their second call set / count matrix exists only at `contig verify` time
(user-supplied or autorun), not in the run dir — S1 revisit trigger, the day a second
set is run-dir-derivable for those assays or a verify-time capture channel arrives that
does not break the signed payload. The dashboard trend card is still a deferred
nice-to-have.)* *(Superseded a fifth time by the `reproduce-eval-fold-in` slice
(Unreleased): the reproduce track is now fold-in'd — `contig reproduce-guard` replays 14
frozen scenarios through the **real** `run_reproduction` loop (scripted
executor/installer seams only) and guards the per-scenario outcome-match rate at a
committed baseline of **13/14 (92.9%)** over all five locator families plus staleness
and the env-resurrection heal, the single mismatch being the deliberate `known-miss`
scenario; flags mirror verify-guard, the trend is the append-only
`reproduce_history.jsonl`, and CI wiring sits after `verify-guard`. Verify-side capture
is unaffected; capture of reproduce outcomes (pending `ReproduceCase` + promote, the
capture-promote aspect) remains pending in the follow-on slice — the guard stays live
via its anti-tautology mutation-control pin, not field data.)* *(Superseded a sixth
time by the `reproduce-case-promote` capture channel (Unreleased): the pending
`ReproduceCase` sidecar capture from real `contig reproduce` runs and
`reproduce-case-promote` into the golden corpus are now shipped — the full record
lives in the C8 fold-in paragraph; the reproduce-guard itself did not move.)*
*(Superseded a seventh time by the `verify-time-concordance-capture` slice
(Unreleased): the R4a deferral now **closes for all four concordance families** —
the S1 revisit trigger shipped, not as run-dir derivation but as a **verify-time
capture channel that does not break the signed payload**: `contig verify
--concordance-*` appends one pending `VerificationCase` per concordance
invocation (case_id `{run_id}-verify-concordance`, source `pending:{run_id}`,
inputs `{family: {"S1": {"value", "n_shared"}}}` from the evaluators' new
`capture_metrics=` out-params) into the same pending sidecar, deduped by
case_id, promoted via the unchanged `verify-case-promote`, and re-derived under
the current bands — round-trip, status-consistency, mutation-control, and
family-key-enumeration pins guard it. `concordance_genotype` (germline) and
`concordance_spearman` (RNA-seq/single-cell) are now captured like the
run-dir-derived families; the four guards and baselines did not move.)*

**Both guards moved for the first time (heartbeat stall watchdog slice — Unreleased).**
The C2 stall-watchdog slice above made `no_progress` emittable by the `rules` detector,
and both C6 guards recorded it. **`eval-guard`: held-out accuracy 0.846 → 0.923**
(11/13 → 12/13) against a deliberately refrozen `holdout_baseline.json` — the held-out
file itself was **not edited**, so its `corpus_sha` is unchanged and the guard reported
*improved*, not *regressed*. That number had been **flat across all six recorded trend
points, v0.22.0 → v0.48.0** (`holdout_history.jsonl`), with `holdout-no-progress-1`
misclassified as `tool_crash` every single time; the per-class table moved for the right
reason (`tool_crash` predicted 3 → 2 — the `no_progress` case no longer falling through
the catch-all), independently verified rather than inferred from the headline.
**`heal-guard`: `covered_classes` 5 → 6** (`no_progress` added), over 8 frozen scenarios
instead of 7, with **outcome-match still 1.0** and `recovery_rate` 5/8 = 0.625 reported
alongside as the informational-only sub-metric it has always been. The new
`no-progress-heal` scenario avoids both traps by construction: exit **143** (not 137) and
a real watchdog-shaped `log_text` with no OOM needles, so it cannot pass by accident.
**`qc_anomaly` remains the one structurally unreachable class** — this slice did not
close it and must not be read as having done so; its honest trigger is the verdict
object, not log text (~~QC runs at `_finalize`, not as a pipeline step~~ — **this
parenthetical is false and was disproved by the slice below**: `_finalize` never
computes QC at all; `_discover_qc` runs inside `run_pipeline` at `runner.py:1223`, gated
only on `artifact_path.exists()`, on **every** attempt and **before** the `returncode != 0`
check. The real reason the `no_progress` mechanism did not transfer is that the **success
path had no diagnosis call at all** — `diagnose_failure` was reachable only from the
`except PipelineExecutionError` branch), so it needs its own slice. *(Superseded: that
slice shipped — see "`qc_anomaly` closed" below.)* **The accuracy gain is partly self-graded and is not oversold:** we made
reachable a class whose held-out fixture we wrote ourselves. It is legitimate evidence
that a documented taxonomy gap closed, and nothing more. Refreezing also exposed a latent
invariant bug in the snapshot-history tests — both the detector and heal seed tests
asserted that history line 0 (the v0.22.0 seed) still equals the *current* baseline, which
only ever held because no refreeze had changed accuracy. History is append-only and must
never be rewritten, so the **tests** were corrected (some recorded trend point must match
the baseline on accuracy/outcome-match + `corpus_sha`; `contig_version` dropped from the
cross-check, since `--snapshot` stamps the current version without touching the baseline
and tying them would turn master red at the very next release). The heal sibling carried
the identical latent bug and was fixed in the same round.

**`qc_anomaly` closed — no failure class is structurally unreachable any more
(`qc_anomaly` verdict-trigger slice, Unreleased).** `self_heal_run` only ever diagnosed a
non-zero exit, so a run that finished with **every task green** and whose QC then reduced
to **FAIL** returned straight into `_finalize` undiagnosed, absent from `repair_history`,
and absent from the corpus — the verdict was an output only, never an input. It now fires
a structural trigger on exactly three conditions (`RunSummary.succeeded`, non-empty
`qc_results`, `overall_verdict(...) == "fail"`), synthesizing the `Diagnosis` in place:
`detect.py` is **untouched**, because this is a deterministic read of our own verdict
object rather than an inference over log text. Keying on `record.verdict` instead would
misattribute a crash (`verdict` is already `"fail"` for a FAILED task event before QC is
consulted, `models.py:373-385`). The outcome literal is a new `qc_verdict_flagged`, not
`gave_up`, which would claim an attempt that never happened, and the run also writes a
pending-corpus `FailureCase` where it previously wrote none. **`heal-guard`:
`covered_classes` 6 → 7**, over **9** frozen scenarios, **outcome-match still 1.0** —
achieved without any QC-bypassing seam, since one header-only `.vcf.gz` under the run dir
drives the **real** `_discover_qc` to a FAIL (`variant_count fail_below: 1` over zero data
rows). **Read honestly, and each of these is load-bearing:** (1) **`eval-guard` is
deliberately unmoved at 92.3%** — the held-out `holdout-qc-anomaly-1` is *log-text* shaped,
so closing it would need needles matching text **Contig never emits**, and the
`no_progress` slice's "our own wording is ordinary English" defence was therefore
unavailable; the guard prints its own evidence (`MISS holdout-qc-anomaly-1: expected
qc_anomaly, predicted tool_crash`), and any claim that detector accuracy improved would be
false. (2) **It recovers nothing, by design** — every task exited 0, so a `-resume` retry
is a 100% cache hit that re-derives an identical verdict (`runner.py:1116-1117` appends
`-resume` with no cache invalidation, and Contig has no mechanism of its own to invalidate
Nextflow's task cache); `propose_patches` gains **no** branch and a test pins its absence.
(3) The `recovery_rate` move **0.625 → 0.667 is an artifact**, not an improvement: the
scenario is green from attempt 1, so the driver's event-derived `recovered` computes true
though nothing was recovered — disclosed rather than fixed, since redefining `recovered`
would retroactively change the meaning of every recorded `heal_history` point to correct a
cosmetic artifact in a metric that is informational-only and never guarded. (4) **Push, not
demand-pull:** across the 17 `run_record.json` bundles on the development machine, 1 trips
the trigger — and that bundle carries `contig_version: 0.0.1`, its `ts_tv = 3.5` is a
**WARN** under today's `fail_above: 3.6` band, and its recorded `status: "fail"` predates
the current bands, so **under today's bands the organic frequency is 0 of 17**. (5) The
`heal-guard` gain is a scenario **we** authored for a class **we** made reachable, and **no
real nf-core run happens in CI** — whether a real sarek truncation lands exactly on
events-succeeded + QC-FAIL is reasoned, not observed. **Committed revisit trigger:** if the
trigger fires on **zero non-authored runs across the next 20 real runs**, the diagnosis
path is removed and the behaviour reduced to a report-only note; if it fires and the
diagnosed check names cluster, that cluster is the demand signal for the actual remediation
this slice declines to build.

**The repair record became structured, and `recovered` became honest (`patch_applied` slice,
Unreleased).** The follow-up the `qc_anomaly` slice filed against itself. `RepairStep` recorded
that a patch was *proposed*, never that it was *enacted*, so **a user who rejected a patch at
the approval gate was told their run was `Repaired`** — five paths record a non-null patch and
return before `apply_patch` is ever called. A new `RepairStep.patch_applied` is now set at all
eleven `_record_attempt` sites **from control flow** (`_apply_patch_and_maybe_build`'s existing
`continue_`), never from the outcome string: `apply_patch` runs on that helper's *first* line,
before the build/recompress is attempted, so the naive rule would have stamped four failure
branches as applied and hardened the bug into the **signed** record. Verified rather than
assumed — all 17 returns across the three helpers were enumerated; `continue_` is `True` at
exactly 4, all enacted-and-proceeding. **The cheaper alternative was real and was declined for
a stated reason:** the 18 live outcome literals partition cleanly today, so a derived
`outcome → applied` map would have worked with **no signature break** — but it is
hand-maintained, and a literal added later would silently default to "not applied",
reintroducing the bug by another door. The field is correct **by construction rather than by
review**; no concrete pending literal is claimed.

For C6 specifically the payoff is `heal-guard`: **`recovered` no longer counts a
green-by-construction scenario as a recovery.** It was purely event-derived
(`RunSummary.from_events(...).succeeded`), which is why the `qc_anomaly` slice's
`recovery_rate` move was recorded above as "an **artifact**, not an improvement" and left
unfixed — no honest signal existed. One does now: `succeeded AND any(step.patch_applied)`.
**Exactly one frozen expectation changed** (`qc-anomaly-verdict-flagged`, `expected_recovered`
`true` → `false`) and the **guarded `outcome_match_rate` stays 1.0 precisely because that
correction landed in the same commit** — `recovered` feeds `divergence` → `matched`, so
refreezing without it would have laundered a real regression into the baseline. The scenarios
also gained an optional `expected_patch_applied`, asserted through the **real** loop, so the
field is CI-guarded rather than unit-tested only. **`recovery_rate` 0.667 → 0.556 is a
correction, and its sixth trend point is NOT comparable to the prior five** (0.571 ×3, 0.625,
0.667) — the exact objection raised when this change was previously declined, accepted here
because the metric is informational-only (`regressed` is computed from `outcome_match_rate`
alone) and the new definition is truthful where the old one was not. `heal_history.jsonl` is
append-only and was not rewritten. **`eval-guard` is unmoved at 92.3%**, correctly — the
detector corpus carries no `RepairStep`. **Honest limits:** push, not demand-pull (a
self-audit, not a partner request); it recovers nothing new, only changes what the record
*says*; and it is the **fourth disclosed signature break** though the **narrowest** — the key
is nested in a list, so a record with an empty `repair_history` still verifies, which is
pinned by its own test rather than asserted.

**The honest half of the failure catalog is now covered — and the half left out is the finding
(catalog-coverage slice, Unreleased).** This closes the gap this section itself named above
(*"the wider failure-class catalog … has no scenario yet"*). `heal-guard`'s frozen set went
**9 → 16 scenarios** and **`covered_classes` 7 → 11** — adding `missing_reference`,
`reference_not_bgzf`, `container_pull_failed` and `download_failed` — with the **guarded
`outcome_match_rate` still 1.0**, the informational-only `recovery_rate` at **0.5625 (9/16)**
(was 0.5556), and a deliberately refrozen baseline (`corpus_sha 07c19e17…`,
`contig_version 0.49.0`). **`eval-guard` is unmoved at 92.3%**, with the same single known miss
it prints itself; the detector corpora and `holdout_baseline.json` were **not touched**, and
neither were `repair.py`, `self_heal.py` or `detect.py`. Seven new lines: four recovering, three
honest give-ups (`rejected_by_user`, `reference_recompress_unresolvable`, `gave_up`); the nine
pre-existing lines are **byte-identical** (verified with `cmp`). The only mechanism change is
`HealScenario.fasta_artifact: Literal["plain_gzip"] | None = None`, a **named fixture
directive** on the `qc_artifact` precedent — the driver writes a real plain-gzip (non-BGZF)
FASTA and points `params["fasta"]` at it, so the scenario drives the **real**
`_recompress_reference` instead of an injected outcome. **No seam bypasses the code under
test**; the field defaults to `None`. `heal-guard`'s honest-scope docstring was corrected in the
same slice and now carries **a reason per uncovered class** rather than one undifferentiated
backlog — inert-repair (5, deferred pending propose-vs-don't), reproduce-local
(`missing_dependency`, emitted only by `contig reproduce --allow-install` and by no detector
rule), and non-target (`unknown`) — and states what *covered* means: the class has a frozen
synthetic scenario whose declared outcome the loop still reproduces, **not** that the engine
handles that failure well in the field.

**The brief asked for all nine uncovered classes; four shipped, and the deferral is the
finding, not a shortfall.** The other five emit a patch whose operation is read by **nothing**.
Four are `kind="env"` patches whose operation `apply_patch` string-merges into
`target.backend_options` (`self_heal.py:583-586`), out of which `nfconfig.py:71-98` reads only
`queue`/`region`/`partition`/`account`/`qos`/`time` — `disk_full`→`clean_work_dir`
(`repair.py:145`, nothing deletes a work dir, no `statvfs`),
`permission_denied`→`fix_permissions` (`repair.py:169`, no `chmod`/`chown` exists),
`conda_solve_failed`→`relax_or_pin_env` (`repair.py:123`, nothing relaxes or pins an env spec),
and `platform_unsupported`→`use_native_arch_backend` (`repair.py:109`, `target.backend` is
unchanged, so the approved retry re-runs on the same host the patch's **own rationale** calls
hopeless). The fifth is inert for a **different** reason, kept distinct rather than flattened:
`container_unavailable`'s patch is `kind="retry"` (`repair.py:50`), and `apply_patch` is a
**documented** no-op for retry patches, so the `wait_seconds: 15` its rationale promises is
silently dropped and the fix degenerates to the bare re-run `container_pull_failed` already
covers. The loop's story for all five is propose → "apply" → `patch_applied=True` → retry →
`Repaired`,
which is **one layer below** the bug the `patch_applied` slice fixed: the flag is now honest
about *enactment*, but enacting a no-op still renders as a repair on every surface. Covering
them would have frozen five expectations we already suspect are wrong into CI. `repair.py:173-176`
already says of `permission_denied` that *"only a human can decide and do that safely"*, so the
**C2 follow-up is filed with propose-vs-don't as its first question**, not "how to implement".

**Read honestly, with nothing softened:** (1) **push, not demand-pull** — no user asked, and the
organic frequency of these classes is **unmeasured**; (2) **synthetic throughout** — no real
nf-core run, container registry, network, disk or permission state in CI, no stronger than any
prior heal scenario; (3) **self-graded** — we authored the fixtures for the classes we grade,
exactly as the `no_progress` and `qc_anomaly` slices disclosed of themselves; (4) **it recovers
nothing new for a user** — it changes what CI *guards*, not what the engine *does*;
(5) **`covered_classes: 11` invites over-reading** — eleven classes have a frozen synthetic
scenario, which is not a claim that the engine handles those failures well, and for the five
excluded it demonstrably does not; (6) **the narrowed scope is a judgement, not a proof** — we
suspect the five inert repairs should stop proposing rather than be implemented, and that is not
established; (7) **this was not ordinary TDD and saying it was would be false** — no genuine
per-scenario RED was possible because the slice adds no production code beyond the seam, so a
**deliberate-mismatch control** was run instead (scenario 5's shape with inverted expectations,
returning `matched=False` with all three divergences including `patch_applied`), proving the
check is live and non-vacuous; corpus-level RED **was** genuine (the `total 9 → 16` assertion,
the `corpus_sha` mismatch, the stale-sha warning); (8) the commit split left three
baseline-coupled tests red at the first commit boundary — deliberate and disclosed on the
`648989c` precedent, though `429693b` bundled scenario and refreeze into one commit for exactly
that reason; and (9) the new `recovery_rate` trend point moved on **corpus composition**
(9 → 16 lines, three of them give-ups), not on loop behaviour — `heal_history.jsonl` is
append-only and no historical point was rewritten.

**Revisit trigger, in both directions.** *(a)* If any of the five inert repairs is **implemented
or withdrawn**, the deferral reason must be revisited in that same commit, at which point those
classes become coverable against corrected behaviour. Enforced by CI rather than by review:
`test_five_inert_patch_operations_are_still_consumed_by_nothing` asserts each operation is still
emitted by `repair.py` **and** referenced nowhere else in `src/contig/`, and its failure message
names this trigger. The test exists to **fail** when the gap closes.
*(b)* If the **next 20 runs** appended to the pending corpus contain **no** case diagnosed as any
of these nine classes, the coverage claim is restated as **taxonomy** coverage only and no
further breadth is added on push alone. The counter is the pending-corpus append the loop already
performs on every diagnosed failure (`self_heal.py:1096`) — group that file by `failure_class`;
**no new instrumentation**. Precedent: the `qc_anomaly` slice's "0 of 17 recorded runs".

**Eval data captured:** this *is* the capture loop; it closes over all the above.

**Dependencies:** consumes the outputs of C1 to C5.

---

## C7. Research-use variant annotation & prioritization  ·  M1 + M2 + M3 + M4 + M5 (surface + provenance) SHIPPED (Unreleased) — germline structural verify + provenance, somatic gate, annotation plausibility (both assays), VEP-vs-SnpEff concordance (both assays), "corroborated by" surface + cache/build provenance; M5 C6 eval fold-in SHIPPED (Unreleased)

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
never adjudicates significance. **Live-cache caveat — CLOSED by the
`annotation-cache-wiring` slice (Unreleased):** a real run's annotation step needs a VEP/SnpEff
cache, and the caveat's "when that annotation output is absent the verifier reports UNVERIFIED"
wording was optimistic — sarek 3.5.1's `ANNOTATION_CACHE_INITIALISATION` subworkflow calls
`error()` on a missing cache dir, so a cache-less run **hard-fails at cache initialisation**
(verified against sarek 3.5.1 source, `subworkflows/local/annotation_cache_initialisation/main.nf`)
rather than completing without annotation. The enablement is now wired: `_dispatch_run` injects
`download_cache=true` + `outdir_cache=<runs_dir>/caches/annotation/<pipeline>@<revision>/`
(setdefault, user values win) for both `VARIANT_ASSAYS` — with `download_cache=true` sarek takes
the `DOWNLOAD_CACHE_SNPEFF_VEP` branch and **skips the hard-error validation** (main.nf if/else),
downloading the cache at run time on the user's compute. `--step annotate` is deliberately not
used: sarek's `step` enum is a restart mode needing a VCF-dir `--input`; annotation runs
automatically after calling when `vep`/`snpeff` are in `--tools`. Honest limits: no real
VEP/SnpEff/sarek run in CI (the wiring is pinned by argv/param tests; a real-run smoke test stays
a manual post-merge gate); `outdir_cache` is required because without it sarek publishes the cache
into `${outdir}/cache/` inside the run bundle; and the download is keyed to sarek's default
`GATK.GRCh38` genome attrs (`conf/igenomes.config`), so an explicit `--fasta/--gtf` run with a
**non-GRCh38** reference would download the GRCh38 cache (wrong build) — accepted, with
user-supplied `--vep_cache`/`--snpeff_cache` paths still a future slice. Test-first; no real
VEP/SnpEff/sarek run in CI.

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
per-variant biological/clinical judgement. The live-cache caveat is **closed** (see M1 — the
`annotation-cache-wiring` slice wired `download_cache`/`outdir_cache`); no real
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
- **M5 — surface + eval fold-in. Surface + provenance SHIPPED (Unreleased); the C6 eval
  fold-in has since SHIPPED (Unreleased) — see C6.** A pure `verification/annotation_surface.py::corroborated_by_line`
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
  CI. **Still deferred (superseded):** folding annotation concordance/plausibility
  outcomes into the C6 eval corpus — this is now **shipped** (Unreleased, see C6: the
  `eval-corroboration-fold-in` slice shipped the labeling design, `verify-guard`, and the
  capture/promote channel; the old "blocked pending a labeling design" record no longer
  holds).

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

## C8. Reproduce & verify *existing published* work  ·  first slice SHIPPED v0.40.0 + output-locator slice 1.5 SHIPPED v0.41.0 + environment-resurrection slice 2 SHIPPED (Unreleased) + TSV/CSV table-locator slice 3 SHIPPED (Unreleased) + stdout/log pattern-locator slice 4 SHIPPED (Unreleased) + notebook (`.ipynb`) locator slice 5 SHIPPED (Unreleased) + freshness guard extended to **all** binding surfaces SHIPPED (Unreleased) + remote `https://` git-URL intake slice 6 SHIPPED (Unreleased) + `--rev` revision pinning slice 7 SHIPPED (Unreleased) + checkout-tree hash slice 8 SHIPPED (Unreleased) + local tree hash slice 9 SHIPPED (Unreleased) + paper-claim extraction (`contig extract-claims`) SHIPPED (Unreleased) + DOI/PDF intake (`extract-claims` accepts a DOI or local `.pdf`) SHIPPED (Unreleased)  ·  M7+

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
below); remote `<doi|url>`; a dashboard card.

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
honestly. **Deferred:** slice 2 (environment resurrection) and everything after it (unchanged from
the slice-1 list above). Test-first (walker → `load_claims` → engine → CLI); deterministic; no real
repo or network in CI.

**Shipped (environment resurrection — slice 2, Unreleased).** The load-bearing piece: `contig
reproduce` can now recover a repo that *doesn't run yet* because it's missing a Python dependency —
the dominant reproduction-failure class (`ModuleNotFoundError` / `ImportError` + installs are ~76%
of failures). A new **opt-in `--allow-install` flag** (off by default) turns a first run that exits
non-zero with a `No module named 'X'` message into a bounded **detect → install → retry-once**
self-heal that reuses the C2 machinery. A new pure `detect_missing_module` extracts the missing
top-level package (case-insensitive, `sklearn.utils` → `sklearn`, charset-validated
`^[A-Za-z0-9._-]+$`); a new injected installer seam (`runner.Installer` + `default_installer` +
`_pip_install_argv`, mirroring `IndexBuilder`) runs a **fixed** argv `[sys.executable, "-m", "pip",
"install", <module>]` (no shell, no interpolation); the run retries exactly once and the claims
re-classify against the retried run's fresh output. **Bounded** (one install + one retry, no loop, no
second-module chase → provable termination) and **honest on every unresolved path** (flag off, no
module, install fails, retry fails → all `UNVERIFIED`, never a false reproduce; import-name ≠
package-name mismatches like `cv2` → `opencv-python` fail the install and degrade honestly). Off by
default the behavior is byte-identical to slice 1.5; the flag gates all network + environment
mutation. The heal is recorded on an additive `ReproduceRecord.repair_history: list[RepairStep]`
(default `[]`, pre-slice-2 bundles load unchanged) — `Diagnosis(failure_class="missing_dependency")`,
a new literal kept **reproduce-local** (deliberately *not* wired into the shared `diagnose_failure`,
so the C6 eval-guard held-out baseline is unmoved, confirmed at 84.6%), plus `Patch(kind="env",
operation={"install": <module>})` — surfaced as a one-line `env-repair` note and round-tripped
through the signed bundle; `exit_code` reflects the final (retried) run. To see the error text, the
reproduce command-executor seam widened from `int` to `(exit_code, combined_output)`
(`default_command_executor` now captures combined stdout+stderr); the Nextflow `Executor`/`IndexBuilder`
seams are untouched. No new runtime dependency (injected installer). Test-first with a scripted
executor + scripted installer — **no real repo, network, or pip in CI**. **Deferred:** import→package
alias map, iterative multi-module resolution, version pinning from a traced execution, venv
isolation. Plan/PRD under `docs/planning/reproduce-env-resurrection/`.

**Shipped (TSV/CSV output-locator — slice 3, Unreleased).** Slice 1.5 could only bind a claim's
observed value from a repo's **structured JSON** output; but in bioinformatics the numbers a paper
reports overwhelmingly live in **tabular** output — DESeq2 results tables, count matrices,
feature/stat tables — as `.tsv`/`.csv` (often gzipped), against which every claim degraded to
`UNVERIFIED`. A claim's locator may now also carry `{"from": <repo-relative .tsv/.csv[.gz] file>,
"column": <name|int>, "row": <int|{key:val}>, "header"?: bool, "delimiter"?: str}`, naming a cell
the same way the JSON locator names a `path`. Two addressing modes: named (header column name +
a `{key: value}` row match) and positional (integer column + integer row, `header: false`), 0-based
like the JSON locator's `[n]`. A new pure stdlib table reader
(`verification/reproduce.py::_read_table` + `resolve_cell`, siblings of the JSON walker) reads
`.tsv`/`.csv` via `csv.reader`, is gzip-transparent (`.tsv.gz`/`.csv.gz`), and is index-safe on any
shape — ragged rows, empty files, header-only tables, directory paths, non-UTF-8 files — **never
raising**; `_resolve_delimiter` infers the delimiter from the extension (an explicit `delimiter`
always overrides). `load_claims` validates the table shape structurally, pre-run: exactly one of
`{path}` xor `{column, row}`, `column`/`row`/`delimiter`/`header` type/shape rules, and a
`row`-object or string `column` **requires** `header: true` — every contradiction is a load-time
`ClaimsError` (exit non-zero, nothing written), never a silent misread. `run_reproduction`
dispatches on the locator's type to a new `_observe_table_located` (sibling of `_observe_located`)
reusing the same containment guard and a per-run parse cache (`_table_cache` — a table `from` is
parsed **at most once per run** even across several claims on the same file); the resolved cell is
`float()`-parsed after `.strip()` and feeds the **unchanged** `classify`. **The deliberate
divergence from the JSON rule: a numeric-string cell is the normal, valid case** (every table cell
is a string by construction) — `"30.4"` classifies here, unlike the JSON locator's
strict-UNVERIFIED numeric string. Every unresolved/ambiguous address is `UNVERIFIED`, never
`DIVERGED`: missing/dir/non-UTF-8/unparseable `from`; absent or duplicate header column name;
column/row index out of range; a ragged row shorter than the addressed column; a `row`-key match
with **0 or more than 1** hits (never an arbitrary pick, the count is named in the message); an
unparseable or non-finite cell. Safety and reuse are unchanged: a table claim's `from` flows
through the same `.source` field the CLI containment loop and the engine's defense-in-depth guard
already check — **no new code was needed there**; `classify`/`ClaimResult`/`ReproduceRecord`/
bundle/signing/`--fail-on-diverged` all reused as-is, **no `models.py` change**, `claims_sha256`
already covers the new claim fields. Stdlib-only (`csv`+`gzip`, both already stdlib) — no new
dependency. **Deferred:** multi-key/predicate row match, column ranges, regex; notebook
(`.ipynb`) numeric extraction; paper-parsing; figure/plot & table-image claims
(still hard-blocked — no plot-hash, stdlib-only); remote `<doi|url>`; dashboard card.
Test-first (pure reader → engine dispatch → CLI containment/e2e); deterministic; **no
real repo or network in CI** (on-disk fixture `.tsv`/`.csv`/`.tsv.gz` tables). Plan/PRD under
`docs/planning/reproduce-tsv-csv-locator/`.

**Shipped (stdout/log pattern locator — slice 4, Unreleased).** Slices 1.5 and 3 both required the
repo to write its numbers into a **structured file** (JSON or a TSV/CSV table). A large share of
published analysis scripts do not: they `print()` the headline number or append it to a `.log`, and
write no JSON and no table at all — so every claim against them degraded to `UNVERIFIED`. A claim
may now carry `{"pattern": <Python regex>}`, optionally with `{"from": <repo-relative text/log
file>}`. **Two addressing modes:** `pattern` **without** `from` matches the run's own captured
combined **stdout+stderr** (text the engine already held, until now read only by
`detect_missing_module` and the diagnosis evidence); `pattern` **with** `from` matches that
repo-relative file. `PatternLocator(source: str | None, pattern: str)` carries both — `source is
None` **is** the stdout mode, and the field is named `source` deliberately so the file case reuses
every existing `.source` code path. A new pure stdlib `resolve_match` (sibling of
`resolve_pointer`/`resolve_cell`) finds **all** non-overlapping matches via `re.finditer`, returns
the raw captured **string**, and **never raises**. **Capture selection: group 1 if the pattern has
capturing groups, else the whole match** (a named group is group 1 too); flags are **inline**
(`(?i)`/`(?m)`/`(?s)`) — no `flags`, `group`, or `occurrence` key this slice. **Ambiguity is never
guessed:** 0 or >1 matches is `UNVERIFIED` with the **count named**, never an arbitrary first-match
pick; a group 1 that did not participate in the match (`(?:x)?(y)?z` against `"z"`) — the one shape
that would otherwise crash a caller on `float(None)` — degrades with its own message and test.
Matching is bounded at **8 MiB** (`_MAX_MATCH_BYTES`), text over the cap being `UNVERIFIED` naming
the size rather than a silently truncated search (which could report a false "0 matches"); **this
is a ReDoS input bound, not a memory guard** — in file mode the size is `stat()`ed **before** any
read so an oversized log is never loaded, but in stdout mode `default_command_executor` already
buffers the whole output through `subprocess.PIPE` uncapped, a **pre-existing upstream** issue this
slice neither creates nor solves. `load_claims` validates structurally, pre-run: `pattern` must be
a non-empty string and **must compile** (`re.error` → `ClaimsError`, exit non-zero, **nothing
written**), and the xor became a **three-way** exclusion — exactly one of `path`, `column`+`row`,
or `pattern`, with `pattern` plus **any** table field (`column`/`row`/`header`/`delimiter`)
rejected rather than silently ignored. `pattern` is the first locator legal **without** `from`, so
the orphan guard was relaxed for `pattern` only; a bare `path`/table field without `from` stays an
error. The dispatch head became an explicit `isinstance` chain (the old unguarded `else` would have
routed the new type into the JSON reader and raised `AttributeError`), calling a new
`_observe_pattern_located` that reuses the same containment guard and a per-run read cache
(`_text_cache`). Because the observers are closures over `run_output` and are only called *after*
the `--allow-install` retry rebinds it, a stdout claim binds the **retried** run's output for free —
no new mechanism. A **numeric-string capture is the normal, valid case** (the slice-3 rule, not the
slice-1.5 strict JSON rule): it is `.strip()`ed, `float()`-parsed, and if finite feeds the
**unchanged** `classify`; unparseable or non-finite is `UNVERIFIED`. Safety and reuse hold: a file
`from` flows through the same CLI pre-run refusal and engine `relative_to(repo_root)` guard, a
`from`-less claim touches the filesystem **not at all**, and the one CLI change is the stdout-mode
skip (`claim.locator.source is None`) that keeps the containment loop from joining a `None`.
`classify`/`ClaimResult`/`ReproduceRecord`/bundle/signing/`--fail-on-diverged` reused as-is, **no
`models.py` change**, stdlib-only (`re`, already imported) — no new dependency. **Honest limits:** a
regex binds to **output formatting**, not a data structure, making this the **weakest locator
shipped** — mitigated not by cleverness but by the verdict contract (a non-match is `UNVERIFIED`
naming the count, **never `DIVERGED`**, so formatting drift can never be misread as a failed
reproduction); and the engine short-circuits every claim to `UNVERIFIED` on a non-zero exit
*before* any locator runs, so a stdout pattern reads **successful runs only**. **Deferred:**
`occurrence: first|last` and a `group` override (gated on a counted post-merge experiment over 5
real repos), a `flags` array, notebook (`.ipynb`) extraction, regex over binary files, persisting
matched output on the record, paper-parsing, remote `<doi|url>`, dashboard card;
figure/plot & table-image claims stay hard-blocked (no plot-hash, stdlib-only). Test-first (schema →
pure resolver → engine dispatch → CLI containment/e2e); deterministic; **no real repo, network, or
pip in CI** (scripted executors + on-disk fixture logs). Plan/PRD under
`docs/planning/reproduce-stdout-log-locator/`.

**Shipped (notebook `.ipynb` locator — slice 5, Unreleased).** Slices 1.5/3/4 read a repo's JSON,
TSV/CSV, or free-text output; none could read a **Jupyter notebook** — the very medium the C8
problem statement is built on (of 27,271 biomedical-paper notebooks only ~3.2% reproduced;
Samuel & Mietchen 2024). Against a `.ipynb` every claim degraded to `UNVERIFIED`. A claim may now
carry `{"from": <.ipynb>, "cell": <int | {"contains": <source substring>}>, "pattern": <regex>}`.
**Cell addressing mirrors `TableLocator.row`:** an int indexes the full `cells` array
(JSON-faithful, out of range → UNVERIFIED naming the count), or `{"contains": s}` selects the one
cell whose `source` contains `s` (survives reordering, needs no repo edit — unlike a tags scheme);
**0-or->1 → UNVERIFIED with the count named**, never a pick. **Output text = stdout streams +
`text/plain`, in output order** (a new pure stdlib `resolve_notebook_cell_text`, sibling of the JSON
walker / table reader / regex resolver, never-raising); **`stderr` and `error` tracebacks are
excluded** so a progress bar or traceback can't be the match surface. `pattern` is **required** and
the capture reuses slice-4's unchanged `resolve_match`; a numeric-string capture is the normal case
(slice-3/4 rule). **The load-bearing piece is an mtime freshness guard:** a committed notebook holds
the *authors'* stored outputs, so reading them would report a false `REPRODUCED` — the exact failure
the verdict contract prevents, and one a committed notebook *always* presents. The undecidable
"executed vs committed" question is replaced by the decidable one Contig needs — *was this file
rewritten by **this** run?* A notebook resolves only when its **mtime ≥ the run start** (stamped
once before the first run, not re-stamped on an `--allow-install` retry; no fudge tolerance),
checked **before** any parse; otherwise UNVERIFIED naming the staleness. The guard is
**non-bypassable** — a notebook claim with no run-start raises rather than silently passing.
**Honest limit:** it proves *rewritten*, not *recomputed* (a `--run` of `cp committed.ipynb out.ipynb`
passes while computing nothing) — it closes the dominant honest hole, not an adversarial self-deceit,
the same boundary slice 1's "re-runnable" drew. `load_claims` went **four-way** (`path` xor
`column`+`row` xor `pattern` xor `cell`+`pattern`), rejecting a `cell` with `path`/table fields
pre-run (exit non-zero, nothing written); a `pattern`+`from` claim without `cell` stays a
byte-identical slice-4 `PatternLocator`. Containment, the 8 MiB size bound, a per-run
`_notebook_cache`, `classify`/`ClaimResult`/`ReproduceRecord`/bundle/signing/`--fail-on-diverged`
all reused — **no `models.py` change**, stdlib-only, **no `nbformat`/`jupyter` dependency**.
**Deferred:** notebook-specific size bound (8 MiB is tight for embedded figures),
~~extending the freshness guard to the JSON/table locators~~ (**now shipped — see the paragraph
below; this slice's "guard scope is deliberately inconsistent … belongs in its own slice" is
CLOSED**), `metadata.tags`/multi-key/regex cell matching, non-text
outputs, plus the standing C8 list (paper-parsing, remote `<doi|url>`, dashboard card);
figures stay hard-blocked. Test-first (pure extractor → schema → engine + guard → CLI e2e);
deterministic (fixture `.ipynb`, `os.utime` mtimes, injected `run_started_at`, scripted executors);
**no real repo, notebook execution, network, or pip in CI**. Plan/PRD under
`docs/planning/reproduce-notebook-locator/`.

**Shipped (freshness guard — all binding surfaces, Unreleased).** Slice 5 shipped the mtime
freshness guard for the **notebook locator only** and recorded the inconsistency as a known gap
("the freshness guard is notebook-only … the JSON/table locators keep the same stale-artifact
hole, a separate slice"; the slice-5 PRD's R2 said the same). **That gap is now closed, and this
paragraph is the record that R2 is DONE.** The gap was the strongest remaining false-pass in C8: a
repo that **commits its outputs** — a checked-in `results.json`, `de.tsv`, `metrics.json`, or
`run.log` — reported `REPRODUCED` for a computation that never ran, because the engine read the
*authors'* stored numbers and compared them to the *authors'* published claim, so the comparison
always matched. **All four remaining disk-reading paths are now guarded:** the JSON `path` locator
(slice 1.5), the TSV/CSV `column`/`row` table locator (slice 3), the **file-mode** `pattern`
locator (slice 4), and the flat `--results` `results.json` read (slice 1 — the **oldest** instance
of the bug and the one **every "cooperative repo" uses**). One shared nested helper
`_require_fresh(resolved, noun, label)` in `run_reproduction` returns an UNVERIFIED message when
the artifact's mtime predates `run_started_at`, and it fires **before the file is parsed** and
before the parse enters the per-run cache (`_json_cache`/`_table_cache`/`_text_cache`), so a stale
artifact is never read for content; the notebook observer (slice 5) now routes through the **same**
helper instead of a second inline copy — `_require_fresh` takes an optional `mtime=` so a caller
holding a `stat()` result can pass it in, letting the notebook branch keep its single `stat()` and
its size-check-before-freshness ordering with identical wording (no notebook test changed).
**The stdout-mode pattern locator (`pattern` with no `from`) is exempt by
construction, not by oversight** — it binds the run's own captured combined stdout+stderr, touches
no filesystem, and cannot be stale; recorded so nobody later bolts a meaningless mtime check onto
text with no file behind it. **Non-bypassable:** there is **no opt-out flag**, and an **unstamped**
run start **raises** rather than degrading (a `None` meaning "guard off" would silently disable a
false-pass guard exactly where it is needed). A path that cannot be `stat()`'d is **not** a
freshness failure — the caller's existing missing/unreadable message still wins, so no pre-existing
error was pre-empted; and a **stale-but-valid `results.json`** reports the freshness message, never
the pre-existing "missing or unparseable" wording (the file parses fine — it is merely stale, and
the old wording would send a user to debug a syntax error that does not exist). The guard
**follows symlinks** deliberately, and the mechanism is `Path.stat()`'s `follow_symlinks=True`
**default**, *not* a `resolve()` call — the locator observers do `resolve()`, but the flat
`--results` path is plain `repo_path / results_path` and is never resolved, yet follows symlinks
just the same, so the *target's* mtime decides everywhere. `follow_symlinks=False` must never be
introduced (a prohibition now written into `_require_fresh`'s docstring): statting the link itself
would let a `ln -s` created during the run mark ancient content "fresh", turning real staleness
into a false pass. One consistent message stem — *"was not rewritten by
this run (mtime predates run start)"* — across all five guarded surfaces makes staleness greppable
and countable **without new telemetry**; a structured `ClaimResult` field was deliberately deferred
(it would cost a `models.py` change this slice otherwise avoids). **Honest limits, stated not
softened:** it proves *rewritten*, not *recomputed* — a `--run` of `cp committed.json out.json`, a
bare `touch`, or a restored cache passes while computing nothing, so this closes the dominant
**honest** hole, not adversarial self-deceit (the same boundary slices 1 and 5 drew); there is
**no fudge tolerance, deliberately** — on a coarse-mtime filesystem a genuinely regenerated file
can report an mtime marginally before the run start and yield a **false UNVERIFIED**, accepted
because a false UNVERIFIED is honest and recoverable while a false REPRODUCED is not, and because
a tolerance is exactly the size of the hole it opens; **clock skew is a distinct cause with the
same symptom** (the stamp is `time.time()` on the orchestrating host while an mtime may be written
over NFS/SMB by a machine with a different clock — same posture, recorded separately so a future
debugger is not sent to the wrong explanation); and there is an **accepted behavior change** — a
legitimate run that does not rewrite an artifact (a `make`/`snakemake` target already up to date, a
repo writing into a timestamped output dir, or a `--run` executing only the final step of a
multi-step analysis while the claim addresses an earlier artifact) now reports `UNVERIFIED` where
it previously bound a value; that was a deliberate product decision (strict, no opt-out), whose
**revisit trigger is the first real repo where a legitimately-reproducing run is blocked**.
**Base rate unverified:** we do **not** know what share of published repos commit their outputs —
no such number was measured and none is cited; the case rests on the defect being **possible and
silent**. (The ~3.2%-of-27,271-notebooks figure above is a *reproduction* rate, **not** a
committed-artifact rate, and is not evidence here.) Scope: the CLI already stamped the run start
once before the first run and does **not** re-stamp it on an `--allow-install` retry, so **no CLI
signature change and no new flag** were needed — only the `reproduce` docstring, which now states
the requirement once for all locator forms and `--results` and names the stdout exemption. **No
`models.py` change**, no new claim-file syntax, no new dependency, stdlib-only (`Path.stat()`).
Test-first (per surface: stale-with-an-exactly-matching-value → UNVERIFIED, fresh → still
REPRODUCED, missing run-start → raises; plus stdout-mode-needs-no-freshness, symlink-follows-target,
and retry-written artifacts). The four "fresh" controls stamp the artifact at **exactly** the run
start, pinning the `>=` boundary (a coarse-granularity filesystem truncates mtime to the second, so
`mtime == run_start` is precisely what a real run lands on), and the four missing-file cases assert
the freshness wording is **absent** while each surface's own missing/unreadable message is intact,
pinning "un-`stat()`-able is not a freshness failure". Determinism, precisely: the
**guard-specific** tests are decided purely by `os.utime`-set mtimes against a fixed 1970-era
synthetic run start, while the ~40 **pre-existing** located/table/pattern tests pass the guard
because a file written at real wall-clock time has an mtime far past that 1970-era stamp. **No real
repo, network, or pip in CI.** **Known debt carried, not introduced by this slice:** the flat
`--results` read catches only `json.JSONDecodeError`, so a **non-UTF-8 `results.json` raises
`UnicodeDecodeError` out of `run_reproduction`** rather than degrading to `UNVERIFIED`; the three
locator observers already handle it (they catch `(ValueError, OSError)`, which covers
`UnicodeDecodeError`), making the flat path the lone outlier. Fixing it is a behavior change
needing its own test and is out of scope for a freshness slice.

**Shipped (remote intake — slice 6, Unreleased).** Every slice above assumed the user had already
cloned the paper's repo and could point `contig reproduce` at a local directory — so the bundle's
`repo` field was a **local path that means nothing to anyone else**, and the verdict was not
attributable to a revision. `contig reproduce <https-url> --allow-fetch` now closes that: the repo
is shallow-cloned (`git clone --depth 1 -- <url> <dest>`) into `<runs-dir>/<reproduce_id>/source/`,
`HEAD` is resolved, and the 40-hex commit is recorded on two **additive** `ReproduceRecord` fields,
`source_url`/`source_commit` (both default `None`; `reproduce.json` emits **both keys
unconditionally**, `null` for a local run, so a consumer never needs a `.get()` dance). The
record's `repo` holds the **URL**, never the per-run checkout path — a scratch path under someone's
runs directory is meaningless to a reader, while URL + commit is the portable pin that makes a
reproduction claim checkable by a third party. **`--allow-fetch` is off by default** and a URL
without it is refused naming the flag: like `--allow-install` it gates a side effect the user may
not want (it reaches the **network** and writes a checkout under `--runs-dir`), and the two flags
are independent — neither implies the other. **Classification is pure and ordered, refusing before
anything is written:** a leading `-` is refused **first and unconditionally**, ahead of all scheme
parsing (an argument like `--upload-pack=…` reaching git as an *option* rather than the repo
positional is a remote-code-execution shape, so no scheme or path pattern can be crafted to bypass
it); then `https://` is accepted **verbatim, unnormalized** (it becomes provenance); then a DOI
(`doi:…` or bare `10.<digits>/…`) is refused **naming DOI explicitly** so a pasted DOI gets the
real reason instead of "No such repo directory: 10.1234/xyz"; then `http`/`ssh`/`git`/`file`/git's
arbitrary-command `ext::`/scp-like `git@host:path` are refused naming `https://`; everything else
is a local path exactly as before. The `--` terminator in the clone argv is a **second line of
defence**, not cosmetic. **The pin is validated, never scavenged:** `git rev-parse HEAD`'s output
is stripped and matched with `fullmatch` against 40-hex — not searched for a SHA-shaped substring —
so a multi-line output (the fetcher merges stderr into stdout, since git's stderr is the only
useful clone diagnostic) is **refused outright**; a fabricated pin is worse than no pin. Every
failure path (bad URL, failed clone, failed `rev-parse`, unvalidated SHA, non-empty destination)
exits non-zero with **no bundle and no leftover directory**, with cleanup scoped to what the call
created (`<id>/source` always; its parent only if this call created it, so a caller's pre-existing
directory is never deleted out from under it). **The clone happens BEFORE the run-start freshness
stamp, and that ordering is load-bearing:** a `git clone` writes *every* file at clone time, so
stamping first would make every author-committed artifact look freshly written by this run and
**silently disable the guard above on exactly the repos it exists for** — real, published,
third-party ones. Verified by mutation (invert the ordering and
`test_committed_results_file_in_a_fetched_checkout_stays_unverified` flips from `unverified` to
`reproduced`); any future refactor of this command's preamble must preserve it. **The checkout is
evidence, not attestation:** `_maybe_write_signature` signs the **record** only — the `source/`
tree is unsigned and unhashed and can be modified afterwards with nothing detecting it, so **the
commit SHA is the attested fact and `source/` is a convenience copy for inspection**; hashing the
tree is deliberately a separate slice. **Caveat for signing users, disclosed not fixed:** because
`canonical_record_bytes` is `record.model_dump(mode="json")` (`signing.py:63`) and includes every
field, a **pre-slice-6 signed reproduce bundle no longer verifies** — it still *loads* (both fields
default to `None`, tested) but its canonical payload now carries two extra `null` keys. Verified
empirically. Same shape as the somatic FAIL-floor slice's `verdict` disclosure, with one honest
difference: **that blast radius was only bundles whose verdict flips; this is *every* signed
reproduce bundle** (signing is opt-in via `CONTIG_SIGNING_KEY`, which bounds it — not a reason to
soften it). Not fixed because canonicalizing with `exclude_none` would change `RunRecord`'s bytes
too and break **every** existing signature — strictly worse; pinned instead by
`test_pre_slice_6_signature_over_a_record_without_source_fields_no_longer_verifies`. **Honest
limits:** **no real git, network, or repo in CI** — the `Fetcher` seam is injected everywhere
(mirroring `Executor`/`IndexBuilder`/`Installer`) and the real `default_fetcher` is asserted on for
**argv shape only, never executed** — so the slice is **reasoned and unit-tested, not observed: no
real clone has been performed**, and the go/no-go is a post-merge manual smoke test (clone one
small real public repo, confirm the SHA is recorded and that a repo with committed outputs reports
`UNVERIFIED`) that **has not been run yet**; and **bundle-local checkouts are never pruned**, so the
runs directory grows. No new dependency (stdlib `subprocess`/`shutil`; `git` needed only on the
remote path). **Still deferred:** DOI resolution (explicitly out of scope, refused with a message
saying so), hashing or signing the checkout tree, private-repo credentials, submodules, and
checkout pruning. (`--rev`/tag/branch selection was deferred here and **shipped in slice 7**,
below, which retires this slice's RISK-5. Hashing the checkout tree was likewise deferred here
and is **shipped in slice 8**, below, closing this paragraph's own "hashing the tree is
deliberately a separate slice" disclosure.)

**Shipped (revision pinning — slice 7, Unreleased).** `--rev <sha|tag|branch>` makes a remote
reproduction **replayable** rather than merely attributable, retiring slice 6's RISK-5: until now
**nothing in the product consumed `source_commit`**, and the clone was always `--depth 1` of
whatever `HEAD` happened to be at fetch time — so re-running after the authors pushed silently
reproduced a *different* revision than the bundle attested to, with no error. With `--rev`, a
targeted fetch (`git init` / `remote add origin --` / `fetch --depth 1 origin -- <rev>` /
`checkout --detach FETCH_HEAD`, all cwd'd to the destination) replaces the clone. **The mechanism
is the ruling slice 6 left open** ("`--depth 1 --branch <ref>` **or** a targeted fetch"): they are
not equivalent — `--branch` accepts a tag or branch **only and rejects a raw SHA**, and a raw SHA
is the input that matters most since it is exactly what `source_commit` contains. Verified against
real git that one targeted fetch resolves a full SHA, a tag, and a branch. **A requested full SHA
must equal the resolved one** or the run refuses — a pin that is not what was asked for is worse
than no pin — while a tag/branch has nothing to compare against. `--rev` requires a URL **and**
`--allow-fetch`; with a local repo it is **refused, not ignored**. **An abbreviated SHA is refused
up front** naming the full form (git cannot fetch one, and a 7-hex string is a *valid refname* so
the refname rules would not catch it). **A remote refusing fetch-by-commit is an honest refusal**
naming `uploadpack.allowReachableSHA1InWant` and suggesting a tag/branch — a full-clone fallback
was **declined by design** (it can pull gigabytes unasked), with the first blocked real repo as the
revisit trigger. Validation is pure and ordered with a **leading `-` refused first and
unconditionally** (the RCE shape), plus `--` terminators verified to be accepted by `git remote
add` and `git fetch`. **The requested ref lands in the UNSIGNED `reproduce.json` as
`requested_rev`** (additive `write_reproduce_bundle` parameter) and **not** on the record: a new
signed field would have re-broken **every v0.47.0 signed reproduce bundle**, a second break in two
releases — so existing signatures still verify (asserted, not assumed), at the stated cost that a
tag/branch requested-ref is **not attested**. Without `--rev` the clone path is **byte-identical**
to slice 6 (its whole test file passes untouched), and the fetch still precedes the run-start
freshness stamp — **verified by mutation**, which kills both slices' ordering tests. **Honest
limits:** fetch-by-bare-commit depends on **server policy** that **CI cannot observe** (the
validating experiment used the permissive local transport and proves client mechanics only);
tag/branch have no such dependency; no real git, network, or repo in CI; the manual gate — now
carrying slice 6's never-run checklist too — remains the only real validation. No new dependency.
Plan/PRD under `docs/planning/reproduce-rev-pin/`.

**Shipped (paper-claim extraction — Unreleased).** Slices 1–7 built the whole verify/locator/
bundle spine, but the user still had to **hand-author the claims file** — the last manual step
between a published paper and a checkable reproduction, and exactly the "paper-parsing to extract
claims" item every prior C8 slice deferred. `contig extract-claims <paper.txt|md> --out
<draft.json>` now turns a paper's **plain text/markdown** into a **draft** claims file the user
reviews and completes. It is claims-file **input generation** only — it does **not** touch
`run_reproduction`, `classify`, `ClaimResult`, `ReproduceRecord`, the bundle, signing, or any exit
code (the whole reproduce suite is untouched). A **deterministic stdlib-only core** (a new
`verification/claim_extraction.py`, never raises) extracts **named-metric + number** claims from a
curated metric vocabulary joined to a number by a connective within a bounded window; percentages
keep the **raw** value with `unit="%"` (never ÷100 — the human reconciles scale), inequalities are
skipped (`p < 0.001` is not a point value), ids are a deterministic per-file metric slug, duplicates
collapse on `(metric, value)`, and the nearer metric owns a shared number (precision over recall).
An **optional env-gated LLM assist** (`extract_with_llm`) mirrors the shipped `llm`-detector seam
exactly — gated on the reused `detect._selected_provider()`, a single lazy-SDK/network touch point
tests monkeypatch, a defensive prose-tolerant reply parser that swallows every error into `[]`, and
`merge_claims` with the core winning; importing the module pulls **no** provider SDK, the real seam
is **shape-asserted only** in CI (fake `anthropic`/`openai` in `sys.modules`) and **never executed**
(a documented manual pre-merge gate runs it once), and no key is logged. **The load-bearing
invariant:** the command round-trips its draft through the **unchanged `load_claims`** before
committing `--out` (temp → `os.replace`; a `ClaimsError` is an internal error, exit non-zero,
nothing written), so it never emits a draft the reproduce path would reject. The draft is
**locator-less by design** (`id`/`value`/`tolerance` only — the paper gives the value, not where it
lives in the repo, so inventing a locator would be dishonest; the user adds it during review), with
a companion **`<out>.review.md` sidecar** carrying per-claim value/unit/origin/source-sentence and
the workflow guidance the JSON can't. Honest on every boundary: missing/oversized (> 8 MiB,
`stat()`ed first)/non-UTF-8 input, `--out` == input, or an existing `--out` without `--force` all
exit non-zero with nothing written; an empty extraction writes `[]` + a "no claims found" sidecar
and exits **0**; `--no-llm` forces core-only; flags asserted by Click-param introspection, not
`--help` scraping. Because extraction only ever produces a draft the user reviews, and any
unreviewed/wrong claim degrades to `UNVERIFIED` at reproduce time, it can be imperfect **without
ever manufacturing a false `REPRODUCED`**. **Deferred:** PDF/DOI/paper-fetching, locator inference,
figure/plot & table-image claims (still hard-blocked — no plot-hash, stdlib-only), a dashboard card.
Stdlib-only core (`re`); the provider SDK is a lazy optional import — no new
dependency; no real LLM/network/PDF/repo in CI. Plan/PRD under `docs/planning/reproduce-paper-claims/`.

**Shipped (DOI/PDF intake — the paper-fetch slice, Unreleased).** The paper-parsing deferral's
other half closes: `contig extract-claims` now accepts a paper **DOI** (`doi:10.x/y`, bare
`10.x/y`, `https://doi.org/…`) or a **local `.pdf`**, converting the PDF to text through an
injectable `pdftotext` seam and feeding the **shipped extractor unchanged**. A pure
`classify_paper_argument` (mirroring `classify_repo_argument`) refuses a leading `-` first
unconditionally, classifies DOI forms via the shared `_is_doi` (a DOI containing `?`/`#` is
refused — a different document), and refuses **any other URL scheme before the `.pdf`
extension** (a remote `x.pdf` is never read as a local path). DOI fetch is stdlib-only
(`urllib` + `html.parser`): `default_paper_fetcher` resolves `https://doi.org/<doi>` (30 s
timeout), takes a response that is itself a PDF (Content-Type or `%PDF` magic) directly, and
otherwise locates the PDF via the landing page's `<meta name="citation_pdf_url">` — absent →
paywall-aware refusal ("the paper may be paywalled; download the PDF and pass its path
instead"), **duplicate metas → refusal naming the count, never guessed**. `pdftotext`
(poppler) runs behind an injectable `PdfTextExtractor` seam (Fetcher/Installer mould);
missing tool → `(127, …)` naming the install, never a traceback. Bounds: landing page 2 MiB,
PDF 64 MiB (`MAX_PDF_BYTES`, reasoned-uncalibrated), extracted text 8 MiB (the existing
`_MAX_MATCH_BYTES` input contract) — every give-up exits non-zero with the reason and
**nothing written**, temp cleaned on every path. `--allow-fetch` (off by default) gates the
network in the slice-6 posture: a DOI without it is refused naming the flag, and the
`--out`/`--force`/`--out-dir` guards fire before any fetch. The review sidecar gains a
`Source:` line for DOI/PDF sources; the text path is byte-identical. **Manual post-merge
gate RUN (2026-08-27) and passed condition (a) with (b) recorded:** a real Scientific
Reports DOI fetched through the real urllib path yielded a draft (`accuracy 50.0`); the
GigaScience landing page refused with HTTP 403 (publisher bot protection — surfaced
honestly), a nonexistent DOI was refused with 404, and a paywalled Nature paper served its
full-text PDF anyway, yielding an honest empty draft (the paywall refusal remains pinned by
unit tests only). Test-first, 2754 passed / 1 skipped, `test_cli_extract_claims.py` green
unmodified, no new dependency, no real network/PDF/`pdftotext` in CI (injected seams).
Plan/PRD/specs under `docs/planning/reproduce-doi-pdf-intake/`. **Deferred:**
direct non-doi.org PDF URLs, locator inference, PDF-table extraction, a `--pdf-extractor`
override, a loopback-server test of the real urllib path (the "no real network in CI"
posture), and figure/plot claims (still hard-blocked).

**Shipped (checkout-tree hash — slice 8, Unreleased).** Closes the gap slice 6 disclosed in its
own words above ("hashing the tree is deliberately a separate slice"): a remote (`--allow-fetch`)
reproduce run now records a deterministic content hash of the fetched `source/` checkout, so the
bundle attests *which bytes* produced the verdict, not only *which commit* was nominally fetched.
A new pure, stdlib-only `compute_tree_sha256(root)` (`bundle.py`, next to
`compute_output_checksums`) walks with `os.walk(followlinks=False)`, prunes any directory
component named `.git` (any depth) and any symlinked directory, keys each regular non-symlink
file by its POSIX-relative path with `sha256_file` as the value, folds the sorted
`f"{relpath}\0{hexdigest}\n"` lines (NUL delimiter), and returns the hex SHA-256 of that UTF-8
blob — published so a third party can recompute it byte-for-byte without git or Contig's source.
A missing/non-directory root or any `OSError` reading a file returns `None` for the whole digest,
never a partial or fabricated one. **Computed pre-run and remote-only:** right after `fetch_repo`
succeeds and before the `run_started_at` freshness stamp, over `repo_path`, so neither an
`--allow-install` retry nor the run's own writes into the checkout can change the recorded value;
a local repo-path run records `None`. **Signed:** the new additive
`ReproduceRecord.source_tree_sha256: str | None = None` rides the existing
`canonical_record_bytes` signature unchanged; `reproduce.json` gains an unsigned echo, emitted
unconditionally like `source_url`/`source_commit`. **What it adds over `source_commit` — stated
honestly:** for a full-SHA pin the commit already binds the tree, so a re-clone plus
`git rev-parse HEAD` proves much the same thing; the marginal value is the `--rev` tag/branch case
slice 7 left "not attested", git-free verification (no git or network needed to recompute), and
groundwork for the deferred local-path and shipped-`source/` hashing. **Honest limits:** it
attests bytes present/rewritten at hash time, not that they were *scientifically* recomputed
(same boundary as the freshness guard); and it attests the commit↔tree linkage verifiable by
re-clone, deliberately **not** the bundle's post-run `source/` copy (which gains the run's own
outputs after the hash is taken — a distinct, deferred feature). **Caveat for signing users, the
third disclosed signature break, not fixed:** the new signed field changes
`canonical_record_bytes`, so a pre-slice-8 signed reproduce bundle still *loads* but no longer
*verifies* — after slice 6's `source_url`/`source_commit` and the somatic FAIL-floor's `verdict`,
bounded to opt-in `CONTIG_SIGNING_KEY` signers, pinned by
`test_pre_slice_8_signature_over_a_record_without_tree_hash_no_longer_verifies`. Unlike every
prior C8 slice, the core of this one is **fully CI-observable** — real fixture trees on disk, no
injected-seam reasoning required — only the CLI-remote wiring rides the `Fetcher` seam. No new
dependency (stdlib `hashlib`/`os`). **Still deferred:** hashing the
bundle's `source/` copy as shipped (post-run), paper-parsing, figure/plot claims, DOI resolution,
private-repo credentials, submodules, checkout pruning, dashboard card. Plan/PRD under
`docs/planning/reproduce-checkout-hash/`.

**Shipped (local tree hash — slice 9, Unreleased).** Closes the "local-path checkout
hashing" deferral slice 8 named above: a **local** `contig reproduce <path> --run` run now
records `ReproduceRecord.source_tree_sha256` too — the user's directory hashed pre-run,
before the run-start stamp, via the same `compute_tree_sha256` (which gains an optional
`exclude` parameter). One universal exclusion rule on both branches: the CLI passes the
resolved `--runs-dir` whenever it is a descendant of the hashed tree (the
`cd repo && contig reproduce .` shape), so Contig's own prior bundles never contaminate its
own measurement; for remote it is a provable no-op (the runs dir is the checkout's parent).
**Honestly narrowed, not inherited:** local has no `source/` copy and no commit, so the value
is drift evidence over time + tamper-evidence (the digest rides the signature) +
disambiguation (`null` now means only "could not be computed") — **not** third-party
attestation, which is stated plainly rather than over-sold. A `None` digest degrades honestly
and never fails the run. Not a signature break (key set unchanged). Local
`source_commit`/dirty-state capture named as the deferred follow-on. No new dependency.
Plan/PRD under `docs/planning/reproduce-local-tree-hash/`.

**Shipped (C6 eval fold-in — reproduce-guard slice, Unreleased).** The reproduce track
is now fold-in'd into the C6 flywheel as the **fourth regression guard**: `contig
reproduce-guard` replays a frozen `ReproduceScenario` set
(`src/contig/data/reproduce_scenarios.jsonl`, **14 scenarios**) through the **real**
`run_reproduction` loop — real `load_claims`, real `classify`, real locators, real
freshness guard — with only the executor/installer seams scripted, and guards the
per-scenario **outcome-match rate** against a committed baseline
(`src/contig/data/reproduce_baseline.json`, `--update-baseline` refreeze, sha/version
warnings). The committed baseline is honestly **13/14 (92.9%)** — the single mismatch is
the deliberate `known-miss` scenario, the liveness demonstration that the number can sit
below 1.0 — over all five locator families (`flat`/`json`/`table`/`pattern`/`notebook`)
plus a stale-artifact case and the env-resurrection heal (`installed_and_retried`, the
slice-2 repair, with its install-fail give-up); `recovery_rate` (1/14) rides along
informational-only, never guarded. Flags mirror verify-guard
(`--update-baseline`/`--snapshot`/`--history`/`--json`/`--tolerance`), the trend is the
append-only `reproduce_history.jsonl`, and CI wiring sits immediately after
`verify-guard`. **Honest scope, stated not softened:** the guarded number is over a
**synthetic, self-graded seed** — we authored the fixtures we grade — with **no real
repo, git, network, or pip in CI** (scripted executor/installer, injected run stamp);
it is **push, not demand-pull** (organic reproduce-run volume unmeasured); it
**recovers nothing for a user** (it changes what CI guards, not what the engine does);
and the guard is live only via the anti-tautology **mutation-control pin**, not field
data. **Shipped (capture/promote channel — Unreleased).** The channel now ships: a
finished `contig reproduce` run earns a pending `ReproduceCase` in the sidecar
`<runs_dir>/pending_reproduce_corpus.jsonl` whenever it is interesting for a human —
any `diverged`/`unverified` claim, any repair history, or a non-zero exit — always-on,
no flag toggles it, and a clean run is never captured (the honest-skip contract); the
capture writes ONLY the sidecar, leaving the bundle untouched. `contig
reproduce-case-promote` moves a reviewed case from pending into the golden corpus
`src/contig/data/reproduce_corpus.jsonl` (created on first promote), with per-claim
`--expected-claims id:status` partial labeling (optional `--expected-repair` /
`--expected-exit`), and the informational scorer re-derives each claim under the
CURRENT `classify` bands via the shipped classify with an injectable classifier seam
(the mutation-control pin: a mutated looser classifier must flip stored cases),
counting only labeled claims; every promote auto-snapshots a
`ReproduceCorpusSnapshot` into the committed `reproduce_corpus_history.jsonl` trend.
**Honest scope, restated:** the golden corpus starts **empty** (created on first
promote), remains **push, not demand-pull**, CI still touches **no real repo, git,
network, or pip** (scripted seams), the guard stays **13/14** with every baseline
unmoved — the golden corpus is deliberately never the guard's default, so golden cases
never leak into the regression guard — and no signed field changed (models purely
additive). **Revisit trigger:** if the next **20 real reproduce runs** file zero
non-authored pending cases, the channel is restated as taxonomy-only. The other
standing C8 deferrals are unchanged: PDF/DOI
resolution, figure/plot & table-cell(-image) claims (hard-blocked — no plot-hash,
stdlib-only), a dashboard card, checkout pruning, private-repo credentials, submodules,
local-path & shipped-`source/` tree hashing, and the locator niceties (multi-key row
match, `occurrence`/`group` selectors, notebook-specific size bound, a structured
staleness field on `ClaimResult`). A **real-repo smoke test remains a manual post-merge
gate**, per every prior C8 slice.

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
unresolvable environment yields `UNVERIFIED`, never a false reproduce. **The acceptance suite stays
deterministic and offline** — every network-touching seam (`Installer`, `Fetcher`) is injected, and
no test performs a real install or clone. That is now a statement about **CI**, not about the
command: as of the `--allow-install` (slice 2) and `--allow-fetch` (slice 6) flags, `contig
reproduce` **can** reach the network when the user opts in. Both are off by default, so the default
invocation still touches nothing beyond the local repo — but "no network" is a property of the test
harness and of the defaults, not an absolute property of the command.

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
| C2 | Self-heal breadth plus auto resource-scaling | M2 to M3 (resource-aware + single-file missing-index family `.fai`/`.bai`/`.tbi`/`.csi`/`.dict` shipped; chr-prefix GTF harmonization shipped; per-contig alias harmonization (mito `M`↔`MT` + GRCh38 scaffold seed) shipped; directory-shaped STAR index build+redirect shipped, classic BWA + bwa-mem2 detector+corpus-only (v0.11.0); peak-RSS-informed OOM memory scaling shipped (Unreleased, honest two-tier: own-peak → blind fallback; sibling rescue deferred); walltime-informed `time_limit` scaling shipped (Unreleased, floored at blind — censored realtime, tail-only win + field instrument); **input-format-conversion class's first slice shipped (Unreleased): bgzip'd (non-BGZF) reference FASTA self-heal, sarek-scoped (rnaseq immune by construction), stream-decompress to uncompressed `.fa` + retry; CRAM↔BAM conversion is the deferred second half**; **opt-in heartbeat stall watchdog shipped (Unreleased): `--detect-stalls`/`--stall-timeout` (default 3600 s, OFF by default) supervise the child over a composite `trace.txt`/`.nextflow.log`/`run.log` heartbeat, terminate a stalled run's process group, and make `no_progress` reachable by the detector for the first time — honest limits: never observed on a real run, uncalibrated window, no real Nextflow in CI, Nextflow-only, not persisted to the launch manifest (D4)**; **stale-index rebuild slice shipped (Unreleased): an index older than the data it indexes (htslib `hts_idx_load3` family) classifies `missing_index` via a freshness-anchored branch ordered before the generic missing-index branch (confidence 0.85), rebuilt into scratch via a symlinked source + the unchanged `_INDEX_BUILD` table and atomically swapped (same-dir dot-temp fallback on cross-device) — user's file never half-written, build-once, honest give-ups, `built_index_and_retried` with mtime+argv detail; golden `stale-bai` corpus case + `stale-index-heal` heal-guard scenario (21 scenarios, covered_classes 15, baseline refrozen 4afc3513…); honest scope: push not demand-pull, needle reasoned not observed, `.fai` covered defensively (samtools silently rebuilds a stale `.fai` — hard-fail surface is `.bai`/`.csi`/`.tbi`); no signature break**; bwa-mem2/classic-BWA build+redirect, assembly-signature + exhaustive per-assembly alias completeness, stall-window calibration + on-by-default pending) | Unattended-completion rate, corpus fuel |
| C3 | Biological-plausibility verification | SHIPPED v0.3.0 (germline) + RNA-seq (v0.6.0) + single-cell ingestion (Unreleased) + germline sex-check (Unreleased) + RNA-seq mapping-composition (Unreleased) + germline variant-count (Unreleased) + germline plausibility FAIL-severity (Unreleased) + somatic empty-call-set FAIL floor (Unreleased) + RNA-seq plausibility ingestion fix (Unreleased) | Verdict gets smarter about biology (germline Ti/Tv, het/hom, sex-check, variant-count band — germline Ti/Tv, het/hom, and variant-count now **FAIL** on gross implausibility via WES-safe bands; somatic `variant_count` now **FAILs** on an empty call set; a FAIL verdict reaches the exit code only under the opt-in `--fail-on-verdict`; RNA-seq `duplication_rate` now correctly keyed to MultiQC's `PERCENT_DUPLICATION`/a 0-1 fraction — informational-only, no band by design — after never once firing under its old wrong key/unit; `rRNA` remains a guessed slug, WARN-capped; + exonic/intronic/unassigned read-composition from RSeQC read_distribution; single-cell cell-QC now *fires* via STARsolo/Cell Ranger ingestion — was a dormant no-op; gene-body-coverage/mito/doublet deferred; **somatic-VAF and RNA-seq FAIL severity declined by design, not deferred** — tumor VAF's expectation depends on unobserved purity/clonality, and every RNA-seq extreme is a legitimate protocol; annotation-pack FAIL severity is a separate C7 item, still deferred) |
| C4 | New assay: somatic variant calling | SHIPPED v0.13.0 (intake→launch→verify) + VAF/count/PON plausibility slice (Unreleased) + Strelka2-vs-Mutect2 concordance slice (Unreleased) + Strelka2-native VAF slice (Unreleased) + empty-call-set FAIL floor (Unreleased — `somatic_variant_count fail_below: 1`; **VAF/PON FAIL bands declined by design, not deferred**: tumor VAF depends on unobserved purity/clonality, `strelka_median_vaf` is bounded to [0,1] so a ceiling is dead code, `pon_applied` is a non-numeric 3-state string) + swapped-pair smell-test slice (Unreleased — `normal_median_vaf`, the median VAF over the Mutect2 VCF's NORMAL column via a new never-guessing `##normal_sample=` resolver, WARN-capped at `warn_above: 0.30`, UNVERIFIED-when-unresolvable; a *smell*, not a determination — swap, mislabel, and tumor-in-normal contamination give the same number and the message names all three; the call-set-depleting form of a swap is already covered by the `fail_below: 1` floor); PON reference wiring deferred | Breadth, depth-first, new corpus |
| C5 | Reference and input-data integrity | M5 (reference-identity **capture** slice shipped — explicit `sha256` + iGenomes key-only, rendered in methods/panel; pre-flight **mismatch detector**, known-sites, GTF version, RO-Crate pending) | Kills a silent-failure class, deepens reproduce |
| C6 | Eval flywheel as a continuous loop | M6 (detector held-out guard slice 1 SHIPPED, Unreleased — shipped honestly at 0.833/10:12, two classes structurally unreachable; repair-loop outcome-match guard slice 2 SHIPPED, Unreleased — shipped honestly at 1.0/7:7, 5 classes covered; both wired into CI; **both guards moved for the first time in the C2 stall-watchdog slice (Unreleased): eval-guard 0.846 → 0.923 (12/13), flat across all six recorded trend points v0.22.0 → v0.48.0 until now, and heal-guard covered classes 5 → 6 with outcome-match still 1.0 over 8 scenarios — partly self-graded (we wrote the fixture for the class we made reachable), and `qc_anomaly` remains the sole unreachable class**; **the `qc_anomaly` verdict-trigger slice (Unreleased) then closed it — heal-guard covered classes 6 → 7 over 9 scenarios, outcome-match still 1.0, and no failure class is structurally unreachable any more; `eval-guard` deliberately unmoved at 92.3% (its held-out case is log-text shaped and closing it would need needles Contig never emits), it recovers nothing by design, the recovery 0.625 → 0.667 move is an artifact of a green-by-construction scenario, and organic frequency is 0 of 17 recorded runs under today's bands**; **the `patch_applied` slice (Unreleased) then retired that very artifact**: `RepairStep` gained a control-flow-derived `patch_applied` (set at all 11 `_record_attempt` sites from `_apply_patch_and_maybe_build`'s existing `continue_` — never from the outcome string, since `apply_patch` runs on that helper's first line and the naive rule would stamp four failure branches as applied), so `heal-guard`'s `recovered` became `succeeded AND any(step.patch_applied)`; exactly one frozen expectation changed (`qc-anomaly-verdict-flagged` `true` → `false`) and **guarded outcome-match stayed 1.0 because that correction landed in the same commit**, while the informational `recovery_rate` 0.667 → 0.556 is a **correction whose sixth trend point is not comparable to the prior five**; scenarios also gained an optional `expected_patch_applied` asserted through the real loop, `eval-guard` correctly unmoved at 92.3%, and it is the **fourth but narrowest** signature break (nested key → an empty `repair_history` still verifies, tested not asserted); **the catalog-coverage slice (Unreleased) then widened the frozen set, and its deferral is the finding**: `heal-guard` 9 → 16 scenarios and covered classes 7 → 11 (`missing_reference`, `reference_not_bgzf`, `container_pull_failed`, `download_failed`), guarded outcome-match **still 1.0**, informational recovery 0.5556 → 0.5625 (9/16), `eval-guard` unmoved at 92.3% with the detector corpora untouched, the nine pre-existing lines byte-identical, and one additive `HealScenario.fasta_artifact` **named fixture directive** (a real plain-gzip FASTA driving the **real** `_recompress_reference`, never an injected outcome) — **the brief asked for all nine uncovered classes and only four shipped deliberately**, because the other five have **inert** repairs — four `env` patches (`disk_full`, `permission_denied`, `conda_solve_failed`, `platform_unsupported`) string-merged into `backend_options` and read by nothing, plus `container_unavailable`, whose `retry`-kind patch makes `apply_patch` a documented no-op so its promised `wait_seconds` is silently dropped — so covering them would have frozen five suspect expectations into CI; a C2 follow-up is filed with **propose-vs-don't as its first question**, and a gap-pinning test turns red the moment any of the five is implemented or withdrawn; **read honestly**: push not demand-pull, synthetic throughout, self-graded, it recovers nothing new for a user, and `covered_classes: 11` is a count of frozen scenarios, not a claim the engine handles those failures well; **held-out-accuracy trend SHIPPED** — `holdout_history.jsonl`/`heal_history.jsonl`, `--snapshot`/`--history`, and the dashboard's `holdout-history.tsx`/`heal-history.tsx` cards (this row previously still called it pending, which was stale); **the C1/C3 fold-in SHIPPED (Unreleased)** — labeled verification corpus + `contig verify-guard` + capture/promote channel, honest scope: synthetic self-graded seed (baseline deliberately < 1.0 via a known-miss case), non-tautological only as real runs get labeled; concordance-family capture deferred at the time, now CLOSED for the run-dir-derived families — `concordance_somatic_overlap`, `concordance_consequence`, `somatic_plausibility`, `annotation_plausibility` captured into `verification_inputs` (stats out-params, per-kind status-consistency + round-trip + family-key pins, guards unmoved); `concordance_spearman`/`concordance_genotype` stay deferred — their second sets exist only at `contig verify` time, committed revisit trigger); **the reproduce fold-in SHIPPED (Unreleased)** — `contig reproduce-guard`, the fourth guard, replays 14 frozen reproduce scenarios through the real `run_reproduction` loop (scripted executor/installer seams only) and guards the per-scenario outcome-match rate at a committed baseline of **13/14 (92.9%)**, the single mismatch the deliberate known-miss, over all five locator families plus staleness and the env-resurrection heal; reproduce-outcome capture/promote (the capture-promote aspect) stays pending in the follow-on slice) | Compounding accuracy from real runs |
| C7 | Research-use variant annotation & prioritization | M1 + M2 + M3 + M4 + M5 surface+provenance SHIPPED (Unreleased) — germline structural verify + provenance, somatic annotation gate, annotation plausibility (both assays), VEP-vs-SnpEff concordance (both assays: `consequence_concordance` WARN-capped + `gene_symbol_concordance` informational, auto in the verdict, both VCF layouts, annotator-version provenance pair), M5 "corroborated by" line across text/HTML report + `contig methods` + dashboard (reads M4 results, never recomputes) + `AnnotationProvenance.db_version` cache/build token (VEP `cache=` / SnpEff genome) rendered and round-tripped through reproduce with pre-M5 back-compat; **M5 C6 eval fold-in SHIPPED (Unreleased)** — labeled verification corpus + `contig verify-guard` + capture/promote channel (see C6; honest scope: synthetic self-graded seed, non-tautological only as real runs get labeled) (germline+somatic `annotation_present`/`annotation_complete` structural checks via `VARIANT_ASSAYS`, `AnnotationProvenance` tool+cache/build capture, `--tools …,vep` enablement on both assays, `annotation_real_fraction`/`annotation_consequence_distribution` plausibility checks, all WARN-capped/UNVERIFIED-when-absent; **the live-cache caveat is CLOSED — `annotation-cache-wiring` (Unreleased) injects `download_cache=true`/`outdir_cache` for both variant assays, so a real run downloads its VEP/SnpEff cache instead of hard-failing cache initialisation (the caveat's "UNVERIFIED" wording was optimistic — sarek `error()`s on a missing cache; verified in source); `--step annotate` unused (restart mode); download keyed to sarek's default GATK.GRCh38 genome attrs — custom-reference runs get a wrong-build cache, accepted; user-supplied cache paths still a future slice; verify-only, prioritization deferred) | Disease-research breadth on-thesis, new corpus; run+verify annotation, never a clinical verdict |

| C8 | Reproduce & verify *existing published* work | first slice SHIPPED v0.40.0 + output-locator slice 1.5 SHIPPED v0.41.0 + env-resurrection slice 2 SHIPPED (Unreleased) + TSV/CSV table-locator slice 3 SHIPPED (Unreleased) + stdout/log pattern-locator slice 4 SHIPPED (Unreleased) + notebook (`.ipynb`) locator slice 5 SHIPPED (Unreleased) + freshness guard across **all** binding surfaces SHIPPED (Unreleased) + remote `https://` git-URL intake slice 6 SHIPPED (Unreleased) + `--rev` revision pinning slice 7 SHIPPED (Unreleased) + checkout-tree hash slice 8 SHIPPED (Unreleased) + paper-claim extraction (`contig extract-claims`) SHIPPED (Unreleased) + **DOI/PDF intake slice SHIPPED (Unreleased)** — `extract-claims` accepts a DOI (`doi:…`, bare, `https://doi.org/…`) or a local `.pdf`; pure `classify_paper_argument`; stdlib `urllib` DOI→PDF fetch (PDF-first sniff, `citation_pdf_url` meta, paywall-aware refusal, duplicate-metas never guessed) behind opt-in `--allow-fetch`; injectable `pdftotext` seam (`(127, …)` naming the install); 64 MiB PDF / 8 MiB extracted-text caps; nothing written on any failure; manual real-DOI gate RUN and recorded + **C6 eval fold-in (`contig reproduce-guard`) SHIPPED (Unreleased)** · M7+ | Turns the engine on third-party papers (repo+claims → per-claim `REPRODUCED`/`WITHIN-TOLERANCE`/`DIVERGED`/`UNVERIFIED`); strongest quantified pain (~3.2% of 27,271 notebooks reproduce), a free viral community-trust channel, and a new publicly-sourced corpus stream. **Shipped:** `contig reproduce <repo> --run --claims` walking skeleton — scalar per-claim verdict reusing `benchmark._relative_delta`, values bound from a repo-written `results.json`, signed re-runnable bundle via the generic signer, `--fail-on-diverged`; cooperative-repos-only, UNVERIFIED-when-unresolved, no real repo/network in CI. **+ Output-locator (slice 1.5):** a claim may carry `{"from": <repo JSON>, "path": "$.a.b[0]"}` to read numbers out of a repo's own **structured JSON as-is** (a new stdlib dotted+`[n]` `resolve_pointer` walker that never raises; located claims classify through the unchanged core; numeric-string strictly UNVERIFIED; escaping `from` refused pre-run + engine never reads outside the repo; JSON-only, full back-compat, no new dep). **+ Environment resurrection (slice 2):** opt-in `--allow-install` (off by default) turns a first run failing on `No module named 'X'` into a bounded detect→install→retry-once self-heal reusing C2 — pure `detect_missing_module` (charset-guarded top-level pkg) + injected `Installer` seam (fixed `pip install` argv, no shell), one install + one retry (provable termination), every unresolved path UNVERIFIED (never a false reproduce), heal recorded on additive `ReproduceRecord.repair_history` (`missing_dependency` literal kept reproduce-local so the C6 eval-guard baseline is unmoved), executor seam widened `int`→`(exit_code, output)`, no new dep, no real pip/network in CI. **+ TSV/CSV table locator (slice 3):** a claim may also carry `{"from": <repo .tsv/.csv[.gz]>, "column": <name|int>, "row": <int|{key:val}>, "header"?, "delimiter"?}` to read a **tabular** cell — DESeq2/count-matrix/feature-table output — via a new stdlib `_read_table`+`resolve_cell` reader (gzip-transparent, index-safe, never raises) and a per-run parse cache; a numeric-string cell is the normal, valid case here (unlike the JSON rule) and classifies through the unchanged core; row-key 0-or-many matches, ragged rows, duplicate/absent header names, and unparseable/non-finite cells all degrade to UNVERIFIED, never DIVERGED; reuses the JSON locator's containment guard, signer, bundle, and exit contract as-is, no `models.py` change, no new dep. **+ stdout/log pattern locator (slice 4):** a claim may also carry `{"pattern": <regex>}` — with `from` it matches a repo-relative text/log file, **without** `from` it matches the run's own captured stdout+stderr — so repos that merely `print()` their headline number become checkable at all; a new pure stdlib `resolve_match` (never raises) takes group 1 if the pattern has groups else the whole match, inline flags only, and is **strict on ambiguity** (0 or >1 matches → UNVERIFIED with the count named, never an arbitrary pick), with the non-participating-group shape (`float(None)` `TypeError`) guarded; matching is bounded at 8 MiB (a ReDoS input bound, not a memory guard — `default_command_executor` already buffers stdout uncapped upstream); `load_claims` compiles the regex pre-run (uncompilable → `ClaimsError`, nothing written) and the locator xor became three-way (`pattern` + any table field rejected, not silently ignored); the dispatch head became an explicit `isinstance` chain, the retried run's output binds for free via the observer closure, a numeric-string capture is the normal valid case (the slice-3 rule), a `from`-less claim never touches the filesystem, and the CLI containment loop gained only a `source is None` skip; no `models.py` change, no new dep. **Weakest locator shipped** — a regex binds to output formatting, so a non-match is UNVERIFIED, never DIVERGED, and a failed run still short-circuits before any locator. **+ Notebook (`.ipynb`) locator (slice 5):** a claim may also carry `{"from": <.ipynb>, "cell": <int|{"contains": s}>, "pattern": <regex>}` to bind a value out of a notebook cell's captured output (stdout streams + `text/plain`, in output order; `stderr`/tracebacks excluded), cell addressing mirroring `TableLocator.row` and capture reusing slice-4's `resolve_match`; introduced the **mtime freshness guard** so a committed notebook's stored outputs can never be read as a false REPRODUCED. **+ Freshness guard on all binding surfaces:** that guard now also covers the JSON locator, the TSV/CSV table locator, the file-mode pattern locator, and the flat `--results` read (slice 1's, the oldest instance and the one every cooperative repo uses) via one shared `_require_fresh` helper — a file whose mtime predates the run start is UNVERIFIED and is **never parsed**, closing the "repo commits its outputs → false REPRODUCED" hole; stdout-mode `pattern` is **exempt by construction** (no file to be stale); **non-bypassable** (no opt-out flag; an unstamped run start raises); an un-`stat()`-able path keeps the caller's missing/unreadable message; symlinks are followed deliberately; **honest limits:** it proves *rewritten*, not *recomputed* (a `cp`/`touch`/restored cache passes), there is **no fudge tolerance** and none will be added (coarse mtimes and clock skew can each yield a **false UNVERIFIED** — accepted, since a false UNVERIFIED is recoverable and a false REPRODUCED is not), and a legitimate run that does not rewrite an artifact (an up-to-date `make` target, a timestamped output dir, a final-step-only `--run`) now reports UNVERIFIED — a deliberate decision whose revisit trigger is the first real repo it blocks; the base rate of repos committing their outputs is **unmeasured and is not claimed**. No `models.py` change, no new dep, no CLI signature change. **+ Remote `https://` git-URL intake (slice 6):** the repo argument may now be an `https://` git URL behind opt-in `--allow-fetch` (off by default; a URL without it is refused naming the flag) — shallow `git clone --depth 1 -- <url>` into `<runs-dir>/<id>/source/`, `HEAD` resolved and recorded on additive `ReproduceRecord.source_url`/`source_commit` (both emitted unconditionally in `reproduce.json`, `null` for a local run), with `repo` holding the **URL** and never the per-run checkout path, so a bundle finally says *which revision of which repository* produced the verdict. Classification is pure and ordered — leading `-` refused **first and unconditionally** (an option reaching git instead of the repo positional is an RCE shape; `--` in the argv is a second line of defence), `https://` kept **verbatim** as provenance, DOI refused **naming DOI**, and `http`/`ssh`/`git`/`file`/`ext::`/scp-like refused naming `https://`. The pin is `fullmatch`ed against 40-hex on the whole stripped output (multi-line output refused, never scavenged for a SHA); every failure exits non-zero with **no bundle and no leftover directory**, cleanup scoped to what the call created. **The clone precedes the run-start stamp deliberately** — a clone writes every file at clone time, so stamping first would silently disable the freshness guard on exactly the published repos it exists for (verified by mutation). **The checkout is evidence, not attestation:** only the **record** is signed, so the commit SHA is the attested fact and `source/` is an unsigned convenience copy. **Caveat:** a pre-slice-6 **signed** reproduce bundle still loads but **no longer verifies** (the canonical payload gained two `null` keys) — every signed reproduce bundle, not just some; disclosed, pinned by a test, not fixed (an `exclude_none` canonicalization would break `RunRecord` signatures too). **Honest limits:** no real git/network/repo in CI (the `Fetcher` is injected; `default_fetcher` is asserted on for argv shape only) — **reasoned, not observed**, with the real-clone smoke test **not yet run**; `--rev` shipped in slice 7 below, so the pin is now **replayable**, not merely auditable; checkouts are never pruned. **+ `--rev` revision pinning (slice 7):** `--rev <sha|tag|branch>` makes the pin **replayable** (retiring slice 6's RISK-5) — a targeted fetch (`init`/`remote add`/`fetch --depth 1 <rev>`/`checkout --detach`) replaces the clone **only** when `--rev` is given, chosen over `clone --branch` because that rejects a raw SHA and a raw SHA is exactly what `source_commit` holds; a requested full SHA **must equal** the resolved one or the run refuses; an abbreviated SHA is refused up front (git cannot fetch one, and a 7-hex string is a *valid refname* the refname rules would miss); a remote refusing fetch-by-commit gets an honest refusal naming `uploadpack.allowReachableSHA1InWant`, **never** a silent full-clone fallback; `--rev` with a local repo is refused, not ignored; the requested ref lands in the **unsigned** `reproduce.json` as `requested_rev` so **every v0.47.0 signed bundle still verifies** (at the stated cost that a tag/branch ref is not attested); the no-`--rev` clone path stays byte-identical and the fetch still precedes the freshness stamp (**verified by mutation**). **Honest limit:** fetch-by-bare-commit depends on **server policy CI cannot observe**. **+ Checkout-tree hash (slice 8):** a remote (`--allow-fetch`) run now hashes the fetched `source/` checkout pre-run — right after fetch, before the freshness stamp, so an `--allow-install` retry or the run's own writes never change it — via a new stdlib `compute_tree_sha256` (`os.walk(followlinks=False)`, `.git` pruned at any depth, symlinks skipped, sorted `f"{relpath}\0{hexdigest}\n"` fold → `sha256`, published so a third party can recompute it byte-for-byte); records it as the new **signed** `ReproduceRecord.source_tree_sha256` (echoed unsigned in `reproduce.json`); local runs record `null`; a missing/non-dir root or unreadable file returns `None` for the whole digest, never fabricated or partial. Closes slice 6's self-disclosed "hashing the tree is deliberately a separate slice" gap. **Honest, not oversold:** for a full-SHA pin the commit already binds the tree, so the marginal value is the `--rev` tag/branch case slice 7 left unattested, git-free verification, and groundwork for the still-deferred local-path/shipped-tree hashing — not novelty for the full-SHA case. **Caveat:** the new signed field is the **third** disclosed signature break (after slice 6 and the somatic FAIL-floor) — a pre-slice-8 signed bundle still loads but no longer verifies, pinned by `test_pre_slice_8_signature_over_a_record_without_tree_hash_no_longer_verifies`. Fully CI-observable (real fixture trees, no injected-seam reasoning needed for the core). No new dep. **Deferred:** multi-key/predicate row match, `occurrence`/`group` selectors, a notebook-specific size bound, a structured staleness field on `ClaimResult`, **paper-claim extraction now shipped** (`contig extract-claims` — deterministic core + optional LLM assist, locator-less draft + review sidecar; PDF/DOI/locator-inference still deferred), figure/plot & table-cell(-image) claims (**plot-hash does not exist and can't be added without breaking the stdlib-only dep contract**), **DOI resolution** (`contig reproduce <doi>` — explicitly out of scope, refused with a message that says so), local-path & shipped-`source/` tree hashing, private-repo credentials, submodules, checkout pruning, dashboard card |

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
