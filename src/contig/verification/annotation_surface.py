"""Human-legible surface for M4's VEP-vs-SnpEff annotation concordance (C7 M5).

`annotation_concordance.py` COMPUTES the two cross-tool concordance metrics and
stores them as `kind="concordance"` `QCResult`s on the record. This module does
NOT recompute anything: it READS those already-computed results and turns them
into one plain-language "Corroborated by ..." line for the verdict surfaces
(text/HTML report, `contig methods`).

Hard constraints (PRD M-1/M-11, D2/D3, S-1):
- Pure function: no file I/O, no call into the compute path, no recompute.
- Render ONLY when `consequence_concordance.value is not None` (D2); a single
  annotator / absent annotation / below-floor UNVERIFIED all collapse to `None`,
  so a fabricated agreement number is never shown.
- The gene-symbol clause is marked "informational" (S-1) so a low symbol
  fraction never reads as a failure.
"""

from __future__ import annotations

import re

from contig.models import QCResult, RunRecord

# The concordance messages both open with "{a}/{b} ..." counts; the FIRST
# "int/int" token in each is the matches/total pair (see
# annotation_concordance.evaluate_consequence_concordance /
# evaluate_gene_symbol_concordance). Regex over that confirmed substring rather
# than recomputing.
_FRACTION_RE = re.compile(r"(\d+)/(\d+)")

# The messages open with "{label_a} vs {label_b}: ..." on the computable branch;
# used only as a fallback for annotator names when annotation_identity is empty.
_LABELS_RE = re.compile(r"^(\S+) vs (\S+):")


def _find(record: RunRecord, check: str) -> QCResult | None:
    for result in record.qc_results:
        if result.kind == "concordance" and result.check == check:
            return result
    return None


def _matches_total(message: str) -> tuple[str, str] | None:
    match = _FRACTION_RE.search(message)
    if match is None:
        return None
    return match.group(1), match.group(2)


def _annotator_names(record: RunRecord, consequence: QCResult) -> str:
    """"VEP and SnpEff" from the identity list; fall back to the message labels."""
    tools = [p.tool for p in record.annotation_identity if p.tool]
    if tools:
        return " and ".join(tools)
    labels = _LABELS_RE.match(consequence.message)
    if labels is not None:
        return f"{labels.group(1)} and {labels.group(2)}"
    return "the two annotators"


def corroborated_by_line(record: RunRecord) -> str | None:
    """Render M4's concordance results as a "Corroborated by ..." line, or None.

    Reads `consequence_concordance` (WARN-capable) and, when present,
    `gene_symbol_concordance` (informational-only) from `record.qc_results`.
    Returns `None` when the consequence check is missing or its `value is None`
    (D2) -- never recomputes, never fabricates a fraction.
    """
    consequence = _find(record, "consequence_concordance")
    if consequence is None or consequence.value is None:
        return None

    cons_counts = _matches_total(consequence.message)
    if cons_counts is None:  # defensive: computable branch always carries counts
        return None
    cons_matches, cons_total = cons_counts

    names = _annotator_names(record, consequence)
    line = (
        f"Corroborated by {names}: {cons_matches}/{cons_total} consequences "
        f"agree ({consequence.value:.2f})"
    )

    gene_symbol = _find(record, "gene_symbol_concordance")
    if gene_symbol is not None and gene_symbol.value is not None:
        gs_counts = _matches_total(gene_symbol.message)
        if gs_counts is not None:
            gs_matches, gs_total = gs_counts
            line += (
                f"; gene symbols {gs_matches}/{gs_total} "
                f"({gene_symbol.value:.2f}, informational)"
            )

    return line + "."
