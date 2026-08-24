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


# --- stale single-file index: OLDER than the data it indexes (htslib) ---------


def test_stale_bai_index_is_missing_index() -> None:
    # htslib refuses an index that is OLDER than the data it indexes
    # (hts_idx_load3). The message carries no absence phrase ("not found"/
    # "missing"), so the generic branch below misses it and it would fall to
    # tool_crash; the freshness branch must catch it.
    events = [TaskEvent(process="SAMTOOLS", status="FAILED", exit=1)]
    log = "[E::hts_idx_load3] The index file is older than the data file: /ref/aln.bam.bai"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert any(".bai" in e for e in d.evidence)


def test_stale_fai_tbi_csi_indexes_classify() -> None:
    # One stale line per supported single-file kind must classify the same way.
    events = [TaskEvent(process="SAMTOOLS", status="FAILED", exit=1)]
    for line in (
        "[E::fai_load] The index file is older than the FASTA file: ref.fa.fai",
        "[E::hts_idx_load3] The index file is older than the data file: calls.vcf.gz.tbi",
        "[E::hts_idx_load3] The index file is older than the data file: calls.vcf.gz.csi",
    ):
        d = diagnose_failure(events, log_text=line)
        assert d.failure_class == "missing_index", line


def test_stale_absent_index_phrasing_still_generic() -> None:
    # An absence-phrased line (no freshness wording) must STILL classify via the
    # generic branch, root_cause unchanged -- the stale branch must not steal it.
    events = [TaskEvent(process="SAMTOOLS", status="FAILED", exit=1)]
    log = 'samtools index: failed to open "aln.bam.bai": No such file or directory'
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert d.root_cause == "A required index file is missing."


def test_mixed_missing_or_older_classifies_stale() -> None:
    # A line carrying BOTH absence and freshness wording must classify
    # STALE-first: the freshness branch is ordered before the generic one, and
    # the rebuild+replace repair covers both flavors.
    events = [TaskEvent(process="SAMTOOLS", status="FAILED", exit=1)]
    log = (
        "[E::hts_idx_load3] The index file is missing or older than the "
        "data file: /ref/aln.bam.bai"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"
    assert d.root_cause == "An index file is older than the data it indexes."


def test_benign_older_than_mention_is_not_missing_index() -> None:
    # The AND-guard must hold: "older than" alone is not enough. A line with no
    # index token and no "index file" wording must fall through, never
    # missing_index.
    events = [TaskEvent(process="PREPARE_GENOME", status="FAILED", exit=1)]
    log = "the reference was updated, so this sample sheet is older than the expected revision"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class != "missing_index"


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
    # GATK's "incompatible contigs" wording is the DELIBERATELY EXCLUDED control
    # for the reference_mismatch branch: it lacks the contig-absence phrase, so
    # the tight family leaves it as an unrecognized crash.
    assert d.failure_class == "tool_crash"


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


def test_contig_not_found_in_reference_dictionary_is_reference_mismatch() -> None:
    # A contig absent from the reference (wrong-genome/build signature) is its
    # own class now; it must still never be swallowed by the missing-index
    # family (the dictionary line names a reference file, not an absent index).
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)]
    log = "ERROR: Contig 'chr1' not found in the reference dictionary /work/ref/genome.fasta"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "reference_mismatch"
    assert d.confidence == 0.85
    assert log in d.evidence
    assert d.failure_class != "missing_index"


def test_star_sequence_not_found_in_reference_genome_is_reference_mismatch() -> None:
    # STAR's hard-fail wording for reads carrying a contig absent from the
    # reference FASTA -- the canonical wrong-genome/build signature.
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)]
    log = (
        "EXITING because of FATAL ERROR: sequence 'chr1' not found in the "
        "reference genome /work/ref/genome.fasta"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "reference_mismatch"
    assert d.confidence == 0.85
    assert d.evidence


def test_reference_phrase_without_contig_token_is_not_reference_mismatch() -> None:
    # The AND-guard is load-bearing: "not found in the reference" WITHOUT a
    # contig/sequence token is a different problem and must stay an unrecognized
    # crash, never be stolen by the reference_mismatch family.
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)]
    log = "WARNING: reads not found in the reference; skipping"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "tool_crash"


def test_missing_reference_log_is_not_stolen_by_reference_mismatch() -> None:
    # A genuinely absent reference file ("no such file or directory" + .fasta
    # token) keeps its own class; the contig-absence phrase is absent.
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=1)]
    log = (
        "samtools faidx: failed to open /work/ref/genome.fasta: No such file "
        "or directory"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_reference"


def test_missing_index_log_is_not_stolen_by_reference_mismatch() -> None:
    # An absent index keeps the missing_index family; the contig-absence phrase
    # is absent, so the reference_mismatch branch must not fire.
    events = [TaskEvent(process="BWA_MEM", status="FAILED", exit=1)]
    log = "[E::bwa_idx_load_from_disk] fail to locate the index files"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "missing_index"


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


# --- CRAM decode failures: alignment format mismatch (C2) ----------------------


def test_cram_decode_slice_without_reference_is_alignment_format_mismatch() -> None:
    # samtools view on a CRAM input fails at decode time when htslib has no
    # reference FASTA for CRAM->BAM conversion. Distinct and actionable
    # (supply the reference / point at the right CRAM), not an opaque crash.
    events = [TaskEvent(process="SAMTOOLS_VIEW", status="FAILED", exit=1)]
    log = (
        "[E::cram_decode_slice] No reference file specified for CRAM decoding\n"
        "samtools view failed on /work/aln.cram"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "alignment_format_mismatch"
    assert d.confidence == 0.85
    assert "CRAM" in d.root_cause.upper()
    assert any("cram_decode_slice" in e.lower() for e in d.evidence)


def test_cram_decode_line_that_also_says_reference_not_found_is_alignment_format_mismatch() -> None:
    # The absence phrase ("reference not found") shares a line with the decode
    # error. The CRAM branch's AND-guard must beat the missing_index absence
    # needles (which require an index token on the line) and must not fall
    # through to tool_crash.
    events = [TaskEvent(process="SAMTOOLS_VIEW", status="FAILED", exit=1)]
    log = (
        "samtools view: [E::cram_decode_slice] Reference file is required for "
        "CRAM decoding: reference not found for /data/aln.cram"
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "alignment_format_mismatch"


def test_bare_cram_filename_without_decode_phrase_is_tool_crash() -> None:
    # The branch must not fire on the bare token "cram" inside a filename; only
    # a CRAM decode-failure phrase triggers it. Without one, this stays an
    # unrecognized crash.
    events = [TaskEvent(process="SAMTOOLS_VIEW", status="FAILED", exit=1)]
    log = "Error processing /data/aln.cram: invalid argument"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "tool_crash"


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


# --- no_progress: stall watchdog termination (D6) -------------------------------


def test_stall_watchdog_message_is_no_progress() -> None:
    # Our own emitted sentinel (stall.py:stall_message) must classify as
    # no_progress. No events: the watchdog kills the run out-of-band, before
    # Nextflow itself ever reports a task failure.
    from contig.stall import stall_message

    log = stall_message(
        idle_sec=1800.0, timeout_sec=1800.0, silent_surfaces=("trace.txt", ".nextflow.log", "run.log")
    )
    d = diagnose_failure([], log_text=log)
    assert d.failure_class == "no_progress"


def test_genuine_oom_exit_137_with_no_stall_text_is_still_oom() -> None:
    # A5: no_progress must not shadow a real OOM. Exit 137, no stall wording.
    events = [TaskEvent(process="ALIGN", status="FAILED", exit=137)]
    d = diagnose_failure(events, log_text="process terminated")
    assert d.failure_class == "oom"


def test_genuine_oom_by_text_with_no_stall_text_is_still_oom() -> None:
    # A5: same, but OOM is signalled by log text rather than the exit code.
    events = [TaskEvent(process="ASSEMBLE", status="FAILED", exit=1)]
    log = "java.lang.OutOfMemoryError: Java heap space"
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "oom"


def test_stall_message_with_incidental_exit_137_is_still_no_progress() -> None:
    # D6: a dying Nextflow can write a trace row with exit 137 as it is torn
    # down by the watchdog's SIGTERM/SIGKILL ladder. The first-party stall
    # verdict must still win over that incidental exit code.
    from contig.stall import stall_message

    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=137)]
    log = stall_message(
        idle_sec=1800.0, timeout_sec=1800.0, silent_surfaces=("trace.txt", ".nextflow.log", "run.log")
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "no_progress"


def test_strict_leaves_no_progress_undemoted() -> None:
    # no_progress is a high-confidence, first-party signal (0.9), not one of the
    # two weak-evidence guesses strict steps back from; it must pass through.
    from contig.stall import stall_message

    log = stall_message(
        idle_sec=1800.0, timeout_sec=1800.0, silent_surfaces=("trace.txt", ".nextflow.log", "run.log")
    )
    assert diagnose_failure_strict([], log_text=log).failure_class == "no_progress"


def test_holdout_no_progress_fixture_classifies_as_no_progress() -> None:
    # Verbatim log_text from src/contig/data/detector_corpus_holdout.jsonl,
    # case_id "holdout-no-progress-1" (third-party wording, not ours) -- proves
    # the needles are phrase-level, not fitted to stall.py's exact string. It
    # matches on "no new output or trace update" and "no forward progress",
    # BOTH of which it happens to share verbatim with our own message: the
    # generalization is real, and it comes from our phrasing being ordinary
    # English rather than from a needle written to catch this fixture.
    events = [TaskEvent(process="STAR_ALIGN", status="FAILED", exit=None)]
    log = (
        "Task produced no new output or trace update for 6 hours; the progress "
        "monitor terminated it as stalled (no forward progress)."
    )
    d = diagnose_failure(events, log_text=log)
    assert d.failure_class == "no_progress"


def test_every_no_progress_needle_is_one_the_watchdog_actually_emits() -> None:
    # The needle tuple widens a branch that sits ABOVE the unconditional OOM
    # check, so every phrase in it is false-positive surface charged against
    # every diagnosis Contig ever makes. A needle our own message does not emit
    # buys nothing to pay for that: it can only ever match somebody else's text.
    # (One such needle, "terminated it as stalled", was carried for a while on
    # the belief that the held-out fixture needed it. It did not -- the fixture
    # hits two other needles verbatim -- so it was dropped.)
    from contig.detect import _NO_PROGRESS_NEEDLES
    from contig.stall import stall_message

    emitted = stall_message(
        idle_sec=5400.0,
        timeout_sec=3600.0,
        silent_surfaces=("trace.txt", ".nextflow.log", "run.log"),
    ).lower()

    unsourced = [n for n in _NO_PROGRESS_NEEDLES if n not in emitted]
    assert not unsourced, (
        f"needles the watchdog never emits, so they only match third-party text: {unsourced}"
    )


def test_every_shipped_no_progress_fixture_still_classifies() -> None:
    # The safety net for narrowing the tuple: every no_progress text this repo
    # ships -- the training corpus case, the frozen held-out case, and the
    # heal-guard scenario -- has to keep classifying. eval-guard and heal-guard
    # would both catch a regression here, but only at guard time; this fails in
    # the unit suite, next to the tuple being edited.
    import json
    from pathlib import Path

    data_dir = Path(__file__).resolve().parents[1] / "src" / "contig" / "data"
    texts: dict[str, str] = {}
    for name in ("detector_corpus.jsonl", "detector_corpus_holdout.jsonl"):
        for line in (data_dir / name).read_text().splitlines():
            case = json.loads(line)
            if case.get("expected_class") == "no_progress":
                texts[case["case_id"]] = case["log_text"]
    for line in (data_dir / "heal_scenarios.jsonl").read_text().splitlines():
        scenario = json.loads(line)
        if scenario.get("expected_class") == "no_progress":
            texts[scenario["scenario_id"]] = scenario["attempts"][0]["log_text"]

    assert len(texts) >= 3, f"expected the three shipped no_progress texts, found {list(texts)}"
    for case_id, log in texts.items():
        assert diagnose_failure([], log_text=log).failure_class == "no_progress", case_id
