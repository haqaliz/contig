# Contig Usage

The complete guide to running Contig: prerequisites, every CLI command, running
on your own data, cloud backends, the reproducible bundle, and the failure
corpus. For the high-level pitch see the [README](../README.md); for the bet and
system design see [VISION.md](../VISION.md) and
[ARCHITECTURE.md](technical/ARCHITECTURE.md).

---

## Prerequisites

Contig is a Python 3.12 package managed with [`uv`](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/haqaliz/contig.git
cd contig
uv sync                 # create the venv and install deps
uv run pytest           # run the full test suite
```

To run a **real** pipeline you also need:

| Requirement | Why | Install |
|---|---|---|
| **Nextflow** | Executes the nf-core pipelines | `brew install nextflow` |
| **Java runtime** | Nextflow runs on the JVM (`JAVA_HOME` → a JDK) | e.g. Homebrew's `openjdk` |
| **Docker** | Pulls pinned tool containers; must be running | [Docker Desktop](https://www.docker.com/) |
| **samtools** | Coverage/depth for `contig readiness --bam` | `brew install samtools` |
| **tabix** | Builds the real GIAB trio subset script (optional) | `brew install htslib` |

The CLI and the test suite work **without** Nextflow/Java/Docker; only live runs need them.

> **Source checkout:** use `uv run contig ...` (or `.venv/bin/contig`). A stale
> `contig` on `PATH` may be an older Homebrew install without the workbench
> commands.

---

## Files and formats

| Term | What it means here |
|---|---|
| **VCF** | Variant calls (`CHROM POS ID REF ALT QUAL FILTER INFO FORMAT sample`). Variants can carry VEP `CSQ` or SnpEff `ANN` annotations. |
| **BED** | 0-based, half-open intervals: `chrom start end [name]`. Panel BEDs add gene/transcript columns. |
| **GTF** | Gene/exon annotation (1-based, inclusive); gzipped is fine. |
| **HGNC** | Approved gene symbols, aliases, and previous symbols; used to normalize panel genes. |
| **BAM/CRAM** | Aligned reads, sorted and indexed. Readiness needs one of these (or a depth TSV), **not** a VCF alone. |
| **FASTA** | Reference genome sequence. Needed by `samtools` for some CRAMs; `--reference` is optional when the CRAM is self-contained. |
| **Depth TSV** | `samtools depth -a` output: `chrom pos depth` (1-based). |
| **Sidecar** | The JSON companion to a report (`--meta`), with input paths/hashes and the HTML hash. |
| **M1 / M2** | Internal milestone labels for the variant table (`variants`) and readiness table (`readiness`); not biology. |
| **Build** | Genome assembly (GRCh37/GRCh38). The calls, BED/GTF, BAM/CRAM, and annotation must match; Contig skips a mismatched Iranome/ClinVar source rather than guessing. |

A variant without VEP/SnpEff annotation is shown as `unannotated`; it is never
dropped. A blank readiness `caveats` cell means the caveat BED was checked (see
the metadata note `caveats checked` / `caveats not checked`).

---

## Commands

| Command | What it does |
|---|---|
| `contig plan --goal "…" --input <sheet>` | Propose a pipeline + params from your goal and data, to approve |
| `contig run --run-id <id>` | Run a pipeline, self-heal failures, verify, report the verdict |
| `contig show <id>` | The verdict + provenance + repair chain of a past run (`--explain` for the deciding QC checks, `--html` for a shareable report) |
| `contig status <id>` | One-shot live snapshot of a run: state, elapsed, tasks completed and running |
| `contig watch <id>` | Redraw the live snapshot until the run is no longer running |
| `contig cancel <id>` | Stop an active run (signals its process group) and mark it cancelled |
| `contig resume <id>` | Re-run a cancelled or interrupted run from its cached tasks (Nextflow `-resume`) |
| `contig rerun <id>` | Reproduce a past run from its launch manifest under a fresh run id |
| `contig verify <id>` | Re-hash a finished run's outputs against the record (and check the signature, if signed) and report any drift. `--concordance-vcf <vcf>` also corroborates a germline run's variants against a second, independent call set (genotype concordance over shared sites plus site overlap); concordance is at most WARN and never changes the exit code |
| `contig keygen` | Generate an Ed25519 signing keypair; set `CONTIG_SIGNING_KEY` to the private key to sign runs |
| `contig cost <id>` | Per-task duration and peak memory from the run, costed at configurable `--rate-cpu-hour` / `--rate-mem-gb-hour` |
| `contig estimate --pipeline <p> --input <sheet>` | Pre-run runtime and cost estimate, data-driven from past runs of that pipeline with a sample-count heuristic fallback |
| `contig export <id> --rocrate` | Export the run's provenance as an RO-Crate (ro-crate-metadata.json) |
| `contig methods <id>` | A deterministic, citation-ready methods paragraph from the bundle |
| `contig variants <vcf>` | Research-use variant table: join a call set to ClinVar, Iranome, and a population-frequency TSV, filter deterministically, and export TSV/JSON. `--spec` replays a saved filter; `--json` includes provenance; `--max-records` bounds a WGS input (default 1,000,000) |
| `contig iranome-lift --iranome <tsv> --chain <chain.gz> --out <tsv>` | Lift the GRCh37 Iranome table to GRCh38 with the UCSC chain; writes a `.lift.json` sidecar with counts and hashes |
| `contig readiness --depth <tsv>` | Per-target coverage and interpretation readiness: mean depth, % ≥20x/50x/100x, zero-coverage bases, homology/pseudogene caveats, explicit caveat coverage, build label, optional VCF sex check / possible-sample-swap caution, and a `ready`/`caution`/`not-interpretable` state |
| `contig panel-build --name <n>` | Build a canonical, checksummed panel BED from a gene list + GTF (optional HGNC normalization) or an existing BED; writes `<id>.bed` + `<id>.json` to the registry |
| `contig panel-list` / `contig panel-show <id>` | List or inspect panels in the registry |
| `contig panel-diff <a> <b>` | Compare two panel versions (metadata and BED intervals); `--json`, `--fail-on-diff` |
| `contig panel-archive <id>` | Move a validated panel into `<dir>/archive` without deleting it |
| `contig report <id>` | Build a self-contained research report from a run bundle, optionally attaching M1 variants and M2 readiness; writes HTML + a JSON sidecar with input hashes. `--template publication\|internal\|audit` |
| `contig report-check <sidecar>` | Recompute the report inputs’ SHA-256 and the HTML hash, verify the Ed25519 sidecar signature when present, and optionally re-hash the run’s outputs (`--outputs`) and the attached tables’ upstream sources (`--sources`); `--base-dir` resolves relative paths, `--require-signature` rejects unsigned reports |
| `contig report-bundle <sidecar> --out <dir>` | Copy the HTML, sidecar, run record, and attached tables into a portable directory with relative paths; all table rows are kept |
| `contig report-batch --project <json>` | Build every report in a project manifest; `--check` verifies each afterward |
| `contig report-check-batch --project <json>` | Check every report in a project manifest; `--outputs`, `--sources`, `--require-signature` apply to each |
| `contig family --vcf <vcf> --ped <ped>` | Research-use trio/family analysis: per-child inheritance, Mendelian consistency, de novo candidates, and pairwise sample concordance. Multiple families/quads per PED; autosomal plus basic X/Y/MT rules |
| `contig carriers --vcf <vcf> --ped <ped>` | Research-use per-person carrier and couple shared-carrier views, optionally filtered to a recessive gene panel (`--genes` / `--panel`). Autosomal only |
| `contig biomarkers --vcf <vcf> --callable-bed <bed>` | Research-use TMB verification from PASS variants in callable regions; compares a reported TMB within tolerance. MSI, CNV, and LOH can be verified from independent inputs; without them they are `not_verified` |
| `contig cohort-build --name <n> --variants <json,...>` | Build a local-only cohort index from M1 variant tables: per-variant seen-run counts/frequencies and per-gene summaries. `--trace` records contributing run labels. No network, no sample IDs |
| `contig cohort-list --cohort <json>` | List the runs that contributed to a cohort |
| `contig cohort-append --cohort <json> --variants <json,...>` | Add runs to a traced cohort, updating counts/frequencies |
| `contig cohort-merge <a> <b> --out <json>` | Merge two traced cohorts, deduping runs by content SHA-256 |
| `contig cohort-query --cohort <json>` | Query a local cohort by gene, variant, or minimum run count |
| `contig ask <id> "question"` | Grounded answers from the run bundle and optional M1/M2 tables, with source citations and suggested actions. `--llm` paraphrases the grounded answer; no model is required |
| `contig ask-eval <id> --cases <jsonl>` | Run the frozen question/citation eval set against the deterministic router |
| `contig approve <id>` | Approve (or `--reject`) the patch a paused self-heal run is waiting on; `--choose N` picks a ranked fix on a choice gate |
| `contig benchmark <id>` | Compare a run's QC against a designated reference (`benchmark set <id>` to record one) within a tolerance |
| `contig clusters` | Group failure-corpus cases by class and a normalized log signature (recurring failure modes) |
| `contig coverage` | Corpus coverage: per-class support, thin-coverage flags, confirmed cases over time |
| `contig list` | All bundled runs |
| `contig corpus-promote` | Promote a confirmed pending failure case into the golden corpus |
| `contig eval-detector` | Score the failure detector against the labeled failure corpus (`--detector rules-strict` or `--detector llm` to score a different detector, `--snapshot` to record a point in the history, `--history` to show the trend) |
| `contig reproduce <repo\|url> --run "<cmd>" --claims <file>` | Run a third-party repo's script and report, per stated number, whether it actually regenerates: `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`. Takes a local path, or an `https://` git URL with `--allow-fetch`; `--rev <sha\|tag\|branch>` pins the revision (see below) |
| `contig version` | Installed version |

Run `uv run contig <command> --help` for the full flag list of any command.

A long run is observable while it is in flight: `contig watch <id>` streams its
task progress, and the self-heal loop pauses for you when it proposes a risky
patch. A patch it judges `safe` is applied automatically; a `needs_confirmation`
or `destructive` patch pauses the run (state `awaiting_approval`) until you
`contig approve <id>` or `contig approve --reject <id>`, with a timeout
(`contig run --approval-timeout`, default 1800 seconds) so it never hangs forever.
Pass `contig run --auto-approve` to apply risky patches without waiting (for
non-interactive runs).

A run can also reach you when it finishes, fails, is cancelled, or starts waiting
for your approval: every such event is appended to `<runs-dir>/notifications.jsonl`
(the dashboard activity bell reads it). `contig run --notify <https-url>` POSTs each
event to a webhook (Slack, Discord, your own endpoint), and if the `CONTIG_SMTP_HOST`,
`CONTIG_SMTP_PORT`, `CONTIG_SMTP_USER`, `CONTIG_SMTP_PASSWORD`, `CONTIG_SMTP_FROM`,
and `CONTIG_SMTP_TO` environment variables are set, the same event is emailed.
Notifications are best-effort: a failing webhook or email never fails the run.

To run on AWS Batch, see the step-by-step [AWS Batch runbook](technical/AWS_BATCH_RUNBOOK.md);
`contig run --backend aws_batch` refuses up front if the queue, region, S3 work dir,
or AWS credentials are missing. To run on a SLURM cluster, see the
[SLURM runbook](technical/SLURM_RUNBOOK.md); `contig run --backend slurm
--queue <partition>` (with `--opt account=...`) refuses up front if the partition,
account, or `sbatch`/`sinfo` are missing.

Contig is workflow-engine-agnostic: alongside Nextflow it can run a Snakemake
workflow through the same capture, verify, reproduce engine with `contig run
--engine snakemake --snakefile <Snakefile>`.

To make a run tamper-evident, generate a keypair with `contig keygen`, set
`CONTIG_SIGNING_KEY` to the private key, and run: the bundle is signed into a
`signature.json` and `contig verify` confirms the record was not modified.

---

## Try it in 30 seconds (no real data)

```bash
uv run contig run --run-id smoke      # runs nf-core/rnaseq's bundled test profile
uv run contig show smoke              # see the verdict + repair chain
```

---

## Run on your own data

### 1. Write a sample sheet

`samplesheet.csv`, in nf-core/rnaseq format. Paths may be relative to the sheet:

```csv
sample,fastq_1,fastq_2,strandedness
CTRL_REP1,reads/ctrl1_R1.fastq.gz,reads/ctrl1_R2.fastq.gz,auto
TREAT_REP1,reads/treat1_R1.fastq.gz,reads/treat1_R2.fastq.gz,auto
```

### 2. (Optional) Plan first

Describe your goal in plain language and let Contig propose a pipeline + params
to approve. It flags problems (no replicates, single-end, missing reference)
*before* you run, and declines goals it has no curated pipeline for rather than
inventing a workflow:

```bash
uv run contig plan --goal "find differentially expressed genes" \
  --input samplesheet.csv --genome GRCh38
# → Plan: nf-core/rnaseq @ <pinned revision>  (assay: rnaseq) … + any warnings
```

The goal→pipeline matching is deterministic and **replaceable**: a better model
can be swapped in behind it. Contig's value is the curated registry and the
run/verify/reproduce engine, not generating workflows from English (that's a
commodity it consumes; see [VISION.md](../VISION.md)).

### 3. Run it

Point at a reference: an iGenomes key **or** your own FASTA+GTF:

```bash
uv run contig run --run-id my-analysis \
  --input samplesheet.csv \
  --genome GRCh38                       # or: --fasta ref.fa --gtf genes.gtf
```

Contig first **validates the sample sheet** (missing files, duplicate samples,
bad columns) and refuses to launch if it's broken, catching the error before it
costs you a multi-hour run. Then it runs the pipeline, **self-heals** recoverable
failures, **verifies** the output, and writes a reproducible bundle. Your reads
never leave your machine; only file hashes are recorded.

---

## Reading the result

Every run ends in an honest verdict:

| Verdict | Meaning |
|---|---|
| `PASS` | Ran to completion and every QC check passed |
| `WARN` | Completed, but a QC check is borderline; look before you trust it |
| `FAIL` | A task failed, or a QC check failed; do not trust the output |
| `UNVERIFIED` | Completed but nothing checked it; we won't claim it's correct |

If a step broke and Contig recovered, the report shows the **repair chain**
(e.g. `attempt 1: oom → resource patch → patched_and_retried`).

By default the verdict is reported but does not change the exit code (only a
pipeline failure, output drift, or a signature mismatch does). To **gate a script
or CI step on the verdict**, pass `--fail-on-verdict` to `contig run` or
`contig verify`: a `FAIL` verdict then exits non-zero (`1`), while `WARN`,
`UNVERIFIED`, and `PASS` still exit `0`. It is opt-in, so existing invocations are
unaffected; `--json` output is unchanged.

`UNVERIFIED` deliberately exits `0`: "we could not check this" is not the same
claim as "this is broken", and Contig will not convert one into the other.

### What can actually FAIL

FAIL bands are **gross-implausibility engineering tripwires** — "this run is
broken" — never a biological or clinical claim. A check only gets one where a
grossly-wrong value is distinguishable from unusual-but-real science:

| Check | FAILs when |
|---|---|
| Structural / integrity | an expected output is missing, empty, or unreadable |
| "Did it run" QC (alignment rate, coverage, bisulfite conversion, ASV count, bin contamination, …) | the metric is far outside the range any usable run reaches |
| Germline `ts_tv_ratio`, `het_hom_ratio` | grossly outside the germline range (e.g. Ti/Tv ≈ 0.5 — the signature of random calls) |
| Germline `variant_count` | the call set is empty |
| Somatic `somatic_variant_count` | no biallelic records were called (an empty or truncated call set) |

Everything else is **WARN-capped by design, not pending calibration** — most
notably tumour VAF and every RNA-seq plausibility metric. Their extremes are
occupied by legitimate protocols (a low-purity or subclonal tumour really does
have a low VAF; a deeply-sequenced library really is highly duplicated), so no
threshold separates "broken" from "unusual but real", and a FAIL there would
reject good science. See `docs/technical/CAPABILITY_ROADMAP.md` (C3/C4) for the
full reasoning.

Concordance never affects the exit code: it is corroboration, not ground truth.

---

## Variant workbench (research use)

After a verified germline or somatic call set, `contig variants` turns the VCF
into a deterministic, filterable table. It joins the calls to open evidence
sources and never makes a clinical call: ClinVar is shown as "ClinVar reports …",
not restated as Contig's own pathogenicity judgement.

```bash
contig variants sample.vcf \
  --clinvar clinvar.vcf.gz \
  --iranome iranome_panel.tsv \
  --frequencies gnomad_frequencies.tsv \
  --build GRCh38 \
  --gene BRCA1,BRCA2 \
  --consequence missense,frameshift \
  --max-af 0.01 \
  --pass-only \
  --out table.tsv

# Same filters, replayable:
contig variants sample.vcf --clinvar clinvar.vcf.gz --spec table.spec.json --out again.tsv

# gnomAD v4 API for a filtered panel (max 1000 sites; local cache optional)
contig variants sample.vcf --gnomad-api --gnomad-cache gnomad-cache.json --out table.tsv
```

- **Input:** a plain or `.gz` text VCF with one sample column. VEP `CSQ` and
  SnpEff `ANN` annotations are read when present; a variant without either is
  shown as `unannotated`, never dropped.
- **Evidence:** ClinVar (`CLNSIG`, `CLNREVSTAT`, `CLNDN`, `CLNVC`, `CLNHGVS`),
  Iranome GRCh37 frequencies, a `CHROM POS REF ALT AF [AN]` frequency TSV, or
  the gnomAD v4 GraphQL API (`--gnomad-api`, optional `--gnomad-cache`; capped
  at 1000 sites). A source that cannot be joined (wrong build, missing file,
  zero matches) is recorded honestly in the metadata.
- **Filters:** gene, consequence substring, max population AF, ClinVar
  significance substring, PASS-only, minimum depth, minimum VAF, zygosity, and
  region. All filters combine with AND.
- **Output:** TSV by default; `--json` emits the table plus metadata (source
  paths, SHA-256, build, filter spec, Contig version, notes). `--out` writes to a
  file; `--save-spec` writes the effective filter spec.
- **Scale guard:** a WGS call set is bounded to 1,000,000 kept records by
  default. Without `--region` or `--gene`, exceeding the cap is an error that
  tells you to bound the input; `--max-records` raises the cap explicitly when
  you really mean it. Region/gene filtering happens while streaming, so the full
  call set is never held in memory.
- **Research-use boundary:** no ACMG classification, diagnosis, prognosis,
  screening, or treatment recommendation is emitted by Contig. ClinVar
  significance is attributed, not re-owned.

Iranome is GRCh37 by default. For a GRCh38 input, lift it once with the public
UCSC chain and declare the lifted table's build:

```bash
curl -fsSL -o hg19ToHg38.over.chain.gz \
  https://hgdownload.soe.ucsc.edu/goldenPath/hg19/liftOver/hg19ToHg38.over.chain.gz
contig iranome-lift --iranome data/iranome/iranome_panel.tsv \
  --chain hg19ToHg38.over.chain.gz --out data/iranome/iranome_grch38.tsv
contig variants sample.vcf --iranome data/iranome/iranome_grch38.tsv \
  --iranome-build GRCh38 --build GRCh38 --out table.tsv
```

The sidecar records mapped/unmapped counts, the chain/output SHA-256, and both
builds. A variant spanning a chain gap or a reverse-strand chain is unmapped,
never guessed. A GRCh38 input still skips a GRCh37 Iranome table with a note.
The v1 table is built in memory, so it is intended for one sample's call set,
not a population catalogue; subset by region first if needed.
See `docs/planning/research-workbenches/DATA_SOURCES.md` for the source license table
and the `data/README.md` for the starter data.

---

## Coverage & interpretation readiness (research use)

Before interpreting a gene, check whether the data can support it:

```bash
samtools depth -a -b panel.bed sample.bam > depth.tsv

contig readiness \
  --depth depth.tsv \
  --bed panel.bed \
  --caveats homology_caveats_GRCh38.bed \
  --build GRCh38 \
  --out readiness.tsv

# Or let Contig run samtools depth on a BAM/CRAM:
contig readiness --bam sample.cram --reference GRCh38.fa \
  --bed panel.bed --build GRCh38 --out readiness.tsv
```

- **Input:** a `samtools depth -a` TSV (`chrom pos depth`, 1-based), or a
  BAM/CRAM plus `--bam` (Contig runs `samtools depth -a -b` behind an injectable
  seam; `--reference` is optional and only needed when `samtools` cannot decode
  the CRAM without it). **A VCF alone is not enough for readiness.** Targets are
  a BED (`chrom start end [name]`) or a GTF with `--genes`.
- **Metrics:** bases, covered bases, mean depth, % ≥20x/50x/100x, and
  zero-coverage bases per target.
- **Readiness:** `ready` when the target meets the depth and fraction thresholds
  with no caveat; `caution` when a homology/pseudogene caveat overlaps, the
  covered fraction is below the ready floor, or the mean depth is below the
  threshold; `not-interpretable` when the covered fraction is below the caution
  floor or the target has no bases. Every row carries the reason.
- **Thresholds:** `--depth-threshold` (default 20), `--ready-fraction` (0.90),
  `--caution-fraction` (0.50).
- **Gene summary:** `--by-gene` aggregates exon/target rows into one row per
  gene with the worst readiness state and weight-averaged depth/percentages.
  A BED3 (no gene column) produces no gene summaries; add a 4th-column gene
  symbol or use `--gtf --genes` (the note says so).
- **Build and preflight:** `--build` records the reference build in the table
  (and the report compatibility preflight compares it to the run). A target/depth
  chromosome-name mismatch is recorded as a note instead of silently producing
  all-zero coverage.
- **Caveat coverage:** the JSON meta says whether caveats were checked
  (`caveats_checked`) and how many regions were loaded (`caveat_regions`); the
  notes say it too.
- **Sex check / possible swap:** `--sex-vcf` runs the VCF-only karyotypic-sex
  signal and records `meta.sample_qc` (inferred sex, X-het, chrX/chrY sites).
  `--expected-sex XX|XY` (or `female`/`male`) marks a mismatch as a
  **possible sample swap** and downgrades `ready` targets to `caution`; an
  inconclusive VCF is reported as inconclusive, never as a swap.
- **Output:** TSV by default; `--json` includes source paths, SHA-256,
  thresholds, build, caveat coverage, and the Contig version. `--out` writes to a
  file.
- **Scale:** a whole-genome `--depth` TSV is streamed and filtered to the
  target intervals; positions outside the panel are counted and skipped, not
  held in memory. `--bam` already emits only target regions via `samtools depth
  -b`. The M1 variant table has its own explicit record cap.

The homology BED is deliberately a separate input: use
`data/homology/homology_caveats_GRCh38.bed` for the curated list (SMN1/SMN2,
PMS2/PMS2CL, HBA1/HBA2, CYP21A2/CYP21A1P, GBA1/GBA1LP, PKD1/PKD1P1-P6,
STRC/STRCP1, NCF1/NCF1B/NCF1C, CYP2D6/CYP2D7/CYP2D8P, PTEN/PTENP1, GJB2/GJB6,
IKBKG/IKBKGP1, HBB/HBD), or supply your own BED4/BED8. The derived BED uses one
representative transcript per gene (MANE Select, else Ensembl canonical), so a
gene's alternative exons are not caveated unless they are in that transcript.
Rebuild the derived BED with `python3 scripts/build_derived_data.py` after
updating the GTF. A readiness state is a data-sufficiency statement, not a
clinical guarantee.

---

## Panel builder & registry

Define a reusable, checksummed BED from genes or an existing BED:

```bash
contig panel-build --name "Hereditary cancer" \
  --genes BRCA1,BRCA2 \
  --gtf Homo_sapiens.GRCh38.113.gtf.gz \
  --hgnc hgnc_complete_set.txt \
  --version 1 \
  --out-dir panels

contig panel-list --dir panels
contig panel-show <panel-id> --dir panels
contig panel-diff <old-id> <new-id> --dir panels
contig panel-archive <panel-id> --dir panels
```

- **Gene list:** symbols are resolved against HGNC when `--hgnc` is supplied
  (approved symbol, alias, or previous symbol); unknown symbols fail with a
  clear list. Without HGNC, symbols are kept uppercase with a note.
- **Exons:** built from the GTF, preferring MANE Select when tagged;
  `--transcripts all` keeps all protein-coding transcripts.
- **Existing BED:** `--bed panel.bed` normalizes `chr` prefixes, sorts, dedupes,
  and checksums.
- **Registry:** `<id>.bed` + `<id>.json` with name, source, genes, transcripts,
  build, version, method, checksum, creation time, and Contig version. The id is a slug
  plus a short SHA-256 of the canonical BED. `sources` records the BED/GTF/HGNC
  path and SHA-256, so a rebuilt panel names exactly what it consumed.
- **Diff and archive:** `panel-diff` compares metadata and BED intervals (added /
  removed, `--json`, `--fail-on-diff`). `panel-archive` moves a validated panel
  into `<dir>/archive`; it disappears from the active list but stays loadable
  with `--dir <dir>/archive` and is never overwritten.
- **Reuse:** the BED works directly as `--bed` for `contig variants` and
  `contig readiness`.

Panels are research-use interval definitions, not clinical panel
certifications.

---

## Research report (HTML + sidecar)

Turn a verified run, the M1 variant table, and the M2 readiness table into one
self-contained research report:

```bash
contig variants sample.vcf --clinvar clinvar.vcf.gz --json --out variants.json
contig readiness --depth depth.tsv --bed panel.bed --json --out readiness.json

contig report r1 \
  --variants variants.json \
  --readiness readiness.json \
  --spec report-spec.json \
  --out report.html \
  --meta report.json

contig report-check report.json

# Compare two report sidecars:
contig report-diff report-a.json report-b.json
```

- **Run bundle:** the report renders the pipeline/revision, verdict, deciding QC
  checks, methods paragraph, provenance, and signature status.
- **Attached tables:** M1 variants and M2 readiness are optional; each section
  names its source file and SHA-256. Tables are capped (`max_rows`, default 100)
  with a note; the full data stays in the attached JSON.
- **Spec:** `--spec` accepts a JSON narrative/template:
  `title`, `subtitle`, `author`, `institution`, `summary`, `notes`,
  `limitations`, `template` (`publication`, `internal`, `audit`), `reviewer`
  (`name`, `role`, `reviewed_at`, `statement`), and `max_rows`.
- **Sidecar:** `report.json` records every input path + SHA-256, the spec, the
  Contig version, the generated timestamp, and the HTML hash.
  `contig report-check` recomputes the inputs and the HTML hash, and exits
  non-zero if any is stale or missing. `--outputs` also re-hashes the run's
  recorded outputs, `--sources` verifies the upstream files recorded by the
  attached M1/M2 tables, and `--base-dir` resolves relative paths against a
  chosen directory. An unrecorded output/source set is reported `unverified`,
  never a false pass. `contig report-diff` compares two sidecars (spec, inputs,
  hashes, notes) as text or JSON; `--fail-on-diff` makes differences exit
  non-zero.
- **Signing:** set `CONTIG_SIGNING_KEY` (the same Ed25519 key used for run
  bundles) when running `contig report` and the sidecar is signed; the detached
  signature `<sidecar>.sig.json` binds the HTML hash, every input hash, the spec,
  and the reviewer block. `contig report-check` verifies it and exits non-zero on
  a tampered manifest; `--require-signature` exits non-zero when the report is
  unsigned. An unsigned rewrite removes a stale signature rather than leaving one
  that vouches for different content. The signature does not make the report a
  clinical document.
- **Compatibility warnings:** if the run’s assay/build or the attached table’s
  build/genes do not line up, `contig report` still renders the report but names
  the mismatch in the HTML, the sidecar (`warnings`), and stderr. Unknown builds
  are not guessed.
- **Portable bundle:** `contig report-bundle report.json --out bundle/` copies
  the HTML, sidecar, run record (and its signature, when present), and attached
  tables into one directory and rewrites the sidecar paths to relative ones, so
  `contig report-check bundle/report.json` keeps working after the directory is
  moved. The table JSON keeps every row, including rows beyond the HTML
  `max_rows` cap. Run outputs and upstream source files are not bundled.
- **Batch projects:** `contig report-batch --project project.json` builds every
  entry; `contig report-check-batch --project project.json` checks them. All
  relative paths in the manifest resolve against the manifest's directory, not
  the current shell. Example:
  ```json
  {
    "name": "Cardio panel",
    "out_dir": "reports",
    "reports": [
      {"id": "r1", "run_id": "r1", "variants": "r1/variants.json",
       "readiness": "r1/readiness.json", "spec": "spec.json", "bundle": true}
    ]
  }
  ```
  A failing entry does not stop the others; the batch exits 1 and names it.
- **Research-use boundary:** the report carries a research-use banner, never a
  diagnosis, ACMG classification, treatment recommendation, or medical sign-off.
  PDF is produced by opening the self-contained HTML and printing to PDF; a
  native PDF export is a follow-up.

---

## Family / trio analysis (research use)

```bash
contig family --vcf family.vcf --ped family.ped --out family.tsv
```

- **Input:** one multi-sample VCF containing every child and parent, plus a PED
  that may contain multiple families/quads. Separate per-sample VCFs must be
  merged first. A sample may belong to only one family.
- **Per row:** family id, child, chrom/pos/ref/alt, gene/consequence, the three
  genotypes, inheritance (`paternal`, `maternal`, `biparental`, `de_novo`,
  `not_carried`, `unknown`, `not_evaluated`), Mendelian consistency, and a de
  novo candidate flag. X/Y/MT use basic sex-aware rules when the PED supplies
  sex; unknown sex stays `not_evaluated`.
- **Summary:** total families, evaluated sites, Mendelian-inconsistent sites
  (excluding de novo candidates), de novo candidate count, error rate,
  inheritance counts, per-family summaries, and pairwise
  same-genotype/opposite-homozygote rates with a possible-swap flag. The JSON
  `family_ids` list is authoritative; `family_id` is the first family for
  back-compat.
- **Boundary:** multiple families/quads are supported; a de novo candidate is
  not a validated event. This is a research calculation, not clinical
  counselling, diagnosis, or PGT-M.

---

## Carrier / couple view (research use)

```bash
contig carriers --vcf family.vcf --ped family.ped \
  --genes BRCA1,BRCA2 --out carriers.tsv

# Or a panel BED with gene names in column 4:
contig carriers --vcf family.vcf --ped family.ped \
  --panel panels/<id>.bed --out carriers.tsv
```

- **Per-person view:** every family member with an ALT genotype in the
  recessive panel, labelled `carrier` or `homozygous_alt` (no genotype is
  omitted).
- **Couple view:** variants where both parents carry an ALT allele, labelled
  `both_carriers`, `one_homozygous`, or `both_homozygous`; the children's
  genotypes and a `child_status` are included for context.
- **Panel filter:** `--genes` and `--panel` are unioned; with neither, no panel
  filter is applied and the report says so. Unannotated variants cannot pass a
  panel filter.
- **Boundary:** autosomal only; X/Y/MT variants are skipped and counted. This
  is a genotype calculation, not a risk estimate, diagnosis, or reproductive
  advice. No clinical counselling.

---

## Oncology biomarkers (research use)

```bash
contig biomarkers \
  --vcf somatic.vcf \
  --callable-bed high_confidence_regions.bed \
  --reported-tmb 12.4 \
  --out biomarkers.tsv

# MSI from an existing MSIsensor output:
contig biomarkers --vcf somatic.vcf --callable-bed regions.bed \
  --msi-output example.paired.output --reported-msi MSI \
  --out biomarkers.tsv

# LOH from allele-specific segments (minor copy number column):
contig biomarkers --vcf somatic.vcf --callable-bed regions.bed \
  --loh-segments run.ascat.seg.txt --loh-truth tcga.ascat.seg.txt \
  --out biomarkers.tsv
```

MSI can also be run from BAMs with `--msi-tumor-bam`, `--msi-normal-bam`,
`--msi-sites`, `--msi-bed` and `--msisensor <binary>`; `--msi-threshold`
(default 10% unstable sites) sets the MSI-H boundary.

- **TMB:** PASS variants inside the callable BED divided by callable Mb. The
  output names the definition; `--coding-only` counts only variants with a
  coding VEP/SnpEff consequence and reports the unannotated count.
- **Reported comparison:** `--reported-tmb` compares the computed value within
  `--tmb-tolerance` (default 20% relative) and labels `match` or `divergent`.
- **MSI:** when an MSIsensor output or BAM set is supplied, the unstable-site
  percentage and `MSI-H`/`MSS` status are reported and compared to
  `--reported-msi` (`match`/`divergent`). Threshold defaults to 10% and is
  exposed as `--msi-threshold`; it is not yet calibrated on a real MSI-H/MSS
  pair.
- **CNV:** when `--cnv-segments` and `--cnv-truth` are supplied, the
  overlap-weighted segment concordance and mean absolute delta are reported as
  `match`/`divergent`/`unverified` (`--cnv-tolerance` default 0.2,
  `--cnv-min-concordance` default 0.90).
- **LOH:** when `--loh-segments` and `--loh-truth` are supplied, the
  base-level Jaccard overlap of the LOH intervals (minor copy number < 0.5) is
  reported as `match`/`divergent`/`unverified` (`--loh-min-agreement` default
  0.90). The input must carry a minor-copy-number column
  (`Minor_Copy_Number`, `minor_cn`, `lcn.em`); total copy number alone is
  refused. A self-comparison proves the parser/comparator, not a caller; real
  validation needs a run's own allele-specific segments.
- **Boundary:** research reproducibility check only; no NCCN, drug, or treatment
  recommendation.

---

## Local cohort frequency (research use)

```bash
contig cohort-build --name "Lab cohort" \
  --variants run1.json,run2.json,run3.json \
  --trace \
  --out cohort.json

contig cohort-list --cohort cohort.json
contig cohort-query --cohort cohort.json --gene BRCA1
contig cohort-query --cohort cohort.json --variant 17-43057063-C-CT
contig cohort-query --cohort cohort.json --min-runs 2

contig cohort-append --cohort cohort.json --variants run4.json
contig cohort-merge a.json b.json --out merged.json
```

- **Local only:** aggregates the M1 `contig variants --json` tables already on
  this machine. No network, no central service, no sample IDs.
- **Per variant:** seen-run count, frequency, genes, consequences, and ClinVar
  significance strings.
- **Per gene:** unique variant count and runs with the gene.
- **Traceability:** `--trace` records the contributing run labels per variant;
  `cohort-list` lists the runs, and `cohort-query` shows the labels in a
  `run_labels` column/field.
- **Lifecycle:** `cohort-append` adds runs to an existing traced cohort;
  `cohort-merge` unions two traced cohorts, deduping runs by content SHA-256 and
  recomputing counts/frequencies. Merging an untraced cohort is refused rather
  than guessed.
- **Anonymize:** `--anonymize` hashes run labels and omits paths.
- **Federated sharing is not part of v1.** Cross-lab aggregation still needs
  consent, privacy design, and legal review.

---

## Ask your run (research use)

Ask the bundle a question instead of opening JSON:

```bash
contig ask r1 "what is the verdict?"
contig ask r1 "why did it repair?"
contig ask r1 "is BRCA1 ready?" --readiness readiness.json
contig ask r1 "tell me about BRCA1" --variants variants.json
contig ask r1 "what is the verdict?" --json
contig ask r1 "what is the verdict?" --execute 1
contig ask r1 "what is the verdict?" --execute 1 --approve-action
```

- **Grounded:** answers come from `run_record.json` and the optional M1/M2
  tables; every answer lists the source path and SHA-256.
- **Intents:** verdict, QC, repairs, provenance/reproducibility, methods,
  attached variants (including gene queries), attached readiness, report next
  steps, and help. Anything else is refused with “I won’t guess.”
- **Actions:** answers suggest the next command (`contig show --explain`,
  `contig verify`, `contig report`, etc.). They never run unless you pass
  `--execute N` (1-based). The selected action is shown and asks `y/N`; use
  `--approve-action` for the explicit non-interactive approval. Execution is
  argv-based (no shell), limited to `show`, `verify`, `methods`, `report`, and
  `report-check`, and refuses actions that still contain placeholders such as
  `<vcf>`. `--execute` cannot be combined with `--json`.
- **Optional LLM:** `--llm` paraphrases the already-grounded answer using an
  OpenAI-compatible endpoint configured with `CONTIG_LLM_URL`,
  `CONTIG_LLM_MODEL`, and optional `CONTIG_LLM_API_KEY`. The model is told to
  rephrase only and to keep the citations; the deterministic answer is the
  fallback when no model is configured.
- **Eval:** `contig ask-eval r1 --cases eval.jsonl --min-accuracy 0.9` runs the
  frozen question/citation set against the deterministic router.

---

## Reproduce / share

Each run writes `runs/<id>/run_record.json`, a portable record pinning inputs
(checksums), pipeline + revision, parameters, container/tool versions, every QC
result, and the full repair chain. `contig show <id>` re-reads it; hand the
bundle to a colleague (or a reviewer) to reproduce the result.

---

## Reproduce someone else's published work

`contig reproduce` points the same engine at a **third-party, already-published**
repository and reports which of the paper's stated numbers actually regenerate.
It is the run → verify loop turned around to face other people's analyses.

```bash
contig reproduce ./cloned-paper-repo \
  --run "python analysis.py" \
  --claims claims.json
```

A claims file lists the numbers the paper states, and where each one lives in the
output the script produces:

```json
[
  {"id": "auc", "value": 0.91, "tolerance": 0.01,
   "from": "out/metrics.json", "path": "$.model.auc"},

  {"id": "log2fc", "value": 2.31,
   "from": "out/de.tsv", "column": "log2FoldChange", "row": {"gene": "ENSG1"}},

  {"id": "n_sig", "value": 412,
   "pattern": "significant genes: ([0-9]+)"},

  {"id": "median_depth", "value": 30.4,
   "from": "out/report.ipynb", "cell": {"contains": "print(depth)"},
   "pattern": "depth: ([0-9.]+)"}
]
```

Five ways to address a number: a **JSON** pointer (`path`), a **TSV/CSV** cell
(`column` + `row`, gzip-transparent), a **regex** over a text/log file (`pattern`
with `from`), a regex over the run's own **stdout/stderr** (`pattern` with no
`from`), and a **notebook** cell's output (`cell` + `pattern`). Each claim is
compared to the regenerated value and classified; the result is a signed,
re-runnable bundle. `--fail-on-diverged` turns a divergence into a non-zero exit.

`--allow-install` (off by default) additionally lets a repo that fails with
`ModuleNotFoundError` be healed once: detect the missing module, `pip install`
it, retry the run exactly once. It touches the network and mutates your
environment, which is why you have to ask for it.

`--allow-fetch` (off by default) lets you skip the clone-it-yourself step: pass
an `https://` git URL instead of a path and Contig clones it for you, shallowly,
into `runs/<id>/source/`, and runs there.

```bash
contig reproduce https://github.com/lab/paper-code --allow-fetch \
  --run "python analysis.py" \
  --claims claims.json
```

The point is not convenience — it is that the bundle then records **which
revision** it ran. It resolves `HEAD` after cloning and pins the exact 40-character
commit on the record as `source_commit`, alongside the URL as `source_url`. A
local-path run leaves both `null`. That pin is what lets someone else check your
reproduction claim; a local directory path tells them nothing.

`--rev` names the revision to check out, so the pin becomes something Contig
itself can consume rather than only a human:

```bash
contig reproduce https://github.com/lab/paper-code --allow-fetch \
  --rev 5a8dce6c03eed91b742215ce61f5415ca617f654 \
  --run "python analysis.py" \
  --claims claims.json
```

It takes a full 40-character commit SHA, a tag, or a branch, and requires a URL
plus `--allow-fetch`. Given a full SHA, Contig verifies the checkout actually
landed on it and **refuses rather than records a pin that isn't what you asked
for**. The requested ref is written to `reproduce.json` as `requested_rev`; the
resolved SHA stays on the record as `source_commit`. That is the round-trip:
take a bundle's `source_commit`, pass it back as `--rev`, get the same checkout.

Two honest limits. An **abbreviated** SHA is refused up front — git cannot fetch
one, and the error you would otherwise get reads like a typo'd branch name. And
fetching a **bare commit** requires the server to allow it
(`uploadpack.allowReachableSHA1InWant`); GitHub and GitLab do, some self-hosted
remotes do not. When a remote refuses, Contig says so and suggests a tag or
branch — it does **not** silently fall back to a full clone, which could pull
gigabytes without asking.

Without `--allow-fetch`, a URL is refused rather than treated as a path — it
reaches the network and writes a checkout under your runs directory, so you have
to ask. Only `https://` is accepted: `ssh://`, `git://`, `file://`, the
`git@host:path` shorthand, and DOIs are all refused up front, before anything is
written. (DOI intake is not supported yet; the refusal says so.)

Three things worth knowing about a fetched run:

- **The commit is the attested fact; the checkout is a convenience copy.** The
  signature covers the *record*, not the `source/` tree — that tree is unsigned
  and unhashed, and nothing detects it if you edit it afterwards.
- **Without `--rev`, you get whatever `HEAD` was at fetch time.** The clone is
  `--depth 1` and unpinned, so re-running tomorrow — after the authors push —
  reproduces a *different* revision than your earlier bundle attests to, with no
  error. Pass `--rev` (below) when that matters.
- **The freshness rule below applies to a fetched checkout exactly as to a local
  repo.** A clone writes every file at clone time, so Contig clones *before* it
  stamps the run's start — a repo that commits its outputs still reports
  `UNVERIFIED`, not a false `REPRODUCED`.

Checkouts are not cleaned up: each fetched run leaves a full copy of the repo
under its run directory.

### Every value must come from a file *this run* wrote

A published repo very often ships its outputs — a committed `results.json`, a
committed results table, a notebook with the authors' stored cell outputs. Read
naively, those would report `REPRODUCED` for a computation that never ran.

So every value read off disk must come from a file the run **rewrote**: each
locator carrying a `from`, and the `--results` file itself, resolve only when the
file's mtime is at or after the run's start. A file the run did not rewrite stays
`UNVERIFIED` rather than binding a committed artifact as a false pass. **There is
no opt-out.** The single exemption is a `pattern` with no `from`, which matches
the run's own captured stdout/stderr and so can never be stale.

Two honest limits, worth knowing before you read a verdict:

- It proves the file was **rewritten**, not that the numbers were **recomputed**.
  A `--run` that copies or touches a committed file passes while computing
  nothing. This closes the common, honest failure — not deliberate self-deception.
- There is deliberately **no tolerance window** on the timestamp comparison. On a
  filesystem with coarse mtime resolution, or when the file's clock and yours
  disagree (an NFS mount), a genuinely regenerated file can read as `UNVERIFIED`.
  That is the intended trade: a false `UNVERIFIED` is honest and recoverable, a
  false `REPRODUCED` is not.

Research-use, computation-only: Contig reports whether the *numbers* regenerate.
It never judges whether the paper's *conclusions* are correct.

---

## Where it runs (compute backends)

The same run lands unchanged on your laptop or your cloud: Contig maps the
target to a generated `nextflow.config` and lets Nextflow's native executors do
the submission. Pick the backend with `--backend`:

```bash
# Local (default): Docker on your machine
uv run contig run --run-id local-run --input samplesheet.csv --genome GRCh38

# AWS Batch: runs in your account; reads stay in your S3, not ours
uv run contig run --run-id cloud-run \
  --input samplesheet.csv --genome GRCh38 \
  --backend aws_batch \
  --work-dir s3://your-bucket/contig-work \
  --queue your-batch-queue --region eu-west-1
```

Contig validates the backend up front: e.g. an `aws_batch` run with no `--queue`
fails immediately with a clear message, not a half-hour in. AWS credentials are
read from your environment by Nextflow; Contig never holds them. The generated
config is written to `runs/<id>/nextflow.config` for inspection. (`local` and
`aws_batch` are wired today; `slurm`/`gcp_batch`/`k8s` map through the same layer
as they're validated.)

---

## Supported analyses

| Goal | Pipeline | QC |
|---|---|---|
| RNA-seq differential expression | `nf-core/rnaseq` | alignment/assignment rate, library-size skew, replicate checks |
| Single-cell RNA-seq | `nf-core/scrnaseq` | estimated cells, median genes per cell, reads in cells |
| Germline variant calling (research) | `nf-core/sarek` | Ti/Tv & het/hom ratios, variant count, coverage, sex check |
| Somatic variant calling, tumour–normal (research) | `nf-core/sarek` | tumour VAF (Mutect2 + Strelka2), somatic variant count, panel-of-normals applied, Mutect2-vs-Strelka2 concordance |
| Methylation (bisulfite) | `nf-core/methylseq` | bisulfite conversion rate, mapping efficiency, duplication |
| 16S amplicon (microbiome) | `nf-core/ampliseq` | DADA2 read retention, ASV count, sample read depth |
| Shotgun metagenomics | `nf-core/mag` | assembly N50, bin completeness, contamination |

`contig plan --goal "…"` routes to the right one (and declines goals it has no
curated pipeline for). The same run → self-heal → verify → reproduce engine
serves all of them. Adding an assay is a registry entry plus a QC rule pack: see
[ADD_AN_ASSAY.md](technical/ADD_AN_ASSAY.md).

---

## How the detector improves (failure corpus)

Every recoverable failure Contig recovers from is a labeled data point. Those
accumulate into a versioned failure corpus (`failure -> diagnosis -> fix ->
outcome`), and `contig eval-detector` replays the detector over it to report
accuracy plus per-class precision/recall:

```bash
uv run contig eval-detector
# Detector eval: 11/11 correct (accuracy 100.0%)
#   bad_param: precision 1.00  recall 1.00  (support 2)
#   ...
```

A drop in accuracy means either the detector regressed or a real run exposed a
gap worth a new rule. This is the compounding asset: the engine gets better as
runs accrue, independent of any single model.

The detector is pluggable. `--detector rules` (the default) and `--detector
rules-strict` are deterministic; `--detector llm` is an optional model-backed
detector that scores the same corpus, enabled by setting `CONTIG_LLM_PROVIDER`
(`claude` or `openai`) and the matching `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.
With no provider configured the llm detector is simply unavailable, so the corpus
eval and the test suite never need a key or the network. This is how "gets better
as models improve" is measured rather than asserted: score a new detector against
the frozen corpus and read the delta on the trend.

Capture is automatic: every failed run stashes a case to
`<runs-dir>/pending_corpus.jsonl` with the detector's diagnosis as a provisional
label. A human confirms or corrects the label before promoting it into the
golden corpus with `contig corpus-promote`, so the eval never grades the
detector on its own guesses.

---

## Dashboard (web UI)

A local Next.js dashboard reads the run bundles and corpus straight from disk and
adds an interactive surface over the same engine: launch a run, watch live task
progress and the self-heal feed, approve or reject risky patches, cancel and
resume runs, read the "why this verdict" explanation, reproduce a past run, and
track detector accuracy over time. It is localhost-only with no auth (it runs the
CLI on your machine), so do not expose it.

```bash
cd dashboard
npm install
npm run dev            # http://localhost:3000 (reads ../runs)
```

The **Research** page (`/research`) is read-only: it renders a local
`dashboard/research/manifest.json` (or `CONTIG_RESEARCH_DIR`) pointing at the
JSON/HTML produced by the workbench commands — variants, readiness (including
`--by-gene`), report sidecar/HTML, family, biomarkers, and cohort — plus a
grounded Ask panel. When no explicit manifest exists, it auto-discovers the
newest `runs/<id>/research/manifest.json`. See `dashboard/research/README.md`.

## What's not built yet

An LLM-backed planner (the goal→pipeline matcher is deterministic and replaceable
today), more assays, and live-tested `slurm`/`gcp_batch`/`k8s` backends (the
mapping layer is in place; `local` and `aws_batch` are wired). See
[docs/ROADMAP.md](ROADMAP.md).
