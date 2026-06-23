---
name: Failure case (corpus contribution)
about: A real pipeline failure Contig should detect and recover from. The highest-leverage contribution.
title: "[failure] "
labels: failure-case
---

A real run that broke is the most valuable thing you can share: it grows the
failure corpus that makes the detector better. See
docs/USAGE.md (the failure-corpus section) and `contig corpus-promote`.

## What failed

<!-- The pipeline, assay, and backend (e.g. nf-core/rnaseq on slurm). The task or step that broke. -->

## The error

<!-- The relevant log lines or .command.err. Redact any paths or identifiers you do not want public. -->

## True failure class

<!-- Which of the failure classes fits (oom, time_limit, missing_reference, missing_index,
bad_param, container_pull_failed, container_unavailable, conda_solve_failed,
platform_unsupported, disk_full, download_failed, permission_denied, tool_crash,
no_progress, qc_anomaly, unknown), or "not sure". -->

## What did Contig diagnose / do (if you ran it)

<!-- The diagnosis and any self-heal attempt, or "did not run it on this yet". -->

## The fix (if known)

<!-- What actually resolved it, so we can encode the recovery. -->
