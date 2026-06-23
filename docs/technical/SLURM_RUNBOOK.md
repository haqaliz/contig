# SLURM runbook: pointing Contig at a real cluster

This runbook covers running a Contig pipeline on a SLURM cluster. Contig does not
talk to SLURM directly; it generates a `nextflow.config` that selects Nextflow's
native `slurm` executor, and Nextflow submits each process as an `sbatch` job. Our
job is the mapping plus a preflight that refuses a misconfigured launch before any
job is submitted.

## What you need on the cluster

- A SLURM controller you can submit to (`sbatch` and `sinfo` on PATH).
- A partition to submit into (the SLURM queue).
- An account, if your cluster enforces accounting (most shared clusters do).
- Singularity (or Apptainer) for containers. HPC nodes rarely run Docker, so the
  default container runtime for SLURM here is `singularity`.
- A shared work directory both the login node and the compute nodes can read and
  write (a scratch or project filesystem path). This is the Nextflow `workDir`.

## How the options map

| Contig flag | Where it lands in nextflow.config |
| --- | --- |
| `--backend slurm` | `process.executor = 'slurm'` |
| `--queue <partition>` | `process.queue = '<partition>'` (the SLURM partition) |
| `--opt account=<acct>` | `process.clusterOptions = '--account=<acct>'` |
| `--opt qos=<qos>` | adds `--qos=<qos>` to `process.clusterOptions` |
| `--opt time=<lit>` | `process.time = '<lit>'` (e.g. `8.h`) |
| `--container-runtime singularity` | `singularity.enabled = true` |
| `--work-dir <shared path>` | `workDir = '<shared path>'` |

`account` and `qos` are not first-class Nextflow knobs, so they ride into
`process.clusterOptions` as the literal `sbatch` flags Nextflow forwards. Every
`--opt` value is validated (a conservative token, no leading dash, no shell
metacharacters) before it reaches the generated config.

## The preflight

Before launching, `contig run --backend slurm` runs `preflight_slurm`, which refuses
the launch (non-zero exit, a clear message per problem) when:

- no partition is set (pass `--queue`);
- no account is set (pass `--opt account=...`);
- `sbatch` is not on PATH (SLURM not installed or its module not loaded);
- `sinfo` is not on PATH.

Every problem is listed at once so you fix them in one pass. No cluster call is made
during the preflight; it is offline.

## The exact command

From the cluster login node, with SLURM loaded and a reference available:

```bash
contig run \
  --run-id slurm-demo \
  --backend slurm \
  --container-runtime singularity \
  --queue general \
  --opt account=mylab \
  --opt qos=normal \
  --work-dir /scratch/$USER/contig/work \
  --input samplesheet.csv \
  --genome GRCh38 \
  --max-memory 16.GB \
  --max-cpus 4
```

Without `--input`, Contig runs nf-core's bundled test profile, which is the quickest
way to confirm the executor path end to end before committing real data.

## What to expect

1. Contig writes `runs/slurm-demo/nextflow.config` with the `slurm` executor and your
   partition/account/qos, then `runs/slurm-demo/launch.json` (the reproduce sidecar).
2. Nextflow submits each process as a separate `sbatch` job into your partition. You
   can watch them with `squeue -u $USER`.
3. Output, the captured trace, and `run.log` land under `runs/slurm-demo/`. The
   self-heal loop reacts to recoverable failures (for example an out-of-memory job
   gets a bumped `process.resourceLimits` and a `-resume` retry).
4. On success you get a verdict and a verified, bundled `RunRecord`, identical in
   shape to a local run. `contig show slurm-demo` and `contig verify slurm-demo` work
   the same way regardless of backend.

## Troubleshooting

- "sbatch not found on PATH": load the SLURM module (`module load slurm`) or run from
  a node where the client binaries are installed.
- Jobs sit in `PENDING` forever: the partition or account is wrong for your cluster.
  Check `sinfo` for valid partitions and `sacctmgr show assoc user=$USER` for the
  accounts you may charge to.
- Containers fail to pull: confirm Singularity (or Apptainer) is available on the
  compute nodes, not only the login node.
