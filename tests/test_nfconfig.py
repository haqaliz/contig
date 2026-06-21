"""Tests for ExecutionTarget -> nextflow.config generation (ARCHITECTURE §4.1).

The compute abstraction is a mapping layer: Contig turns an ExecutionTarget into
a generated nextflow.config profile and lets Nextflow's native executors do the
submission. These tests pin the mapping; live cloud submission is Nextflow's job.
"""

import pytest

from contig.models import ExecutionTarget
from contig.nfconfig import ConfigGenerationError, generate_nextflow_config


def _target(backend, runtime="docker", work_dir="/runs/r1/work", **opts):
    return ExecutionTarget(
        backend=backend,
        container_runtime=runtime,
        work_dir=work_dir,
        backend_options=opts or {},
    )


def test_local_backend_selects_local_executor():
    cfg = generate_nextflow_config(_target("local"))
    assert "process.executor = 'local'" in cfg


def test_docker_runtime_enables_docker():
    cfg = generate_nextflow_config(_target("local", runtime="docker"))
    assert "docker.enabled = true" in cfg


def test_singularity_runtime_enables_singularity():
    cfg = generate_nextflow_config(_target("slurm", runtime="singularity"))
    assert "singularity.enabled = true" in cfg


def test_work_dir_is_set_from_target():
    cfg = generate_nextflow_config(_target("local", work_dir="/runs/abc/work"))
    assert "workDir = '/runs/abc/work'" in cfg


# --- resource limits (modern nf-core ignores --max_memory; uses resourceLimits) -
def _rl_target(limits):
    return ExecutionTarget(
        backend="local", container_runtime="docker", work_dir="/w", resource_limits=limits
    )


def test_no_resource_limits_emits_no_resourcelimits_line():
    cfg = generate_nextflow_config(_rl_target({}))
    assert "resourceLimits" not in cfg


def test_resource_limits_emit_process_resourcelimits():
    cfg = generate_nextflow_config(_rl_target({"memory": "6.GB", "cpus": "2", "time": "24.h"}))
    assert "process.resourceLimits = [ memory: 6.GB, cpus: 2, time: 24.h ]" in cfg


def test_partial_resource_limits_emit_only_given_keys():
    cfg = generate_nextflow_config(_rl_target({"memory": "3.GB"}))
    assert "process.resourceLimits = [ memory: 3.GB ]" in cfg


# --- AWS Batch (P6: the second compute backend) ---------------------------
def _aws_target(**overrides):
    opts = {"queue": "contig-q", "region": "eu-west-1"}
    opts.update({k: v for k, v in overrides.items() if k in ("queue", "region")})
    work_dir = overrides.get("work_dir", "s3://contig-bucket/work")
    return ExecutionTarget(
        backend="aws_batch",
        container_runtime="docker",
        work_dir=work_dir,
        backend_options=opts,
    )


def test_aws_batch_selects_awsbatch_executor():
    cfg = generate_nextflow_config(_aws_target())
    assert "process.executor = 'awsbatch'" in cfg


def test_aws_batch_sets_queue_and_region():
    cfg = generate_nextflow_config(_aws_target(queue="my-queue", region="us-east-1"))
    assert "process.queue = 'my-queue'" in cfg
    assert "aws.region = 'us-east-1'" in cfg


def test_aws_batch_uses_s3_work_dir():
    cfg = generate_nextflow_config(_aws_target(work_dir="s3://my-bucket/runs"))
    assert "workDir = 's3://my-bucket/runs'" in cfg


def test_aws_batch_without_queue_is_a_loud_error():
    target = ExecutionTarget(
        backend="aws_batch",
        container_runtime="docker",
        work_dir="s3://b/w",
        backend_options={"region": "eu-west-1"},
    )
    with pytest.raises(ConfigGenerationError):
        generate_nextflow_config(target)


def test_aws_batch_without_region_is_a_loud_error():
    target = ExecutionTarget(
        backend="aws_batch",
        container_runtime="docker",
        work_dir="s3://b/w",
        backend_options={"queue": "q"},
    )
    with pytest.raises(ConfigGenerationError):
        generate_nextflow_config(target)
