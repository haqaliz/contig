"""ExecutionTarget -> nextflow.config generation: Contig's compute abstraction.

Per ARCHITECTURE §4.1, the abstraction over local/cloud/HPC is mostly a *mapping
layer*: an ExecutionTarget becomes a generated `nextflow.config` profile, and
Nextflow's native executors do the actual submission. This module is that map.
It is pure (target -> text) so it is fully testable without any live backend.
"""

from __future__ import annotations

import os

from contig.models import ExecutionTarget

# The env that proves AWS credentials are available to Nextflow's awsbatch
# executor. Either explicit keys, or a named profile, satisfies the check; the
# values themselves are never read or logged here.
_AWS_CREDENTIAL_ENV = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE")

# Contig backend -> Nextflow `process.executor` value. Nextflow already speaks
# all of these; we only choose the name and supply the executor's required knobs.
_EXECUTOR = {
    "local": "local",
    "aws_batch": "awsbatch",
    "gcp_batch": "google-batch",
    "slurm": "slurm",
    "k8s": "k8s",
}

# Container runtime -> the scope Nextflow enables. nf-core containers are pinned
# upstream; we just turn on the right runtime for the host (Docker on cloud,
# Singularity on HPC, Conda as the no-container fallback).
_RUNTIME_LINE = {
    "docker": "docker.enabled = true",
    "singularity": "singularity.enabled = true\nsingularity.autoMounts = true",
    "conda": "conda.enabled = true",
}


class ConfigGenerationError(ValueError):
    """A target cannot be mapped to a valid nextflow.config (missing required knob)."""


def generate_nextflow_config(target: ExecutionTarget) -> str:
    """Render the nextflow.config text for an ExecutionTarget.

    Raises ConfigGenerationError when a backend's required options are absent
    (e.g. AWS Batch with no queue); failing loudly beats submitting a job that
    Nextflow would reject deep in execution.
    """
    lines: list[str] = [_RUNTIME_LINE[target.container_runtime]]
    lines.append(f"process.executor = '{_EXECUTOR[target.backend]}'")

    # Resource ceilings via Nextflow's native resourceLimits (memory/cpus/time
    # as Nextflow literals, e.g. 6.GB / 2 / 24.h). This is what modern nf-core
    # honors; the legacy --max_memory params are ignored.
    if target.resource_limits:
        parts = [
            f"{key}: {target.resource_limits[key]}"
            for key in ("memory", "cpus", "time")
            if key in target.resource_limits
        ]
        lines.append(f"process.resourceLimits = [ {', '.join(parts)} ]")

    if target.backend == "aws_batch":
        opts = target.backend_options
        queue = opts.get("queue")
        region = opts.get("region")
        if not queue:
            raise ConfigGenerationError("aws_batch target requires a 'queue' backend option")
        if not region:
            raise ConfigGenerationError("aws_batch target requires a 'region' backend option")
        lines.append(f"process.queue = '{queue}'")
        lines.append(f"aws.region = '{region}'")

    lines.append(f"workDir = '{target.work_dir}'")
    return "\n".join(lines) + "\n"


def preflight_aws_batch(target: ExecutionTarget) -> list[str]:
    """List the reasons an AWS Batch launch would fail, before launching (contract E).

    Checks the things Nextflow would only fail on deep in submission: a missing
    queue or region, a work dir that is not an s3:// URI (Batch tasks share state
    through S3, not a local path), and absent AWS credentials in the environment.
    An empty list means the launch is configured; otherwise each string is a
    human-readable problem to fix. No AWS call is made; this is offline.
    """
    problems: list[str] = []
    opts = target.backend_options
    if not opts.get("queue"):
        problems.append("no Batch job queue set (pass --queue)")
    if not opts.get("region"):
        problems.append("no AWS region set (pass --region)")
    if not str(target.work_dir).startswith("s3://"):
        problems.append(
            f"work dir {target.work_dir!r} is not an s3:// URI (AWS Batch needs an S3 work dir; pass --work-dir s3://...)"
        )
    if not any(os.environ.get(var) for var in _AWS_CREDENTIAL_ENV):
        problems.append(
            "no AWS credentials in the environment (set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or AWS_PROFILE)"
        )
    return problems
