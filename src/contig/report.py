"""Human-readable rendering of a RunRecord for the terminal.

The CLI calls render_run_report to turn a captured run into a report a
researcher can read at a glance: the verdict, what ran, and what was verified.
"""

from __future__ import annotations

from contig.models import RunRecord, RunSummary


def render_run_report(record: RunRecord) -> str:
    """Render a multi-line, terminal-friendly report of a run."""
    summary = RunSummary.from_events(record.events)
    lines = [
        f"VERDICT: {record.verdict.upper()}",
        f"Pipeline: {record.pipeline} (revision {record.pipeline_revision})",
        f"Tasks: {summary.total_tasks} ({summary.failed_tasks} failed)",
        f"Inputs: {len(record.input_checksums)} input files checksummed",
    ]
    if record.contig_version is not None:
        lines.append(f"Contig version: {record.contig_version}")
    if record.nextflow_version is not None:
        lines.append(f"Nextflow version: {record.nextflow_version}")
    if record.qc_results:
        lines.append("QC checks:")
        for qc in record.qc_results:
            lines.append(f"  - {qc.check}: {qc.status.upper()} (value {qc.value})")
    else:
        lines.append("QC checks: no QC checks ran (run is unverified).")
    if record.repair_history:
        lines.append("Repair history:")
        for step in record.repair_history:
            patch_kind = step.patch.kind if step.patch else "none"
            lines.append(
                f"  - attempt {step.attempt}: {step.diagnosis.failure_class} "
                f"→ {patch_kind} patch → {step.outcome}"
            )
    return "\n".join(lines)
