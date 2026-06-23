"""Tests for ExecutionTarget -> nextflow.config generation (ARCHITECTURE §4.1).

The compute abstraction is a mapping layer: Contig turns an ExecutionTarget into
a generated nextflow.config profile and lets Nextflow's native executors do the
submission. These tests pin the mapping; live cloud submission is Nextflow's job.
"""

import pytest

from contig.models import ExecutionTarget
from contig.nfconfig import (
    ConfigGenerationError,
    generate_nextflow_config,
    preflight_aws_batch,
    preflight_slurm,
)

_AWS_ENV = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE")


def _set_aws_creds(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.delenv("AWS_PROFILE", raising=False)


def _clear_aws_creds(monkeypatch):
    for var in _AWS_ENV:
        monkeypatch.delenv(var, raising=False)


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
    cfg = generate_nextflow_config(_target("local", runtime="singularity"))
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


# --- AWS Batch preflight (PRD contract E: refuse a misconfigured launch) --------
def test_preflight_aws_batch_passes_when_fully_configured(monkeypatch):
    _set_aws_creds(monkeypatch)
    assert preflight_aws_batch(_aws_target()) == []


def test_preflight_aws_batch_reports_missing_queue(monkeypatch):
    _set_aws_creds(monkeypatch)
    target = ExecutionTarget(
        backend="aws_batch",
        container_runtime="docker",
        work_dir="s3://b/w",
        backend_options={"region": "eu-west-1"},
    )
    problems = preflight_aws_batch(target)
    assert any("queue" in p.lower() for p in problems)


def test_preflight_aws_batch_reports_missing_region(monkeypatch):
    _set_aws_creds(monkeypatch)
    target = ExecutionTarget(
        backend="aws_batch",
        container_runtime="docker",
        work_dir="s3://b/w",
        backend_options={"queue": "q"},
    )
    problems = preflight_aws_batch(target)
    assert any("region" in p.lower() for p in problems)


def test_preflight_aws_batch_reports_non_s3_work_dir(monkeypatch):
    _set_aws_creds(monkeypatch)
    target = _aws_target(work_dir="/local/work")
    problems = preflight_aws_batch(target)
    assert any("s3://" in p for p in problems)


def test_preflight_aws_batch_reports_absent_credentials(monkeypatch):
    _clear_aws_creds(monkeypatch)
    problems = preflight_aws_batch(_aws_target())
    assert any("credential" in p.lower() for p in problems)


def test_preflight_aws_batch_accepts_aws_profile_as_credentials(monkeypatch):
    _clear_aws_creds(monkeypatch)
    monkeypatch.setenv("AWS_PROFILE", "contig")
    assert preflight_aws_batch(_aws_target()) == []


def test_preflight_aws_batch_collects_all_problems(monkeypatch):
    _clear_aws_creds(monkeypatch)
    target = ExecutionTarget(
        backend="aws_batch",
        container_runtime="docker",
        work_dir="/local/work",
        backend_options={},
    )
    problems = preflight_aws_batch(target)
    # queue, region, work_dir, credentials: every problem surfaces at once so the
    # user fixes them in one pass rather than one error at a time.
    assert len(problems) >= 4


# --- SLURM backend (PRD contract A: the HPC executor) ----------------------
def _slurm_target(**opts):
    options = {"partition": "general", "account": "lab", "time": "4.h", "qos": "normal"}
    options.update(opts)
    # An explicit None value clears that knob (lets a test omit a single field).
    options = {k: v for k, v in options.items() if v is not None}
    return ExecutionTarget(
        backend="slurm",
        container_runtime="singularity",
        work_dir="/scratch/contig/work",
        backend_options=options,
    )


def test_slurm_backend_selects_slurm_executor():
    cfg = generate_nextflow_config(_slurm_target())
    assert "process.executor = 'slurm'" in cfg


def test_slurm_backend_sets_partition_as_queue():
    cfg = generate_nextflow_config(_slurm_target(partition="bigmem"))
    assert "process.queue = 'bigmem'" in cfg


def test_slurm_backend_passes_account_through_clusteroptions():
    cfg = generate_nextflow_config(_slurm_target(account="genomics"))
    assert "--account=genomics" in cfg


def test_slurm_backend_passes_qos_through_clusteroptions():
    cfg = generate_nextflow_config(_slurm_target(qos="high"))
    assert "--qos=high" in cfg


def test_slurm_backend_sets_time_as_process_time():
    cfg = generate_nextflow_config(_slurm_target(time="8.h"))
    assert "process.time = '8.h'" in cfg


def test_slurm_backend_without_partition_is_a_loud_error():
    with pytest.raises(ConfigGenerationError):
        generate_nextflow_config(_slurm_target(partition=None))


def test_slurm_backend_omits_account_clusteroptions_when_absent():
    cfg = generate_nextflow_config(_slurm_target(account=None))
    assert "--account" not in cfg


# --- SLURM preflight (PRD contract A: refuse a misconfigured launch) ------------
def _slurm_on_path(monkeypatch, present=True):
    import contig.nfconfig as nfconfig

    def fake_which(name):
        if name in ("sbatch", "sinfo"):
            return f"/usr/bin/{name}" if present else None
        return None

    monkeypatch.setattr(nfconfig.shutil, "which", fake_which)


def test_preflight_slurm_passes_when_fully_configured(monkeypatch):
    _slurm_on_path(monkeypatch, present=True)
    assert preflight_slurm(_slurm_target()) == []


def test_preflight_slurm_reports_missing_partition(monkeypatch):
    _slurm_on_path(monkeypatch, present=True)
    problems = preflight_slurm(_slurm_target(partition=None))
    assert any("partition" in p.lower() for p in problems)


def test_preflight_slurm_reports_missing_account(monkeypatch):
    _slurm_on_path(monkeypatch, present=True)
    problems = preflight_slurm(_slurm_target(account=None))
    assert any("account" in p.lower() for p in problems)


def test_preflight_slurm_reports_sbatch_not_on_path(monkeypatch):
    _slurm_on_path(monkeypatch, present=False)
    problems = preflight_slurm(_slurm_target())
    assert any("sbatch" in p.lower() for p in problems)


def test_preflight_slurm_reports_sinfo_not_on_path(monkeypatch):
    import contig.nfconfig as nfconfig

    monkeypatch.setattr(
        nfconfig.shutil, "which", lambda name: "/usr/bin/sbatch" if name == "sbatch" else None
    )
    problems = preflight_slurm(_slurm_target())
    assert any("sinfo" in p.lower() for p in problems)


def test_preflight_slurm_collects_all_problems(monkeypatch):
    _slurm_on_path(monkeypatch, present=False)
    target = ExecutionTarget(
        backend="slurm",
        container_runtime="singularity",
        work_dir="/scratch/work",
        backend_options={},
    )
    problems = preflight_slurm(target)
    # partition, account, sbatch, sinfo: surface every problem in one pass.
    assert len(problems) >= 4
