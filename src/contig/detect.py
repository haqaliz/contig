"""Rule-based failure detection for a FAILED run (ARCHITECTURE §5.1).

`diagnose_failure` classifies a failed Nextflow run from its terminal task
events plus the captured error-log text. Rules are matched in priority order;
the first match wins. The result is a structured `Diagnosis` carrying the
matching evidence and a confidence the self-healing loop can act on.
"""

from __future__ import annotations

from contig.models import Diagnosis, TaskEvent


def _matching_lines(log_text: str, needles: tuple[str, ...]) -> list[str]:
    """Log lines (original-case) containing any needle, matched case-insensitively."""
    hits = []
    for line in log_text.splitlines():
        low = line.lower()
        if any(n in low for n in needles):
            hits.append(line.strip())
    return hits


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    """True if any needle appears in text, matched case-insensitively."""
    low = text.lower()
    return any(n in low for n in needles)


def diagnose_failure(events: list[TaskEvent], log_text: str) -> Diagnosis:
    # OOM wins outright: an exit-137 kill is unambiguous even if the log also
    # carries a generic error, so it is checked before any log-text rule.
    oom_exit = any(e.exit == 137 for e in events)
    oom_lines = _matching_lines(
        log_text, ("out of memory", "outofmemoryerror", "killed", "oom")
    )
    if oom_exit or oom_lines:
        evidence = (["exit 137"] if oom_exit else []) + oom_lines
        return Diagnosis(
            failure_class="oom",
            root_cause="Process ran out of memory.",
            evidence=evidence,
            confidence=0.9,
        )

    time_lines = _matching_lines(
        log_text, ("due to time limit", "term_runlimit", "time limit")
    )
    if time_lines:
        return Diagnosis(
            failure_class="time_limit",
            root_cause="Run exceeded its wall-clock time limit.",
            evidence=time_lines,
            confidence=0.9,
        )

    unavailable_lines = _matching_lines(
        log_text,
        (
            "docker desktop is unable to start",
            "cannot connect to the docker daemon",
            "docker.sock",
        ),
    )
    if unavailable_lines:
        return Diagnosis(
            failure_class="container_unavailable",
            root_cause="Container runtime (Docker daemon) is not available.",
            evidence=unavailable_lines,
            confidence=0.9,
        )

    pull_lines = _matching_lines(
        log_text,
        (
            "failed to pull",
            "manifest unknown",
            "pull access denied",
            "error response from daemon: pull",
        ),
    )
    if pull_lines:
        return Diagnosis(
            failure_class="container_pull_failed",
            root_cause="Container image could not be pulled.",
            evidence=pull_lines,
            confidence=0.9,
        )

    conda_lines = _matching_lines(
        log_text, ("resolvepackagenotfound", "packagesnotfounderror")
    )
    low = log_text.lower()
    if "conda" in low and "solve" in low:
        conda_lines = conda_lines or _matching_lines(log_text, ("conda", "solve"))
    if conda_lines:
        return Diagnosis(
            failure_class="conda_solve_failed",
            root_cause="Conda environment could not be solved.",
            evidence=conda_lines,
            confidence=0.9,
        )

    notfound_lines = _matching_lines(
        log_text, ("not found", "missing", "no such file")
    )
    # Require the index/.fai to appear ON a "not found"/"missing"/"no such file"
    # line. A bare .fai mention is noise - e.g. `samtools faidx` naming its own
    # successful output genome.fasta.fai - and must not trigger missing_index.
    index_lines = [
        line
        for line in notfound_lines
        if ("index" in line.lower() or _has_any(line, (".fai", ".bai", ".tbi", ".csi")))
    ]
    if index_lines:
        return Diagnosis(
            failure_class="missing_index",
            root_cause="A required index file is missing.",
            evidence=index_lines,
            confidence=0.85,
        )

    nosuchfile_lines = _matching_lines(log_text, ("no such file or directory",))
    ref_tokens = (".fasta", ".fa", ".gtf", ".gff", "reference", "genome")
    ref_lines = [line for line in nosuchfile_lines if _has_any(line, ref_tokens)]
    if ref_lines:
        return Diagnosis(
            failure_class="missing_reference",
            root_cause="A required reference file is missing.",
            evidence=ref_lines,
            confidence=0.85,
        )

    param_lines = _matching_lines(
        log_text,
        (
            "unknown option",
            "unrecognized arguments",
            "unexpected argument",
            "is not a valid parameter",
        ),
    )
    if param_lines:
        return Diagnosis(
            failure_class="bad_param",
            root_cause="A pipeline parameter or tool option is invalid.",
            evidence=param_lines,
            confidence=0.85,
        )

    # Apple-Silicon-style architecture mismatch: nf-core's amd64-only containers
    # run under emulation, and a step gets KILLED (no exit code). The platform
    # warning alone is noise - it appears on healthy tasks too - so we require it
    # together with a killed (exit-less) failure.
    platform_lines = _matching_lines(
        log_text,
        (
            "does not match the detected host platform",
            "requested image's platform",
            "no matching manifest for",
        ),
    )
    if platform_lines and any(e.is_failure and e.exit is None for e in events):
        return Diagnosis(
            failure_class="platform_unsupported",
            root_cause=(
                "A pipeline step's container has no image for this host's CPU "
                "architecture; it ran under emulation and was killed."
            ),
            evidence=platform_lines,
            confidence=0.7,
        )

    # No specific signal matched. If a task did fail, the tool itself crashed
    # for a reason we could not classify; otherwise we have nothing to go on.
    if any(e.is_failure for e in events):
        crash_lines = [
            line for line in log_text.splitlines() if line.strip()
        ][-1:]
        return Diagnosis(
            failure_class="tool_crash",
            root_cause="A task failed with an unrecognized error.",
            evidence=crash_lines,
            confidence=0.4,
        )

    return Diagnosis(
        failure_class="unknown",
        root_cause="No matching failure signal.",
        confidence=0.2,
    )
