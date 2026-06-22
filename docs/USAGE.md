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
| `contig verify <id>` | Re-hash a finished run's outputs against the record and report any drift |
| `contig approve <id>` | Approve (or `--reject`) the patch a paused self-heal run is waiting on |
| `contig list` | All bundled runs |
| `contig corpus-promote` | Promote a confirmed pending failure case into the golden corpus |
| `contig eval-detector` | Score the failure detector against the labeled failure corpus (`--detector rules-strict` to score a different detector, `--snapshot` to record a point in the history, `--history` to show the trend) |
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
or AWS credentials are missing.

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
# → Plan: nf-core/rnaseq @ 3.26.0  (assay: rnaseq) … + any warnings
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

---

## Reproduce / share

Each run writes `runs/<id>/run_record.json`, a portable record pinning inputs
(checksums), pipeline + revision, parameters, container/tool versions, every QC
result, and the full repair chain. `contig show <id>` re-reads it; hand the
bundle to a colleague (or a reviewer) to reproduce the result.

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
| Single-cell RNA-seq | `nf-core/scrnaseq` | estimated cells, median genes per cell, reads in cells, mito fraction |
| Germline variant calling (research) | `nf-core/sarek` | Ti/Tv & het/hom ratios, coverage |

`contig plan --goal "…"` routes to the right one (and declines goals it has no
curated pipeline for). The same run → self-heal → verify → reproduce engine
serves all three.

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
