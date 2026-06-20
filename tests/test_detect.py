"""Tests for the rule-based failure detector (ARCHITECTURE §5.1).

Real code, no mocks: each case feeds plain TaskEvent fixtures and captured
Nextflow error-log text into `diagnose_failure` and asserts the classification.
"""

from __future__ import annotations

from contig.detect import diagnose_failure
from contig.models import TaskEvent


def test_exit_137_is_oom() -> None:
    events = [TaskEvent(process="ALIGN", status="FAILED", exit=137)]
    d = diagnose_failure(events, log_text="some output\nprocess terminated")
    assert d.failure_class == "oom"
    assert d.evidence  # the matching signal is recorded


def test_due_to_time_limit_is_time_limit() -> None:
    events = [TaskEvent(process="SORT", status="FAILED", exit=1)]
    log = "slurmstepd: error: JOB 42 CANCELLED DUE TO TIME LIMIT"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "time_limit"
    assert any("TIME LIMIT" in e for e in d.evidence)


def test_oom_from_log_text_without_exit_137() -> None:
    events = [TaskEvent(process="ASSEMBLE", status="FAILED", exit=1)]
    log = "java.lang.OutOfMemoryError: Java heap space"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "oom"
    assert any("OutOfMemoryError" in e for e in d.evidence)


def test_docker_desktop_down_is_container_unavailable() -> None:
    events = [TaskEvent(process="FASTQC", status="FAILED", exit=125)]
    log = "Docker Desktop is unable to start, please check your installation"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "container_unavailable"
    assert any("Docker Desktop" in e for e in d.evidence)


def test_manifest_unknown_is_container_pull_failed() -> None:
    events = [TaskEvent(process="ALIGN", status="FAILED", exit=1)]
    log = "failed to pull image: manifest unknown: manifest unknown"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "container_pull_failed"
    assert any("manifest unknown" in e for e in d.evidence)


def test_resolvepackagenotfound_is_conda_solve_failed() -> None:
    events = [TaskEvent(process="SETUP", status="FAILED", exit=1)]
    log = "ResolvePackageNotFound:\n  - samtools=1.99"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "conda_solve_failed"
    assert any("ResolvePackageNotFound" in e for e in d.evidence)


def test_missing_fai_is_missing_index() -> None:
    events = [TaskEvent(process="ALIGN", status="FAILED", exit=1)]
    log = "[E::fai_load] Failed to open the index reference.fasta.fai: No such file or directory"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert any(".fai" in e for e in d.evidence)


def test_missing_genome_fasta_is_missing_reference() -> None:
    events = [TaskEvent(process="ALIGN", status="FAILED", exit=1)]
    log = "Error: No such file or directory: /data/genome.fasta"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_reference"
    assert any("genome.fasta" in e for e in d.evidence)


def test_unknown_option_is_bad_param() -> None:
    events = [TaskEvent(process="TRIM", status="FAILED", exit=2)]
    log = "Unknown option: --foo"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "bad_param"
    assert any("--foo" in e for e in d.evidence)


def test_generic_failed_task_is_tool_crash() -> None:
    events = [TaskEvent(process="CALL", status="FAILED", exit=1)]
    log = "Segmentation fault (core dumped) while processing sample"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "tool_crash"


def test_no_failures_empty_log_is_unknown() -> None:
    d = diagnose_failure(events=[], log_text="")
    assert d.failure_class == "unknown"
    assert d.confidence <= 0.3


def test_oom_exit_137_wins_over_generic_log_error() -> None:
    # Both an exit-137 kill and a generic crash signal are present; OOM must win.
    events = [TaskEvent(process="ASSEMBLE", status="FAILED", exit=137)]
    log = "Segmentation fault (core dumped)\nUnknown option: --foo"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "oom"


def test_confidence_always_within_unit_interval() -> None:
    cases = [
        ([TaskEvent(process="A", status="FAILED", exit=137)], "killed"),
        ([TaskEvent(process="B", status="FAILED", exit=1)], "Unknown option: --x"),
        ([TaskEvent(process="C", status="FAILED", exit=1)], "weird crash"),
        ([], ""),
    ]
    for events, log in cases:
        d = diagnose_failure(events, log_text=log)
        assert 0.0 <= d.confidence <= 1.0


def test_platform_mismatch_with_killed_task_is_platform_unsupported() -> None:
    # Apple Silicon (arm64) running amd64-only containers under emulation: a step
    # is KILLED (no exit code) and the platform-mismatch warning is present.
    events = [TaskEvent(process="MAKE_TRANSCRIPTS_FASTA", status="FAILED", exit=None)]
    log = (
        "WARNING: The requested image's platform (linux/amd64) does not match the "
        "detected host platform (linux/arm64/v8) and no specific platform was requested\n"
        "Execution cancelled -- Finishing pending tasks before exit"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "platform_unsupported"


def test_failed_task_with_real_exit_code_is_not_platform_unsupported() -> None:
    # The platform warning appears on EVERY task; a real non-zero exit is a genuine
    # tool error, not the emulation killing the binary.
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)]
    log = (
        "WARNING: The requested image's platform (linux/amd64) does not match the "
        "detected host platform (linux/arm64/v8)\nsome tool error"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class != "platform_unsupported"


def test_benign_fai_mention_is_not_missing_index() -> None:
    # "samtools faidx genome.fasta" creates genome.fasta.fai — a SUCCESSFUL op.
    # A bare .fai mention (no "not found" context) must not trigger missing_index.
    events = [TaskEvent(process="STAR_GENOMEGENERATE", status="FAILED", exit=1)]
    log = "Running: samtools faidx genome.fasta\nCreated genome.fasta.fai\nunrelated tool error"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class != "missing_index"
