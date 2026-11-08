"""Self-contained HTML renderer for the research report."""

from __future__ import annotations

import html
from typing import Any

from contig.methods import render_methods
from contig.models import RunRecord
from contig.reporting.models import ReportInput, ReportSpec
from contig.reporting.summaries import (
    qc_summary,
    readiness_summary,
    variant_summary,
    verdict_label,
)

TEMPLATE_SECTIONS = {
    "publication": [
        "summary", "verdict", "methods", "qc", "variants", "readiness",
        "provenance", "limitations", "reviewer",
    ],
    "internal": [
        "summary", "verdict", "methods", "qc", "repairs", "variants",
        "readiness", "provenance", "notes", "limitations", "reviewer",
    ],
    "audit": [
        "verdict", "qc", "repairs", "provenance", "limitations", "reviewer",
    ],
}

VERDICT_CLASS = {
    "pass": "pass",
    "warn": "warn",
    "fail": "fail",
    "unverified": "unverified",
}


def esc(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _table(headers: list[str], rows: list[list[object]], *, klass: str = "") -> str:
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(_fmt(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    class_attr = f' class="{esc(klass)}"' if klass else ""
    return f"<table{class_attr}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _section(title: str, body: str) -> str:
    return f"<section><h2>{esc(title)}</h2>{body}</section>"


def _header(record: RunRecord, spec: ReportSpec) -> str:
    title = spec.title or f"Research report: {record.run_id}"
    subtitle = spec.subtitle or f"{record.pipeline} @ {record.pipeline_revision}"
    meta = [f"Run <code>{esc(record.run_id)}</code>"]
    if spec.author:
        meta.append(f"Author: {esc(spec.author)}")
    if spec.institution:
        meta.append(esc(spec.institution))
    return (
        "<header>"
        f"<h1>{esc(title)}</h1>"
        f"<p class=\"subtitle\">{esc(subtitle)}</p>"
        f"<p class=\"muted\">{' · '.join(meta)}</p>"
        "</header>"
    )


def _banner() -> str:
    return (
        '<div class="banner"><strong>Research use only.</strong> This report is '
        "not a clinical report, diagnosis, or treatment recommendation. "
        "ClinVar values are what ClinVar reported, not a Contig classification."
        "</div>"
    )


def _banner() -> str:
    return (
        '<div class="banner"><strong>Research use only.</strong> This report is '
        "not a clinical report, diagnosis, or treatment recommendation. "
        "ClinVar values are what ClinVar reported, not a Contig classification."
        "</div>"
    )


def _compatibility_warnings(warnings: list[str] | None) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{esc(warning)}</li>" for warning in warnings)
    return (
        '<div class="warnings"><strong>Compatibility warnings.</strong>'
        f"<ul>{items}</ul></div>"
    )


def _summary(record: RunRecord, spec: ReportSpec) -> str:
    text = spec.summary or (
        f"Run {record.run_id} from {record.pipeline} "
        f"({record.pipeline_revision})."
    )
    return _section("Summary", f"<p>{esc(text)}</p>")


def _verdict(record: RunRecord) -> str:
    verdict = record.verdict
    summary = qc_summary(record)
    deciding = summary["deciding"]
    if deciding:
        deciding_text = "Deciding checks: " + ", ".join(deciding)
    else:
        deciding_text = "No warn/fail check drove the verdict."
    return _section(
        "Verdict",
        f'<p><span class="badge {VERDICT_CLASS.get(verdict, "")}">{esc(verdict_label(verdict))}</span></p>'
        f"<p>{esc(deciding_text)}</p>",
    )


def _methods(record: RunRecord) -> str:
    return _section("Methods", f"<p>{esc(render_methods(record))}</p>")


def _qc(record: RunRecord) -> str:
    rows = [
        [result.check, result.status, result.value, result.expected_range, result.message]
        for result in record.qc_results
    ]
    if not rows:
        return _section("QC checks", '<p class="muted">No QC checks were recorded.</p>')
    return _section(
        "QC checks",
        _table(["Check", "Status", "Value", "Expected", "Message"], rows, klass="compact"),
    )


def _repairs(record: RunRecord) -> str:
    rows = []
    for step in record.repair_history:
        rows.append([
            step.attempt,
            step.diagnosis.failure_class,
            step.diagnosis.root_cause,
            step.outcome,
            step.patch.kind if step.patch else "",
        ])
    if not rows:
        return _section("Repair chain", '<p class="muted">No repairs were needed.</p>')
    return _section(
        "Repair chain",
        _table(["Attempt", "Class", "Root cause", "Outcome", "Patch"], rows, klass="compact"),
    )


def _variants(payload: dict[str, Any] | None, source: ReportInput | None, spec: ReportSpec) -> str:
    if payload is None:
        return _section("Variant evidence", '<p class="muted">No variant table attached.</p>')
    summary = variant_summary(payload)
    rows = []
    for row in payload.get("variants", [])[: spec.max_rows]:
        key = row.get("key", {})
        rows.append([
            row.get("gene") or "",
            key.get("chrom", ""),
            key.get("pos", ""),
            key.get("ref", ""),
            key.get("alt", ""),
            row.get("rsid") or "",
            row.get("genotype") or "",
            row.get("depth") or "",
            row.get("vaf") or "",
            row.get("filter") or "",
            row.get("consequence") or "unannotated",
            row.get("clinvar_significance") or "not in ClinVar",
            row.get("clinvar_review_status") or "",
            row.get("population_af", row.get("gnomad_af", "")),
            row.get("iranome_af", ""),
        ])
    count = len(payload.get("variants", []))
    cap_note = (
        f'<p class="muted">Showing {min(spec.max_rows, count)} of {count} variants; '
        "the full table is in the attached JSON.</p>"
        if count > spec.max_rows else ""
    )
    source_note = f'<p class="source">Source: {esc(source.path)} (sha256 {esc(source.sha256)})</p>' if source else ""
    buckets = ", ".join(f"{name}={count}" for name, count in summary["clinvar"].items())
    return _section(
        "Variant evidence",
        f"<p><strong>{count}</strong> variants. ClinVar buckets: {esc(buckets)}.</p>"
        + cap_note
        + _table(
            ["Gene", "Chrom", "Pos", "Ref", "Alt", "rsID", "GT", "Depth", "VAF",
             "Filter", "Consequence", "ClinVar", "ClinVar review", "Population AF", "Iranome AF"],
            rows,
            klass="compact",
        )
        + source_note,
    )


def _readiness(payload: dict[str, Any] | None, source: ReportInput | None, spec: ReportSpec) -> str:
    if payload is None:
        return _section("Coverage readiness", '<p class="muted">No readiness table attached.</p>')
    summary = readiness_summary(payload)
    counts = summary["counts"]
    rows = []
    for row in payload.get("targets", [])[: spec.max_rows]:
        target = row.get("target", {})
        rows.append([
            target.get("name", ""),
            target.get("gene", ""),
            row.get("mean_depth", ""),
            f"{(_float(row.get('pct_20x')) or 0.0) * 100:.1f}%",
            row.get("readiness", ""),
            row.get("reason", ""),
        ])
    count = len(payload.get("targets", []))
    cap_note = (
        f'<p class="muted">Showing {min(spec.max_rows, count)} of {count} targets.</p>'
        if count > spec.max_rows else ""
    )
    source_note = f'<p class="source">Source: {esc(source.path)} (sha256 {esc(source.sha256)})</p>' if source else ""
    blocked = ", ".join(summary["blocked"]) if summary["blocked"] else "none"
    return _section(
        "Coverage readiness",
        f"<p>ready={counts['ready']}, caution={counts['caution']}, "
        f"not-interpretable={counts['not-interpretable']}. Not interpretable: {esc(blocked)}.</p>"
        + cap_note
        + _table(
            ["Target", "Gene", "Mean depth", "% ≥20x", "Readiness", "Reason"],
            rows,
            klass="compact",
        )
        + source_note,
    )


def _signature_label(signature: dict[str, Any] | None) -> str:
    if not signature or not signature.get("signed"):
        return "Unsigned (not signed)"
    if signature.get("signature_ok") is True:
        return "Signed; signature verified"
    if signature.get("signature_ok") is False:
        return "Signed; signature verification FAILED"
    return "Signed; verification unavailable"


def _provenance(record: RunRecord, inputs: list[ReportInput], signature: dict[str, Any] | None) -> str:
    rows = [
        ["Pipeline", record.pipeline],
        ["Revision", record.pipeline_revision],
        ["Assay", record.assay or "not recorded"],
        ["Contig version", record.contig_version or "not recorded"],
        ["Nextflow version", record.nextflow_version or "not recorded"],
        ["Signature", _signature_label(signature)],
        ["Input checksums", len(record.input_checksums)],
        ["Output checksums", f"{len(record.output_checksums)} (recorded; use contig verify to re-hash)"],
        ["Container digests", len(record.container_digests)],
    ]
    if record.reference_identity:
        ref = record.reference_identity
        rows.append(["Reference", ref.genome or ref.fasta or ref.mode])
        if ref.fasta_sha256:
            rows.append(["Reference SHA-256", ref.fasta_sha256])
    for annotation in record.annotation_identity:
        rows.append([
            f"Annotation ({annotation.tool})",
            f"{annotation.version or ''} {annotation.db_version or ''}".strip(),
        ])

    inputs_rows = [[item.kind, item.path, item.sha256, item.note or ""] for item in inputs]
    return _section(
        "Provenance",
        _table(["Field", "Value"], rows, klass="compact")
        + '<p class="muted">Input checksums are recorded as counts; output checksums '
        "are not re-hashed here. Use <code>contig verify</code> for output integrity "
        'and the Report inputs table below for the report artifacts. Signing is '
        'optional: use <code>contig keygen</code> and <code>CONTIG_SIGNING_KEY</code>, '
        'then <code>contig verify</code>.</p>'
        + "<h3>Report inputs</h3>"
        + _table(["Kind", "Path", "SHA-256", "Note"], inputs_rows, klass="compact"),
    )


def _notes(spec: ReportSpec) -> str:
    return _section("Notes", f"<p>{esc(spec.notes or 'No additional notes.')}</p>")


def _limitations(spec: ReportSpec) -> str:
    text = spec.limitations or (
        "This is a research-use report. It does not establish a diagnosis, a "
        "clinical classification, or a treatment recommendation. Verify results "
        "against the attached sources and the original run bundle before use."
    )
    return _section("Limitations", f"<p>{esc(text)}</p>")


def _reviewer(spec: ReportSpec) -> str:
    if not spec.reviewer:
        return _section("Research review", '<p class="muted">No reviewer recorded.</p>')
    reviewer = spec.reviewer
    details = [reviewer.name, reviewer.role, reviewer.reviewed_at]
    return _section(
        "Research review",
        f"<p><strong>{esc(' · '.join(part for part in details if part))}</strong></p>"
        f"<p>{esc(reviewer.statement)}</p>",
    )


CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       max-width: 980px; margin: 2rem auto; padding: 0 1rem; color: #1f2937; line-height: 1.5; }
h1 { margin-bottom: 0.2rem; }
h2 { border-bottom: 1px solid #e5e7eb; padding-bottom: 0.25rem; margin-top: 2rem; }
h3 { margin-top: 1.25rem; }
.subtitle { color: #4b5563; margin-top: 0; }
.muted { color: #6b7280; }
.source { color: #6b7280; font-size: 0.85rem; }
.banner { background: #fef3c7; border: 1px solid #f59e0b; padding: 0.75rem 1rem;
          border-radius: 6px; margin: 1rem 0; }
.warnings { background: #fff7ed; border: 1px solid #fb923c; padding: 0.75rem 1rem;
            border-radius: 6px; margin: 1rem 0; }
.warnings ul { margin: 0.5rem 0 0 1.25rem; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.9rem; }
th, td { border: 1px solid #d1d5db; padding: 0.4rem 0.5rem; text-align: left;
         vertical-align: top; }
th { background: #f3f4f6; }
table.compact td, table.compact th { font-size: 0.85rem; }
.badge { display: inline-block; padding: 0.3rem 0.6rem; border-radius: 999px;
         font-weight: 700; font-size: 0.9rem; }
.badge.pass { background: #dcfce7; color: #166534; }
.badge.warn { background: #fef3c7; color: #92400e; }
.badge.fail { background: #fee2e2; color: #991b1b; }
.badge.unverified { background: #e5e7eb; color: #374151; }
code { background: #f3f4f6; padding: 0.1rem 0.25rem; border-radius: 4px; }
footer { margin-top: 3rem; border-top: 1px solid #e5e7eb; padding-top: 1rem;
         color: #6b7280; font-size: 0.85rem; }
"""


def render_html(
    record: RunRecord,
    spec: ReportSpec,
    *,
    variants: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
    inputs: list[ReportInput] | None = None,
    signature: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> str:
    inputs = inputs or []
    variants_input = next((item for item in inputs if item.kind == "variants"), None)
    readiness_input = next((item for item in inputs if item.kind == "readiness"), None)

    renderers = {
        "summary": lambda: _summary(record, spec),
        "verdict": lambda: _verdict(record),
        "methods": lambda: _methods(record),
        "qc": lambda: _qc(record),
        "repairs": lambda: _repairs(record),
        "variants": lambda: _variants(variants, variants_input, spec),
        "readiness": lambda: _readiness(readiness, readiness_input, spec),
        "provenance": lambda: _provenance(record, inputs, signature),
        "notes": lambda: _notes(spec),
        "limitations": lambda: _limitations(spec),
        "reviewer": lambda: _reviewer(spec),
    }

    sections = "".join(renderers[name]() for name in TEMPLATE_SECTIONS[spec.template])
    footer = (
        "<footer>Generated by Contig. Research use only; not a clinical report. "
        f"Run <code>{esc(record.run_id)}</code>.</footer>"
    )
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{esc(spec.title or 'Contig research report')}</title>"
        f"<style>{CSS}</style></head><body>"
        f"{_header(record, spec)}{_banner()}{_compatibility_warnings(warnings)}"
        f"{sections}{footer}"
        "</body></html>"
    )
