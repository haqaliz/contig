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

## C1. Cross-tool concordance verification  ·  SHIPPED v0.2.0 (germline slice)

**Shipped (slice 1) in v0.2.0.** The verdict gained a third axis alongside QC
thresholds and structural checks: `verification/concordance.py` computes a
deterministic `genotype_concordance` (over shared sites) plus a `site_overlap`
check, both `kind="concordance"`, surfaced via `contig verify --concordance-vcf
<vcf>` and grouped in the text/HTML reports and the dashboard QC panel. Concordance
is at most WARN (corroboration, not ground truth), never changes the verify exit
code, and reports `unverified` (never a false pass) when the two call sets share no
comparable site. **Deferred to a follow-on slice:** auto-running a second caller
(today the user supplies the second VCF), RNA-seq and single-cell concordance, and
FAIL-severity once thresholds are calibrated on real data.

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
**Deferred to later C2 slices:** classic-BWA index build/redirect (needs a supported
`bwa index` target, e.g. sarek `--aligner bwa-mem`); bwa-mem2 index set + the
classic-vs-mem2 aligner-mismatch heal; a corrupt/partial STAR index signature; peak-RSS-
informed scaling (needs a refactor — `resource_usage` is only populated at finalize, after
the patch decision); the still-missing single-file index kind (the BAM/CRAM form of
`.csi`) plus stale-index detection on the same seam; and the wider failure catalog — the
assembly-signature form of reference/build mismatch (no sample-side contig signal in raw
FASTQ or finished bundle), per-contig name mapping (e.g., `chrM`↔`MT`), known-sites/GTF-
version consistency, a runtime `reference_mismatch` detector-corpus case, format
conversion, and pin conflict.

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

## C3. Biological-plausibility verification  ·  SHIPPED v0.3.0 (germline slice)

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

## C4. New assay, depth-first: somatic variant calling  ·  months 4 to 5

Add one assay end to end rather than several shallowly. Recommended:
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

**Eval data captured:** this *is* the capture loop; it closes over all the above.

**Dependencies:** consumes the outputs of C1 to C5.

---

## Sequencing summary

| ID | Capability | Window | Leverage |
|----|-----------|--------|----------|
| C1 | Cross-tool concordance verification | SHIPPED v0.2.0 | Verdict trust, novel primitive (germline slice; auto-run second caller deferred) |
| C2 | Self-heal breadth plus auto resource-scaling | M2 to M3 (resource-aware + single-file missing-index family `.fai`/`.bai`/`.tbi`/`.csi`/`.dict` shipped; chr-prefix GTF harmonization shipped; directory-shaped STAR index build+redirect shipped, classic BWA detector+corpus-only; bwa-mem2, peak-RSS, assembly-signature + wider catalog pending) | Unattended-completion rate, corpus fuel |
| C3 | Biological-plausibility verification | SHIPPED v0.3.0 | Verdict gets smarter about biology (germline Ti/Tv, het/hom; other assays deferred) |
| C4 | New assay: somatic variant calling | M4 to M5 | Breadth, depth-first, new corpus |
| C5 | Reference and input-data integrity | M5 (reference-identity **capture** slice shipped — explicit `sha256` + iGenomes key-only, rendered in methods/panel; pre-flight **mismatch detector**, known-sites, GTF version, RO-Crate pending) | Kills a silent-failure class, deepens reproduce |
| C6 | Eval flywheel as a continuous loop | M6 | Compounding accuracy from real runs |

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
