"""Deterministic, grounded answers over a run bundle and attached tables."""

from __future__ import annotations

import re
import shlex

from contig.assistant.context import Context
from contig.assistant.models import Answer, Citation
from contig.methods import render_methods
from contig.reporting.summaries import (
    qc_summary,
    readiness_summary,
    variant_summary,
    verdict_label,
)

# More specific intents first.
INTENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("readiness", ("ready", "readiness", "coverage", "interpretable", "depth", "not-interpretable")),
    ("variants", ("variant", "mutation", "clinvar", "gnomad", "iranome", "pathogenic", "gene")),
    ("repairs", ("repair", "heal", "fix", "oom", "error", "failure")),
    ("qc", ("qc", "quality", "check", "metric")),
    ("provenance", ("provenance", "reproduc", "version", "checksum", "signature", "pipeline", "reference")),
    ("methods", ("method", "citation", "cite", "paper")),
    ("report", ("report", "share", "pdf", "hand off")),
    ("verdict", ("verdict", "pass", "warn", "fail", "trust", "result", "summary")),
]


def intent_of(question: str) -> str:
    text = question.strip().lower()
    if text in {"help", "what can you do", "what can you answer", "?"}:
        return "help"
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return intent
    return "unknown"


def _known_genes(context: Context) -> list[str]:
    genes: set[str] = set()
    for row in (context.variants or {}).get("variants", []):
        gene = row.get("gene")
        if gene:
            genes.add(gene)
    for row in (context.readiness or {}).get("targets", []):
        target = row.get("target", {})
        for key in ("gene", "name"):
            gene = target.get(key)
            if gene and re.fullmatch(r"[A-Za-z0-9_.-]+", gene):
                genes.add(gene)
    return sorted(genes, key=len, reverse=True)


def _gene_in_question(context: Context, question: str) -> str | None:
    text = question.lower()
    for gene in _known_genes(context):
        if re.search(rf"\b{re.escape(gene.lower())}\b", text):
            return gene
    return None


def _run_citation(context: Context) -> Citation:
    return context.citations["run_record"]


def _runs_dir_suffix(context: Context) -> str:
    return f" --runs-dir {shlex.quote(context.runs_dir)}" if context.runs_dir != "runs" else ""


def _run_command(context: Context, subcommand: str) -> str:
    return f"contig {subcommand} {context.record.run_id}{_runs_dir_suffix(context)}"


def _action(context: Context, command: str) -> str:
    return f"{command} {context.record.run_id}".strip()


def _verdict(context: Context) -> Answer:
    record = context.record
    summary = qc_summary(record)
    deciding = ", ".join(summary["deciding"]) if summary["deciding"] else "none"
    counts = summary["counts"]
    text = (
        f"Verdict: {verdict_label(record.verdict)}.\n"
        f"Deciding checks: {deciding}.\n"
        f"QC counts: {counts['pass']} pass, {counts['warn']} warn, "
        f"{counts['fail']} fail, {counts['unverified']} unverified."
    )
    return Answer(
        intent="verdict",
        answer=text,
        citations=[_run_citation(context)],
        actions=[
            _run_command(context, "show") + " --explain",
            _run_command(context, "verify"),
        ],
    )


def _qc(context: Context) -> Answer:
    record = context.record
    summary = qc_summary(record)
    counts = summary["counts"]
    lines = [
        f"QC: {len(record.qc_results)} checks "
        f"({counts['pass']} pass, {counts['warn']} warn, "
        f"{counts['fail']} fail, {counts['unverified']} unverified)."
    ]
    for result in record.qc_results[:10]:
        value = f" (value {result.value:g})" if result.value is not None else ""
        lines.append(f"- {result.check}: {result.status} — {result.message}{value}")
    return Answer(
        intent="qc",
        answer="\n".join(lines),
        citations=[_run_citation(context)],
        actions=[_run_command(context, "show") + " --explain"],
    )


def _repairs(context: Context) -> Answer:
    history = context.record.repair_history
    if not history:
        text = "No repairs were recorded for this run."
    else:
        lines = [f"{len(history)} repair attempt(s):"]
        for step in history[:10]:
            patch = step.patch.kind if step.patch else "no patch"
            applied = "applied" if step.patch_applied else "not applied"
            lines.append(
                f"- attempt {step.attempt}: {step.diagnosis.failure_class} — "
                f"{step.diagnosis.root_cause} -> {step.outcome} ({patch}, {applied})"
            )
        text = "\n".join(lines)
    return Answer(
        intent="repairs",
        answer=text,
        citations=[_run_citation(context)],
        actions=[_run_command(context, "show")],
    )


def _provenance(context: Context) -> Answer:
    record = context.record
    signature = context.signature
    if not signature or not signature.get("signed"):
        signature_label = "unsigned"
    elif signature.get("signature_ok") is True:
        signature_label = "signed, signature verified"
    elif signature.get("signature_ok") is False:
        signature_label = "signed, signature verification failed"
    else:
        signature_label = "signed, verification unavailable"
    text = (
        f"Pipeline: {record.pipeline} @ {record.pipeline_revision}.\n"
        f"Contig {record.contig_version or 'unknown'}; "
        f"Nextflow {record.nextflow_version or 'unknown'}.\n"
        f"Input checksums: {len(record.input_checksums)}; "
        f"output checksums: {len(record.output_checksums)}; "
        f"container digests: {len(record.container_digests)}.\n"
        f"Signature: {signature_label}."
    )
    return Answer(
        intent="provenance",
        answer=text,
        citations=[_run_citation(context)],
        actions=[_run_command(context, "methods"), _run_command(context, "verify")],
    )


def _methods(context: Context) -> Answer:
    return Answer(
        intent="methods",
        answer=render_methods(context.record),
        citations=[_run_citation(context)],
        actions=[_run_command(context, "methods")],
    )


def _variants(context: Context, question: str) -> Answer:
    if context.variants is None:
        return Answer(
            intent="variants",
            answer=(
                "No variant table is attached. Run `contig variants ... --json` and "
                "pass it with `--variants`."
            ),
            citations=[_run_citation(context)],
            actions=["contig variants <vcf> --json --out variants.json"],
        )

    summary = variant_summary(context.variants)
    gene = _gene_in_question(context, question)
    lines = []
    if gene:
        rows = [
            row for row in context.variants.get("variants", [])
            if (row.get("gene") or "").upper() == gene.upper()
        ]
        lines.append(f"{gene}: {len(rows)} variant(s) in the attached table.")
        for row in rows[:10]:
            key = row.get("key", {})
            lines.append(
                f"- {key.get('chrom')}:{key.get('pos')} {key.get('ref')}>{key.get('alt')}: "
                f"{row.get('consequence') or 'unannotated'}; "
                f"ClinVar {row.get('clinvar_significance') or 'not in ClinVar'}"
            )
    else:
        buckets = ", ".join(f"{name}={count}" for name, count in summary["clinvar"].items())
        top = ", ".join(f"{gene}={count}" for gene, count in summary["top_genes"][:5])
        lines.append(f"{summary['total']} variants in the attached table.")
        lines.append(f"ClinVar buckets: {buckets}.")
        if top:
            lines.append(f"Top genes: {top}.")

    return Answer(
        intent="variants",
        answer="\n".join(lines),
        citations=[context.citations["variants"]],
        actions=["contig variants <vcf> --json --out variants.json"],
    )


def _readiness(context: Context, question: str) -> Answer:
    if context.readiness is None:
        return Answer(
            intent="readiness",
            answer=(
                "No readiness table is attached. Run `contig readiness ... --json` "
                "and pass it with `--readiness`."
            ),
            citations=[_run_citation(context)],
            actions=["contig readiness --depth <tsv> --bed <panel.bed> --json --out readiness.json"],
        )

    summary = readiness_summary(context.readiness)
    gene = _gene_in_question(context, question)
    if gene:
        matches = [
            row for row in context.readiness.get("targets", [])
            if (row.get("target", {}).get("gene") or row.get("target", {}).get("name") or "").upper() == gene.upper()
        ]
        if matches:
            lines = [f"{gene}: {len(matches)} target(s)."]
            for row in matches[:10]:
                lines.append(
                    f"- {row.get('target', {}).get('name')}: {row.get('readiness')} — "
                    f"{row.get('reason')}"
                )
        else:
            lines = [f"{gene} is not in the attached readiness table."]
    else:
        counts = summary["counts"]
        blocked = ", ".join(summary["blocked"]) if summary["blocked"] else "none"
        lines = [
            f"Readiness: {summary['total']} target(s): "
            f"{counts['ready']} ready, {counts['caution']} caution, "
            f"{counts['not-interpretable']} not-interpretable.",
            f"Not interpretable: {blocked}.",
        ]

    return Answer(
        intent="readiness",
        answer="\n".join(lines),
        citations=[context.citations["readiness"]],
        actions=["contig readiness --depth <tsv> --bed <panel.bed> --json --out readiness.json"],
    )


def _report(context: Context) -> Answer:
    return Answer(
        intent="report",
        answer=(
            "Build a self-contained research report with `contig report "
            f"{context.record.run_id}`. Attach the M1/M2 JSON with --variants and "
            "--readiness; use `contig report-check` to detect stale inputs."
        ),
        citations=[_run_citation(context)],
        actions=[_run_command(context, "report"), "contig report-check <sidecar.json>"],
    )


def _help(context: Context) -> Answer:
    return Answer(
        intent="help",
        answer=(
            "I can answer from this run bundle about: verdict, QC checks, repairs, "
            "provenance/reproducibility, methods, attached variant evidence, "
            "attached coverage readiness, and report next steps. I will refuse "
            "questions that are not in the bundle or attached tables."
        ),
        citations=[_run_citation(context)],
        actions=[
            _run_command(context, "show") + " --explain",
            _run_command(context, "report"),
        ],
    )


def _unknown(context: Context) -> Answer:
    return Answer(
        intent="unknown",
        answer=(
            "I can answer about the verdict, QC, repairs, provenance, methods, "
            "attached variant evidence, attached readiness, and reports. "
            "I won't guess beyond the bundle."
        ),
        citations=[],
        confidence="none",
        actions=[f"contig ask {context.record.run_id} \"help\"{_runs_dir_suffix(context)}"],
    )


def answer_question(context: Context, question: str) -> Answer:
    intent = intent_of(question)
    if intent == "verdict":
        return _verdict(context)
    if intent == "qc":
        return _qc(context)
    if intent == "repairs":
        return _repairs(context)
    if intent == "provenance":
        return _provenance(context)
    if intent == "methods":
        return _methods(context)
    if intent == "variants":
        return _variants(context, question)
    if intent == "readiness":
        return _readiness(context, question)
    if intent == "report":
        return _report(context)
    if intent == "help":
        return _help(context)
    if intent == "unknown":
        gene = _gene_in_question(context, question)
        if gene:
            if context.variants is not None:
                return _variants(context, question)
            if context.readiness is not None:
                return _readiness(context, question)
    return _unknown(context)
