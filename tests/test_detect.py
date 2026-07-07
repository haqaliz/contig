"""Tests for the rule-based failure detector (ARCHITECTURE §5.1).

Real code, no mocks: each case feeds plain TaskEvent fixtures and captured
Nextflow error-log text into `diagnose_failure` and asserts the classification.
"""

from __future__ import annotations

import pytest

from contig.detect import (
    DETECTORS,
    diagnose_failure,
    diagnose_failure_strict,
    get_detector,
)
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


def test_missing_bai_is_missing_index() -> None:
    events = [TaskEvent(process="SAMTOOLS", status="FAILED", exit=1)]
    log = 'samtools index: failed to open "aln.bam.bai": No such file or directory'
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert any(".bai" in e for e in d.evidence)


def test_missing_tbi_is_missing_index() -> None:
    events = [TaskEvent(process="BCFTOOLS", status="FAILED", exit=1)]
    log = "[E::idx_load] Could not load the index calls.vcf.gz.tbi: No such file or directory"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert any(".tbi" in e for e in d.evidence)


def test_missing_csi_is_missing_index() -> None:
    events = [TaskEvent(process="BCFTOOLS", status="FAILED", exit=1)]
    log = "Failed to open calls.vcf.gz.csi: No such file or directory"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert any(".csi" in e for e in d.evidence)


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


def test_nfcore_schema_validation_failure_is_bad_param() -> None:
    # Real failure from a live run: nf-core's param schema rejected the inputs.
    # This is a parameter problem, not an unclassified tool crash.
    events = [TaskEvent(process="NFCORE_RNASEQ", status="FAILED", exit=1)]
    log = (
        "ERROR ~ Validation of pipeline parameters failed!\n"
        "The following invalid input values have been detected:\n"
        "* --input (sheet.csv): the file or directory 'sheet.csv' does not exist"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "bad_param"


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


_GATK_MISSING_DICT_LOG = (
    "A USER ERROR has occurred: Fasta dict file /work/ref/genome.dict for "
    "reference /work/ref/genome.fasta does not exist. Please build it using "
    "e.g. picard CreateSequenceDictionary or samtools dict."
)


def test_missing_gatk_dict_is_missing_index() -> None:
    # GATK reports a missing sequence dictionary with "does not exist" wording,
    # which is NOT in the generic notfound tuple, so a targeted branch must catch it.
    events = [TaskEvent(process="GATK4_HAPLOTYPECALLER", status="FAILED", exit=1)]
    d = diagnose_failure(events, log_text=_GATK_MISSING_DICT_LOG)
    assert d.failure_class == "missing_index"
    assert any(".dict" in e for e in d.evidence)


def test_missing_gatk_dict_is_missing_index_not_missing_reference() -> None:
    # The canonical dict log mentions .fasta/reference too; it must classify as
    # missing_index (the dict is what's absent), never missing_reference.
    events = [TaskEvent(process="GATK4_HAPLOTYPECALLER", status="FAILED", exit=1)]
    d = diagnose_failure(events, log_text=_GATK_MISSING_DICT_LOG)
    assert d.failure_class == "missing_index"
    assert d.failure_class != "missing_reference"


def test_contig_mismatch_is_not_missing_index_dict() -> None:
    # A wrong-reference / contig-mismatch line mentions .fasta/reference but has
    # NO absence phrase ("does not exist"/"not found"). It is a different, deferred
    # failure class and the narrow dict branch must not swallow it.
    events = [TaskEvent(process="GATK4_HAPLOTYPECALLER", status="FAILED", exit=1)]
    log = (
        "A USER ERROR has occurred: Input files reference and reads have "
        "incompatible contigs. The reference /work/ref/genome.fasta has contig "
        "'chr1' but the reads use '1'."
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class != "missing_index"


def test_benign_fai_mention_is_not_missing_index() -> None:
    # "samtools faidx genome.fasta" creates genome.fasta.fai, a SUCCESSFUL op.
    # A bare .fai mention (no "not found" context) must not trigger missing_index.
    events = [TaskEvent(process="STAR_GENOMEGENERATE", status="FAILED", exit=1)]
    log = "Running: samtools faidx genome.fasta\nCreated genome.fasta.fai\nunrelated tool error"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class != "missing_index"


# --- STAR / BWA aligner index (missing or version-incompatible) ----------------


def test_star_missing_genome_file_is_missing_index() -> None:
    # STAR opens genomeParameters.txt first; an absent/partial index surfaces
    # as this "could not open genome file" FATAL ERROR line.
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)]
    log = (
        "EXITING because of FATAL ERROR: could not open genome file "
        "/work/idx/genomeParameters.txt"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert any("genomeParameters.txt" in e for e in d.evidence)


def test_star_incompatible_genome_version_is_missing_index() -> None:
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)]
    log = (
        "EXITING because of FATAL ERROR: Genome version: 20201 is INCOMPATIBLE "
        "with running STAR version: 2.7.5a_2020-06-29\n"
        "SOLUTION: please re-generate genome from scratch with STAR >= 2.5"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert any("INCOMPATIBLE" in e for e in d.evidence)


def test_bwa_missing_index_is_missing_index() -> None:
    events = [TaskEvent(process="BWA_MEM", status="FAILED", exit=1)]
    log = "[E::bwa_idx_load_from_disk] fail to locate the index files"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert any("bwa_idx_load_from_disk" in e for e in d.evidence)


def test_wrong_reference_contig_mismatch_is_not_missing_index() -> None:
    # A wrong-reference / contig-mismatch line must NOT be swallowed by the new
    # STAR/BWA missing-index branches (it is a different, deferred class).
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)]
    log = "ERROR: Contig 'chr1' not found in the reference dictionary /work/ref/genome.fasta"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class != "missing_index"


def test_bwamem2_unreadable_index_is_missing_index() -> None:
    events = [TaskEvent(process="BWA_MEM2_MEM", status="FAILED", exit=1)]
    log = "ERROR! Unable to open the file: /work/idx/genome.fasta.bwt.2bit.64"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert any("bwt.2bit.64" in e for e in d.evidence)


def test_bwamem2_generic_unable_to_open_without_index_token_is_not_missing_index() -> None:
    # The bwa-mem2 branch matches on "unable to open the file" alone, but the
    # AND-guard requires the bwt.2bit.64 sidecar token too. A generic
    # "unable to open the file" line that references some non-index file must
    # NOT be classified missing_index -- this proves the token is genuinely
    # required, not just decorative.
    events = [TaskEvent(process="SOME_PROC", status="FAILED", exit=1)]
    log = "ERROR! Unable to open the file: /work/tmp/scratch.txt"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class != "missing_index"


def test_gzip_reference_is_reference_not_bgzf() -> None:
    # samtools faidx refuses a plain-gzip'd (non-BGZF) reference FASTA. This is
    # a distinct, recoverable class (recompress to plain uncompressed .fa),
    # not an opaque tool_crash.
    events = [TaskEvent(process="SAMTOOLS_FAIDX", status="FAILED", exit=1)]
    log = (
        "[E::fai_build_core] File truncated at line 1\n"
        "[E::fai_build3_core] Cannot index files compressed with gzip, please use bgzip\n"
        "[faidx] Could not build fai index /work/ref.fa.gz.fai"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "reference_not_bgzf"
    assert any("cannot index files compressed with gzip" in e.lower() for e in d.evidence)


def test_vcf_please_use_bgzip_without_faidx_token_is_not_reference_not_bgzf() -> None:
    # tabix/bcftools also say "please use bgzip" -- but for VCFs, a different
    # fix entirely. Only the faidx-specific "cannot index files compressed
    # with gzip" phrase should trigger reference_not_bgzf; the bare
    # "please use bgzip" phrasing must not be over-matched.
    events = [TaskEvent(process="TABIX", status="FAILED", exit=1)]
    log = "[tabix] was bgzip used to compress this file? please use bgzip"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class != "reference_not_bgzf"


# --- broader failure classes for common nf-core failures (contract D) ----------


def test_no_space_left_on_device_is_disk_full() -> None:
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)]
    log = "samtools sort: failed writing to tmp: No space left on device"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "disk_full"
    assert any("No space left" in e for e in d.evidence)


def test_enospc_is_disk_full() -> None:
    events = [TaskEvent(process="SORT", status="FAILED", exit=1)]
    log = "OSError: [Errno 28] ENOSPC: No space left"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "disk_full"


def test_failed_to_download_is_download_failed() -> None:
    events = [TaskEvent(process="STAGE", status="FAILED", exit=1)]
    log = "Failed to download https://example.org/ref.fa.gz after 3 attempts"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "download_failed"
    assert any("Failed to download" in e for e in d.evidence)


def test_connection_timed_out_while_staging_is_download_failed() -> None:
    events = [TaskEvent(process="STAGE", status="FAILED", exit=1)]
    log = "Unable to stage foreign file: connection timed out"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "download_failed"


def test_permission_denied_is_permission_denied() -> None:
    events = [TaskEvent(process="PUBLISH", status="FAILED", exit=1)]
    log = "mkdir: cannot create directory '/results': Permission denied"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "permission_denied"
    assert any("Permission denied" in e for e in d.evidence)


def test_eacces_is_permission_denied() -> None:
    events = [TaskEvent(process="PUBLISH", status="FAILED", exit=1)]
    log = "Error: EACCES: permission denied, open '/results/out.txt'"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "permission_denied"


def test_disk_full_not_misread_as_tool_crash() -> None:
    # ENOSPC is a clear resource problem; it must beat the generic tool_crash
    # fallback even though the task also exited nonzero.
    events = [TaskEvent(process="SORT", status="FAILED", exit=1)]
    log = "some noise\nNo space left on device\nmore noise"
    assert diagnose_failure(events, log_text=log).failure_class == "disk_full"


# --- pluggable detector registry (PRD contract C) ------------------------------


def test_registry_exposes_rules_detector_as_diagnose_failure() -> None:
    assert DETECTORS["rules"] is diagnose_failure


def test_registry_exposes_a_strict_detector() -> None:
    assert "rules-strict" in DETECTORS
    assert DETECTORS["rules-strict"] is diagnose_failure_strict


def test_get_detector_returns_the_named_callable() -> None:
    assert get_detector("rules") is diagnose_failure
    assert get_detector("rules-strict") is diagnose_failure_strict


def test_get_detector_unknown_name_raises_a_clear_error() -> None:
    with pytest.raises(KeyError) as excinfo:
        get_detector("does-not-exist")
    # the message names the bad detector and lists what is available
    assert "does-not-exist" in str(excinfo.value)
    assert "rules" in str(excinfo.value)


def test_a_detector_is_a_callable_returning_a_diagnosis() -> None:
    events = [TaskEvent(process="ALIGN", status="FAILED", exit=137)]
    for name, detector in DETECTORS.items():
        d = detector(events, "out of memory: killed")
        assert d.failure_class == "oom", name


# --- rules-strict: higher precision on weak evidence ---------------------------


def test_strict_agrees_with_rules_on_strong_oom_signal() -> None:
    # An exit-137 kill is unambiguous; strict keeps the confident classification.
    events = [TaskEvent(process="ALIGN", status="FAILED", exit=137)]
    log = "Process killed: out of memory (exit 137)"
    assert diagnose_failure_strict(events, log).failure_class == "oom"


def test_strict_demotes_platform_unsupported_to_tool_crash() -> None:
    # platform_unsupported is the detector's lowest-confidence specific guess
    # (it leans on a warning that shows up on healthy tasks too). Strict refuses
    # to name it and falls back to the unarguable fact: a task crashed.
    events = [TaskEvent(process="MAKE_TRANSCRIPTS_FASTA", status="FAILED", exit=None)]
    log = (
        "WARNING: The requested image's platform (linux/amd64) does not match the "
        "detected host platform (linux/arm64/v8) and no specific platform was requested\n"
        "Execution cancelled -- Finishing pending tasks before exit"
    )
    assert diagnose_failure(events, log).failure_class == "platform_unsupported"
    assert diagnose_failure_strict(events, log).failure_class == "tool_crash"


def test_strict_keeps_strong_conda_signal_but_drops_the_loose_heuristic() -> None:
    # The strong needle (ResolvePackageNotFound) is kept by strict.
    events = [TaskEvent(process="SETUP", status="FAILED", exit=1)]
    strong = "ResolvePackageNotFound:\n  - samtools=1.99"
    assert diagnose_failure_strict(events, strong).failure_class == "conda_solve_failed"
    # The loose "conda" + "solve" co-occurrence is weak evidence: rules guesses
    # conda_solve_failed, strict refuses and reports the bare crash instead.
    loose = "running conda activate base\ncould not solve the puzzle in this step"
    assert diagnose_failure(events, loose).failure_class == "conda_solve_failed"
    assert diagnose_failure_strict(events, loose).failure_class == "tool_crash"


def test_strict_keeps_unknown_when_no_task_failed() -> None:
    # No failing task and no signal: both detectors agree on unknown.
    assert diagnose_failure_strict([], "").failure_class == "unknown"
