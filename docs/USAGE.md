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

The CLI and the test suite work **without** Nextflow/Java/Docker; only live runs need them.

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
| `contig approve <id>` | Approve (or `--reject`) the patch a paused self-heal run is waiting on; `--choose N` picks a ranked fix on a choice gate |
| `contig benchmark <id>` | Compare a run's QC against a designated reference (`benchmark set <id>` to record one) within a tolerance |
| `contig clusters` | Group failure-corpus cases by class and a normalized log signature (recurring failure modes) |
| `contig coverage` | Corpus coverage: per-class support, thin-coverage flags, confirmed cases over time |
| `contig list` | All bundled runs |
| `contig corpus-promote` | Promote a confirmed pending failure case into the golden corpus |
| `contig eval-detector` | Score the failure detector against the labeled failure corpus (`--detector rules-strict` or `--detector llm` to score a different detector, `--snapshot` to record a point in the history, `--history` to show the trend) |
| `contig reproduce <repo\|url> --run "<cmd>" --claims <file>` | Run a third-party repo's script and report, per stated number, whether it actually regenerates: `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`. Takes a local path, or an `https://` git URL with `--allow-fetch` (see below) |
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

Without `--allow-fetch`, a URL is refused rather than treated as a path — it
reaches the network and writes a checkout under your runs directory, so you have
to ask. Only `https://` is accepted: `ssh://`, `git://`, `file://`, the
`git@host:path` shorthand, and DOIs are all refused up front, before anything is
written. (DOI intake is not supported yet; the refusal says so.)

Three things worth knowing about a fetched run:

- **The commit is the attested fact; the checkout is a convenience copy.** The
  signature covers the *record*, not the `source/` tree — that tree is unsigned
  and unhashed, and nothing detects it if you edit it afterwards.
- **The pin is auditable, not automatically replayable.** There is no `--rev`
  yet, so nothing in Contig consumes `source_commit` — a human reads it and runs
  `git checkout <sha>`. The clone is `--depth 1`, so what you get is whatever
  `HEAD` was at fetch time.
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

## What's not built yet

An LLM-backed planner (the goal→pipeline matcher is deterministic and replaceable
today), more assays, and live-tested `slurm`/`gcp_batch`/`k8s` backends (the
mapping layer is in place; `local` and `aws_batch` are wired). See
[docs/ROADMAP.md](ROADMAP.md).
