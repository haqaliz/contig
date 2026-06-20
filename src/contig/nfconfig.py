"""ExecutionTarget -> nextflow.config generation: Contig's compute abstraction.

Per ARCHITECTURE §4.1, the abstraction over local/cloud/HPC is mostly a *mapping
layer*: an ExecutionTarget becomes a generated `nextflow.config` profile, and
Nextflow's native executors do the actual submission. This module is that map.
It is pure (target -> text) so it is fully testable without any live backend.
"""

from __future__ import annotations

from contig.models import ExecutionTarget

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
    (e.g. AWS Batch with no queue) — failing loudly beats submitting a job that
    Nextflow would reject deep in execution.
    """
    lines: list[str] = [_RUNTIME_LINE[target.container_runtime]]
    lines.append(f"process.executor = '{_EXECUTOR[target.backend]}'")

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
