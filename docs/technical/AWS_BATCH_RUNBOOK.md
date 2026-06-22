# AWS Batch runbook

How to run a Contig pipeline on AWS Batch, end to end. Contig does not submit
jobs itself: it generates a `nextflow.config` that points Nextflow's native
`awsbatch` executor at your queue, and Nextflow does the submission. This runbook
covers the AWS setup, the exact `contig run` command, and what a from-scratch
PASS looks like.

Contig runs a preflight before it launches anything on AWS Batch (PRD contract
E). A misconfigured launch (no queue, no region, a non s3 work dir, or absent
credentials) is refused with a clear list of problems, before Nextflow is ever
invoked. So the first thing to get right is the four things the preflight checks.

---

## 1. What the preflight checks

`contig run --backend aws_batch` refuses unless all four hold:

1. a Batch job queue is set (`--queue`),
2. an AWS region is set (`--region`),
3. the work dir is an `s3://` URI (`--work-dir s3://...`), because Batch tasks
   share state through S3, not a local path,
4. AWS credentials are present in the environment.

If any are missing, the run exits non-zero and prints each problem. Nothing is
launched. Fix them and re-run.

---

## 2. AWS setup (one time)

You need an AWS account with permission to use Batch, S3, EC2, IAM, and ECS.

### 2.1 Credentials

Contig reads AWS credentials only from the environment, never from a flag, and
never logs them. Provide either explicit keys or a named profile:

```bash
# Option A: explicit keys
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

# Option B: a named profile from ~/.aws/credentials
export AWS_PROFILE=contig
```

Either one satisfies the preflight's credential check.

### 2.2 An S3 work dir

Create (or pick) an S3 bucket and a prefix for Nextflow's work dir:

```bash
aws s3 mb s3://your-contig-bucket
# the work dir you will pass is, for example, s3://your-contig-bucket/work
```

Nextflow stages task inputs and outputs through this prefix while running on
Batch. It must be writable by the role your Batch compute environment uses.

### 2.3 A Batch compute environment, queue, and the job role

Set up, in the AWS Batch console or with the CLI/Terraform:

1. a compute environment (managed, on Fargate or EC2),
2. a job queue attached to that compute environment (this is the `--queue`
   value),
3. an IAM job role / execution role that can read and write your S3 bucket and
   pull the pipeline's containers.

The queue name (not its ARN) is what you pass to `--queue`. The region you
created it in is what you pass to `--region`.

A minimal Fargate setup is enough for a first smoke test; size the compute
environment for the real pipeline before a production run.

---

## 3. The exact command

A from-scratch run on AWS Batch, against nf-core's bundled test profile (no real
input), looks like this:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

uv run contig run \
  --run-id aws-smoke-1 \
  --pipeline nf-core/rnaseq \
  --revision 3.26.0 \
  --backend aws_batch \
  --queue your-batch-queue \
  --region eu-west-1 \
  --work-dir s3://your-contig-bucket/work \
  --runs-dir runs
```

For a real-data run, add the sample sheet and a reference, exactly as for a local
run:

```bash
uv run contig run \
  --run-id aws-real-1 \
  --backend aws_batch \
  --queue your-batch-queue \
  --region eu-west-1 \
  --work-dir s3://your-contig-bucket/work \
  --input samplesheet.csv \
  --genome GRCh38 \
  --runs-dir runs
```

Optional: add `--notify https://your-webhook` to get a POST on every lifecycle
transition (finished, failed, cancelled, awaiting_approval).

---

## 4. What a from-scratch PASS looks like

A clean AWS Batch run ends like a clean local run, just with the work happening
on Batch. You should see, in order:

1. the preflight passes silently (no "Cannot launch on AWS Batch" message),
2. Nextflow submits tasks to your queue; the AWS Batch console shows jobs moving
   SUBMITTED to RUNNABLE to RUNNING to SUCCEEDED,
3. `contig run` prints the run report ending in a verdict line. A healthy first
   run on the test profile reports `PASS` (or `UNVERIFIED` if no QC rule covered
   the assay), exit code 0,
4. the bundle is written to `runs/aws-smoke-1/run_record.json`, including
   `output_checksums` over the produced outputs.

Then verify the outputs were captured and are intact:

```bash
uv run contig verify aws-smoke-1 --runs-dir runs
# Outputs verified for run aws-smoke-1: all recorded outputs match.
```

A PASS plus a clean `contig verify` is the from-scratch success signal: the
pipeline ran on your AWS compute, produced outputs, and those outputs are
anchored in the reproducible record.

---

## 5. Troubleshooting

- "Cannot launch on AWS Batch: no AWS credentials in the environment": set
  `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, or `AWS_PROFILE`, in the same
  shell you run `contig` from.
- "work dir ... is not an s3:// URI": pass `--work-dir s3://your-bucket/work`.
  The local default work dir is not usable on Batch.
- Jobs stuck in RUNNABLE: the compute environment cannot place them. Check its
  instance role, max vCPUs, and subnet/security group networking.
- Tasks fail pulling a container: the job role lacks ECR/registry access, or the
  compute environment has no outbound network route.
- A task fails on memory or time: Contig's self-heal loop will diagnose and, for
  a safe fix, bump `process.resourceLimits` and retry automatically; a gated fix
  pauses for your approval (`contig approve <id>`).
