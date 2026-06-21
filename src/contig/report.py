"""Human-readable rendering of a RunRecord for the terminal.

The CLI calls render_run_report to turn a captured run into a report a
researcher can read at a glance: the verdict, what ran, and what was verified.
"""

from __future__ import annotations

from html import escape

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


_HTML_STYLE = """
  body { font-family: -apple-system, system-ui, sans-serif; margin: 2rem auto; max-width: 60rem;
         color: #1a1a1a; line-height: 1.5; }
  h1 { margin-bottom: 0.25rem; }
  .verdict { display: inline-block; padding: 0.4rem 1rem; border-radius: 0.4rem;
             font-weight: 700; font-size: 1.4rem; letter-spacing: 0.05em; }
  .verdict.pass { background: #e6f6e6; color: #1a7a1a; }
  .verdict.warn { background: #fff6e0; color: #8a6500; }
  .verdict.fail { background: #fce4e4; color: #a31515; }
  .verdict.unverified { background: #eee; color: #555; }
  h2 { border-bottom: 1px solid #ddd; padding-bottom: 0.25rem; margin-top: 2rem; }
  table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #eee; }
  th { background: #fafafa; }
  code, .mono { font-family: ui-monospace, monospace; font-size: 0.9rem; word-break: break-all; }
  .note { color: #555; font-style: italic; }
  .status-pass { color: #1a7a1a; }
  .status-warn { color: #8a6500; }
  .status-fail { color: #a31515; }
"""


def _provenance_rows(items: dict[str, object]) -> str:
    if not items:
        return '<tr><td colspan="2" class="note">none</td></tr>'
    rows = []
    for key, value in items.items():
        rows.append(
            f"<tr><td class=\"mono\">{escape(str(key))}</td>"
            f"<td class=\"mono\">{escape(str(value))}</td></tr>"
        )
    return "".join(rows)


def render_run_report_html(record: RunRecord) -> str:
    """Render a self-contained, shareable HTML report of a run.

    A single HTML document (no external resources, no JavaScript) carrying the
    verdict, QC table, repair chain, and pinned provenance. Hashes and metadata
    only: never raw reads. Any free text is escaped before it enters the markup.
    """
    summary = RunSummary.from_events(record.events)
    verdict = record.verdict
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head><meta charset="utf-8">')
    parts.append(f"<title>Contig run {escape(record.run_id)}</title>")
    parts.append(f"<style>{_HTML_STYLE}</style></head><body>")

    parts.append(f"<h1>Contig run report</h1>")
    parts.append(f'<p class="mono">Run id: {escape(record.run_id)}</p>')
    parts.append(
        f'<p><span class="verdict {escape(verdict)}">{escape(verdict.upper())}</span></p>'
    )
    parts.append(
        f"<p>Pipeline: <strong>{escape(record.pipeline)}</strong> "
        f"(revision {escape(record.pipeline_revision)})</p>"
    )
    parts.append(
        f"<p>Tasks: {summary.total_tasks} ({summary.failed_tasks} failed)</p>"
    )

    # QC table
    parts.append("<h2>QC checks</h2>")
    if record.qc_results:
        parts.append(
            "<table><thead><tr><th>Check</th><th>Status</th><th>Value</th>"
            "<th>Expected range</th><th>Message</th></tr></thead><tbody>"
        )
        for qc in record.qc_results:
            value = "" if qc.value is None else str(qc.value)
            expected = qc.expected_range or ""
            parts.append(
                f"<tr><td>{escape(qc.check)}</td>"
                f'<td class="status-{escape(qc.status)}">{escape(qc.status.upper())}</td>'
                f"<td class=\"mono\">{escape(value)}</td>"
                f"<td class=\"mono\">{escape(expected)}</td>"
                f"<td>{escape(qc.message)}</td></tr>"
            )
        parts.append("</tbody></table>")
    else:
        parts.append('<p class="note">No QC checks ran (run is unverified).</p>')

    # Repair chain
    parts.append("<h2>Repair chain</h2>")
    if record.repair_history:
        parts.append(
            "<table><thead><tr><th>Attempt</th><th>Failure class</th>"
            "<th>What was patched</th><th>Outcome</th></tr></thead><tbody>"
        )
        for step in record.repair_history:
            patched = step.patch.kind if step.patch else "none"
            parts.append(
                f"<tr><td>{step.attempt}</td>"
                f"<td>{escape(step.diagnosis.failure_class)}</td>"
                f"<td>{escape(patched)}</td>"
                f"<td>{escape(step.outcome)}</td></tr>"
            )
        parts.append("</tbody></table>")
    else:
        parts.append('<p class="note">No repairs were needed for this run.</p>')

    # Provenance
    parts.append("<h2>Provenance</h2>")
    versions: dict[str, object] = {}
    if record.contig_version is not None:
        versions["contig"] = record.contig_version
    if record.nextflow_version is not None:
        versions["nextflow"] = record.nextflow_version
    parts.append("<h3>Versions</h3>")
    parts.append(f"<table><tbody>{_provenance_rows(versions)}</tbody></table>")
    parts.append("<h3>Parameters</h3>")
    parts.append(f"<table><tbody>{_provenance_rows(record.parameters)}</tbody></table>")
    parts.append("<h3>Container digests</h3>")
    parts.append(f"<table><tbody>{_provenance_rows(record.container_digests)}</tbody></table>")
    parts.append("<h3>Input checksums</h3>")
    parts.append(f"<table><tbody>{_provenance_rows(record.input_checksums)}</tbody></table>")
    parts.append("<h3>Output checksums</h3>")
    parts.append(f"<table><tbody>{_provenance_rows(record.output_checksums)}</tbody></table>")

    parts.append("</body></html>")
    return "".join(parts)
