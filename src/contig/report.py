"""Human-readable rendering of a RunRecord for the terminal.

The CLI calls render_run_report to turn a captured run into a report a
researcher can read at a glance: the verdict, what ran, and what was verified.
"""

from __future__ import annotations

from html import escape

from pydantic import BaseModel

from contig.models import QCResult, RunRecord, RunSummary, overall_verdict


class VerdictExplanation(BaseModel):
    """Why a run earned its recorded verdict (PRD contract E).

    Presentation only: it explains the verdict models.py already computed, never
    re-derives trust. `deciding_checks` are the QC checks whose status equals the
    overall verdict (empty for a fail forced by an incomplete run).
    """

    verdict: str
    reason: str
    deciding_checks: list[QCResult] = []


def explain_verdict(record: RunRecord) -> VerdictExplanation:
    """Explain a run's recorded verdict, mirroring models.py exactly.

    A run that did not complete is a fail regardless of QC; a completed run with
    no QC is unverified; otherwise the QC verdict (fail over warn over pass) holds
    and the deciding checks are those sharing that status.
    """
    summary = RunSummary.from_events(record.events)
    if not summary.succeeded:
        return VerdictExplanation(
            verdict="fail",
            reason=f"Run did not complete: {summary.failed_tasks} task(s) failed",
            deciding_checks=[],
        )
    if not record.qc_results:
        return VerdictExplanation(
            verdict="unverified",
            reason="No QC check covered this run",
            deciding_checks=[],
        )
    overall = overall_verdict(record.qc_results)
    deciding = [qc for qc in record.qc_results if qc.status == overall]
    return VerdictExplanation(
        verdict=overall,
        reason=_explain_reason(overall, deciding, len(record.qc_results)),
        deciding_checks=deciding,
    )


def _explain_reason(overall: str, deciding: list[QCResult], total: int) -> str:
    """A one-line reason naming the lowest-valued deciding check and its threshold."""
    headline = f"{overall.upper()}: {len(deciding)} of {total} checks flagged"
    valued = [qc for qc in deciding if qc.value is not None]
    if not valued:
        return headline
    lowest = min(valued, key=lambda qc: qc.value)
    threshold = f" vs {lowest.expected_range}" if lowest.expected_range else ""
    return f"{headline} (lowest: {lowest.check} {lowest.value}{threshold})"


def render_explain(record: RunRecord) -> str:
    """Render the verdict explanation as a terminal-friendly block."""
    explanation = explain_verdict(record)
    lines = [
        f"VERDICT: {explanation.verdict.upper()}",
        explanation.reason,
    ]
    if explanation.deciding_checks:
        lines.append("Decided by:")
        for qc in explanation.deciding_checks:
            value = "" if qc.value is None else str(qc.value)
            threshold = f" (expected {qc.expected_range})" if qc.expected_range else ""
            lines.append(f"  - {qc.check}: {qc.status.upper()} {value}{threshold}")
    return "\n".join(lines)


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
        # Concordance (cross-tool corroboration) is named in its own section so
        # a reader can tell agreement between tools apart from a file's own checks.
        concordance = [qc for qc in record.qc_results if qc.kind == "concordance"]
        primary = [qc for qc in record.qc_results if qc.kind != "concordance"]
        lines.append("QC checks:")
        for qc in primary:
            lines.append(f"  - {qc.check}: {qc.status.upper()} (value {qc.value})")
        if concordance:
            lines.append("Concordance (cross-tool corroboration):")
            for qc in concordance:
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
  :root { --ink: #1a1a1a; --muted: #555; --line: #e3e3e3; --rule: #ddd;
          --pass: #1a7a1a; --warn: #8a6500; --fail: #a31515; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, system-ui, "Segoe UI", sans-serif;
         margin: 2.5rem auto; max-width: 62rem; padding: 0 1.5rem;
         color: var(--ink); line-height: 1.55; }
  header.report-head { border-bottom: 2px solid var(--ink); padding-bottom: 1rem;
                       margin-bottom: 1.5rem; }
  h1 { margin: 0 0 0.25rem; font-size: 1.6rem; }
  .subtitle { color: var(--muted); margin: 0; }
  .verdict-row { display: flex; align-items: center; gap: 1rem; margin: 1rem 0 0.25rem; flex-wrap: wrap; }
  .verdict { display: inline-block; padding: 0.4rem 1.1rem; border-radius: 0.4rem;
             font-weight: 700; font-size: 1.3rem; letter-spacing: 0.05em; }
  .verdict.pass { background: #e6f6e6; color: var(--pass); }
  .verdict.warn { background: #fff6e0; color: var(--warn); }
  .verdict.fail { background: #fce4e4; color: var(--fail); }
  .verdict.unverified { background: #eee; color: var(--muted); }
  .badge { display: inline-block; padding: 0.25rem 0.7rem; border-radius: 1rem;
           font-size: 0.85rem; font-weight: 600; }
  .badge.signed-ok { background: #e6f0fb; color: #14457a; }
  .badge.signed-bad { background: #fce4e4; color: var(--fail); }
  h2 { border-bottom: 1px solid var(--rule); padding-bottom: 0.3rem;
       margin: 2.2rem 0 0.5rem; font-size: 1.2rem; }
  h3 { margin: 1.2rem 0 0.25rem; font-size: 1rem; color: var(--muted); }
  table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; font-size: 0.95rem; }
  th, td { text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--line);
           vertical-align: top; }
  th { background: #fafafa; font-weight: 600; }
  caption { text-align: left; color: var(--muted); font-size: 0.9rem;
            padding: 0.3rem 0; caption-side: top; }
  code, .mono { font-family: ui-monospace, "SF Mono", monospace; font-size: 0.88rem;
                word-break: break-all; }
  .note { color: var(--muted); font-style: italic; }
  .status-pass { color: var(--pass); font-weight: 600; }
  .status-warn { color: var(--warn); font-weight: 600; }
  .status-fail { color: var(--fail); font-weight: 600; }
  .status-unverified { color: var(--muted); font-weight: 600; }
  footer.report-foot { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--rule);
                       color: var(--muted); font-size: 0.85rem; }
  @media print {
    body { margin: 0; max-width: none; padding: 0; font-size: 11pt; color: #000; }
    header.report-head { border-bottom-color: #000; }
    h2 { break-after: avoid; }
    table { break-inside: auto; }
    tr { break-inside: avoid; }
    .verdict, .badge { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    a[href]:after { content: ""; }
  }
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


def _qc_table(rows: list[QCResult]) -> str:
    """Render a QC result table; the caller has already grouped by kind."""
    parts = [
        "<table><thead><tr><th>Check</th><th>Status</th><th>Value</th>"
        "<th>Expected range</th><th>Message</th></tr></thead><tbody>"
    ]
    for qc in rows:
        value = "" if qc.value is None else str(qc.value)
        expected = qc.expected_range or ""
        parts.append(
            f"<tr><td>{escape(qc.check)}</td>"
            f'<td class="status-{escape(qc.status)}">{escape(qc.status.upper())}</td>'
            f'<td class="mono">{escape(value)}</td>'
            f'<td class="mono">{escape(expected)}</td>'
            f"<td>{escape(qc.message)}</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def _signature_badge(signature_status: dict | None) -> str:
    """A small badge near the verdict: signed and verified, or signed but unverified."""
    if not signature_status or not signature_status.get("signed"):
        return ""
    if signature_status.get("signature_ok"):
        return '<span class="badge signed-ok">signed, signature verified</span>'
    return '<span class="badge signed-bad">signed, signature NOT verified</span>'


def render_run_report_html(
    record: RunRecord, signature_status: dict | None = None
) -> str:
    """Render a polished, self-contained, print-to-PDF-friendly HTML report.

    A single HTML document (no external resources, no JavaScript) carrying the
    verdict, the QC results grouped into metric and structural checks, the repair
    chain, the pinned provenance, and the signature status when one is supplied.
    Hashes and metadata only: never raw reads. Any free text is escaped before it
    enters the markup. The print CSS (`@media print`) makes a browser Save-as-PDF
    yield a clean one-document report.

    `signature_status` is the optional dict the CLI/dashboard pass after checking
    signature.json: {signed, signature_ok, public_key, algo}. When absent, the
    report makes no signature claim.
    """
    summary = RunSummary.from_events(record.events)
    verdict = record.verdict
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append(f"<title>Contig run {escape(record.run_id)}</title>")
    parts.append(f"<style>{_HTML_STYLE}</style></head><body>")

    parts.append('<header class="report-head">')
    parts.append("<h1>Contig run report</h1>")
    parts.append(
        f'<p class="subtitle mono">Run id: {escape(record.run_id)}</p>'
    )
    parts.append('<div class="verdict-row">')
    parts.append(
        f'<span class="verdict {escape(verdict)}">{escape(verdict.upper())}</span>'
    )
    badge = _signature_badge(signature_status)
    if badge:
        parts.append(badge)
    parts.append("</div>")
    parts.append(
        f"<p>Pipeline: <strong>{escape(record.pipeline)}</strong> "
        f"(revision {escape(record.pipeline_revision)})</p>"
    )
    parts.append(
        f"<p>Tasks: {summary.total_tasks} ({summary.failed_tasks} failed)</p>"
    )
    parts.append("</header>")

    # QC, grouped into metric (content) and structural (integrity) checks so a
    # reader can tell "the file is there and intact" apart from "the numbers pass".
    parts.append("<h2>QC checks</h2>")
    if record.qc_results:
        metric = [qc for qc in record.qc_results if qc.kind == "metric"]
        structural = [qc for qc in record.qc_results if qc.kind == "structural"]
        if metric:
            parts.append("<h3>Metric checks</h3>")
            parts.append(_qc_table(metric))
        if structural:
            parts.append("<h3>Structural and integrity checks</h3>")
            parts.append(_qc_table(structural))
        # Concordance (cross-tool corroboration) is grouped apart from the
        # metric and structural checks: it answers "does an independent tool
        # agree?", not "does this file pass its own rule pack".
        concordance = [qc for qc in record.qc_results if qc.kind == "concordance"]
        if concordance:
            parts.append("<h3>Concordance (cross-tool corroboration)</h3>")
            parts.append(_qc_table(concordance))
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

    # Reference identity — genome used by the run, with provenance.
    if record.reference_identity is not None:
        ri = record.reference_identity
        parts.append("<h3>Reference identity</h3>")
        ri_rows: dict[str, object] = {"mode": ri.mode}
        if ri.mode == "igenomes":
            if ri.genome is not None:
                ri_rows["genome"] = ri.genome
            ri_rows["checksums"] = "downloaded by pipeline"
        else:  # explicit
            if ri.fasta is not None:
                ri_rows["fasta"] = ri.fasta
            if ri.gtf is not None:
                ri_rows["gtf"] = ri.gtf
            if ri.fasta_sha256 is not None:
                ri_rows["fasta sha256"] = ri.fasta_sha256
            if ri.gtf_sha256 is not None:
                ri_rows["gtf sha256"] = ri.gtf_sha256
            if ri.annotation_version is not None:
                ri_rows["annotation version"] = ri.annotation_version
        parts.append(f"<table><tbody>{_provenance_rows(ri_rows)}</tbody></table>")

    # Annotation identity — the annotator(s) (VEP/SnpEff) that produced the
    # annotated VCF (capability C7). M4 enables both on the variant assays, so
    # this is a list; each entry gets its own row. Defensive against a raw
    # single-object shape (the pre-M4 legacy serialization) in case this field
    # is ever read before the model validator has normalized it.
    annotation_identity = record.annotation_identity
    if annotation_identity is not None and not isinstance(annotation_identity, list):
        annotation_identity = [annotation_identity]
    if annotation_identity:
        parts.append("<h3>Annotation identity</h3>")
        ann_rows: dict[str, object] = {
            ai.tool: (ai.version or "unknown") for ai in annotation_identity
        }
        parts.append(f"<table><tbody>{_provenance_rows(ann_rows)}</tbody></table>")

    # Signature provenance (the key and algorithm the verdict was signed under).
    if signature_status and signature_status.get("signed"):
        parts.append("<h2>Signature</h2>")
        sig_rows: dict[str, object] = {
            "algorithm": signature_status.get("algo", "ed25519"),
            "public key": signature_status.get("public_key", ""),
            "status": (
                "verified" if signature_status.get("signature_ok") else "NOT verified"
            ),
        }
        parts.append(f"<table><tbody>{_provenance_rows(sig_rows)}</tbody></table>")

    parts.append(
        '<footer class="report-foot">Generated by Contig. '
        "Hashes and metadata only; no raw sequence data is included.</footer>"
    )
    parts.append("</body></html>")
    return "".join(parts)
